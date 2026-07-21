import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util
from common.utils.sham_booking_util import ShamBookingUtil
from flights.myanmarairways.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("myanmarAirwaysWebShamBooking")


def _price_range(value: Optional[str]) -> tuple[Decimal, Decimal]:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[-~至]\s*(\d+(?:\.\d+)?)\s*", value or "")
    if not match:
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "8M 价格区间格式应为最低价-最高价")
    try:
        minimum, maximum = (Decimal(item) for item in match.groups())
    except InvalidOperation:
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "8M 价格区间无效")
    if minimum > maximum:
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "8M 价格区间最低价不能高于最高价")
    return minimum, maximum


def _select(journeys: list[FlightJourneyModel], flight_number: str,
            price_interval: Optional[str]) -> tuple[FlightJourneyModel, FlightBundleModel]:
    normalized = flight_number.replace("-", "").replace(" ", "").upper()
    matches = [j for j in journeys if j.segments and j.segments[0].flight_number.upper() == normalized]
    if len(matches) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, flight_number)
    journey = matches[0]
    minimum, maximum = _price_range(price_interval)
    bundles = [
        bundle for bundle in journey.bundles or []
        if minimum <= bundle.price_info.adult_ticket_price <= maximum
    ]
    if not bundles:
        current_prices = ",".join(str(bundle.price_info.adult_ticket_price) for bundle in journey.bundles or [])
        raise ServiceError(
            ServiceStateEnum.NO_AVAILABLE_CABIN,
            f"8M 价格区间[{minimum}-{maximum}]",f"当前价格[{current_prices}]",
        )
    return journey, min(bundles, key=lambda bundle: bundle.price_info.adult_ticket_price)


def _run(service: WebService, request: RequestShamBookingTaskDataModel,
         response: ResponseOrderInfoModel) -> ResponseOrderInfoModel:
    ext = request.ext or {}
    seat_count = int(ext.get("passengerCount", 1))
    if seat_count < 1:
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "压位人数必须大于 0")
    journeys = service.search(
        request.dep_airport, request.arr_airport, request.dep_date, seat_count, 0,
        request.booking_config.currency_code, "BUSINESS" if request.cabin == "C" else "ECONOMY",
    )
    journey, bundle = _select(journeys, request.flight_number, request.priceInterval)
    passengers = ShamBookingUtil.build_sham_passenger_info(seat_count, True)
    for passenger in passengers:
        passenger.document_info.expire_date = "2035-12-31"
    contact_info = ShamBookingUtil.build_sham_contact_info()
    contact_info.last_name = passengers[0].last_name
    contact_info.first_name = passengers[0].first_name
    booking_id = service.hold(journey, bundle, passengers, contact_info)
    journey.bundles = [bundle]
    response.order_number = booking_id
    response.pnr = booking_id[:6]
    response.order_state = OrderStateEnum.HOLD
    response.journeys = [journey]
    response.passengers = passengers
    response.contact_info = contact_info
    response.currency_code = bundle.price_info.currency
    response.total_amount = bundle.price_info.adult_ticket_price * seat_count
    return response


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, sham_booking_data: RequestShamBookingTaskDataModel,
         response_order_data: ResponseOrderInfoModel):
    service = WebService(None)
    service.initialize_session()
    return _run(service, sham_booking_data, response_order_data)


if __name__ == "__main__":
    print(main({
        "taskId": "8mweb-local-sham-booking",
        "taskType": "shamBooking",
        "source": "8MWEB",
        "taskData": {
            "depAirport": "RGN",
            "arrAirport": "CAN",
            "depDate": "20260811",
            "flightNumber": "8M713",
            "cabin": "",
            "priceInterval": "1-250",
            "bookingConfig": {
                "bookRate": 10,
                "currencyCode": "USD",
            },
            "ext": {
                "passengerCount": 9,
                "proxy": {
                    "source": "8MWEB",
                    "host": "proxy.iproyal.net",
                    "port": 9000,
                    "username": "rakdvjweb01",
                    "password": "rakdvjvj01",
                    "region": "sg",
                    "sessId": None,
                    "sessionTime": 10,
                    "format": (
                        "http://client-{username}_area-{region}_session-{sessId}_life-"
                        "{sessionTime}:{password}@{host}:{port}"
                    ),
                },
            },
        },
    }))
