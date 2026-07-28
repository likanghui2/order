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
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.sham_booking_util import ShamBookingUtil
from flights.malaysiaairlines_mh.service.web_service import WebService
from task.MHweb import session_cache
from task.MHweb.utils import web_date


CELERY_APP = celery_util.create(
    GlobalVariable.RABBITMQ_USERNAME,
    GlobalVariable.RABBITMQ_PASSWORD,
)
LOG = log_util.LogUtil("malaysiaAirlinesWebShamBooking")
MAX_PASSENGER_COUNT = 9


def _promo_code(ext: dict) -> str:
    value = (ext or {}).get("privateCode") or (ext or {}).get("promoCode") or ""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def _find_journey(
    journeys: list[FlightJourneyModel],
    flight_number: str,
) -> FlightJourneyModel:
    normalized_target = str(flight_number or "").replace("$", ",")
    matches = [
        journey
        for journey in journeys
        if ",".join(segment.flight_number for segment in journey.segments)
        == normalized_target
    ]
    if len(matches) != 1:
        raise ServiceError(
            ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER,
            flight_number,
        )
    return matches[0]


def _select_bundle(
    journey: FlightJourneyModel,
    cabin: Optional[str],
    product_tag: Optional[str],
) -> FlightBundleModel:
    bundles = list(journey.bundles or [])
    if cabin:
        bundles = [
            bundle
            for bundle in bundles
            if cabin == bundle.cabin or cabin in str(bundle.cabin or "").split("|")
        ]
        if not bundles:
            current_cabins = "|".join(
                str(bundle.cabin or "") for bundle in journey.bundles or []
            )
            raise ServiceError(
                ServiceStateEnum.NO_AVAILABLE_CABIN,
                cabin,
                current_cabins,
            )
    if product_tag:
        bundles = [
            bundle
            for bundle in bundles
            if bundle.product_tag == product_tag
        ]
    if not bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    return bundles[0]


def _passenger_count(request: RequestShamBookingTaskDataModel, available: int) -> int:
    available = int(available or 0)
    if available <= 0:
        raise ServiceError(
            ServiceStateEnum.NO_AVAILABLE_CABIN,
            request.cabin or "",
            request.cabin or "",
        )
    ext = request.ext or {}
    requested = ext.get("passengerCount", 1)
    try:
        requested = int(requested)
    except (TypeError, ValueError):
        requested = 1
    return min(max(1, requested), available, MAX_PASSENGER_COUNT)


def _search_target(
    service: WebService,
    request: RequestShamBookingTaskDataModel,
    routes: list[tuple[str, str, str]],
    promo_code: str,
    adult_count: int,
) -> tuple[FlightJourneyModel, FlightBundleModel]:
    service.prepare_search(routes, adult_count, 0, promo_code)
    service.initialization(request.booking_config.currency_code)
    journey = _find_journey(
        service.search(
            airport_data=routes,
            adult_count=adult_count,
            child_count=0,
            promo_code=promo_code,
        ),
        request.flight_number,
    )
    product_tag = (request.ext or {}).get("productTag")
    return journey, _select_bundle(journey, request.cabin, product_tag)


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(
    self,
    sham_booking_data: RequestShamBookingTaskDataModel,
    response_order_data: ResponseOrderInfoModel,
):
    cached = session_cache.CACHE.get_data()
    service = cached["value"] if cached is not None else None
    if service is None:
        LOG.info("未命中MH搜索会话缓存，初始化新会话")
        service = WebService(proxy_info_from_ext(sham_booking_data.ext))
        service.initialize_session()
        service.initialize_security()
    else:
        LOG.info(f"复用MH搜索会话，缓存过期时间[{cached['timeOut']}]")

    routes = [(
        sham_booking_data.dep_airport,
        sham_booking_data.arr_airport,
        web_date(sham_booking_data.dep_date),
    )]
    promo_code = _promo_code(sham_booking_data.ext or {})

    try:
        _, initial_bundle = _search_target(
            service,
            sham_booking_data,
            routes,
            promo_code,
            1,
        )
        passenger_count = _passenger_count(
            sham_booking_data,
            initial_bundle.seat,
        )
        journey, bundle = _search_target(
            service,
            sham_booking_data,
            routes,
            promo_code,
            passenger_count,
        )
        if bundle.seat < passenger_count:
            raise ServiceError(
                ServiceStateEnum.NO_AVAILABLE_CABIN,
                sham_booking_data.cabin or "",
                bundle.cabin or "",
            )
    except ServiceError as error:
        if session_cache.can_reuse_service(error):
            session_cache.cache_service(service, cached)
        raise

    LOG.info("MH航班/套餐/舱位校验通过，进入生单链路，会话不再回收缓存")

    passengers = ShamBookingUtil.build_sham_passenger_info(
        passenger_count,
        True,
    )
    contact = ShamBookingUtil.build_sham_contact_info()
    contact.last_name = passengers[0].last_name
    contact.first_name = passengers[0].first_name
    contact.phone_code = str((sham_booking_data.ext or {}).get("mobileCountryCode") or "60")
    contact.email_address = (
        f"{contact.email_address.split('@')[0]}@gmail.com".lower()
    )

    cart = service.select_flight(bundle)
    cart = service.add_passengers(passengers, cart, contact)
    order_response = service.purchase_order(cart, passengers)
    order = (order_response.get("data") or [{}])[0]
    pnr = str(order.get("id") or "")
    if not pnr:
        raise ServiceError(
            ServiceStateEnum.DATA_VALIDATION_FAILED,
            "pnr",
        )
    total_amount, currency = service.order_total(order_response)
    if not currency:
        currency = bundle.price_info.currency
    if total_amount <= Decimal(0):
        total_amount = (
            bundle.price_info.adult_ticket_price
            + bundle.price_info.adult_tax_price
        ) * passenger_count

    journey.bundles = [bundle]
    response_order_data.order_number = pnr
    response_order_data.pnr = pnr
    response_order_data.order_state = OrderStateEnum.HOLD
    response_order_data.journeys = [journey]
    response_order_data.passengers = passengers
    response_order_data.contact_info = contact
    response_order_data.total_amount = total_amount
    response_order_data.currency_code = currency
    return response_order_data


if __name__ == "__main__":
    for i in range(10):

        print(main({
        "taskId": "mhweb-local-sham-booking",
        "source": "MHWEB",
        "taskType": "shamBooking",
        "taskData": {
            "depAirport": "KUL",
            "arrAirport": "BKI",
            "depDate": "20260901",
            "flightNumber": "MH26121",
            "cabin": "",
            "bookingConfig": {
                "bookRate": 10,
                "currencyCode": "MYR",
            },
            "ext": {"passengerCount": 1,
                "proxy": {
                    "source": "VJWEB",
                    "host": "proxy.iproyal.net",
                    "port": 9000,
                    "username": "rakdvjweb01",
                    "password": "rakdvjvj01",
                    "region": "sg",
                    "sessId": None,
                    "sessionTime": 10,
                    "format": "http://client-{username}_area-{region}_session-{sessId}_life-{sessionTime}:{password}@{host}:{port}"

            }},
        },
    }))
