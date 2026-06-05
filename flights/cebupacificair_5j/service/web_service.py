import html
import json
import re
import time
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

from common.decorators.retry_decorator import retry_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.payment_info_model import PaymentInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from flights.cebupacificair_5j.config import CebupacificairConfig
from flights.cebupacificair_5j.flight_common.booking_utils import CebupacificairBookingUtils
from flights.cebupacificair_5j.flight_common.flight_parse import FlightParser
from flights.cebupacificair_5j.flight_common.payment_utils import CebupacificairPaymentUtils
from flights.cebupacificair_5j.script.web_script import WebScript


class WebService:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__script = WebScript(proxy_info=proxy_info)

    def initialize_session(self):
        self.__script.initialize_session()

    def get_akm(self):
        self.__script.get_akm()

    def close(self):
        self.__script.close()

    @retry_decorator([
        (ServiceStateEnum.AKM_RISK_CHECK_FAILED, None),
        (ServiceStateEnum.ROBOT_CHECK, initialize_session),
        (ServiceStateEnum.HTTP_TIMEOUT, initialize_session),
        (ServiceStateEnum.CURL_EXCEPTION, initialize_session),
    ], retry_max_number=5)
    def initialize_html_session(self):
        self.__script.initialize_session()
        self.__script.initialize_html_session()

    @retry_decorator([
        (ServiceStateEnum.AKM_RISK_CHECK_FAILED, None),
        (ServiceStateEnum.ROBOT_CHECK, initialize_session),
        (ServiceStateEnum.HTTP_TIMEOUT, initialize_session),
        (ServiceStateEnum.CURL_EXCEPTION, initialize_session),
    ], retry_max_number=8)
    def initialize_html_session_booking(self):
        self.__script.initialize_session()
        self.__script.initialize_html_session()

    @retry_decorator([
        (ServiceStateEnum.AKM_RISK_CHECK_FAILED, initialize_html_session),
        (ServiceStateEnum.ROBOT_CHECK, initialize_html_session),
        (ServiceStateEnum.HTTP_TIMEOUT, initialize_session),
        (ServiceStateEnum.CURL_EXCEPTION, initialize_session),
    ], retry_max_number=5)
    def availability(self,
                     airport_data: List[Tuple[str, str, str]],
                     adult_count: int,
                     child_count: int,
                     promo_code: str = "",
                     currency: Optional[str] = None) -> List[FlightJourneyModel]:
        flight_data = self.__script.availability(
            airport_data=airport_data,
            adult_count=adult_count,
            child_count=child_count,
            promo_code=promo_code,
            currency=currency,
        )
        if not flight_data.get('routes'):
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)

        return FlightParser.parse_flight_data(
            routes=flight_data['routes'],
            currency=flight_data.get('currencyCode') or currency,
        )

    @staticmethod
    def __build_bundle_codes(bundle: FlightBundleModel) -> List[str]:
        if bundle.ext and ('trip' in bundle.ext or 'return' in bundle.ext):
            return [
                (bundle.ext.get('trip') or {}).get('bundleCode') or '',
                (bundle.ext.get('return') or {}).get('bundleCode') or '',
            ]
        return [(bundle.ext or {}).get('bundleCode') or '']

    @retry_decorator([
        (ServiceStateEnum.AKM_RISK_CHECK_FAILED, initialize_html_session),
        (ServiceStateEnum.ROBOT_CHECK, initialize_html_session),
        (ServiceStateEnum.HTTP_TIMEOUT, initialize_session),
        (ServiceStateEnum.CURL_EXCEPTION, initialize_session),
    ], retry_max_number=5)
    def trip(self,
             dep_airport: str,
             journey: FlightJourneyModel,
             bundle: FlightBundleModel,
             adult_count: int,
             child_count: int,
             passengers: Optional[List[PassengerInfoModel]] = None) -> dict:
        journey_keys = journey.journey_key.split('^')
        fare_keys = (bundle.fare_key or '').split('^')
        bundle_codes = self.__build_bundle_codes(bundle)
        routes = [
            (
                journey_key,
                fare_keys[index] if index < len(fare_keys) else '',
                bundle_codes[index] if index < len(bundle_codes) else '',
            )
            for index, journey_key in enumerate(journey_keys)
        ]
        response = self.__script.trip(
            routes=routes,
            adult_count=adult_count,
            child_count=child_count,
            bundles=[],
            currency=bundle.price_info.currency,
            ssrs=[] if dep_airport == 'HKG' else ['WAFI'],
        )
        if passengers is not None:
            for source_passenger in response.get('passengers') or []:
                passenger = next((
                    item for item in passengers
                    if item.type.value == source_passenger.get('passengerTypeCode') and item.key is None
                ), None)
                if passenger:
                    passenger.key = source_passenger.get('passengerKey')
        return response

    @retry_decorator([
        (ServiceStateEnum.AKM_RISK_CHECK_FAILED, initialize_html_session),
        (ServiceStateEnum.ROBOT_CHECK, initialize_html_session),
        (ServiceStateEnum.HTTP_TIMEOUT, initialize_session),
        (ServiceStateEnum.CURL_EXCEPTION, initialize_session),
    ], retry_max_number=5)
    def add_passenger(self,
                      passengers: List[PassengerInfoModel],
                      contact_info: ContactInfoModel,
                      purchasing: bool = True) -> dict:
        passenger_infos = CebupacificairBookingUtils.passenger_utils(
            passengers=passengers,
            purchasing=purchasing,
        )
        contact_dict = CebupacificairBookingUtils.contact_dict_utils(
            contact_info=contact_info,
            passenger=passengers[0],
        )
        return self.__script.guest_details(passenger_infos, contact_dict)

    @retry_decorator([
        (ServiceStateEnum.AKM_RISK_CHECK_FAILED, initialize_html_session),
        (ServiceStateEnum.ROBOT_CHECK, initialize_html_session),
        (ServiceStateEnum.HTTP_TIMEOUT, initialize_session),
        (ServiceStateEnum.CURL_EXCEPTION, initialize_session),
    ], retry_max_number=5)
    def commit(self, passengers: List[PassengerInfoModel], source_data: dict) -> dict:
        addon_passengers = CebupacificairBookingUtils.empty_addon_passenger_utils(passengers)
        commit_response = self.__script.commit(sell_addon_infos=[
            {
                'addons': 'baggage',
                'passengers': addon_passengers,
            },
            {
                'addons': 'insurance',
                'passengers': [],
            },
            {
                'addons': 'meal',
                'passengers': addon_passengers,
            },
        ])
        if not commit_response.get('bookingSummary'):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'bookingSummary')
        return commit_response

    @staticmethod
    def extract_session_storage_items(response: str) -> dict:
        pattern = re.compile(
            r"sessionStorage\.setItem\(\s*"
            r"(?P<key>'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\")\s*,\s*"
            r"(?P<value>'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\"|null|true|false|-?\d+(?:\.\d+)?)\s*"
            r"\)",
            re.S,
        )

        def parse_js_literal(text: str):
            text = text.strip()
            if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
                inner = text[1:-1]
                inner = inner.replace(r"\/", "/")
                inner = inner.replace(r"\'", "'")
                inner = inner.replace(r"\"", '"')
                inner = inner.replace(r"\\", "\\")
                return inner
            if text == "null":
                return None
            if text == "true":
                return True
            if text == "false":
                return False
            if re.fullmatch(r"-?\d+", text):
                return int(text)
            if re.fullmatch(r"-?\d+\.\d+", text):
                return float(text)
            return text

        payment_dict = {}
        for match in pattern.finditer(response):
            key = parse_js_literal(match.group("key"))
            value = parse_js_literal(match.group("value"))
            if key in {"orderdata", "additionaldata", "jsonconvertedrequestdata"} and isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            payment_dict[key] = value
        return payment_dict

    @staticmethod
    def __parse_hidden_inputs(response: str) -> dict:
        soup = BeautifulSoup(response, "html.parser")
        result = {}
        for input_tag in soup.find_all("input"):
            name = input_tag.get("name")
            if name:
                result[name] = input_tag.get("value") or ""
        if not result:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "payment input")
        return result

    @staticmethod
    def __payment_value(payment_dict: dict, key: str):
        value = payment_dict.get(key)
        if value is None or value == "":
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, key)
        return value

    @classmethod
    def __payment_int_value(cls, payment_dict: dict, key: str) -> int:
        try:
            return int(cls.__payment_value(payment_dict, key))
        except (TypeError, ValueError):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, key)

    @staticmethod
    def __extract_payment_total(order_data: dict) -> Optional[Decimal]:
        payments = order_data.get("payments") or []
        for payment in payments:
            amount = (payment.get("amounts") or {}).get("amount") or payment.get("amount")
            if amount is not None:
                try:
                    return Decimal(str(amount))
                except (InvalidOperation, ValueError):
                    pass

        booking_summary = order_data.get("bookingSummary") or {}
        for key in ("balanceDue", "totalCost", "totalAmount"):
            amount = booking_summary.get(key)
            if amount is not None:
                try:
                    return Decimal(str(amount))
                except (InvalidOperation, ValueError):
                    pass
        return None

    @retry_decorator([
        (ServiceStateEnum.AKM_RISK_CHECK_FAILED, initialize_html_session),
        (ServiceStateEnum.ROBOT_CHECK, initialize_html_session),
        (ServiceStateEnum.HTTP_TIMEOUT, initialize_session),
        (ServiceStateEnum.CURL_EXCEPTION, initialize_session),
    ], retry_max_number=5)
    def init_payment(self) -> dict:
        response = self.__script.init_payment()
        payment_dict = self.__parse_hidden_inputs(response)
        web_response = self.__script.web(payment_dict)
        payment_dict.update(self.extract_session_storage_items(web_response))
        if not payment_dict:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "payment data")
        return payment_dict

    def payment_initialize(self, payment_dict: dict) -> dict:
        return self.__script.initialize(
            order_id=self.__payment_value(payment_dict, "orderid"),
            operator=self.__payment_int_value(payment_dict, "operator"),
            client_id=self.__payment_value(payment_dict, "clientid"),
            account=self.__payment_value(payment_dict, "account"),
            email=self.__payment_value(payment_dict, "email"),
            mobile=self.__payment_value(payment_dict, "mobile"),
            mobile_country=self.__payment_int_value(payment_dict, "mobilecountry"),
            country=self.__payment_int_value(payment_dict, "country"),
            amount=self.__payment_value(payment_dict, "amount"),
            currency=self.__payment_int_value(payment_dict, "currency-code"),
            accept_url=self.__payment_value(payment_dict, "accepturl"),
            cancel_url=self.__payment_value(payment_dict, "cancelurl"),
            callback_url=self.__payment_value(payment_dict, "callbackurl"),
            order_data=json.dumps(self.__payment_value(payment_dict, "orderdata")),
            auth_token=self.__payment_value(payment_dict, "authtoken"),
            hmac=self.__payment_value(payment_dict, "hmac"),
            additional_data=self.__payment_value(payment_dict, "additionaldata"),
            init_token=self.__payment_value(payment_dict, "inittoken"),
            nonce=self.__payment_value(payment_dict, "nonce"),
            profile_id=self.__payment_value(payment_dict, "profileid"),
            gtm_id=self.__payment_value(payment_dict, "gtm-id"),
            time_token=self.__payment_value(payment_dict, "timetoken"),
            json_converted_request_data=json.dumps(self.__payment_value(payment_dict, "jsonconvertedrequestdata")),
            encryptedauthhash=self.__payment_value(payment_dict, "encryptedAuthHash"),
        )

    def payment_authorize(self,
                          payment_dict: dict,
                          transaction: str,
                          contact_info: ContactInfoModel,
                          payment_info: PaymentInfoModel,
                          expired: bool = False):
        response = self.__script.authorize(
            last_name=contact_info.last_name,
            first_name=contact_info.first_name,
            card_number=payment_info.card_number,
            card_vcc=payment_info.card_cvv,
            card_expiry_date=payment_info.card_expiry_date,
            card_type=payment_info.card_type,
            amount=self.__payment_value(payment_dict, "amount"),
            currency=self.__payment_int_value(payment_dict, "currency-code"),
            country=self.__payment_int_value(payment_dict, "country"),
            mobile_country=self.__payment_int_value(payment_dict, "mobilecountry"),
            operator=self.__payment_int_value(payment_dict, "operator"),
            client_id=self.__payment_value(payment_dict, "clientid"),
            account=self.__payment_value(payment_dict, "account"),
            mobile=self.__payment_value(payment_dict, "mobile"),
            email=self.__payment_value(payment_dict, "email"),
            profile_id=self.__payment_value(payment_dict, "profileid"),
            auth_token=self.__payment_value(payment_dict, "authtoken"),
            hmac=self.__payment_value(payment_dict, "hmac"),
            transaction=transaction,
            expired=expired,
        )
        if "3D Verification Failed" in str(response):
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)

        if "body" not in response:
            return response

        text = html.unescape(response["body"])
        soup = BeautifulSoup(text, "html.parser")
        jwt_input = soup.find("input", {"name": "JWT"})
        bin_input = soup.find("input", {"name": "Bin"})
        payment_jwt = jwt_input.get("value") if jwt_input else None
        bin_value = bin_input.get("value") if bin_input else None
        if not payment_jwt:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "JWT")
        return payment_jwt, bin_value

    def payment_auth(self, jwt: str, bin_value: Optional[str]) -> None:
        pay_util = CebupacificairPaymentUtils(
            proxy_info=self.__script.proxy_info,
            user_agent=CebupacificairConfig.USER_AGENT,
        )
        collect_data = pay_util.collect_post(data=f"JWT={jwt}" + (f"&Bin={bin_value}" if bin_value else ""))
        df_url = html.unescape(collect_data.get("dfUrlFullValue") or "")
        if not df_url:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "dfUrlFullValue")

        render_data = pay_util.render_post(
            url=f"{df_url}&origin=CruiseAPI",
            data=CebupacificairPaymentUtils.collect_nonce(bin_value),
        )
        reference_id = render_data.get("referenceId")
        org_unit_id = render_data.get("orgUnitId")
        nonce = render_data.get("nonce")
        if not reference_id or not org_unit_id or not nonce:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cardinal render")

        pay_util.save_browser_data(
            nonce=nonce,
            reference_id=reference_id,
            org_unit_id=org_unit_id,
            referrer=df_url,
        )
        merchant_method = (render_data.get("features") or {}).get("merchantMethodUrlCollection") or {}
        method_urls = merchant_method.get("methodUrls") or []
        if method_urls:
            pay_util.method_url(method_urls[0].get("Payload") or "")
        pay_util.collect_redirect(reference_id=reference_id)

    def payment_complete(self, transaction_id: str, token: str) -> dict:
        return self.__script.payment_complete(transaction_id=transaction_id, token=token)

    def session_complete(self, transaction_id: str, token: str, session_id: str, status_code: str) -> dict:
        return self.__script.session_complete(
            transaction_id=transaction_id,
            session_id=session_id,
            status_code=status_code,
            token=token,
        )

    @retry_decorator([
        (ServiceStateEnum.HTTP_TIMEOUT, initialize_session),
        (ServiceStateEnum.CURL_EXCEPTION, initialize_session),
    ], retry_max_number=3)
    def itinerary(self,
                  response_order_data: ResponseOrderInfoModel,
                  payment_info: PaymentInfoModel) -> ResponseOrderInfoModel:
        time.sleep(3)
        order_data = self.__script.itinerary()
        pnr = order_data.get("recordLocator")
        if not pnr:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "recordLocator")

        response_order_data.pnr = pnr
        response_order_data.order_number = pnr
        response_order_data.currency_code = order_data.get("currencyCode") or response_order_data.currency_code
        response_order_data.order_state = (
            OrderStateEnum.OPEN_FOR_USE
            if (order_data.get("info") or {}).get("status") == "Confirmed"
            else OrderStateEnum.UNKNOWN
        )
        total_amount = self.__extract_payment_total(order_data)
        if total_amount is not None:
            response_order_data.total_amount = total_amount
        if response_order_data.passengers:
            for passenger in response_order_data.passengers:
                passenger.ticket_number = pnr
        return response_order_data
