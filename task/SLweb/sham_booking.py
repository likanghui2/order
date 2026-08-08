from decimal import Decimal
from typing import Optional

from faker import Faker

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.payment_info_model import PaymentInfoModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util
from common.utils.date_util import DateUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.sham_booking_util import ShamBookingUtil
from flights.lionairthai.config_v2 import LionairthaiConfigV2
from flights.lionairthai.service.web_service_v2 import WebServiceV2


CELERY_APP = celery_util.create(
    GlobalVariable.RABBITMQ_USERNAME,
    GlobalVariable.RABBITMQ_PASSWORD,
)
LOG = log_util.LogUtil("lionairthaiWebShamBooking")
MAX_PASSENGERS_PER_ORDER = 9


def _normalize_flight_number(value: str) -> str:
    value = str(value or "").replace(" ", "").upper()
    if len(value) <= 2:
        return value
    return f"{value[:2]}{value[2:].lstrip('0') or '0'}"


def _target_journey(journeys: list[FlightJourneyModel], flight_number: str) -> FlightJourneyModel:
    target = ",".join(
        _normalize_flight_number(value)
        for value in str(flight_number or "").replace("$", ",").split(",")
    )
    matches = [
        journey for journey in journeys
        if ",".join(_normalize_flight_number(segment.flight_number) for segment in journey.segments)
        == target
    ]
    if len(matches) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, flight_number)
    return matches[0]


def _select_bundle(journey: FlightJourneyModel, cabin: Optional[str],
                   product_tag: Optional[str]) -> FlightBundleModel:
    bundles = list(journey.bundles or [])
    if product_tag:
        bundles = [bundle for bundle in bundles if bundle.product_tag == product_tag]
    if not bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    if cabin:
        cabin_bundles = [
            bundle for bundle in bundles
            if cabin in str(bundle.cabin or "").replace("^", "|").split("|")
        ]
        if not cabin_bundles:
            current = "|".join(str(bundle.cabin or "") for bundle in bundles)
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, cabin, current)
        bundles = cabin_bundles
    return bundles[0]


def _passenger_count(ext: dict) -> int:
    value = ext.get("passengerCount", 1)
    if isinstance(value, bool):
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengerCount")
    if isinstance(value, str):
        value = value.strip()
        if not value.isascii() or not value.isdigit():
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengerCount")
        count = int(value)
    elif type(value) is int:
        count = value
    else:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengerCount")
    if not 1 <= count <= MAX_PASSENGERS_PER_ORDER:
        raise ServiceError(
            ServiceStateEnum.BUSINESS_ERROR,
            f"SL压位人数必须在1-{MAX_PASSENGERS_PER_ORDER}之间",
        )
    return count


def _payment_info(cardholder: str) -> PaymentInfoModel:
    fake = Faker(locale="en_US")
    return PaymentInfoModel(
        type="NO_PAY",
        cardNumber=fake.credit_card_number(card_type="visa"),
        cardExpiryDate=fake.credit_card_expire(
            start="now",
            end="+4y",
            date_format="%m/%y",
        ),
        cardHolderName=cardholder,
        cardType="VI",
        cardCVV=fake.credit_card_security_code(card_type="visa"),
    )


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, sham_booking_data: RequestShamBookingTaskDataModel,
         response_order_data: ResponseOrderInfoModel):
    request = sham_booking_data
    response = response_order_data
    ext = request.ext or {}
    proxy = proxy_info_from_ext(ext)
    requested_count = _passenger_count(ext)
    product_tag = str(ext.get("productTag") or "").strip() or None
    private_code = ext.get("privateCode") or []
    if isinstance(private_code, str):
        private_code = [private_code] if private_code else []
    promo_code = str(private_code[0]) if private_code else ""
    dep_date = DateUtil.string_to_target_format(request.dep_date, "%Y-%m-%d")
    currency = request.booking_config.currency_code

    service = WebServiceV2(proxy)
    journey = _target_journey(
        service.search(
            request.dep_airport, request.arr_airport, dep_date,
            requested_count, 0, currency, promo_code,
        ),
        request.flight_number,
    )
    bundle = _select_bundle(journey, request.cabin, product_tag)
    LOG.info(
        f"SL压位，航班[{request.flight_number}]，舱位[{bundle.cabin}]，"
        f"套餐[{bundle.product_tag}]，余座[{bundle.seat}]",
        "压位流程",
    )
    international = (
        LionairthaiConfigV2.airport_country(request.dep_airport)
        != LionairthaiConfigV2.airport_country(request.arr_airport)
    )
    passengers = ShamBookingUtil.build_sham_passenger_info(
        requested_count,
        international or bool(ext.get("usePassport", True)),
    )
    contact = ShamBookingUtil.build_sham_contact_info()
    contact.last_name = passengers[0].last_name
    contact.first_name = passengers[0].first_name
    contact.phone_code = "66"
    contact.email_address = f"{contact.email_address.split('@')[0]}@gmail.com".lower()

    LOG.info(
        f"SL压位，航班[{request.flight_number}]，舱位[{bundle.cabin}]，"
        f"套餐[{bundle.product_tag}]，人数[{requested_count}]",
        "压位流程",
    )
    service.add_cart(bundle, requested_count)
    service.validate_cart(service.get_cart(), bundle, requested_count, journey)
    service.add_passengers(passengers, contact, international)
    booking_cart = service.get_booking_cart()
    service.validate_cart(booking_cart, bundle, requested_count, journey)
    decline_payment = _payment_info(passengers[0].get_passenger_name())
    pnr, payment_response = service.failed_payment_pnr(
        decline_payment,
        contact,
        passengers[0],
        bundle.price_info.currency,
    )
    if not pnr:
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "SL压位未生成PNR")

    journey.bundles = [bundle]
    response.order_number = pnr
    response.pnr = pnr
    response.order_state = OrderStateEnum.HOLD
    response.journeys = [journey]
    response.passengers = passengers
    response.contact_info = contact
    response.total_amount = Decimal(str(booking_cart["totalCost"]))
    response.currency_code = bundle.price_info.currency
    LOG.info(
        f"SL压位成功，人数[{requested_count}]，"
        f"失败支付原因[{payment_response.get('message') or ''}]",
        "压位结果",
    )
    return response


if __name__ == "__main__":
    print(main({
        "taskId": "slweb-local-sham-booking",
        "source": "SLWEB",
        "taskType": "shamBooking",
        "taskData": {
            "depAirport": "DMK",
            "arrAirport": "UBP",
            "depDate": "20261203",
            "flightNumber": "SL0620",
            "cabin": "",
            "bookingConfig": {
                "bookRate": 10,
                "currencyCode": "THB",
            },
            "ext": {
                "passengerCount": 5,
                "usePassport": True,
                "proxy": {
                    "source": "SLWEB",
                    "host": "proxy.iproyal.net",
                    "port": 9000,
                    "username": "rakdvjweb01",
                    "password": "rakdvjvj01",
                    "region": "sg",
                    "sessId": None,
                    "sessionTime": 10,
                    "format": (
                        "http://client-{username}_area-{region}_session-"
                        "{sessId}_life-{sessionTime}:{password}@{host}:{port}"
                    ),
                },
            },
        },
    }))
