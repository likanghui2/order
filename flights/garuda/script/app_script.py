import base64
from urllib.parse import urlparse

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from flights.garuda.config import Config


class AppScript:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__proxy_info_data = proxy_info_data
        self.__timeout = 60
        self.__tls = CurlCffiTls()
        self.__access_token = None
        self.__ga_session = None
        self.__ua = "Dart/3.8 (dart:io)"
        self.initialize_http_util()

    def initialize_http_util(self):
        self.__tls.initialize(self.__proxy_info_data, impersonate="chrome136")

    def init_token(self):
        self.__access_token = self.__authenticate_wso()

    def __authenticate_wso(self) -> str:
        client_id = Config.APP_WSO_CLIENT_ID
        client_secret = Config.APP_WSO_CLIENT_SECRET
        token_url = "https://mikaela.garuda-indonesia.com:8243/token"
        if not client_id or not client_secret:
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                "Garuda APP WSO client credentials",
            )

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Basic {self.__build_basic_token(client_id, client_secret)}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": urlparse(token_url).netloc,
            "User-Agent": self.__ua,
        }
        response = self.__tls.post(
            url=token_url,
            headers=headers,
            data="grant_type=client_credentials",
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        token_data = response.to_dict()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                "Garuda APP WSO access_token",
            )
        return access_token

    @staticmethod
    def __build_basic_token(client_id: str, client_secret: str) -> str:
        raw_token = f"{client_id}:{client_secret}".encode("utf-8")
        return base64.b64encode(raw_token).decode("utf-8")

    def search(self, flight_params: dict, route_index: int = 1) -> dict:
        url = "https://mikaela.garuda-indonesia.com:8243/t/mob.ga/mid-inventory-ali/v.1.0.0/dapi/airFare"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {self.__access_token}",
            "Content-Type": "application/json",
            "Host": urlparse(url).netloc,
            "User-Agent": self.__ua,
        }
        response = self.__tls.post(
            url=url,
            headers=headers,
            data=flight_params,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        flight_result = response.to_dict()
        self.__ga_session = flight_result.get("sessionId")
        return {
            "result": flight_result,
            "routeIndex": route_index,
        }

    def booking_request(self, booking_params: dict) -> dict:
        url = "https://mikaela.garuda-indonesia.com:8243/t/mob.ga/mid-reservation-ali/v.2.0/dapi/booking/cart"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {self.__access_token}",
            "Content-Type": "application/json",
            "GASession": self.__ga_session,
            "Host": urlparse(url).netloc,
            "User-Agent": self.__ua,
        }
        response = self.__tls.post(
            url=url,
            headers=headers,
            data=booking_params,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return {
            "result": response.to_dict(),
        }

    def add_passenger(self, booking_params: dict) -> dict:
        url = "https://mikaela.garuda-indonesia.com:8243/t/mob.ga/mid-reservation-ali/v.2.0/dapi/booking"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {self.__access_token}",
            "Content-Type": "application/json",
            "GASession": self.__ga_session,
            "Host": urlparse(url).netloc,
            "User-Agent": self.__ua,
        }
        response = self.__tls.post(
            url=url,
            headers=headers,
            data=booking_params,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return {
            "result": response.to_dict(),
        }
