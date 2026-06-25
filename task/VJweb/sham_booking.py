import copy
from datetime import datetime
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
from flights.vietjet.service.web_service import WebService

CACHE = machine_cache_util.MachineCache()

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil('vietjetShamBooking')


def _sham_booking(self, sham_booking_data: RequestShamBookingTaskDataModel,
                  response_order_data: ResponseOrderInfoModel):
    """
    虚拟预订任务
    """
    dep_date = datetime.strptime(sham_booking_data.dep_date, "%Y%m%d").strftime("%Y-%m-%d")
    currency_code = sham_booking_data.booking_config.currency_code
    raw_cabin = sham_booking_data.cabin or ""
    use_gls_booking = "00" in raw_cabin
    target_cabin = raw_cabin.replace("00", "")
    passenger_count = sham_booking_data.ext.get('passengerCount', 1)

    def _search_and_validate(web_service, adult_count):
        # web_service.initialize_session()

        journey_list = web_service.search(
            dep_airport=sham_booking_data.dep_airport,
            arr_airport=sham_booking_data.arr_airport,
            dep_date=dep_date,
            adt_number=adult_count,
            chd_number=0,
            infant_count=0,
            currency_code=currency_code, is_hold=True
        )
        journey_list = FlightUtil.number_filter(journey_list, sham_booking_data.flight_number)

        if len(journey_list) != 1:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)

        journey = journey_list[0]
        current_bundle = FlightUtil.bundle_verify(journey, "Eco")
        if target_cabin and current_bundle.cabin != target_cabin:
            LOG.info(f'当前舱位[{current_bundle.cabin}]，目标舱位[{target_cabin}]，当前余座[{current_bundle.seat}]')
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, target_cabin, current_bundle.cabin)

        return journey

    def _booking(web_service, journey, passengers, booking_bundle, order_data):
        booking_func = web_service.booking_gls
        later_response, _ = booking_func(
            journey=journey,
            passenger_infos=passengers,
            contact_info=copy.deepcopy(contact_info),
            use_bundle=booking_bundle,
            response_order_data=order_data,
            need_pay=False,
        )
        reservation = later_response.get('reservation') or {}
        pnr = reservation.get('locator') or StringUtil.generate_random_string(7)
        order_data.order_state = OrderStateEnum.HOLD
        order_data.pnr = pnr
        return order_data

    def _merge_order_result(source_order):
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

    # 联系人信息
    contact_info = ShamBookingUtil.build_sham_contact_info()
    contact_info.phone_code = "60"
    contact_info.email_address = f"{contact_info.email_address.split('@')[0]}@gmail.com".lower()

    def _book_once():
        attempt_no = 1
        script_cache = CACHE.get_data()
        if script_cache is None:
            service = WebService(GlobalVariable.PROXY_INFO_DATA)
        else:
            service = script_cache['value']
        try:
            # if passenger_count < 6:
            #     LOG.info(f'第{attempt_no}次押位前重新搜索')
            #     search_journey = _search_and_validate(service, adult_count=1)
            #     search_bundle = FlightUtil.bundle_verify(search_journey, "Eco")
            #     LOG.info(f'第{attempt_no}次押位校验通过，舱位[{search_bundle.cabin}]，余座[{search_bundle.seat}]')
            #     seat_count = min(9, search_bundle.seat)
            # else:
            #     seat_count = passenger_count
            booking_journey = _search_and_validate(service, adult_count=passenger_count)
            booking_bundle = FlightUtil.bundle_verify(booking_journey, "Eco")
            LOG.info(f'第{attempt_no}次押位二次校验通过，舱位[{booking_bundle.cabin}]，余座[{booking_bundle.seat}]')
            seat_count = min(9, booking_bundle.seat)
            passengers: List[PassengerInfoModel] = ShamBookingUtil.build_sham_passenger_info(seat_count, True)

            order_data = copy.deepcopy(response_order_data)
        except ServiceError as e:
            if e.code in [ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER.name,
                          ServiceStateEnum.NO_AVAILABLE_CABIN.name,
                          ServiceStateEnum.NO_AVAILABLE_BUNDLE.name,
                          ServiceStateEnum.NO_FLIGHT_DATA.name]:
                if script_cache is None:
                    CACHE.set_data(service, 280)
                else:
                    CACHE.set_data(script_cache['value'], None, script_cache['timeOut'])
            raise
        return _booking(service, booking_journey, passengers, booking_bundle, order_data)

    response_order = _book_once()
    _merge_order_result(response_order)
    return response_order


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, sham_booking_data: RequestShamBookingTaskDataModel, response_order_data: ResponseOrderInfoModel):
    return _sham_booking(self, sham_booking_data, response_order_data)


if __name__ == '__main__':
    aa = []
    for i in range(10000000000):
        try:
            task_data = {
                "taskId": "be05b93d2ffd4bdf93a7fb413c866b71",
                "taskType": "shamBooking",
                "source": "VJWEB",
                "taskData": {
                    "depAirport": "PVG",
                    "arrAirport": "SGN",
                    "depDate": "20260625",
                    "flightNumber": "VJ3901",
                    "cabin": "",
                    "bookingConfig": {
                        "bookRate": 10,
                        "currencyCode": "VND"
                    },
                    "callbackData": {
                        "callData": "",
                        "callUrl": "http://trip-api.bjrakd.com/triplex-foreign-external/external/task/pressureback/seatNewCallback"
                    },
                    'ext': {
                        "usePassport": True,
                        "passengerCount": 1
                    }
                }
            }
            r = main(task_data)
            if len(r) > 300:
                aa.append(r)
            print(aa)
        except Exception as e:
            print(e)
