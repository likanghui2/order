from datetime import datetime

from common.decorators.task_decorator import task_decorator
from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.task.request_booking_task_data_model import RequestBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util
from common.utils.flight_util import FlightUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.vietjet.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil('hkexpressBooking')


def _booking(self,
             booking_data: RequestBookingTaskDataModel,
             response_order_data: ResponseOrderInfoModel):
    service = WebService(proxy_info_from_ext(booking_data.ext))

    journey_list = service.search(
        dep_airport=booking_data.dep_airport,
        arr_airport=booking_data.arr_airport,
        dep_date=datetime.strptime(booking_data.dep_time, "%Y%m%d%H%M%S").strftime('%Y-%m-%d'),
        adt_number=sum([1 for x in booking_data.passengers if x.type == PassengerTypeEnum.ADT]),
        chd_number=sum([1 for x in booking_data.passengers if x.type == PassengerTypeEnum.CHD]),
        infant_count=0,
        currency_code=booking_data.ticket_config.currency_code,
    )

    journey_list = FlightUtil.number_filter(journey_list, booking_data.flight_number)

    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, booking_data.flight_number)

    journey = journey_list[0]

    FlightUtil.time_verify(journey, [booking_data.dep_time, booking_data.arr_time])
    use_bundle = FlightUtil.product_tag_verify(journey, booking_data.product_tag)
    print(use_bundle.cabin, use_bundle.seat)
    later_response, add_signature = service.booking(
        journey=journey,
        passenger_infos=booking_data.passengers,
        use_bundle=use_bundle, response_order_data=response_order_data, contact_info=booking_data.contact_info,
        need_pay=False
    )
    pnr = later_response['reservation'].get('locator')

    # try:
    #     # 进入支付流程
    #     if pnr:
    #         response_order_data.pnr = pnr
    #         pay_url = later_response['reservation']['paymentUrl']
    #         # 进入支付流程
    #         service.pay(pay_url)
    #     else:
    #         # 新版支付流程
    #         pnr, currency = service.pay_checkout(later_response, booking_data.vcc_info)
    #         response_order_data.pnr = pnr
    #         response_order_data.currency = currency
    #
    # except ServiceError as e:
    #     raise e
    # except Exception as e:
    #     raise ServiceError(ServiceStateEnum.PAYMENT_EXCEPTION, e)
    response_order_data.pnr = pnr
    response_order_data.order_state = OrderStateEnum.OPEN_FOR_USE

    return response_order_data


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self,
         booking_data: RequestBookingTaskDataModel,
         response_order_data: ResponseOrderInfoModel):
    return _booking(self, booking_data, response_order_data)


@CELERY_APP.task(bind=True, name="task.VZweb.booking.main")
@task_decorator(LOG)
def vz_main(self,
            booking_data: RequestBookingTaskDataModel,
            response_order_data: ResponseOrderInfoModel):
    return _booking(self, booking_data, response_order_data)


if __name__ == '__main__':
    data = {
        "taskId": "rab25091510083247554716_2f01b51635a54c23b3bfffdb8e63c1b4",
        "taskType": "booking",
        "source": "ODweb",
        "taskData": {
            "depAirport": "SYD",
            "arrAirport": "SGN",
            "depTime": "202601171115",
            "arrTime": "202510150210",
            "flightNumber": "VJ086",
            "productTag": "Eco",
            "ticketConfig": {
                "currencyCode": "USD",
                "isForceIssue": False,
                "orderTotalPrice": "354.48",
                "priceThreshold": "11360.37"
            },
            "passengers": [
                {
                    "birthday": "1979-08-27",
                    "documentInfo": {
                        "expireDate": "2031-03-17",
                        "issuingCountry": "CN",
                        "nationality": "CN",
                        "number": "EJ4026937",
                        "type": 2
                    },
                    "firstName": "TENG",
                    "gender": "M",
                    "lastName": "HE",
                    "ssr": {
                        "baggage": []
                    },
                    "type": "ADT"
                },
                {
                    "birthday": "1979-08-27",
                    "documentInfo": {
                        "expireDate": "2031-03-17",
                        "issuingCountry": "CN",
                        "nationality": "CN",
                        "number": "EJ4022347",
                        "type": 2
                    },
                    "firstName": "EWEWRWE",
                    "gender": "M",
                    "lastName": "HE",
                    "ssr": {
                        "baggage": []
                    },
                    "type": "ADT"
                },
                {
                    "birthday": "1979-08-27",
                    "documentInfo": {
                        "expireDate": "2031-03-17",
                        "issuingCountry": "CN",
                        "nationality": "CN",
                        "number": "EJ402343447",
                        "type": 2
                    },
                    "firstName": "EWEDSFSDE",
                    "gender": "M",
                    "lastName": "HE",
                    "ssr": {
                        "baggage": []
                    },
                    "type": "ADT"
                },
                {
                    "birthday": "1979-08-27",
                    "documentInfo": {
                        "expireDate": "2031-03-17",
                        "issuingCountry": "CN",
                        "nationality": "CN",
                        "number": "EJ4023232447",
                        "type": 2
                    },
                    "firstName": "EWEDSFSDE",
                    "gender": "M",
                    "lastName": "HE",
                    "ssr": {
                        "baggage": []
                    },
                    "type": "ADT"
                }
            ],
            "contactInfo": {
                "emailAddress": "PSXGbW@hbxyya.com",
                "firstName": "TENG",
                "lastName": "HE",
                "phoneCode": "60",
                "phoneNumber": "34676901"
            },
            "paymentInfo": {
                "cardCVV": "891",
                "cardExpiryDate": "12/25",
                "cardHolderName": "CHEN/QIUYA",
                "cardNumber": "5395026440627278",
                "cardType": "MC",
                "type": "VCC"
            },
            "freightRateType": "PT",
            "callbackData": {
                "callData": None,
                "callUrl": "http://trip-api.bjrakd.com/triplex-order111ng/order/ticketing/remote/taskBack"
            },
            "configData": None
        }
    }

    t = data
    # t = {
    #     "taskId": "SSSS11111",
    #     "source": "UOapp",
    #     "taskType": "booking",
    #     "taskData": data
    # }
    while True:
        try:
            main(t)
        except Exception as e:
            print(e)
            print("error")
