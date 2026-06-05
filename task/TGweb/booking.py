import time

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.task.request_booking_task_data_model import RequestBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util
from common.utils.date_util import DateUtil
from common.utils.flight_util import FlightUtil
from flights.thaiairways_tg.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil('TGBooking')


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self,
         booking_data: RequestBookingTaskDataModel,
         response_order_data: ResponseOrderInfoModel):
    service = WebService(GlobalVariable.PROXY_INFO_DATA)
    service.initialize_session()

    adult_count, child_count = booking_data.get_passenger_number()
    journey_list = service.search(
        dep_airport=booking_data.dep_airport,
        arr_airport=booking_data.arr_airport,
        dep_date=DateUtil.string_to_date_auto(booking_data.dep_time).strftime('%Y-%m-%d'),
        adt_number=adult_count,
        chd_number=child_count,
        currency_code=booking_data.ticket_config.currency_code,
        cabin_level='Y',
        promo_code=booking_data.promo_code or '',
    )
    journey_list = FlightUtil.number_filter(journey_list, booking_data.flight_number)
    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, booking_data.flight_number)

    journey = journey_list[0]
    FlightUtil.time_verify(journey, [booking_data.dep_time, booking_data.arr_time])
    use_bundle = FlightUtil.product_tag_verify(journey, booking_data.product_tag)
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

    service.booking(
        journey=journey,
        bundle=use_bundle,
        passengers=booking_data.passengers,
        contact_info=booking_data.contact_info,
        response_order_data=response_order_data,
    )

    if booking_data.payment_info.type == 'NO_PAY':
        response_order_data.order_state = OrderStateEnum.HOLD
        return response_order_data

    payment_data = service.prepare_payment_www(
        order_id=response_order_data.pnr,
        last_name=booking_data.passengers[0].last_name,
    )
    LOG.info(
        {
            "pnr": response_order_data.pnr,
            "paymentStatus": payment_data.get("paymentStatus"),
            "paymentOrderNumber": payment_data.get("orderNumber"),
            "redirectionUrl": payment_data.get("redirectionUrl"),
            "paymentExpiryDateTime": payment_data.get("paymentExpiryDateTime"),
        },
        "TG支付初始化",
    )
    service.payment_www(
        payment_info=booking_data.payment_info,
        contact_info=booking_data.contact_info,
        payment_data=payment_data,
        response_order_data=response_order_data,
    )
    return response_order_data


if __name__ == '__main__':
    while True:
        A = main({
            "taskId": "test_tg_booking_001",
            "taskType": 'booking',
            "source": "TGWEB",
            "taskData": {
                "depAirport": "PEK",
                "arrAirport": "BKK",
                "depTime": "202605291705",
                "arrTime": "202605292115",
                "flightNumber": "TG615",
                "productTag": "HOT DEAL",
                "freightRateType": "PT",
                "promoCode": "",
                "ticketConfig": {
                    "currencyCode": "CNY",
                    "isForceIssue": True,
                    "orderTotalPrice": "1000",
                    "priceThreshold": "1000"
                },
                "passengers": [
                    {
                        "type": 'ADT',
                        "lastName": "WANG",
                        "firstName": "QIANG",
                        "gender": "M",
                        "birthday": "1981-12-24",
                        "documentInfo": None,
                        "ssr": {}
                    }
                ],
                "contactInfo": {
                    "lastName": "WANG",
                    "firstName": "QIANG",
                    "emailAddress": "y57vw1z5@erdake.com",
                    "phoneCode": "1",
                    "phoneNumber": "16680451241"
                },
                "paymentInfo": {
                    "type": "CA",
                    "cardNumber": "5395029677342678",
                    "cardExpiryDate": "07/26",
                    "cardHolderName": "WANG QIANG",
                    "cardType": "MC",
                    "cardCVV": "165"
                }
            }
        })
        if len(A) > 300:
            break
        time.sleep(1)
