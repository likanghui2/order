import time

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.task_type_enum import TaskTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.task.request_booking_task_data_model import RequestBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.date_util import DateUtil
from common.utils.flight_util import FlightUtil
from flights.cebupacificair_5j.flight_common.booking_utils import CebupacificairBookingUtils
from flights.cebupacificair_5j.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil('cebupacificairBooking')
CACHE = machine_cache_util.MachineCache()


def _payment_required_value(data: dict, *keys: str):
    for key in keys:
        if key in data:
            value = data.get(key)
            if value is not None and value != '':
                return value
    raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'paymentcomplete')


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self,
         booking_data: RequestBookingTaskDataModel,
         response_order_data: ResponseOrderInfoModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        LOG.info("重新初始化对象")
        service = WebService(GlobalVariable.PROXY_INFO_DATA)
        service.initialize_session()
        service.initialize_html_session()
    else:
        LOG.info("使用缓存对象")
        service = script_cache['value']
    purchasing = CebupacificairBookingUtils.check_document_data(
        dep_airport=booking_data.dep_airport,
        arr_airport=booking_data.arr_airport,
        passenger_list=booking_data.passengers,
    )
    adult_count, child_count = booking_data.get_passenger_number()

    dep_date = DateUtil.string_to_date_auto(booking_data.dep_time)
    if dep_date is None:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'depTime')

    journey_list = service.availability(
        airport_data=[(
            booking_data.dep_airport,
            booking_data.arr_airport,
            dep_date.strftime('%Y-%m-%d'),
        )],
        adult_count=adult_count,
        child_count=child_count,
        promo_code=booking_data.promo_code or '',
        currency=booking_data.ticket_config.currency_code,
    )

    if script_cache is None:
        CACHE.set_data(service, 300)
    else:
        CACHE.set_data(script_cache['value'], None, script_cache['timeOut'])
    journey_list = FlightUtil.number_filter(journey_list, booking_data.flight_number)
    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, booking_data.flight_number)

    journey = journey_list[0]
    FlightUtil.time_verify(journey, [booking_data.dep_time, booking_data.arr_time])
    use_bundle = FlightUtil.product_tag_verify(journey, booking_data.product_tag)
    print(use_bundle.cabin, use_bundle.seat)
    if use_bundle.seat < adult_count + child_count:
        raise ServiceError(
            ServiceStateEnum.BUSINESS_ERROR,
            f'余座不足，当前余座[{use_bundle.seat}]，目标人数[{adult_count + child_count}]',
        )
    if not booking_data.ticket_config.isForceIssue:
        FlightUtil.ticket_price_check(
            use_bundle,
            booking_data.passengers,
            booking_data.ticket_config.priceThreshold,
        )
    if use_bundle.cabin not in ['H']:
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '非指定舱')
    service.trip(
        dep_airport=booking_data.dep_airport,
        journey=journey,
        bundle=use_bundle,
        adult_count=adult_count,
        child_count=child_count,
        passengers=booking_data.passengers,
    )
    source_data = service.add_passenger(
        passengers=booking_data.passengers,
        contact_info=booking_data.contact_info,
        purchasing=purchasing,
    )
    service.commit(passengers=booking_data.passengers, source_data=source_data)

    journey.bundles = [use_bundle]
    response_order_data.order_state = OrderStateEnum.UNKNOWN
    response_order_data.passengers = booking_data.passengers
    response_order_data.contact_info = booking_data.contact_info
    response_order_data.journeys = [journey]
    response_order_data.currency_code = use_bundle.price_info.currency
    price_info = use_bundle.price_info
    response_order_data.total_amount = (
        (price_info.adult_ticket_price + price_info.adult_tax_price) * adult_count
        + (price_info.child_ticket_price + price_info.child_tax_price) * child_count
    )

    payment_dict = service.init_payment()
    if not payment_dict:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'init_payment')
    LOG.info(
        f"init_payment支付字段数: {len(payment_dict)}，"
        f"amount[{payment_dict.get('amount')}]，currency-code[{payment_dict.get('currency-code')}]"
    )

    payment_initialize_data = service.payment_initialize(payment_dict)
    transaction_id = (payment_initialize_data.get('transaction') or {}).get('id')
    if not transaction_id:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'transaction.id')
    LOG.info(f"payment_initialize成功，transaction_id[{transaction_id}]")

    time.sleep(2)
    payment_jwt, bin_value = service.payment_authorize(
        payment_dict=payment_dict,
        transaction=transaction_id,
        contact_info=booking_data.contact_info,
        payment_info=booking_data.payment_info,
    )
    time.sleep(2)
    service.payment_auth(payment_jwt, bin_value)
    time.sleep(2)
    payment_authorize = service.payment_authorize(
        payment_dict=payment_dict,
        transaction=transaction_id,
        contact_info=booking_data.contact_info,
        payment_info=booking_data.payment_info,
        expired=True,
    )
    LOG.info(f"payment_authorize二次响应: {payment_authorize}")
    if not isinstance(payment_authorize, dict) or payment_authorize.get('message') != 'Payment authorized':
        raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)

    payment_complete_data = service.payment_complete(
        transaction_id=transaction_id,
        token=payment_dict['timetoken'],
    )
    session_id = _payment_required_value(payment_complete_data, 'session_id', 'sessionId')
    status_code = _payment_required_value(payment_complete_data, 'status_code', 'statusCode')
    LOG.info(f"payment_complete成功，session_id存在[{bool(session_id)}]，status_code[{status_code}]")

    service.session_complete(
        transaction_id=transaction_id,
        token=payment_dict['timetoken'],
        session_id=session_id,
        status_code=status_code,
    )
    service.itinerary(response_order_data=response_order_data, payment_info=booking_data.payment_info)
    return response_order_data


if __name__ == '__main__':
    while True:
        A = main({
            "taskId": "123",
            "taskType": 'booking',
            "source": "5JWEB",
            "taskData": {
                "depAirport": "CEB",
                "arrAirport": "HKG",
                "depTime": "202605171745",
                "arrTime": "202605172050",
                "flightNumber": "5J236",
                "productTag": "GO Easy",
                "freightRateType": "PT",
                "ticketConfig": {
                    "currencyCode": "PHP",
                    "isForceIssue": True,
                    "orderTotalPrice": "1000",
                    "priceThreshold": "1000"
                },
                "passengers": [
                    {
                        "type": 'ADT',
                        "lastName": "XU",
                        "firstName": "ZILIANG",
                        "gender": "M",
                        "birthday": "1996-10-29",
                        "documentInfo": None,
                        "ssr": {}
                    }
                ],
                "contactInfo": {
                    "lastName": "XU",
                    "firstName": "ZILIANG",
                    "emailAddress": "443007670991sogny@erdake.com",
                    "phoneCode": "1",
                    "phoneNumber": "16680451241"
                },
                "paymentInfo": {
                    "type": "VCC",
                    "cardNumber": "5395029627462246",
                    "cardExpiryDate": "07/26",
                    "cardHolderName": "XU ZILIANG",
                    "cardType": "MC",
                    "cardCVV": "618"
                }
            }
        })
        if len(A) > 300:
            break
        time.sleep(1)
