import copy
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import log_util
from flights.vietjet.config import Config
from flights.vietjet.flight_common.vz_web_flight_parse import VZWebFlightParser
from flights.vietjet.script.vz_web_script import VZWebScript


class VZWebService:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__script = VZWebScript(proxy_info=proxy_info)
        self.__log = log_util.LogUtil("vzWebService")
        self.__last_search_context = None

    def initialize_session(self):
        self.__script.initialize_session()

    def initialize_csrf_token(self):
        return self.__script.initialize_csrf_token()

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               infant_count: int,
               currency_code: str,
               ret_date: Optional[str] = None):
        trip_type = "roundtrip" if ret_date else "onewaytrip"
        site_dep_date = self._site_date(dep_date)
        site_ret_date = self._site_date(ret_date) if ret_date else site_dep_date
        currency = (currency_code or "THB").lower()
        search_data = {
            "tripType": trip_type,
            "from_where": dep_airport,
            "to_where": arr_airport,
            "start": site_dep_date,
            "end": site_ret_date,
            "adultCount": str(adt_number),
            "childCount": str(chd_number),
            "infantCount": str(infant_count or 0),
            "promoCode": "",
            "currency": currency,
        }
        response = self.__script.search_flight(search_data)
        context = {
            "dep_airport": dep_airport,
            "arr_airport": arr_airport,
            "dep_date": site_dep_date,
            "ret_date": "" if not ret_date else site_ret_date,
            "trip_type": trip_type,
            "adult_count": adt_number,
            "child_count": chd_number,
            "infant_count": infant_count or 0,
            "currency": currency,
        }
        journeys = VZWebFlightParser.journey_info_parser(response)
        for journey in journeys:
            journey.ext["search_context"] = context
            for bundle in journey.bundles:
                bundle.ext["search_context"] = context
        self.__last_search_context = context
        return journeys

    def booking(self,
                journey: FlightJourneyModel,
                passenger_infos: List[PassengerInfoModel],
                use_bundle: FlightBundleModel,
                response_order_data: ResponseOrderInfoModel,
                contact_info: ContactInfoModel,
                need_pay: bool = False, is_today: bool = False):
        journey_raw = copy.deepcopy((journey.ext or {}).get("raw") or {})
        fare_raw = copy.deepcopy((use_bundle.ext or {}).get("raw") or {})
        search_context = (
            (use_bundle.ext or {}).get("search_context")
            or (journey.ext or {}).get("search_context")
            or self.__last_search_context
        )
        referer = self._flight_referer(search_context)
        add_to_cart_payload = VZWebScript.add_to_cart_payload(journey_raw, fare_raw, search_context)
        add_to_cart_response = self.__script.add_to_cart(add_to_cart_payload, referer)
        booking_code = add_to_cart_response["booking_code"]

        passenger_page = self.__script.passenger_page(booking_code, referer)
        self.__script.check_status(booking_code, "passenger")
        self.__script.get_countries(booking_code)
        self.__script.get_ssr(booking_code)
        quotation_payload = self._quotation_payload(
            booking_code=booking_code,
            passenger_page=passenger_page,
            passenger_infos=passenger_infos,
            contact_info=contact_info,
        )
        quotation_response = self.__script.quotation(quotation_payload, booking_code)

        self.__script.checkout_page(booking_code)
        self.__script.do_checkout(booking_code)
        payment_page = self.__script.payment_page(booking_code)
        payment_method, funcoin_config = VZWebScript().later_parse_payment_data(html=payment_page, is_today=is_today)
        self.__script.check_payment_fee(
            booking_code=booking_code,
            payment_method=payment_method,
            funcoin_limit=funcoin_config.get("funcoin_limit", 0),
        )
        recaptcha_token = self.__script.get_recaptcha_token()
        self.__script.do_payment(booking_code, recaptcha_token, funcoin_config, payment_group=payment_method['group'])
        booking_detail = self.__script.booking_detail_page(booking_code)
        pnr = VZWebScript.parse_reservation_code(booking_detail) or booking_code

        total_amount = Decimal(str(quotation_response.get("quotationAmount") or quotation_response.get("total") or 0))
        self._fill_response_order(response_order_data, passenger_infos, journey, use_bundle, contact_info, total_amount)
        response_order_data.pnr = pnr
        response_order_data.order_state = OrderStateEnum.HOLD if not need_pay else OrderStateEnum.OPEN_FOR_USE

        return {"reservation": {"locator": pnr, "bookingCode": booking_code}}, quotation_response

    @staticmethod
    def _fill_response_order(response_order_data: ResponseOrderInfoModel,
                             passenger_infos: List[PassengerInfoModel],
                             journey: FlightJourneyModel,
                             use_bundle: FlightBundleModel,
                             contact_info: ContactInfoModel,
                             total_amount: Decimal):
        response_order_data.order_number = ""
        response_order_data.passengers = passenger_infos
        response_order_data.currency_code = use_bundle.price_info.currency
        response_order_data.contact_info = contact_info
        response_order_data.journeys = [copy.deepcopy(journey)]
        response_order_data.journeys[0].bundles = [use_bundle]
        response_order_data.total_amount = total_amount

    @classmethod
    def _quotation_payload(cls,
                           booking_code: str,
                           passenger_page: str,
                           passenger_infos: List[PassengerInfoModel],
                           contact_info: ContactInfoModel):
        security_names = VZWebScript.parse_form_security_names(passenger_page)
        payload = [
            ("code", booking_code),
            ("first_name", contact_info.first_name),
            ("last_name", contact_info.last_name),
            ("country", cls._country_from_phone(contact_info.phone_code)),
            ("area_code", f"+{contact_info.phone_code}"),
            ("phone", contact_info.phone_number),
            ("email", contact_info.email_address),
        ]

        for passenger in passenger_infos:
            if passenger.type == PassengerTypeEnum.CHD:
                prefix = "pax_child"
            else:
                prefix = "pax_adult"
            payload.extend([
                (f"{prefix}_id[]", ""),
                (f"{prefix}_funid[]", ""),
                (f"{prefix}_gender[]", cls._gender_value(passenger.gender)),
                (f"{prefix}_first_name[]", passenger.first_name),
                (f"{prefix}_last_name[]", passenger.last_name),
                (f"{prefix}_dob[]", cls._birth_date(passenger.birthday)),
                (f"{prefix}_nationality[]", cls._nationality(passenger)),
            ])

        if security_names:
            payload.append((security_names[0], cls._client_fingerprint()))
        if len(security_names) > 1:
            payload.append((security_names[1], cls._client_interaction()))
        payload.extend([
            ("client_interaction_inf", ""),
            ("g-recaptcha-response", ""),
            ("applyVoucher", "false"),
            ("serial", ""),
            ("pin", ""),
            ("password", ""),
        ])

        for index, passenger in enumerate(passenger_infos):
            payload.append((f"free_services[{index}][]", ""))
            payload.extend(cls._paxes_inf(index, passenger))
            payload.extend(cls._selected_addon_inf(index))
            payload.extend(cls._selected_other_services(index))

        return payload

    @classmethod
    def _paxes_inf(cls, index: int, passenger: PassengerInfoModel):
        fields = [
            (f"paxes_inf[{index}][ancillary][0][Baggage]", "Baggage"),
            (f"paxes_inf[{index}][ancillary][0][Cabin Baggage]", "Cabin Baggage"),
            (f"paxes_inf[{index}][ancillary][0][Meal]", "Meal"),
            (f"paxes_inf[{index}][ancillary][0][Priority]", "Priority"),
            (f"paxes_inf[{index}][ancillary][0][Special Service]", "Special Service"),
            (f"paxes_inf[{index}][type]", "child" if passenger.type == PassengerTypeEnum.CHD else "adult"),
            (f"paxes_inf[{index}][first_name]", passenger.first_name),
            (f"paxes_inf[{index}][last_name]", passenger.last_name),
            (f"paxes_inf[{index}][gender]", cls._gender_value(passenger.gender)),
            (f"paxes_inf[{index}][dob]", cls._birth_date(passenger.birthday)),
            (f"paxes_inf[{index}][passport]", ""),
            (f"paxes_inf[{index}][nationality]", cls._nationality(passenger)),
            (f"paxes_inf[{index}][funid]", ""),
        ]
        return fields

    @staticmethod
    def _selected_addon_inf(index: int):
        addons = [
            ("Seat", "Seat", 0),
            ("Baggages", "Baggage", 0),
            ("Cabin Baggage", "Cabin Baggage", 0),
            ("Hot meals", "Meal", 0),
            ("Priority Checkin", "Priority", 0),
            ("Vip Lounge", "Vip Lounge", 0),
            ("Special Service", "Special Service", 0),
            ("VAT", "tax", 1),
        ]
        fields = []
        for addon_index, (title, key, quantity) in enumerate(addons):
            prefix = f"selected_addon_inf[{index}][{addon_index}]"
            fields.extend([
                (f"{prefix}[title]", title),
                (f"{prefix}[key]", key),
                (f"{prefix}[totalAmount]", 0),
                (f"{prefix}[baseAmount]", 0),
                (f"{prefix}[taxAmount]", 0),
                (f"{prefix}[quantity]", quantity),
            ])
        return fields

    @staticmethod
    def _selected_other_services(index: int):
        services = [
            ("Travel Insurance", "Insurance"),
            ("Ferry Adult", "FerryAdult"),
            ("Ferry Child", "FerryChild"),
        ]
        fields = []
        for service_index, (title, key) in enumerate(services):
            prefix = f"selected_other_services[{index}][{service_index}]"
            fields.extend([
                (f"{prefix}[provider]", ""),
                (f"{prefix}[title]", title),
                (f"{prefix}[key]", key),
                (f"{prefix}[totalAmount]", 0),
                (f"{prefix}[baseAmount]", 0),
                (f"{prefix}[taxAmount]", 0),
                (f"{prefix}[quantity]", 0),
            ])
        return fields

    @staticmethod
    def _flight_referer(search_context: dict):
        params = {
            "tripType": search_context["trip_type"],
            "currency": search_context["currency"],
            "from_where": search_context["dep_airport"],
            "to_where": search_context["arr_airport"],
            "start": search_context["dep_date"],
            "end": search_context["ret_date"] or search_context["dep_date"],
            "adultCount": search_context["adult_count"],
            "childCount": search_context["child_count"],
            "infantCount": search_context["infant_count"],
            "promoCode": "",
            "findLowestFare": "",
        }
        from urllib.parse import urlencode
        return f"{VZWebScript.BASE_URL}/flight?{urlencode(params)}"

    @staticmethod
    def _site_date(value: str):
        if not value:
            return ""
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return value

    @staticmethod
    def _birth_date(value: str):
        if not value:
            return ""
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return value

    @staticmethod
    def _gender_value(gender):
        return "Male" if gender == GenderEnum.M or getattr(gender, "value", gender) == "M" else "Female"

    @staticmethod
    def _nationality(passenger: PassengerInfoModel):
        nationality = None
        if passenger.document_info:
            nationality = passenger.document_info.nationality
        return Config.NATION_DICT.get(nationality, nationality or "USA")

    @staticmethod
    def _country_from_phone(phone_code: str):
        code = str(phone_code or "").replace("+", "")
        country_info = Config.Country_Code_Dict.get(code)
        return (country_info or {}).get("isoCode1") or "THA"

    @staticmethod
    def _client_fingerprint():
        data = {
            "screen": "1800x1169",
            "timezone": "Asia/Shanghai",
            "ram": 0,
            "cpu": 10,
            "platform": "MacIntel",
            "maxTouchPoints": 0,
        }
        import base64
        import json
        return base64.b64encode(json.dumps(data, separators=(",", ":")).encode("utf-8")).decode("utf-8")

    @staticmethod
    def _client_interaction():
        data = {
            "mousemove": 1,
            "scroll": 1,
            "keydown": 68,
            "focusin": 14,
            "submit": 1,
            "honey": 1,
            "coord": {
                "x": "1046.00",
                "y": "520.00",
                "is_trusted": True,
                "deviation": 42.04998779296875,
                "is_integer": True,
                "is_touch": False,
            },
        }
        import base64
        import json
        return base64.b64encode(json.dumps(data, separators=(",", ":")).encode("utf-8")).decode("utf-8")
