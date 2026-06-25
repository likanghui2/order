import json
from typing import Optional
from urllib.parse import urlencode

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from flights.bookcabin.config import BookCabinConfig


class WebScript:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__proxy_info = proxy_info.model_copy(deep=True) if proxy_info else None
        self.__tls = CurlCffiTls()
        self.__timeout = BookCabinConfig.TIMEOUT

    def initialize_session(self):
        try:
            self.__tls.initialize(self.__proxy_info, impersonate="chrome136")
        except Exception:
            self.__tls.initialize(self.__proxy_info)

    def close(self):
        session = self.__tls.get_session()
        if session:
            session.close()

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adult_count: int,
               child_count: int,
               infant_count: int,
               currency_code: str,
               ret_date: Optional[str] = None,
               promo_code: str = "",
               cabin_class: str = BookCabinConfig.DEFAULT_CABIN_CLASS) -> dict:
        params = {
            "origin": dep_airport,
            "destination": arr_airport,
            "departureDate": self.__normalize_date(dep_date),
            "countAdult": adult_count,
            "countChild": child_count,
            "countInfant": infant_count,
            "cabinClass": cabin_class,
            "tripType": "ROUND_TRIP" if ret_date else "ONE_WAY",
            "promoCode": promo_code or "",
            "currencyCode": currency_code,
        }
        if ret_date:
            params["returnDate"] = self.__normalize_date(ret_date)

        response = self.__tls.get(
            url=f"{BookCabinConfig.FLIGHT_SEARCH_BASE_URL}/search?{urlencode(params)}",
            headers=self.__headers(),
            timeout=self.__timeout,
        )
        response_json = self.__response_json(response)
        self.__check_response(response, response_json)
        return response_json

    def create_cart(self, data: dict) -> dict:
        response = self.__tls.post(
            url=f"{BookCabinConfig.FLIGHT_CART_BASE_URL}/cart",
            headers=self.__headers(content_type="application/json"),
            data=data,
            timeout=self.__timeout,
        )
        response_json = self.__response_json(response)
        self.__check_response(response, response_json)
        return response_json

    def cart_detail(self, cart_id: str) -> dict:
        response = self.__tls.get(
            url=f"{BookCabinConfig.FLIGHT_CART_BASE_URL}/cart/{cart_id}",
            headers=self.__headers(),
            timeout=self.__timeout,
        )
        response_json = self.__response_json(response)
        self.__check_response(response, response_json)
        return response_json

    def ancillary(self, cart_id: str) -> dict:
        response = self.__tls.get(
            url=f"{BookCabinConfig.FLIGHT_ANCILLARY_BASE_URL}/ancillary/{cart_id}",
            headers=self.__headers(),
            timeout=self.__timeout,
        )
        response_json = self.__response_json(response)
        self.__check_response(response, response_json)
        return response_json

    def countries(self) -> dict:
        response = self.__tls.post(
            url=f"{BookCabinConfig.IBE_API_BASE_URL}/location/LocationSearchService/GetCountries",
            headers=self.__headers(content_type="application/json"),
            data={"searchCode": "country"},
            timeout=self.__timeout,
        )
        response_json = self.__response_json(response)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response_json

    def booking(self, data: dict) -> dict:
        response = self.__tls.post(
            url=f"{BookCabinConfig.FLIGHT_BOOKING_BASE_URL}/booking",
            headers=self.__headers(content_type="application/json"),
            data=data,
            timeout=self.__timeout,
        )
        response_json = self.__response_json(response)
        self.__check_response(response, response_json)
        return response_json

    def order_detail(self, order_id: str, order_hash_id: str) -> dict:
        params = {
            "orderId": order_id,
            "orderHashId": order_hash_id,
        }
        response = self.__tls.get(
            url=f"{BookCabinConfig.ORDER_BASE_URL}/v1/order?{urlencode(params)}",
            headers=self.__headers(),
            timeout=self.__timeout,
        )
        response_json = self.__response_json(response)
        self.__check_response(response, response_json)
        return response_json

    @staticmethod
    def __normalize_date(date_text: str) -> str:
        if not date_text:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "date is empty")
        if "-" in date_text:
            return date_text[:10]
        if len(date_text) == 8 and date_text.isdigit():
            return f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:]}"
        return date_text

    @staticmethod
    def __headers(content_type: Optional[str] = None) -> dict:
        headers = {
            "user-agent": BookCabinConfig.USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br, zstd",
            "x-lang": BookCabinConfig.LANGUAGE,
            "x-client-language": BookCabinConfig.LANGUAGE,
            "origin": BookCabinConfig.WEB_BASE_URL,
            "referer": f"{BookCabinConfig.WEB_BASE_URL}/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0",
            "te": "trailers",
        }
        if content_type:
            headers["content-type"] = content_type
        return headers

    @staticmethod
    def __response_json(response) -> dict:
        try:
            return response.to_dict()
        except Exception:
            try:
                return json.loads(response.to_text())
            except Exception:
                return {}

    @staticmethod
    def __check_response(response, response_json: dict):
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if isinstance(response_json, dict) and response_json.get("code") not in (None, "SUCCESS"):
            raise ServiceError(
                ServiceStateEnum.BUSINESS_ERROR,
                response_json.get("message") or response_json.get("errors") or "BookCabin API error",
            )
