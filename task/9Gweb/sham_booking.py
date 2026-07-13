from importlib import import_module
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
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.sham_booking_util import ShamBookingUtil
from flights.sunphuquocairways_9g.service.web_service import WebService

_web_date = import_module("task.9Gweb.search")._web_date

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("sunPhuQuocAirwaysWebShamBooking")
MAX_SEAT_COUNT = 5


def _select_bundle(
    journey: FlightJourneyModel,
    cabin: Optional[str],
    product_tag: Optional[str] = None,
) -> FlightBundleModel:
    bundles = list(journey.bundles or [])
    if cabin:
        bundles = [bundle for bundle in bundles if bundle.cabin == cabin]
        if not bundles:
            current_cabins = "|".join(bundle.cabin or "" for bundle in journey.bundles or [])
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, cabin, current_cabins)
    if product_tag:
        bundles = [bundle for bundle in bundles if bundle.product_tag == product_tag]
    if not bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    return bundles[0]


def _search_target_journey(
    service: WebService,
    request: RequestShamBookingTaskDataModel,
    seat_count: int,
) -> FlightJourneyModel:
    journeys = service.search(
        dep_airport=request.dep_airport,
        arr_airport=request.arr_airport,
        dep_date=_web_date(request.dep_date),
        ret_date=None,
        adt_number=seat_count,
        chd_number=0,
        currency_code=request.booking_config.currency_code,
        promo_code="",
    )
    matches = [
        journey
        for journey in journeys
        if ",".join(segment.flight_number for segment in journey.segments) == request.flight_number
    ]
    if len(matches) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, request.flight_number)
    return matches[0]


def _run_sham_booking(
    service: WebService,
    request: RequestShamBookingTaskDataModel,
    response: ResponseOrderInfoModel,
) -> ResponseOrderInfoModel:
    product_tag = (request.ext or {}).get("productTag")
    first_journey = _search_target_journey(service, request, 1)
    first_bundle = _select_bundle(first_journey, request.cabin, product_tag)
    if first_bundle.seat <= 0:
        raise ServiceError(
            ServiceStateEnum.NO_AVAILABLE_CABIN,
            request.cabin or "",
            first_bundle.cabin or "",
        )

    seat_count = min(first_bundle.seat, MAX_SEAT_COUNT)
    passengers = ShamBookingUtil.build_sham_passenger_info(seat_count, True)
    contact_info = ShamBookingUtil.build_sham_contact_info()
    contact_info.last_name = passengers[0].last_name
    contact_info.first_name = passengers[0].first_name

    journey = _search_target_journey(service, request, seat_count)
    bundle = _select_bundle(journey, request.cabin, product_tag)
    if bundle.seat < seat_count:
        raise ServiceError(
            ServiceStateEnum.BUSINESS_ERROR,
            f"余座不足，当前余座[{bundle.seat}]，目标人数[{seat_count}]",
        )

    booking = service.create_order(bundle, passengers, contact_info)
    journey.bundles = [bundle]
    response.order_number = booking.pnr
    response.pnr = booking.pnr
    response.order_state = OrderStateEnum.HOLD
    response.journeys = [journey]
    response.passengers = booking.passengers
    response.contact_info = booking.contact_info
    response.currency_code = booking.currency
    response.total_amount = booking.total_amount
    return response


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(
    self,
    sham_booking_data: RequestShamBookingTaskDataModel,
    response_order_data: ResponseOrderInfoModel,
):
    service = WebService(proxy_info_from_ext(sham_booking_data.ext))
    service.initialize_session()
    return _run_sham_booking(service, sham_booking_data, response_order_data)


if __name__ == "__main__":
    print(main({
        "taskId": "9gweb-local-sham-booking",
        "taskType": "shamBooking",
        "source": "9GWEB",
        "taskData": {
            "depAirport": "SGN",
            "arrAirport": "PQC",
            "depDate": "20260801",
            "flightNumber": "9G0123",
            "cabin": "Y",
            "bookingConfig": {"bookRate": 10, "currencyCode": "VND"},
            "ext": {
                "productTag": "ECONOMY LITE",
                "proxy": {
                    "host": "proxy.example.com",
                    "port": 8080,
                    "username": "YOUR_USERNAME",
                    "password": "YOUR_PASSWORD",
                    "region": "vn",
                    "sessId": None,
                    "sessionTime": 10,
                    "format": "http://{username}:{password}@{host}:{port}",
                },
            },
        },
    }))
