import copy
import json
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.enums.task_type_enum import TaskTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.flight_util import FlightUtil
from common.utils.redis_util import RedisUtil
from common.utils.sham_booking_util import ShamBookingUtil
from flights.vietjet.flight_common.app_payment_method_enum import VjAppPaymentMethodEnum
from flights.vietjet.service.app_service import AppService

CACHE = machine_cache_util.MachineCache()
REDIS = RedisUtil(
    host=GlobalVariable.REDIS_HOST,
    port=GlobalVariable.REDIS_PORT,
    username=GlobalVariable.REDIS_USERNAME,
    password=GlobalVariable.REDIS_PASSWORD,
)

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("vietjetAppShamBooking")
FLIGHT_CACHE_TTL = 60 * 30
_REDIS_DISABLED = False


def _redis_cache_error(action: str, error: Exception) -> None:
    global _REDIS_DISABLED
    if _REDIS_DISABLED:
        return
    _REDIS_DISABLED = True
    LOG.error(f"VJAPP航班缓存{action}失败，已降级为实时查询，错误[{error}]", "航班缓存")


def _cache_get(key: Optional[str]):
    if not key or _REDIS_DISABLED:
        return None
    try:
        return REDIS.get_value(key)
    except Exception as error:
        _redis_cache_error("读取", error)
        return None


def _cache_set(key: str, value: str, ttl: int) -> bool:
    if _REDIS_DISABLED:
        return False
    try:
        REDIS.set_value_ex(key, value, ttl)
        return True
    except Exception as error:
        _redis_cache_error("写入", error)
        return False


def _cache_delete(key: str) -> bool:
    if _REDIS_DISABLED:
        return False
    try:
        REDIS.delete_key(key)
        return True
    except Exception as error:
        _redis_cache_error("删除", error)
        return False


def _app_date(date_value: str) -> str:
    if len(date_value) == 8 and date_value.isdigit():
        return datetime.strptime(date_value, "%Y%m%d").strftime("%m-%d-%Y")
    if len(date_value) >= 10 and date_value[4] == "-":
        return datetime.strptime(date_value[:10], "%Y-%m-%d").strftime("%m-%d-%Y")
    return date_value


def _cache_date(date_value: str) -> str:
    if len(date_value) == 8 and date_value.isdigit():
        return datetime.strptime(date_value, "%Y%m%d").strftime("%Y-%m-%d")
    if len(date_value) >= 10 and date_value[4] == "-":
        return datetime.strptime(date_value[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    return datetime.strptime(date_value, "%m-%d-%Y").strftime("%Y-%m-%d")


def _flight_cache_key(sham_booking_data: RequestShamBookingTaskDataModel,
                      dep_date: str,
                      cabin: Optional[str]) -> str:
    return (
        f"vjapp:sham:flight:{sham_booking_data.dep_airport}|{sham_booking_data.arr_airport}|"
        f"{dep_date}|{sham_booking_data.flight_number}|{cabin or ''}|"
        f"{sham_booking_data.booking_config.currency_code}"
    )


def _journey_flight_number(journey: FlightJourneyModel) -> str:
    return ",".join(segment.flight_number for segment in journey.segments)


def _journey_summary(journey: FlightJourneyModel) -> str:
    return (
        f"航班[{_journey_flight_number(journey)}]，"
        f"航线[{journey.dep_airport}-{journey.arr_airport}]，"
        f"日期[{journey.dep_time.strftime('%Y-%m-%d')}]"
    )


def _journey_match_request(journey: FlightJourneyModel,
                           sham_booking_data: RequestShamBookingTaskDataModel,
                           dep_date: str) -> bool:
    return (
            journey.dep_airport == sham_booking_data.dep_airport
            and journey.arr_airport == sham_booking_data.arr_airport
            and journey.dep_time.strftime("%Y-%m-%d") == dep_date
            and _journey_flight_number(journey) == sham_booking_data.flight_number
    )


def _select_bundle(journey: FlightJourneyModel,
                   cabin: Optional[str]) -> FlightBundleModel:
    if not journey.bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)

    bundles = journey.bundles
    target_cabin = (cabin or "").replace("00", "")
    if target_cabin:
        bundles = [
            bundle for bundle in bundles
            if bundle.cabin == target_cabin or target_cabin in (bundle.cabin or "").replace("^", "|").split("|")
        ]
        if not bundles:
            current_cabin = "|".join([bundle.cabin or "" for bundle in journey.bundles])
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, target_cabin, current_cabin)

    bundle = next((item for item in bundles if item.product_tag == "Eco"), None)
    if bundle is None:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    return bundle


def _select_cache_bundle(journey: FlightJourneyModel,
                         cabin: Optional[str]) -> Optional[FlightBundleModel]:
    try:
        return _select_bundle(journey, cabin)
    except ServiceError:
        try:
            return _select_bundle(journey, None)
        except ServiceError:
            return None


def _search_target_journey(service: AppService,
                           sham_booking_data: RequestShamBookingTaskDataModel,
                           seat_count: int) -> FlightJourneyModel:
    journey_list = service.search(
        dep_airport=sham_booking_data.dep_airport,
        arr_airport=sham_booking_data.arr_airport,
        dep_date=_app_date(sham_booking_data.dep_date),
        adult_count=seat_count,
        child_count=0,
        currency=sham_booking_data.booking_config.currency_code,
        promo_code="",
    )
    journey_list = FlightUtil.number_filter(journey_list, sham_booking_data.flight_number)
    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)
    return journey_list[0]


def _search_target_journey_with_cache(service: AppService,
                                      sham_booking_data: RequestShamBookingTaskDataModel,
                                      seat_count: int,
                                      target_cabin: Optional[str]) -> FlightJourneyModel:
    dep_date = _cache_date(sham_booking_data.dep_date)
    request_cache_key = _flight_cache_key(sham_booking_data, dep_date, target_cabin) if target_cabin else None
    cache_data = _cache_get(request_cache_key)
    if not request_cache_key:
        LOG.info("未传入舱位，跳过VJAPP航班缓存读取，强制实时查询", "航班缓存")
    if cache_data:
        LOG.info(f"命中VJAPP航班缓存，key[{request_cache_key}]，跳过实时查询", "航班缓存")
        try:
            journey = FlightJourneyModel.model_validate(json.loads(cache_data.decode("utf-8")))
            if _journey_match_request(journey, sham_booking_data, dep_date):
                return journey
            LOG.error(
                f"VJAPP航班缓存与任务参数不一致，删除缓存，key[{request_cache_key}]，"
                f"任务日期[{dep_date}]，缓存{_journey_summary(journey)}",
                "航班缓存"
            )
        except Exception as error:
            LOG.error(f"VJAPP航班缓存解析失败，删除缓存，key[{request_cache_key}]，错误[{error}]", "航班缓存")
        _cache_delete(request_cache_key)

    if request_cache_key:
        LOG.info(f"未命中VJAPP航班缓存，key[{request_cache_key}]，开始实时查询", "航班缓存")
    journey = _search_target_journey(
        service=service,
        sham_booking_data=sham_booking_data,
        seat_count=seat_count,
    )
    if not _journey_match_request(journey, sham_booking_data, dep_date):
        LOG.error(
            f"VJAPP实时查询航班与任务参数不一致，任务日期[{dep_date}]，实际{_journey_summary(journey)}",
            "航班缓存"
        )
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "flightDate")

    journey_cache_value = journey.model_dump_json(by_alias=True)
    cache_keys = set()
    selected_bundle = _select_cache_bundle(journey, target_cabin)
    if selected_bundle and selected_bundle.cabin:
        cache_keys.add(_flight_cache_key(sham_booking_data, dep_date, selected_bundle.cabin))
    for cache_key in cache_keys:
        if _cache_set(cache_key, journey_cache_value, FLIGHT_CACHE_TTL):
            LOG.info(f"写入VJAPP航班缓存，key[{cache_key}]，ttl[{FLIGHT_CACHE_TTL}]", "航班缓存")
    return journey


def _delete_flight_cache(sham_booking_data: RequestShamBookingTaskDataModel,
                         target_cabin: Optional[str],
                         use_bundle: Optional[FlightBundleModel] = None) -> None:
    dep_date = _cache_date(sham_booking_data.dep_date)
    cache_keys = set()
    if target_cabin:
        cache_keys.add(_flight_cache_key(sham_booking_data, dep_date, target_cabin))
    if use_bundle and use_bundle.cabin:
        cache_keys.add(_flight_cache_key(sham_booking_data, dep_date, use_bundle.cabin))
    for cache_key in cache_keys:
        if _cache_delete(cache_key):
            LOG.info(f"删除VJAPP航班缓存，key[{cache_key}]", "航班缓存")


def _sham_booking(self,
                  sham_booking_data: RequestShamBookingTaskDataModel,
                  response_order_data: ResponseOrderInfoModel):
    """
    VJ App 虚拟预订任务
    """
    raw_cabin = sham_booking_data.cabin or ""
    target_cabin = raw_cabin.replace("00", "")

    def _search_and_validate(app_service: AppService, adult_count: int):
        journey = _search_target_journey_with_cache(
            service=app_service,
            sham_booking_data=sham_booking_data,
            seat_count=adult_count,
            target_cabin=target_cabin,
        )
        current_bundle = _select_bundle(journey, target_cabin)
        if current_bundle.seat <= 0:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, target_cabin, current_bundle.cabin)
        return journey

    def _booking(app_service: AppService,
                 journey: FlightJourneyModel,
                 passengers: List[PassengerInfoModel],
                 booking_bundle: FlightBundleModel,
                 order_data: ResponseOrderInfoModel):
        try:
            flow_result = app_service.build_full_booking_flow(
                journey=journey,
                use_bundle=booking_bundle,
                passenger_infos=passengers,
                contact_info=copy.deepcopy(contact_info),
            )
        except ServiceError:
            _delete_flight_cache(sham_booking_data, target_cabin, booking_bundle)
            raise
        reserve_data = flow_result.get("data") or flow_result
        pnr = reserve_data["number"]
        journey.bundles = [booking_bundle]
        order_data.order_number = pnr
        order_data.pnr = pnr
        order_data.order_state = OrderStateEnum.HOLD
        order_data.journeys = [journey]
        order_data.passengers = passengers
        order_data.contact_info = contact_info
        order_data.currency_code = booking_bundle.price_info.currency
        order_data.total_amount = Decimal(str(
            flow_result["processingFee"]["parsed"].get("paymentTransactionAmounts") or 0
        ))
        return order_data

    def _merge_order_result(source_order: ResponseOrderInfoModel):
        response_order_data.currency_code = source_order.currency_code
        response_order_data.journeys = source_order.journeys
        response_order_data.contact_info = source_order.contact_info
        response_order_data.total_amount = source_order.total_amount
        response_order_data.passengers = (response_order_data.passengers or []) + (source_order.passengers or [])
        if source_order.pnr:
            response_order_data.pnr = (
                f"{response_order_data.pnr}|{source_order.pnr}" if response_order_data.pnr else source_order.pnr
            )
        if source_order.order_number:
            response_order_data.order_number = (
                f"{response_order_data.order_number}|{source_order.order_number}"
                if response_order_data.order_number
                else source_order.order_number
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
            service = AppService(GlobalVariable.PROXY_INFO_DATA)
            service.initialize_session()
        else:
            service = script_cache["value"]
        try:
            LOG.info(f"第{attempt_no}次VJAPP押位前重新搜索")
            search_journey = _search_and_validate(service, adult_count=1)
            search_bundle = _select_bundle(search_journey, target_cabin)
            seat_count = sham_booking_data.ext.get('passengerCount', 1)
            LOG.info(f"第{attempt_no}次VJAPP押位校验通过，舱位[{search_bundle.cabin}]，余座[{search_bundle.seat}]")
            seat_count = min(seat_count, 9)
            passengers: List[PassengerInfoModel] = ShamBookingUtil.build_sham_passenger_info(seat_count, True)
            contact_info.last_name = passengers[0].last_name
            contact_info.first_name = passengers[0].first_name
            booking_journey = search_journey
            booking_bundle = search_bundle
            #
            # booking_journey = _search_and_validate(service, adult_count=seat_count)
            # booking_bundle = _select_bundle(booking_journey, target_cabin)
            # LOG.info(
            #     f"第{attempt_no}次VJAPP押位二次校验通过，"
            #     f"舱位[{booking_bundle.cabin}]，余座[{booking_bundle.seat}]"
            # )

            order_data = copy.deepcopy(response_order_data)
        except ServiceError as e:
            if e.code in [ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER.name,
                          ServiceStateEnum.NO_AVAILABLE_CABIN.name,
                          ServiceStateEnum.NO_AVAILABLE_BUNDLE.name,
                          ServiceStateEnum.NO_FLIGHT_DATA.name]:
                _delete_flight_cache(sham_booking_data, target_cabin)
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
def main(self,
         sham_booking_data: RequestShamBookingTaskDataModel,
         response_order_data: ResponseOrderInfoModel):
    return _sham_booking(self, sham_booking_data, response_order_data)


def _build_demo_task_data():
    return {
        "taskId": "vj-app-sham-booking-demo",
        "taskType": TaskTypeEnum.SHAM_BOOKING.value,
        "source": "VJAPP",
        "taskData": {
            "depAirport": "SGN",
            "arrAirport": "CAN",
            "depDate": "20260729",
            "flightNumber": "VJ3908",
            "cabin": "Z",
            "bookingConfig": {
                "bookRate": 10,
                "currencyCode": 'VND',
            },
            'ext': {
                "passengerCount": 2,
            },
            "callbackData": {
                "callData": "",
                "callUrl": "",
            },
        },
    }


if __name__ == "__main__":
    result_list = []
    run_count = 1
    for _ in range(run_count):
        try:
            result = main(_build_demo_task_data())
            if result and len(str(result)) > 300:
                result_list.append(result)
            print(result_list)
        except Exception as e:
            print(e)
