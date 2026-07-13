import re
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.order.payment_info_model import PaymentInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils.cardinalcommerce_util import CardinalcommerceUtil
from flights.sunphuquocairways_9g.config import Config
from flights.sunphuquocairways_9g.flight_common.web_flight_parser import WebFlightParser
from flights.sunphuquocairways_9g.flight_common.web_order_parser import WebOrderParser
from flights.sunphuquocairways_9g.script.web_script import WebScript


@dataclass
class BookingResult:
    pnr: str
    bundle: FlightBundleModel
    passengers: list[PassengerInfoModel]
    contact_info: ContactInfoModel
    total_amount: Decimal
    currency: str
    journey: Optional[FlightJourneyModel] = None
    flight_ids: dict[str, str] = field(default_factory=dict)
    contact_id: str = ""
    raw_order: dict = field(default_factory=dict)


class WebService:
    def __init__(
        self,
        proxy_info: Optional[ProxyInfoModel] = None,
        script=None,
        cardinal_factory=None,
    ):
        self._script = script or WebScript(proxy_info)
        self._proxy_info = proxy_info
        self._currency = ""
        self._cardinal_factory = cardinal_factory or CardinalcommerceUtil

    @property
    def script(self):
        return self._script

    @property
    def currency(self) -> str:
        return self._currency

    def initialize_session(self) -> None:
        self._script.initialize_session()

    def initialize(self, currency: str) -> None:
        normalized = str(currency or "VND").upper()
        if self._currency != normalized:
            self._script.authenticate(normalized)
            self._currency = normalized

    def search(
        self,
        dep_airport: str,
        arr_airport: str,
        dep_date: str,
        adt_number: int,
        chd_number: int,
        currency_code: str,
        ret_date: Optional[str] = None,
        promo_code: str = "",
    ) -> list[FlightJourneyModel]:
        self.initialize(currency_code)
        airport_data = [(dep_airport, arr_airport, dep_date)]
        if ret_date:
            airport_data.append((arr_airport, dep_airport, ret_date))
        response = self._script.search(
            airport_data=airport_data,
            adult_count=adt_number,
            child_count=chd_number,
            promo_code=promo_code,
        )
        journeys = WebFlightParser.parse(response, child_count=chd_number, promo_code=promo_code)
        if not journeys:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        return journeys

    def create_order(
        self,
        bundle: FlightBundleModel,
        passengers: list[PassengerInfoModel],
        contact_info: ContactInfoModel,
    ) -> BookingResult:
        if not bundle.fare_key:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "fare_key")
        if not passengers:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengers")
        cart_response = self._script.create_cart(bundle.fare_key.split("^"))
        cart = cart_response.get("data") or {}
        cart_id = str(cart.get("id") or "")
        cart_travelers = cart.get("travelers") or []
        if not cart_id:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart_id")
        if len(cart_travelers) != len(passengers):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart_travelers")

        assigned_ids = self._update_all_travelers(cart_id, cart_travelers, passengers)
        contacts = self._build_contacts(contact_info, assigned_ids)
        self._script.add_contacts(cart_id, contacts, passengers[0].last_name)

        order_response = self._script.purchase_order(cart_id)
        order = self._first_order(order_response)
        pnr = str(order.get("id") or "")
        if not pnr:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "pnr")
        self._write_order_traveler_ids(passengers, order.get("travelers") or [])
        total_amount, currency = self._order_amount(order_response, order, bundle)
        flight_ids = self._flight_ids(order_response)
        contact_id = next(
            (
                str(item.get("id") or "")
                for item in order.get("contacts") or []
                if item.get("contactType") == "Email"
            ),
            "",
        )
        return BookingResult(
            pnr=pnr,
            bundle=bundle,
            passengers=passengers,
            contact_info=contact_info,
            total_amount=total_amount,
            currency=currency,
            flight_ids=flight_ids,
            contact_id=contact_id,
            raw_order=order_response,
        )

    def add_requested_baggage(
        self,
        pnr: str,
        passengers: list[PassengerInfoModel],
        last_name: str,
    ) -> dict | None:
        requested = []
        missing_codes = False
        for passenger in passengers:
            traveler_id = str((passenger.ext or {}).get("travelerId") or passenger.key or "")
            bags = passenger.buy_baggage or (passenger.ssr.baggage if passenger.ssr else [])
            for bag in bags:
                if bag.type.name != "HAULING_BAGGAGE" or bag.number <= 0:
                    continue
                missing_codes = missing_codes or not bool(bag.code)
                requested.append((traveler_id, bag))
        if not requested:
            return None
        if any(not traveler_id for traveler_id, _ in requested):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "traveler_id")
        available = self._available_baggage(pnr, last_name) if missing_codes else []
        merged = {}
        for traveler_id, bag in requested:
            service_id = bag.code or self._match_baggage_service(available, bag.weight)
            if not service_id:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"未匹配到{bag.weight}KG行李")
            key = (service_id, traveler_id)
            merged[key] = merged.get(key, 0) + bag.number
        services = [
            {
                "serviceId": service_id,
                "travelerId": traveler_id,
                "quantity": quantity,
                "parameters": [],
            }
            for (service_id, traveler_id), quantity in merged.items()
        ]
        return self._script.add_services(pnr, last_name, services)

    def order_detail(self, pnr: str, last_name: str, currency_code: str = "VND") -> ResponseOrderInfoModel:
        self.initialize(currency_code)
        itinerary = self._script.get_itinerary(pnr, last_name)
        baggage = self._script.get_baggage(pnr, last_name)
        return WebOrderParser.parse(itinerary, baggage)

    def pay_order(
        self,
        pnr: str,
        passengers: list[PassengerInfoModel],
        contact_info: ContactInfoModel,
        payment_info: PaymentInfoModel,
    ) -> ResponseOrderInfoModel:
        vendor = self._card_vendor(payment_info.card_type)
        if not passengers:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengers")
        expiry = str(payment_info.card_expiry_date or "").split("/")
        if len(expiry) != 2 or not all(expiry):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "card_expiry_date")
        exp_month, exp_year = expiry
        last_name = passengers[0].last_name

        methods = self._script.payment_methods(pnr, last_name)
        methods_data = methods.get("data") or {}
        available = methods_data.get("availablePaymentMethods") or []
        pp_id = next(
            (
                str(item.get("id") or "")
                for item in available
                if item.get("paymentType") == "CheckoutFormPayment"
            ),
            "",
        )
        if not pp_id:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)

        self._script.payment_action({"PPID": pp_id, "action": "load"})
        base_mopdata = {
            "pan": re.sub(r"[\s-]+", "", payment_info.card_number),
            "CVV": payment_info.card_cvv,
            "holdername": payment_info.card_holder_name.replace("/", " ").strip(),
            "expmonth": exp_month,
            "expyear": exp_year,
            "vendor": vendor,
            "contact": {
                "email": contact_info.email_address,
                "phone": f"{contact_info.phone_code} {contact_info.phone_number}",
            },
        }
        init_response = self._script.payment_action(
            {
                "PPID": pp_id,
                "data": {"mopid": "creditcard", "mopdata": base_mopdata.copy(), "tid": "0"},
                "action": "tdsinit",
            }
        )
        jwt = str(init_response.get("jwt") or "")
        if not jwt:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "3ds_jwt")

        cardinal = self._cardinal_factory(
            proxy_str=self._proxy_string(),
            agent=Config.USER_AGENT,
        )
        cardinal.cardinaltrusted_init_jwt(jwt=jwt, user_agent=Config.USER_AGENT)
        reference_id = f"1_{uuid.uuid4()}"
        render_url = (
            "https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/Render"
            "?threatmetrix=true&alias=Default&orgUnitId=68c40c6ae7d0b603289e8086"
            "&tmEventType=PAYMENT"
            f"&referenceId={urllib.parse.quote(reference_id)}"
            "&geolocation=false&origin=Songbird"
        )
        features = cardinal.render_post(
            render_url,
            urllib.parse.urlencode(
                {"nonce": str(uuid.uuid4()), "bin": base_mopdata["pan"][:6]}
            ),
        )
        fingerprint_reference = str(features.get("referenceId") or reference_id)
        nonce = str(features.get("nonce") or "")
        org_unit_id = str(features.get("orgUnitId") or "")
        if not nonce or not org_unit_id:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "3ds_fingerprint")
        cardinal.cardinalcommerce_save_browser_data(
            nonce=nonce,
            reference_id=fingerprint_reference,
            org_unit_id=org_unit_id,
            user_agent=Config.USER_AGENT,
            referrer="https://centinelapi.cardinalcommerce.com/",
        )

        base_mopdata["tdsSessionId"] = fingerprint_reference
        add_response = self._script.payment_action(
            {
                "PPID": pp_id,
                "data": {"mopid": "creditcard", "mopdata": base_mopdata},
                "action": "add",
            }
        )
        action_token = str(add_response.get("actionToken") or "")
        if not action_token:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)
        self._script.payment_records(
            pnr,
            last_name,
            {
                "paymentRequests": [
                    {
                        "paymentMethod": {
                            "paymentType": "CheckoutFormPayment",
                            "id": pp_id,
                            "actionToken": action_token,
                        }
                    }
                ]
            },
        )

        for attempt in range(5):
            order = WebOrderParser.parse(self._script.get_itinerary(pnr, last_name))
            if order.order_state == OrderStateEnum.OPEN_FOR_USE and order.passengers and all(
                passenger.ticket_number for passenger in order.passengers
            ):
                return order
            if attempt < 4:
                time.sleep(5)
        raise ServiceError(ServiceStateEnum.ORDER_STATE_CHECK_LIMIT)

    def _update_all_travelers(
        self,
        cart_id: str,
        cart_travelers: list[dict],
        passengers: list[PassengerInfoModel],
    ) -> list[str]:
        unused = list(cart_travelers)
        assigned_ids = []
        for passenger in passengers:
            matching = next(
                (
                    item
                    for item in unused
                    if str(item.get("passengerTypeCode") or "") == passenger.type.value
                ),
                None,
            )
            if not matching:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "traveler_type")
            unused.remove(matching)
            traveler_id = str(matching.get("id") or "")
            if not traveler_id:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "traveler_id")
            self._script.update_traveler(
                cart_id,
                traveler_id,
                self._build_traveler(traveler_id, passenger),
                passengers[0].last_name,
            )
            assigned_ids.append(traveler_id)
        return assigned_ids

    @classmethod
    def _build_traveler(cls, traveler_id: str, passenger: PassengerInfoModel) -> dict:
        return {
            "id": traveler_id,
            "passengerTypeCode": passenger.type.value,
            "names": [
                {
                    "title": cls._title(passenger),
                    "firstName": passenger.first_name,
                    "middleName": "",
                    "lastName": passenger.last_name,
                }
            ],
            "nationalityCountryCodes": [],
            "dateOfBirth": passenger.birthday,
        }

    @staticmethod
    def _build_contacts(contact: ContactInfoModel, traveler_ids: list[str]) -> list[dict]:
        phone_code = contact.phone_code if contact.phone_code.startswith("+") else f"+{contact.phone_code}"
        return [
            {
                "id": "",
                "travelerIds": [],
                "category": "personal",
                "contactType": "Email",
                "purpose": "standard",
                "address": contact.email_address,
                "lang": "en",
            },
            {
                "id": "",
                "travelerIds": traveler_ids,
                "category": "personal",
                "contactType": "Email",
                "purpose": "notification",
                "address": contact.email_address,
                "lang": "en",
            },
            {
                "id": "",
                "travelerIds": [],
                "category": "personal",
                "contactType": "Phone",
                "purpose": "standard",
                "deviceType": "mobile",
                "countryPhoneExtension": phone_code,
                "number": contact.phone_number,
                "lang": "en",
            },
            {
                "id": "",
                "travelerIds": traveler_ids,
                "category": "personal",
                "contactType": "Phone",
                "purpose": "notification",
                "deviceType": "mobile",
                "countryPhoneExtension": phone_code,
                "number": contact.phone_number,
                "lang": "en",
            },
        ]

    @staticmethod
    def _title(passenger: PassengerInfoModel) -> str:
        if passenger.type == PassengerTypeEnum.ADT:
            return "MRS" if passenger.gender == GenderEnum.F else "MR"
        return "MISS" if passenger.gender == GenderEnum.F else "MSTR"

    @staticmethod
    def _first_order(response: dict) -> dict:
        data = response.get("data")
        if isinstance(data, list):
            return data[0] if data else {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _write_order_traveler_ids(passengers: list[PassengerInfoModel], order_travelers: list[dict]) -> None:
        by_name = {}
        for traveler in order_travelers:
            name = (traveler.get("names") or [{}])[0]
            by_name[(str(name.get("lastName") or "").upper(), str(name.get("firstName") or "").upper())] = str(
                traveler.get("id") or ""
            )
        for passenger in passengers:
            traveler_id = by_name.get((passenger.last_name.upper(), passenger.first_name.upper()))
            if not traveler_id:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "order_traveler_id")
            passenger.key = traveler_id
            passenger.ext = {**(passenger.ext or {}), "travelerId": traveler_id}

    @staticmethod
    def _order_amount(
        response: dict,
        order: dict,
        bundle: FlightBundleModel,
    ) -> tuple[Decimal, str]:
        amount = order.get("remainingAmount") or order.get("totalAmount") or {}
        currency = str(amount.get("currencyCode") or bundle.price_info.currency)
        value = amount.get("value")
        if value is None:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "order_amount")
        decimal_places = int(
            (((response.get("dictionaries") or {}).get("currency") or {}).get(currency) or {}).get(
                "decimalPlaces", 0
            )
        )
        return Decimal(str(value)) / (Decimal(10) ** decimal_places), currency

    @staticmethod
    def _flight_ids(response: dict) -> dict[str, str]:
        result = {}
        for flight_id, flight in ((response.get("dictionaries") or {}).get("flight") or {}).items():
            carrier = str(flight.get("marketingAirlineCode") or "9G")
            number = str(flight.get("marketingFlightNumber") or "").zfill(4)
            result[f"{carrier}{number}"] = str(flight_id)
        return result

    def _available_baggage(self, pnr: str, last_name: str) -> list[dict]:
        response = self._script.services_by_order(pnr, last_name)
        data = response.get("data") or []
        if isinstance(data, list):
            return (data[0].get("services") or []) if data else []
        return data.get("services") or []

    @staticmethod
    def _match_baggage_service(services: list[dict], weight: int) -> str:
        for service in services:
            description = " ".join(
                str(item.get("content") or "") for item in service.get("descriptions") or []
            )
            match = re.search(r"(\d+(?:\.\d+)?)\s*KG", description, re.IGNORECASE)
            if match and int(Decimal(match.group(1))) == int(weight):
                return str(service.get("id") or "")
        return ""

    @staticmethod
    def _card_vendor(card_type: str) -> str:
        normalized = str(card_type or "").upper()
        if normalized in {"VI", "VISA"}:
            return "visa"
        if normalized in {"CA", "MC", "MASTERCARD"}:
            return "mastercard"
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"不支持的卡类型[{card_type}]")

    def _proxy_string(self) -> str | None:
        if not self._proxy_info:
            return None
        return self._proxy_info.get_proxy_info_to_string()
