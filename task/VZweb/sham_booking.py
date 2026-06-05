import copy
from datetime import datetime
from time import sleep
from typing import List

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.flight_util import FlightUtil
from common.utils.sham_booking_util import ShamBookingUtil
from common.utils.string_util import StringUtil
from flights.vietjet.service.vz_web_service import VZWebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()
LOG = log_util.LogUtil("vzWebShamBooking")
MAX_PASSENGERS_PER_BOOKING = 9


def _sham_booking(self,
                  sham_booking_data: RequestShamBookingTaskDataModel,
                  response_order_data: ResponseOrderInfoModel):
    dep_date = datetime.strptime(sham_booking_data.dep_date, "%Y%m%d").strftime("%Y-%m-%d")
    currency_code = sham_booking_data.booking_config.currency_code
    target_cabin = sham_booking_data.cabin or ""

    def _search_and_validate(web_service, adult_count):
        journey_list = web_service.search(
            dep_airport=sham_booking_data.dep_airport,
            arr_airport=sham_booking_data.arr_airport,
            dep_date=dep_date,
            adt_number=adult_count,
            chd_number=0,
            infant_count=0,
            currency_code=currency_code,
        )
        journey_list = FlightUtil.number_filter(journey_list, sham_booking_data.flight_number)
        if len(journey_list) != 1:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)

        journey = journey_list[0]
        current_bundle = FlightUtil.bundle_verify(journey, "Eco")
        if target_cabin and current_bundle.cabin != target_cabin:
            LOG.info(
                f"current cabin[{current_bundle.cabin}], target cabin[{target_cabin}], seat[{current_bundle.seat}]")
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, target_cabin, current_bundle.cabin)
        return journey, current_bundle

    def _booking(web_service, journey, passengers, booking_bundle, order_data):
        later_response, _ = web_service.booking(
            journey=journey,
            passenger_infos=passengers,
            contact_info=copy.deepcopy(contact_info),
            use_bundle=booking_bundle,
            response_order_data=order_data,
            need_pay=False,
        )
        reservation = later_response.get("reservation") or {}
        pnr = reservation.get("locator") or StringUtil.generate_random_string(7)
        order_data.order_state = OrderStateEnum.HOLD
        order_data.pnr = pnr
        return order_data

    def _merge_order_result(source_order):
        source_order.journeys[0].ext = None
        source_order.journeys[0].segments[0].ext =  None
        source_order.journeys[0].bundles[0].ext = None
        response_order_data.currency_code = source_order.currency_code
        response_order_data.journeys = source_order.journeys
        response_order_data.contact_info = source_order.contact_info
        response_order_data.total_amount = source_order.total_amount
        response_order_data.passengers = (response_order_data.passengers or []) + (source_order.passengers or [])
        if source_order.pnr:
            response_order_data.pnr = (
                f"{response_order_data.pnr}|{source_order.pnr}" if response_order_data.pnr else source_order.pnr
            )
        response_order_data.order_state = OrderStateEnum.HOLD

    contact_info = ShamBookingUtil.build_sham_contact_info()
    contact_info.phone_code = "66"
    contact_info.email_address = f"{contact_info.email_address.split('@')[0]}@gmail.com".lower()

    def _book_once():
        script_cache = CACHE.get_data()
        if script_cache is None:
            service = VZWebService(GlobalVariable.PROXY_INFO_DATA)
        else:
            service = script_cache["value"]

        try:
            LOG.info("search before hold")
            search_journey, search_bundle = _search_and_validate(service, adult_count=1)
            seat_count = min(search_bundle.seat, MAX_PASSENGERS_PER_BOOKING)
            LOG.info(
                f"hold validation ok, cabin[{search_bundle.cabin}], "
                f"site seat[{search_bundle.seat}], booking seat[{seat_count}]"
            )

            passengers: List[PassengerInfoModel] = ShamBookingUtil.build_sham_passenger_info(seat_count, True)
            booking_journey, booking_bundle = _search_and_validate(service, adult_count=seat_count)
            LOG.info(f"second validation ok, cabin[{booking_bundle.cabin}], seat[{booking_bundle.seat}]")

            order_data = copy.deepcopy(response_order_data)
        except ServiceError as e:
            if e.code in [
                ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER.name,
                ServiceStateEnum.NO_AVAILABLE_CABIN.name,
                ServiceStateEnum.NO_AVAILABLE_BUNDLE.name,
                ServiceStateEnum.NO_FLIGHT_DATA.name,
            ]:
                sleep(1)
                if script_cache is None:
                    CACHE.set_data(service, 280)
                else:
                    CACHE.set_data(script_cache["value"], None, script_cache["timeOut"])
            raise
        return _booking(service, booking_journey, passengers, booking_bundle, order_data)

    response_order = _book_once()
    _merge_order_result(response_order)
    return response_order


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, sham_booking_data: RequestShamBookingTaskDataModel, response_order_data: ResponseOrderInfoModel):
    return _sham_booking(self, sham_booking_data, response_order_data)


if __name__ == "__main__":
    data= {
        "taskId": "0aa6dc7aae234aecb456b62b31817906",
        "taskType": "shamBooking",
        "source": "VJWEB",
        "taskData": {
            "depAirport": "SGN",
            "arrAirport": "CAN",
            "depDate": "20260802",
            "flightNumber": "VJ3908",
            "cabin": "",
            "bookingConfig": {
                "bookRate": 5,
                "currencyCode": "THB"
            },
            "callbackData": {
                "callData": "",
                "callUrl": "http://trip-api.bjrakd.com/triplex-foreign-external/external/task/pressureback/seatNewCallback"
            }
        }
    }
    main(data)
