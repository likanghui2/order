from typing import Optional

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.enums.task_type_enum import TaskTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util
from common.utils.date_util import DateUtil
from common.utils.flight_util import FlightUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.sham_booking_util import ShamBookingUtil
from flights.bookcabin.config import BookCabinConfig
from flights.bookcabin.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("BCMwebShamBooking")


def _select_bundle(journey: FlightJourneyModel,
                   cabin: Optional[str],
                   ext: Optional[dict]) -> FlightBundleModel:
    if not journey.bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)

    bundles = journey.bundles
    target_cabin = (cabin or "").strip()
    if target_cabin:
        bundles = [
            bundle for bundle in bundles
            if _bundle_matches(bundle, target_cabin)
        ]
        if not bundles:
            current_cabin = "|".join([bundle.cabin or bundle.code or "" for bundle in journey.bundles])
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, target_cabin, current_cabin)

    ext = ext or {}
    for key, attr in (
        ("fareId", "fare_key"),
        ("bundleCode", "code"),
        ("productTag", "product_tag"),
    ):
        target = ext.get(key)
        if not target:
            continue
        bundle = next((item for item in bundles if getattr(item, attr) == target), None)
        if bundle is None:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
        return bundle

    return bundles[0]


def _bundle_matches(bundle: FlightBundleModel, target: str) -> bool:
    values = [
        bundle.cabin or "",
        bundle.code or "",
        bundle.product_tag or "",
        (bundle.ext or {}).get("bookingKey") or "",
        (bundle.ext or {}).get("rawCabin") or "",
    ]
    for value in values:
        if value == target:
            return True
        parts = [item for item in value.replace("^", ",").replace("|", ",").split(",") if item]
        if target in parts:
            return True
    return False


def _search_target_journey(service: WebService,
                           sham_booking_data: RequestShamBookingTaskDataModel,
                           seat_count: int,
                           promo_code: str,
                           cabin_class: str) -> FlightJourneyModel:
    journey_list = service.search(
        dep_airport=sham_booking_data.dep_airport,
        arr_airport=sham_booking_data.arr_airport,
        dep_date=DateUtil.string_to_target_format(sham_booking_data.dep_date, "%Y-%m-%d"),
        adult_count=seat_count,
        child_count=0,
        currency_code=sham_booking_data.booking_config.currency_code,
        promo_code=promo_code,
        cabin_class=cabin_class,
    )
    journey_list = FlightUtil.number_filter(journey_list, sham_booking_data.flight_number)
    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)
    return journey_list[0]


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self,
         sham_booking_data: RequestShamBookingTaskDataModel,
         response_order_data: ResponseOrderInfoModel):
    ext = sham_booking_data.ext or {}
    private_code = ext.get("privateCode") or []
    if isinstance(private_code, str):
        private_code = [private_code] if private_code else []
    promo_code = private_code[0] if private_code else ""
    cabin_class = ext.get("cabinClass") or BookCabinConfig.DEFAULT_CABIN_CLASS
    seat_count = sham_booking_data.ext.get('passengerCount', 1)

    service = WebService(proxy_info_from_ext(ext))
    service.initialize_session()
    try:
        journey = _search_target_journey(
            service=service,
            sham_booking_data=sham_booking_data,
            seat_count=seat_count,
            promo_code=promo_code,
            cabin_class=cabin_class,
        )
        use_bundle = _select_bundle(journey, sham_booking_data.cabin, ext)
        print(use_bundle.seat, use_bundle.cabin)
        if use_bundle.seat == 0:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, sham_booking_data.cabin, use_bundle.cabin)

        # available_seat = use_bundle.seat if use_bundle.seat > 0 else 1
        # seat_count = min(available_seat, BookCabinConfig.MAX_BOOKING_SEAT_COUNT)
        # journey = _search_target_journey(
        #     service=service,
        #     sham_booking_data=sham_booking_data,
        #     seat_count=seat_count,
        #     promo_code=promo_code,
        #     cabin_class=cabin_class,
        # )
        # use_bundle = _select_bundle(journey, use_bundle.cabin, ext)
        # if use_bundle.seat == 0:
        #     raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, sham_booking_data.cabin, use_bundle.cabin)
        available_seat = seat_count
        seat_count = min(available_seat, BookCabinConfig.MAX_BOOKING_SEAT_COUNT)

        passengers = ShamBookingUtil.build_sham_passenger_info(seat_count, True)
        contact_info = ShamBookingUtil.build_sham_contact_info()
        contact_info.last_name = passengers[0].last_name
        contact_info.first_name = passengers[0].first_name

        service.booking(
            journey=journey,
            passengers=passengers,
            contact_info=contact_info,
            bundle=use_bundle,
            response_order_data=response_order_data,
        )
        response_order_data.order_state = OrderStateEnum.HOLD
        return response_order_data
    finally:
        service.close()


if __name__ == "__main__":
    main({
        "taskId": "bcm-sham-booking-demo",
        "taskType": TaskTypeEnum.SHAM_BOOKING.value,
        "source": "BCMweb",
        "taskData": {
            "depAirport": "KUL",
            "arrAirport": "CGO",
            "depDate": "20260729",
            "flightNumber": "OD692",
            "cabin": "",
            "bookingConfig": {
                "bookRate": 10,
                "currencyCode": "IDR",
            },
            "callbackData": {
                "callData": "",
                "callUrl": "",
            },
            "ext": {
                "privateCode": [],
                "passengerCount":1
            },
        },
    }, ResponseOrderInfoModel())
