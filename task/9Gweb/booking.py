from importlib import import_module

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.task.request_booking_task_data_model import RequestBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util
from common.utils.flight_util import FlightUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.sunphuquocairways_9g.service.web_service import WebService

_web_date = import_module("task.9Gweb.search")._web_date

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("sunPhuQuocAirwaysWebBooking")


def _target_journey(journeys, flight_number: str):
    matches = [
        journey
        for journey in journeys
        if ",".join(segment.flight_number for segment in journey.segments) == flight_number
    ]
    if len(matches) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, flight_number)
    return matches[0]


def _copy_paid_tickets(source_passengers, paid_passengers) -> None:
    tickets = {
        (passenger.last_name.upper(), passenger.first_name.upper()): passenger.ticket_number
        for passenger in paid_passengers or []
        if passenger.ticket_number
    }
    for passenger in source_passengers:
        ticket = tickets.get((passenger.last_name.upper(), passenger.first_name.upper()))
        if ticket:
            passenger.ticket_number = ticket


def _run_booking(
    service: WebService,
    booking_data: RequestBookingTaskDataModel,
    response: ResponseOrderInfoModel,
) -> ResponseOrderInfoModel:
    adult_count, child_count = booking_data.get_passenger_number()
    passenger_count = adult_count + child_count
    if passenger_count <= 0:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengers")
    journeys = service.search(
        dep_airport=booking_data.dep_airport,
        arr_airport=booking_data.arr_airport,
        dep_date=_web_date(booking_data.dep_time[:8]),
        ret_date=None,
        adt_number=adult_count,
        chd_number=child_count,
        currency_code=booking_data.ticket_config.currency_code,
        promo_code=booking_data.promo_code or "",
    )
    journey = _target_journey(journeys, booking_data.flight_number)
    FlightUtil.time_verify(journey, [booking_data.dep_time, booking_data.arr_time])
    bundle = FlightUtil.product_tag_verify(journey, booking_data.product_tag)
    if bundle.seat < passenger_count:
        raise ServiceError(
            ServiceStateEnum.BUSINESS_ERROR,
            f"余座不足，当前余座[{bundle.seat}]，目标人数[{passenger_count}]",
        )
    if not booking_data.ticket_config.isForceIssue:
        threshold = booking_data.ticket_config.priceThreshold
        if threshold is None:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "priceThreshold")
        FlightUtil.ticket_price_check(bundle, booking_data.passengers, threshold)

    booking = service.create_order(bundle, booking_data.passengers, booking_data.contact_info)
    journey.bundles = [bundle]
    response.order_number = booking.pnr
    response.pnr = booking.pnr
    response.order_state = OrderStateEnum.HOLD
    response.passengers = booking.passengers
    response.journeys = [journey]
    response.contact_info = booking.contact_info
    response.total_amount = booking.total_amount
    response.currency_code = booking.currency

    service.add_requested_baggage(booking.pnr, booking.passengers, booking.passengers[0].last_name)

    if str(booking_data.payment_info.type or "").upper() == "NO_PAY":
        return response

    paid = service.pay_order(
        booking.pnr,
        booking.passengers,
        booking.contact_info,
        booking_data.payment_info,
    )
    _copy_paid_tickets(response.passengers, paid.passengers)
    response.order_state = paid.order_state
    return response


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(
    self,
    booking_data: RequestBookingTaskDataModel,
    response_order_data: ResponseOrderInfoModel,
):
    service = WebService(proxy_info_from_ext(booking_data.ext))
    service.initialize_session()
    return _run_booking(service, booking_data, response_order_data)


if __name__ == "__main__":
    print(main({
        "taskId": "9gweb-local-booking",
        "taskType": "booking",
        "source": "9GWEB",
        "taskData": {
            "depAirport": "SGN",
            "arrAirport": "PQC",
            "depTime": "202608010800",
            "arrTime": "202608010900",
            "flightNumber": "9G0123",
            "productTag": "ECONOMY LITE",
            "promoCode": "",
            "freightRateType": "PT",
            "ticketConfig": {
                "currencyCode": "VND",
                "isForceIssue": False,
                "priceThreshold": "1500000",
            },
            "passengers": [{
                "type": "ADT",
                "lastName": "LOVELACE",
                "firstName": "ADA",
                "gender": "F",
                "birthday": "1990-01-01",
                "documentInfo": None,
                "ssr": {"baggage": []},
            }],
            "contactInfo": {
                "lastName": "LOVELACE",
                "firstName": "ADA",
                "emailAddress": "ada@example.com",
                "phoneCode": "+84",
                "phoneNumber": "901234567",
            },
            "paymentInfo": {
                "type": "NO_PAY",
                "cardNumber": "NO_PAY",
                "cardExpiryDate": "01/30",
                "cardHolderName": "NO PAY",
                "cardType": "VI",
                "cardCVV": "000",
            },
            "ext": {
                "proxy": {
                    "host": "proxy.example.com",
                    "port": 8080,
                    "username": "YOUR_USERNAME",
                    "password": "YOUR_PASSWORD",
                    "region": "vn",
                    "sessId": None,
                    "sessionTime": 10,
                    "format": "http://{username}:{password}@{host}:{port}",
                }
            },
        },
    }))
