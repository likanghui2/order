from decimal import Decimal
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
from common.utils.flight_util import FlightUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.sham_booking_util import ShamBookingUtil
from flights.sunphuquocairways_9g.service.app_service import AppService

_app_date = import_module("task.9Gapp.search")._app_date

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("sunPhuQuocAirwaysAppShamBooking")
MAX_SEAT_COUNT = 5


def _select_bundle(
    journey: FlightJourneyModel,
    cabin: Optional[str],
    product_tag: Optional[str] = None,
) -> FlightBundleModel:
    if not journey.bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    bundles = journey.bundles
    if cabin:
        bundles = [bundle for bundle in bundles if bundle.cabin == cabin]
        if not bundles:
            current_cabins = "|".join(bundle.cabin or "" for bundle in journey.bundles)
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, cabin, current_cabins)
    if product_tag:
        bundles = [bundle for bundle in bundles if bundle.product_tag == product_tag]
        if not bundles:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    if not bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    return bundles[0]


def _search_target_journey(
    service: AppService,
    sham_booking_data: RequestShamBookingTaskDataModel,
    seat_count: int,
) -> FlightJourneyModel:
    journeys = service.search(
        dep_airport=sham_booking_data.dep_airport,
        arr_airport=sham_booking_data.arr_airport,
        dep_date=_app_date(sham_booking_data.dep_date),
        ret_date=None,
        adt_number=seat_count,
        chd_number=0,
        currency_code=sham_booking_data.booking_config.currency_code,
        promo_code="",
    )
    matches = FlightUtil.number_filter(journeys, sham_booking_data.flight_number)
    if len(matches) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)
    return matches[0]


def _run_sham_booking(
    service: AppService,
    sham_booking_data: RequestShamBookingTaskDataModel,
    response_order_data: ResponseOrderInfoModel,
) -> ResponseOrderInfoModel:
    product_tag = (sham_booking_data.ext or {}).get("productTag")
    first_journey = _search_target_journey(service, sham_booking_data, 1)
    first_bundle = _select_bundle(first_journey, sham_booking_data.cabin, product_tag)
    if first_bundle.seat <= 0:
        raise ServiceError(
            ServiceStateEnum.NO_AVAILABLE_CABIN,
            sham_booking_data.cabin or "",
            first_bundle.cabin or "",
        )

    seat_count = min(first_bundle.seat, MAX_SEAT_COUNT)
    passengers = ShamBookingUtil.build_sham_passenger_info(seat_count, True)
    contact_info = ShamBookingUtil.build_sham_contact_info()
    contact_info.last_name = passengers[0].last_name
    contact_info.first_name = passengers[0].first_name

    journey = _search_target_journey(service, sham_booking_data, seat_count)
    use_bundle = _select_bundle(journey, sham_booking_data.cabin, product_tag)
    if use_bundle.seat < seat_count:
        raise ServiceError(
            ServiceStateEnum.BUSINESS_ERROR,
            f"余座不足，当前余座[{use_bundle.seat}]，目标人数[{seat_count}]",
        )

    booking_id, pnr = service.create_and_hold(
        bundle=use_bundle,
        passengers=passengers,
        contact_info=contact_info,
        currency_code=sham_booking_data.booking_config.currency_code,
    )

    journey.bundles = [use_bundle]
    response_order_data.order_number = booking_id
    response_order_data.pnr = pnr
    response_order_data.order_state = OrderStateEnum.HOLD
    response_order_data.journeys = [journey]
    response_order_data.passengers = passengers
    response_order_data.contact_info = contact_info
    response_order_data.currency_code = use_bundle.price_info.currency
    response_order_data.total_amount = Decimal(seat_count) * (
        use_bundle.price_info.adult_ticket_price + use_bundle.price_info.adult_tax_price
    )
    return response_order_data


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(
    self,
    sham_booking_data: RequestShamBookingTaskDataModel,
    response_order_data: ResponseOrderInfoModel,
):
    service = AppService(proxy_info_from_ext(sham_booking_data.ext))
    service.initialize_session()
    return _run_sham_booking(service, sham_booking_data, response_order_data)


if __name__ == "__main__":
    # 运行前请先实时搜索，并更新日期、航班号、舱位和产品。
    print(main({
        "taskId": "9gapp-local-sham-booking",
        "taskType": "shamBooking",
        "source": "9GAPP",
        "taskData": {
            "depAirport": "SGN",
            "arrAirport": "PQC",
            "depDate": "20260720",
            "flightNumber": "9G0123",
            "cabin": "Y",
            "bookingConfig": {
                "bookRate": 10,
                "currencyCode": "VND",
            },
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
