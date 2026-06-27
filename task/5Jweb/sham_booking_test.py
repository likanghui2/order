import json
from decimal import Decimal
from time import sleep
from typing import List, Optional

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.date_util import DateUtil
from common.utils.flight_util import FlightUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.redis_util import RedisUtil
from common.utils.sham_booking_util import ShamBookingUtil
from flights.cebupacificair_5j.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()

LOG = log_util.LogUtil('cebupacificairShamBooking')
REDIS = RedisUtil(host=GlobalVariable.REDIS_HOST, port=GlobalVariable.REDIS_PORT, password=GlobalVariable.REDIS_PASSWORD,username=GlobalVariable.REDIS_USERNAME)


def _select_bundle(journey: FlightJourneyModel,
                   cabin: Optional[str],
                   ext: Optional[dict]) -> FlightBundleModel:
    bundles = journey.bundles
    if cabin:
        bundles = [bundle for bundle in bundles if bundle.cabin == cabin]
        if not bundles:
            current_cabin = journey.bundles[0].cabin if journey.bundles else ''
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, cabin, current_cabin)

    return next((item for item in bundles if item.product_tag == 'GO Basic'), bundles[0])


def _search_date(dep_date: str) -> str:
    parsed = DateUtil.string_to_date_auto(dep_date)
    if parsed is None:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'depDate')
    return parsed.strftime('%Y-%m-%d')


def _flight_cache_key(sham_booking_data: RequestShamBookingTaskDataModel,
                      dep_date: str,
                      cabin: Optional[str]) -> str:
    return (
        f'{sham_booking_data.dep_airport}|{sham_booking_data.arr_airport}|{dep_date}|'
        f'{sham_booking_data.flight_number}|{cabin or ""}'
    )


def _journey_flight_number(journey: FlightJourneyModel) -> str:
    return ','.join(segment.flight_number for segment in journey.segments)


def _journey_summary(journey: FlightJourneyModel) -> str:
    return (
        f'航班[{_journey_flight_number(journey)}]，'
        f'航线[{journey.dep_airport}-{journey.arr_airport}]，'
        f'时间[{journey.dep_time.strftime("%Y-%m-%d %H:%M")}]'
    )


def _journey_match_request(journey: FlightJourneyModel,
                           sham_booking_data: RequestShamBookingTaskDataModel,
                           dep_date: str) -> bool:
    return (
        journey.dep_airport == sham_booking_data.dep_airport
        and journey.arr_airport == sham_booking_data.arr_airport
        and journey.dep_time.strftime('%Y-%m-%d') == dep_date
        and _journey_flight_number(journey) == sham_booking_data.flight_number
    )


def _verify_journey(journey: FlightJourneyModel,
                    sham_booking_data: RequestShamBookingTaskDataModel,
                    dep_date: str,
                    source: str) -> None:
    if _journey_match_request(journey, sham_booking_data, dep_date):
        return
    LOG.error(
        f'{source}航班与任务参数不一致，任务航班[{sham_booking_data.flight_number}]，'
        f'任务航线[{sham_booking_data.dep_airport}-{sham_booking_data.arr_airport}]，'
        f'任务日期[{dep_date}]，实际{_journey_summary(journey)}',
        '航班校验'
    )
    raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'flightDate')


def _is_sold_out_error(error: ServiceError) -> bool:
    return (
        error.code == ServiceStateEnum.BUSINESS_ERROR.name
        and '该座位已售完' in error.message
    )


def _get_clean_service(ext: Optional[dict]):
    service_cache = CACHE.get_data()
    if service_cache is None:
        LOG.info('未命中本机session缓存，初始化新session', 'session缓存')
        service = WebService(proxy_info_from_ext(ext))
        service.initialize_html_session_booking()
        return service, None
    LOG.info(f"命中本机session缓存，过期时间[{service_cache['timeOut']}]", 'session缓存')
    return service_cache['value'], service_cache['timeOut']


def _cache_clean_service(service: WebService, timeout_time: Optional[int]) -> None:
    if timeout_time is None:
        LOG.info('回收干净session，缓存400秒', 'session缓存')
        CACHE.set_data(service, 400)
    else:
        LOG.info(f'回收干净session，沿用过期时间[{timeout_time}]', 'session缓存')
        CACHE.set_data(service, None, timeout_time)


def _hold_service(held_services: list,
                  service: WebService,
                  passengers: List[PassengerInfoModel],
                  stage: str) -> None:
    held_services.append(service)
    LOG.info(
        f"{stage}保存成功押位session引用，人数[{len(passengers)}]，"
        f"当前任务held session数[{len(held_services)}]",
        'session缓存'
    )


def _trip_passengers(service: WebService,
                     sham_booking_data: RequestShamBookingTaskDataModel,
                     journey: FlightJourneyModel,
                     use_bundle: FlightBundleModel,
                     seat_number: int) -> List[PassengerInfoModel]:
    LOG.info(
        f"开始trip，航班[{sham_booking_data.flight_number}]，人数[{seat_number}]，"
        f"舱位[{use_bundle.cabin}]，套餐[{use_bundle.product_tag}]",
        'trip请求'
    )
    passengers = ShamBookingUtil.build_sham_passenger_info(seat_number, True)
    service.trip(
        dep_airport=sham_booking_data.dep_airport,
        journey=journey,
        bundle=use_bundle,
        adult_count=seat_number,
        child_count=0,
        passengers=passengers,
    )
    LOG.info(
        f"trip成功，航班[{sham_booking_data.flight_number}]，人数[{seat_number}]，"
        f"乘客key数量[{sum(1 for passenger in passengers if passenger.key)}]",
        'trip结果'
    )
    return passengers


def _trusted_first_seat_count(seat: int) -> int:
    if seat <= 0:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, '', '')
    result = min(seat, 25)
    LOG.info(f'可信座位展示数[{seat}]，首次trip人数[{result}]', '座位策略')
    return result


def _tail_seat_counts(max_seat: int = 25) -> List[int]:
    result = [seat for seat in [16, 8, 4, 2, 1] if seat < max_seat]
    LOG.info(f'尾数补位上限[{max_seat}]，补位序列[{result}]', '座位策略')
    return result


def _return_partial_or_raise(error: ServiceError,
                             passengers: List[PassengerInfoModel],
                             held_services: list,
                             stage: str):
    LOG.error(f'{stage}异常，错误[{error.message}]', '押位异常')
    if passengers:
        LOG.info(
            f'{stage}异常但已有成功押位，停止后续请求并返回部分成功，'
            f'人数[{len(passengers)}]，成功session数[{len(held_services)}]',
            '押位流程'
        )
        return passengers, held_services
    raise error


def _occupy_available_seats(sham_booking_data: RequestShamBookingTaskDataModel,
                            journey: FlightJourneyModel,
                            use_bundle: FlightBundleModel,
                            service: Optional[WebService] = None,
                            trust_seat_count: bool = False):
    held_services = []
    passengers = []
    timeout_time = None
    last_error = None
    skip_full_chunk = False
    tail_max_seat = 25
    LOG.info(
        f"开始押位，航班[{sham_booking_data.flight_number}]，缓存座位可信[{trust_seat_count}]，"
        f"当前bundle座位[{use_bundle.seat}]，舱位[{use_bundle.cabin}]",
        '押位流程'
    )

    if trust_seat_count and use_bundle.seat > 0:
        seat_number = _trusted_first_seat_count(use_bundle.seat)
        if service is None:
            service, timeout_time = _get_clean_service(sham_booking_data.ext)
        try:
            trip_passengers = _trip_passengers(service, sham_booking_data, journey, use_bundle, seat_number)
            _hold_service(held_services, service, trip_passengers, '可信座位首次trip')
            passengers.extend(trip_passengers)
            LOG.info(f'可信座位首次trip成功，人数[{seat_number}]，累计人数[{len(passengers)}]', '押位流程')
            service = None
            timeout_time = None
        except ServiceError as e:
            if not _is_sold_out_error(e):
                return _return_partial_or_raise(e, passengers, held_services, f'可信座位trip[{seat_number}]')
            LOG.info(f'可信座位首次trip售完，人数[{seat_number}]，进入尾数补位，错误[{e.message}]', '押位流程')
            last_error = e
            skip_full_chunk = True
            tail_max_seat = seat_number
        if last_error is None:
            if use_bundle.seat < 25:
                LOG.info(f'可信座位小于25且已全部trip成功，最终人数[{len(passengers)}]', '押位流程')
                return passengers, held_services
            LOG.info(
                f'可信座位展示为[{use_bundle.seat}]，表示至少25，继续25整块探测隐藏余座',
                '押位流程'
            )
    else:
        if service is None:
            service, timeout_time = _get_clean_service(sham_booking_data.ext)
        try:
            trip_passengers = _trip_passengers(service, sham_booking_data, journey, use_bundle, 1)
            _hold_service(held_services, service, trip_passengers, '缓存航班先占1人')
            passengers.extend(trip_passengers)
            LOG.info('缓存航班先占1人成功，继续25整块押位', '押位流程')
            service = None
            timeout_time = None
        except ServiceError as e:
            if not _is_sold_out_error(e):
                return _return_partial_or_raise(e, passengers, held_services, '缓存航班先占1人')
            LOG.info(f'缓存航班先占1人失败，无可押座位，错误[{e.message}]', '押位流程')
            _cache_clean_service(service, timeout_time)
            raise e

    if not skip_full_chunk:
        LOG.info('开始25人整块循环押位', '押位流程')
        while True:
            try:
                if service is None:
                    service, timeout_time = _get_clean_service(sham_booking_data.ext)
                trip_passengers = _trip_passengers(service, sham_booking_data, journey, use_bundle, 25)
                _hold_service(held_services, service, trip_passengers, '25人整块trip')
                passengers.extend(trip_passengers)
                LOG.info(f'25人整块trip成功，累计人数[{len(passengers)}]', '押位流程')
                service = None
                timeout_time = None
            except ServiceError as e:
                if not _is_sold_out_error(e):
                    return _return_partial_or_raise(e, passengers, held_services, '25人整块trip')
                LOG.info(f'25人整块trip售完，进入尾数补位，错误[{e.message}]', '押位流程')
                last_error = e
                break

    for seat_number in _tail_seat_counts(tail_max_seat):
        try:
            if service is None:
                service, timeout_time = _get_clean_service(sham_booking_data.ext)
            trip_passengers = _trip_passengers(service, sham_booking_data, journey, use_bundle, seat_number)
            _hold_service(held_services, service, trip_passengers, f'尾数trip[{seat_number}]')
            passengers.extend(trip_passengers)
            LOG.info(f'尾数trip成功，人数[{seat_number}]，累计人数[{len(passengers)}]', '押位流程')
            service = None
            timeout_time = None
        except ServiceError as e:
            if not _is_sold_out_error(e):
                return _return_partial_or_raise(e, passengers, held_services, f'尾数trip[{seat_number}]')
            LOG.info(f'尾数trip售完，人数[{seat_number}]，继续下一档，错误[{e.message}]', '押位流程')
            last_error = e

    if service is not None and last_error is not None:
        _cache_clean_service(service, timeout_time)

    if not passengers:
        if last_error:
            raise last_error
        raise ServiceError(ServiceStateEnum.BOOKING_SEAT_FAILURE)
    LOG.info(
        f'押位结束，最终人数[{len(passengers)}]，成功session数[{len(held_services)}]',
        '押位流程'
    )
    return passengers, held_services


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self,
         sham_booking_data: RequestShamBookingTaskDataModel,
         response_order_data: ResponseOrderInfoModel):
    service = None
    dep_date = _search_date(sham_booking_data.dep_date)
    cache_key = _flight_cache_key(sham_booking_data, dep_date, sham_booking_data.cabin)
    request_cache_key = cache_key
    skip_flight_cache = not sham_booking_data.cabin
    cache_data = None if skip_flight_cache else REDIS.get_value(cache_key)
    if skip_flight_cache:
        LOG.info('未传入cabin，跳过航班缓存读写，强制实时查询航班', '航班缓存')
    if not cache_data:
        LOG.info(f'未命中航班缓存，key[{cache_key}]，开始实时查询航班', '航班缓存')
        service = WebService(proxy_info_from_ext(sham_booking_data.ext))
        service.initialize_html_session_booking()

        journey_list = service.availability(
            airport_data=[(
                sham_booking_data.dep_airport,
                sham_booking_data.arr_airport,
                dep_date,
            )],
            adult_count=1,
            child_count=0,
            currency=sham_booking_data.booking_config.currency_code,
        )
        journey_list = FlightUtil.number_filter(journey_list, sham_booking_data.flight_number)
        if len(journey_list) != 1:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)
        journey = journey_list[0]
        _verify_journey(journey, sham_booking_data, dep_date, '实时查询')
        use_bundle = _select_bundle(journey, sham_booking_data.cabin, sham_booking_data.ext)
        LOG.info(
            f"实时查询选中航班，航班[{sham_booking_data.flight_number}]，"
            f"舱位[{use_bundle.cabin}]，座位[{use_bundle.seat}]，套餐[{use_bundle.product_tag}]",
            '航班查询'
        )
        if use_bundle.seat == 0:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, sham_booking_data.cabin, use_bundle.cabin)
        cabin_cache_key = _flight_cache_key(sham_booking_data, dep_date, use_bundle.cabin)
        journey_cache_value = journey.model_dump_json(by_alias=True)
        if not skip_flight_cache:
            for key in {request_cache_key, cabin_cache_key}:
                REDIS.set_value_ex(key, journey_cache_value, 60 * 60 * 24)
                LOG.info(f'写入航班缓存，key[{key}]，ttl[86400]', '航班缓存')
    else:
        LOG.info(f'命中航班缓存，key[{cache_key}]，跳过实时查询航班', '航班缓存')
        data_array = cache_data.decode('utf-8').split("||")
        d = json.loads(data_array[0])
        journey = FlightJourneyModel.model_validate(d)
        if not _journey_match_request(journey, sham_booking_data, dep_date):
            LOG.error(
                f'航班缓存与任务参数不一致，删除缓存并实时查询，key[{cache_key}]，'
                f'任务日期[{dep_date}]，缓存{_journey_summary(journey)}',
                '航班缓存'
            )
            REDIS.delete_key(cache_key)
            service = WebService(proxy_info_from_ext(sham_booking_data.ext))
            service.initialize_html_session_booking()
            journey_list = service.availability(
                airport_data=[(
                    sham_booking_data.dep_airport,
                    sham_booking_data.arr_airport,
                    dep_date,
                )],
                adult_count=1,
                child_count=0,
                currency=sham_booking_data.booking_config.currency_code,
            )
            journey_list = FlightUtil.number_filter(journey_list, sham_booking_data.flight_number)
            if len(journey_list) != 1:
                raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)
            journey = journey_list[0]
            _verify_journey(journey, sham_booking_data, dep_date, '缓存失效后实时查询')
            cache_data = None
        use_bundle = _select_bundle(journey, sham_booking_data.cabin, sham_booking_data.ext)
        cache_source = '缓存失效后实时查询' if cache_data is None else '缓存航班'
        LOG.info(
            f"{cache_source}选中bundle，航班[{sham_booking_data.flight_number}]，"
            f"舱位[{use_bundle.cabin}]，缓存座位[{use_bundle.seat}]，套餐[{use_bundle.product_tag}]",
            '航班缓存'
        )
        if use_bundle.seat == 0:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, sham_booking_data.cabin, use_bundle.cabin)
        if cache_data is None:
            journey_cache_value = journey.model_dump_json(by_alias=True)
            cabin_cache_key = _flight_cache_key(sham_booking_data, dep_date, use_bundle.cabin)
            for key in {request_cache_key, cabin_cache_key}:
                REDIS.set_value_ex(key, journey_cache_value, 60 * 60 * 24)
                LOG.info(f'写入刷新后的航班缓存，key[{key}]，ttl[86400]', '航班缓存')

    passengers, held_services = _occupy_available_seats(
        sham_booking_data=sham_booking_data,
        journey=journey,
        use_bundle=use_bundle,
        service=service,
        trust_seat_count=not cache_data,
    )
    contact_info = ShamBookingUtil.build_sham_contact_info()
    contact_info.last_name = passengers[0].last_name
    contact_info.first_name = passengers[0].first_name

    # source_data = service.add_passenger(
    #     passengers=passengers,
    #     contact_info=contact_info,
    #     purchasing=True,
    # )
    # service.commit(passengers=passengers, source_data=source_data)
    # payment_response = service.init_payment()
    # LOG.info(f"init_payment响应长度: {len(payment_response)}")
    if cache_data and not skip_flight_cache:
        REDIS.up_expire(cache_key, 60 * 60 * 24)
        LOG.info(f'刷新航班缓存过期时间，key[{cache_key}]，ttl[86400]', '航班缓存')

    _verify_journey(journey, sham_booking_data, dep_date, '回调前')
    journey.bundles = [use_bundle]
    response_order_data.order_number = '111111'
    response_order_data.pnr = '111111'
    response_order_data.order_state = OrderStateEnum.HOLD
    response_order_data.journeys = [journey]
    response_order_data.passengers = passengers
    response_order_data.contact_info = contact_info
    response_order_data.currency_code = use_bundle.price_info.currency
    response_order_data.total_amount = (
            (use_bundle.price_info.adult_ticket_price + use_bundle.price_info.adult_tax_price)
            * len(passengers)
            or Decimal('0')
    )
    LOG.info(
        f"押位响应完成，pnr[{response_order_data.pnr}]，状态[{response_order_data.order_state.value}]，"
        f"人数[{len(passengers)}]，总价[{response_order_data.total_amount}]，币种[{response_order_data.currency_code}]，"
        f"成功session数[{len(held_services)}]",
        '任务结果'
    )

    return response_order_data


if __name__ == '__main__':
    for i in range(10000000000000000):

        main({
            "taskId": "e95ff47d4b5f43498b6f13caa5d7c3db",
            "taskType": "shamBooking",
            "source": "5JWEB",
            "taskData": {
                "depAirport": "CEB",
                "arrAirport": "HKG",
                "depDate": "20260630",
                "flightNumber": "5J236",
                "cabin": "PA",
                "bookingConfig": {
                    "bookRate": 10,
                    "currencyCode": "PHP"
                },
                "callbackData": {
                    "callData": "",
                    "callUrl": "http://trip-api.bjrakd.com/triplex-foreign-external/external/task/pressureback/seatNewCallback"
                }
            }
        })
        sleep(0.7)
