from decimal import Decimal
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
from common.utils.date_util import DateUtil
from common.utils.flight_util import FlightUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.sham_booking_util import ShamBookingUtil
from flights.garuda.service.app_service import AppService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("garudaAppShamBooking")
MAX_SEAT_COUNT = 9


def _select_bundle(journey: FlightJourneyModel, cabin: Optional[str]) -> FlightBundleModel:
    bundles = journey.bundles
    if cabin:
        bundles = [bundle for bundle in bundles if bundle.cabin == cabin]
        if not bundles:
            current_cabin = " ".join([bundle.cabin or "" for bundle in journey.bundles])
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, cabin, current_cabin)
    if not bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    return bundles[0]


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(
    self,
    sham_booking_data: RequestShamBookingTaskDataModel,
    response_order_data: ResponseOrderInfoModel,
):
    service = AppService(proxy_info_from_ext(sham_booking_data.ext))
    service.initialize_session()

    dep_date = DateUtil.string_to_target_format(sham_booking_data.dep_date, "%Y-%m-%d")
    journey_list = service.search(
        dep_airport=sham_booking_data.dep_airport,
        arr_airport=sham_booking_data.arr_airport,
        dep_date=dep_date,
        ret_date=None,
        adt_number=1,
        chd_number=0,
        currency_code=sham_booking_data.booking_config.currency_code,
    )
    journey_list = FlightUtil.number_filter(journey_list, sham_booking_data.flight_number)
    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)

    journey = journey_list[0]
    use_bundle = _select_bundle(journey, sham_booking_data.cabin)
    if use_bundle.seat <= 0:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, sham_booking_data.cabin, use_bundle.cabin)

    seat_count = min(use_bundle.seat, MAX_SEAT_COUNT)
    passengers = ShamBookingUtil.build_sham_passenger_info(seat_count, True)
    contact_info = ShamBookingUtil.build_sham_contact_info()
    contact_info.last_name = passengers[0].last_name
    contact_info.first_name = passengers[0].first_name

    journey_list = service.search(
        dep_airport=sham_booking_data.dep_airport,
        arr_airport=sham_booking_data.arr_airport,
        dep_date=dep_date,
        ret_date=None,
        adt_number=seat_count,
        chd_number=0,
        currency_code=sham_booking_data.booking_config.currency_code,
    )
    journey_list = FlightUtil.number_filter(journey_list, sham_booking_data.flight_number)
    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)

    journey = journey_list[0]
    use_bundle = _select_bundle(journey, sham_booking_data.cabin)
    if use_bundle.seat < seat_count:
        raise ServiceError(
            ServiceStateEnum.BUSINESS_ERROR,
            f"余座不足，当前余座[{use_bundle.seat}]，目标人数[{seat_count}]",
        )

    cart_data = service.cart_booking(use_bundle)
    booking_data = service.booking_booking(
        cart_data=cart_data,
        passengers=passengers,
        contact_info=contact_info,
        departure_date=dep_date,
    )
    pnr = service.get_pnr(booking_data)

    journey.bundles = [use_bundle]
    response_order_data.order_number = pnr
    response_order_data.pnr = pnr
    response_order_data.order_state = OrderStateEnum.HOLD
    response_order_data.journeys = [journey]
    response_order_data.passengers = passengers
    response_order_data.contact_info = contact_info
    response_order_data.currency_code = use_bundle.price_info.currency
    response_order_data.total_amount = (
        (use_bundle.price_info.adult_ticket_price + use_bundle.price_info.adult_tax_price) * seat_count
        or Decimal("0")
    )
    return response_order_data


if __name__ == "__main__":
    for u in range(100):
        main({
            "taskId": "123",
            "taskType": "shamBooking",
            "source": "GAAPP",
            "taskData": {
                "depAirport": "PVG",
                "arrAirport": "CGK",
                "depDate": "2026-07-23",
                "flightNumber": "GA895",
                "cabin": "N",
                "bookingConfig": {
                    "bookRate": 10,
                    "currencyCode": "IDR",
                },
                'ext': {
                    "proxy": {
                        "source": "VJAPP",
                        "configured": False,
                        "host": "lite.flashproxy.io",
                        "port": 6969,
                        "username": "BHF6UsNS",
                        "password": "X8ABIdpI",
                        "region": "us",
                        "sessId": None,
                        "sessionTime": 10,
                        "format": "http://{username}-country-{region}-time-{sess_time}-session-{session}:{password}@{host}:{port}"
                    }
                }
            },
        })
