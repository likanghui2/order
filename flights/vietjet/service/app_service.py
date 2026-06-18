import base64
import json
from datetime import datetime, timedelta
from typing import Optional, List
from urllib.parse import urlencode

from Crypto.Cipher import AES

from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.utils.aes_ciphering import AesCiphering
from flights.vietjet.flight_common.app_booking_flow import AppBookingFlow
from flights.vietjet.flight_common.app_flight_parse import FlightParser
from flights.vietjet.flight_common.app_payment_method_enum import VjAppPaymentMethodEnum
from flights.vietjet.script.app_script import AppScript


class AppService:
    AES_KEY = b"O]+}9Utoggh4uxfh"
    THIRD_PARTY_LANGUAGE = {
        "vi": {"Code": "vi-VN", "Name": "Vietnamese"},
        "vi-vn": {"Code": "vi-VN", "Name": "Vietnamese"},
        "en": {"Code": "en-US", "Name": "English"},
        "en-us": {"Code": "en-US", "Name": "English"},
        "zh": {"Code": "zh-CN", "Name": "Chinese"},
        "zh-cn": {"Code": "zh-CN", "Name": "Chinese"},
        "zh-tw": {"Code": "tw-CN", "Name": "Chinese"},
        "th": {"Code": "th-TH", "Name": "Thai"},
        "ko": {"Code": "ko-KR", "Name": "Korean"},
        "ja": {"Code": "ja-JP", "Name": "Japanese"},
        "ru": {"Code": "ru-RU", "Name": "Russian"},
    }

    def __init__(self, proxy_info_data: Optional[ProxyInfoModel] = None):
        self.__app_script = AppScript(proxy_info=proxy_info_data)

    def initialize_session(self):
        self.__app_script.initialize_session()

    @classmethod
    def encrypt_payload(cls, payload: dict) -> str:
        plaintext = json.dumps(payload)
        print(plaintext)
        cipher_bytes = AesCiphering.encrypt(
            plaintext.encode("utf-8"),
            cls.AES_KEY,
            None,
            AES.MODE_ECB,
        )
        return base64.b64encode(cipher_bytes).decode("utf-8")

    def build_booking_payload(self,
                              journey: FlightJourneyModel,
                              use_bundle: FlightBundleModel,
                              passenger_infos: List[PassengerInfoModel],
                              contact_info: ContactInfoModel,
                              payment_method: Optional[dict] = None,
                              payment_method_criteria: Optional[dict] = None,
                              total_amount=0,
                              payment_currency: Optional[dict] = None,
                              processing_currency_amounts: Optional[list] = None,
                              return_bundle: Optional[FlightBundleModel] = None,
                              type_payment: str = "pay_later",
                              extra: Optional[dict] = None):
        return AppBookingFlow.build_reserve_payload(
            journey=journey,
            departure_bundle=use_bundle,
            return_bundle=return_bundle,
            passengers=passenger_infos,
            contact_info=contact_info,
            payment_method=payment_method,
            payment_method_criteria=payment_method_criteria,
            total_amount=total_amount,
            currency_code=use_bundle.price_info.currency,
            payment_currency=payment_currency,
            processing_currency_amounts=processing_currency_amounts,
            type_payment=type_payment,
            extra=extra,
            route_type=self.route_type(journey),
        )

    def build_reserve_v2_request(self, reserve_payload: dict):
        return {
            "method": "POST",
            "url": "https://mobileapp-api.vietjetair.com/api/reserveV2",
            "headers": {
                "User-Agent": "Vietjet Air/7 CFNetwork/3860.400.51 Darwin/25.3.0",
                "Connection": "keep-alive",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/json",
                "x-app-timezone": "+08:00",
                "uuid": "AppCenter ",
                "priority": "u=3, i",
                "accept-language": "vi-VN",
                "x-app-build": "500098",
                "x-app-version": "5.9.0",
                "auth-user": "",
                "Authorization": "Bearer ",
            },
            "body": {
                "encryptData": self.encrypt_payload(reserve_payload),
            },
            "plainPayload": reserve_payload,
            "dryRun": True,
        }

    def build_payment_methods_request(self, params: dict):
        return {
            "method": "GET",
            "url": f"https://mobileapp-api.vietjetair.com/api/paymentMethod?{urlencode(params)}",
            "params": params,
            "headers": {
                "User-Agent": "Vietjet Air/7 CFNetwork/3860.400.51 Darwin/25.3.0",
                "Connection": "keep-alive",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/json",
                "x-app-timezone": "+08:00",
                "uuid": "AppCenter ",
                "priority": "u=3, i",
                "accept-language": "vi-VN",
                "x-app-build": "500098",
                "x-app-version": "5.9.0",
            },
            "dryRun": True,
        }

    def build_processing_fee_request(self, reserve_payload: dict):
        return {
            "method": "PUT",
            "url": "https://mobileapp-api.vietjetair.com/api/reserve/quotationsV2",
            "headers": {
                "User-Agent": "Vietjet Air/7 CFNetwork/3860.400.51 Darwin/25.3.0",
                "Connection": "keep-alive",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/json",
                "x-app-timezone": "+08:00",
                "uuid": "AppCenter ",
                "priority": "u=3, i",
                "accept-language": "vi-VN",
                "x-app-build": "500098",
                "x-app-version": "5.9.0",
                "auth-user": "",
                "Authorization": "Bearer ",
            },
            "body": reserve_payload,
            "dryRun": True,
        }

    def payment_methods(self, journey: FlightJourneyModel, use_bundle: FlightBundleModel):
        params = AppBookingFlow.build_payment_methods_params(journey, use_bundle)
        response = self.__app_script.payment_methods(params)
        return self.unwrap_data(response), params

    def processing_fee(self, reserve_payload: dict):
        response = self.__app_script.processing_fee(reserve_payload)
        return self.parse_processing_fee_response(response), response

    def reserve_v2(self, reserve_payload: dict):
        return self.__app_script.reserve_v2({"encryptData": self.encrypt_payload(reserve_payload)})

    def build_full_booking_flow(self,
                                journey: FlightJourneyModel,
                                use_bundle: FlightBundleModel,
                                passenger_infos: List[PassengerInfoModel],
                                contact_info: ContactInfoModel):
        payment_method_enum = VjAppPaymentMethodEnum.VNPAY_QR
        payment_method = {
            "identifier": payment_method_enum.identifier,
            "description": "VNPAY QR",
        }
        selected_type_payment = payment_method_enum.type_payment
        client_ip = self.client_ip()
        payment_method_criteria = self.build_payment_method_criteria({}, client_ip)
        base_total_amount = self.calculate_total_amount(use_bundle, passenger_infos)

        quote_payload = self.build_booking_payload(
            journey=journey,
            use_bundle=use_bundle,
            passenger_infos=passenger_infos,
            contact_info=contact_info,
            payment_method=payment_method,
            payment_method_criteria=payment_method_criteria,
            total_amount=base_total_amount,
            processing_currency_amounts=None,
            type_payment=selected_type_payment,
            extra=self.build_quote_extra(payment_method, client_ip),
        )
        quote_request = self.build_processing_fee_request(quote_payload)
        quote_data, quote_response = self.processing_fee(quote_payload)
        final_payload = self.build_booking_payload(
            journey=journey,
            use_bundle=use_bundle,
            passenger_infos=passenger_infos,
            contact_info=contact_info,
            payment_method=payment_method,
            payment_method_criteria=payment_method_criteria,
            total_amount=quote_data.get("paymentTransactionAmounts") or 0,
            payment_currency=quote_data.get("paymentCurrency"),
            processing_currency_amounts=quote_data.get("processingCurrencyAmounts") or [],
            type_payment=selected_type_payment,
            extra=self.build_payment_extra(journey, payment_method, quote_data, client_ip),
        )
        reserve_request = self.build_reserve_v2_request(final_payload)
        reserve_response = self.reserve_v2(final_payload)
        result = dict(reserve_response or {})
        reserve_data = result.get("data")
        if isinstance(reserve_data, dict):
            result.setdefault(
                "number",
                reserve_data.get("number")
                or reserve_data.get("reservationNumber")
                or reserve_data.get("orderNumber")
            )
            result.setdefault(
                "pnr",
                reserve_data.get("locator")
                or reserve_data.get("reservationLocator")
                or reserve_data.get("reservationCode")
                or reserve_data.get("pnr")
            )
        result.update({
            "paymentMethods": {
                "skipped": True,
                "selected": payment_method,
                "selectedEnum": payment_method_enum.name,
            },
            "processingFee": {
                "request": quote_request,
                "response": quote_response,
                "parsed": quote_data,
            },
            "reserveV2": reserve_request,
            "reserveV2Response": reserve_response,
        })
        return result

    @classmethod
    def infer_type_payment(cls, payment_method: dict, fallback: str = "pay_later"):
        identifier = (payment_method.get("identifier") or "").upper()
        card_type = (payment_method.get("cardType") or "").lower()
        payment_method_enum = VjAppPaymentMethodEnum.from_identifier(identifier)
        if payment_method_enum is not None:
            return payment_method_enum.type_payment
        if identifier.startswith("VJINT"):
            return "vjint"
        if card_type == "international" or identifier in {"VI", "VJAUDVI"}:
            return "international_debit_card"
        return fallback

    @staticmethod
    def calculate_total_amount(use_bundle: FlightBundleModel,
                               passenger_infos: List[PassengerInfoModel]):
        total_amount = 0
        for passenger in passenger_infos:
            if passenger.type == PassengerTypeEnum.CHD:
                total_amount += (
                    use_bundle.price_info.child_ticket_price
                    + use_bundle.price_info.child_tax_price
                )
            elif passenger.type == PassengerTypeEnum.ADT:
                total_amount += (
                    use_bundle.price_info.adult_ticket_price
                    + use_bundle.price_info.adult_tax_price
                )
        return total_amount

    @classmethod
    def build_payment_extra(cls,
                            journey: FlightJourneyModel,
                            payment_method: dict,
                            quote_data: dict,
                            client_ip: str):
        first_segment = journey.segments[0]
        identifier = payment_method.get("identifier")
        is_gpay_international = cls.is_gpay_international(identifier)
        return {
            "IpAddress": client_ip,
            "SessionId": quote_data.get("SessionId"),
            "identifier": identifier,
            "threadPayment": payment_method.get("threadPayment"),
            "cardType": payment_method.get("cardType"),
            "bank": payment_method.get("bank"),
            "flightCode": first_segment.carrier,
            "isGpayInternational": is_gpay_international,
            "SuccessURL": "https://www.vietjetair.com/?status_payment=success",
            "CancelURL": "https://www.vietjetair.com/?status_payment=cancel",
            "FailURL": "https://www.vietjetair.com/?status_payment=fail",
            "PendingURL": "https://www.vietjetair.com/?status_payment=pending",
            "identityNumber": None,
            "phoneInput": "",
            "languageCode": "vi",
            "OneWay": 1,
            "isCheckin": False,
            "userId": "",
            "SendMail": True,
            "SendZalo": False,
            "SendFacebook": False,
            "isPassportConfig": True,
        }

    @classmethod
    def build_quote_extra(cls, payment_method: dict, client_ip: str):
        return {
            "IpAddress": client_ip,
            "identifier": payment_method.get("identifier"),
            "bank": payment_method.get("bank"),
            "cardType": payment_method.get("cardType"),
        }

    @classmethod
    def build_payment_method_criteria(cls, payment_method_criteria: Optional[dict], client_ip: str):
        criteria = dict(payment_method_criteria or {})
        criteria.setdefault(
            "ThirdParty",
            {
                "ClientIP": client_ip,
                "Language": cls.third_party_language(),
            },
        )
        return criteria

    def client_ip(self):
        return self.__app_script.get_ip()

    @classmethod
    def third_party_language(cls):
        return cls.THIRD_PARTY_LANGUAGE["vi"]

    @staticmethod
    def route_type(journey: FlightJourneyModel):
        ext = journey.ext or {}
        route_type = ext.get("routeType")
        if isinstance(route_type, str):
            return {"identifier": route_type}
        if isinstance(route_type, dict) and route_type.get("identifier"):
            return route_type

        route_type_identifier = ext.get("routeTypeIdentifier")
        if route_type_identifier:
            return {"identifier": route_type_identifier}
        return None

    @staticmethod
    def is_gpay_international(identifier: Optional[str]):
        return identifier in {"VJAUDVI", "VJPVI", "VJPMC", "VJPAMEX", "VJPJCB"}

    @classmethod
    def unwrap_data(cls, response_data):
        data = response_data
        for _ in range(3):
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
            else:
                break
        return data

    @classmethod
    def parse_processing_fee_response(cls, response_data):
        data = cls.unwrap_data(response_data)
        payment_transactions = data.get("paymentTransactions") or []
        first_transaction = payment_transactions[0] if payment_transactions else {}
        currency_amounts = first_transaction.get("currencyAmounts") or []
        first_amount = currency_amounts[0] if currency_amounts else {}
        return {
            "paymentTransactionCurrencyAmounts": currency_amounts,
            "paymentCurrency": first_amount.get("currency"),
            "processingCurrencyAmounts": first_transaction.get("processingCurrencyAmounts") or [],
            "paymentTransactionAmounts": first_amount.get("totalAmount", 0),
            "SessionId": data.get("SessionId"),
            "googleCaptchaStatus": data.get("googleCaptchaStatus"),
            "processingFee": data.get("processingFee"),
        }

    @classmethod
    def select_payment_method(cls,
                              payment_methods,
                              preferred_identifier: str = "PL6",
                              currency_code: Optional[str] = None,
                              strict: bool = False):
        candidates = cls.find_payment_method_candidates(payment_methods)
        if not candidates:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "VJ app payment methods empty")
        supported_candidates = [
            candidate for candidate in candidates
            if cls.payment_method_supports_currency(candidate, currency_code)
        ]
        search_candidates = supported_candidates or candidates
        for candidate in search_candidates:
            if candidate.get("identifier") == preferred_identifier:
                return candidate
        if strict:
            available_identifiers = sorted({
                candidate.get("identifier")
                for candidate in search_candidates
                if candidate.get("identifier")
            })
            raise ServiceError(
                ServiceStateEnum.BUSINESS_ERROR,
                (
                    f"VJ app payment method {preferred_identifier} not available; "
                    f"available={','.join(available_identifiers)}"
                ),
            )
        for candidate in search_candidates:
            identifier = candidate.get("identifier") or ""
            if identifier.startswith("VJINT"):
                return candidate
        for candidate in search_candidates:
            if (candidate.get("cardType") or "").lower() == "international":
                return candidate
        for candidate in search_candidates:
            if candidate.get("identifier"):
                return candidate
        return search_candidates[0]

    @staticmethod
    def payment_method_supports_currency(payment_method: dict, currency_code: Optional[str]):
        if not currency_code:
            return True
        currencies = payment_method.get("currencies")
        if not currencies:
            return True
        return currency_code in currencies

    @classmethod
    def find_payment_method_candidates(cls, value):
        result = []
        if isinstance(value, dict):
            if cls.is_payment_method(value):
                result.append(value)
            for item in value.values():
                result.extend(cls.find_payment_method_candidates(item))
        elif isinstance(value, list):
            for item in value:
                result.extend(cls.find_payment_method_candidates(item))
        return result

    @staticmethod
    def is_payment_method(value: dict):
        return bool(
            value.get("identifier")
            and (
                value.get("processingFee") is not None
                or value.get("threadPayment") is not None
                or value.get("paymentGroupCode") is not None
                or value.get("defaultName") is not None
                or value.get("currencies") is not None
            )
        )

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adult_count: int,
               child_count: int,
               currency: str,
               promo_code: str = "",
               ret_date: Optional[str] = None):
        search_data = {
            "cityPair": f"{dep_airport}-{arr_airport}",
            "currencyCode": currency,
            "adultCount": adult_count,
            "childCount": child_count,
            "infantCount": 0,
            "promoCode": promo_code or "",
            "departureTime": (
                datetime.strptime(dep_date, "%m-%d-%Y") + timedelta(days=1)
            ).strftime("%m-%d-%Y"),
            "daysAfterDeparture": 0,
            "daysAfterReturn": 0,
            "dateStart": 1759161600000,
            "typeData": 0,
            "returnTime": ret_date,
            "CaptchaData": {
                "token": "",
            },
            "IsCaptchaV2": False,
            "requestId": "F1V3X3DFH9AX-1774256156083",
        }

        enc_data = {"encryptData": self.encrypt_payload(search_data)}
        search_response = self.__app_script.travel_option(enc_data)
        flight_data = search_response.get("data") or search_response
        target_dates = [datetime.strptime(dep_date, "%m-%d-%Y").strftime("%Y-%m-%d")]
        if ret_date:
            target_dates.append(datetime.strptime(ret_date, "%m-%d-%Y").strftime("%Y-%m-%d"))
        journey_list = FlightParser.journey_info_parser(
            flight_data,
            baggage_data={},
            target_dates=target_dates,
        )
        if not journey_list:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        return journey_list
