import base64
import hashlib
import json
import time
from typing import Optional

from Crypto.Cipher import AES

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.aaa_tls import AaaTls
from common.utils.aes_ciphering import AesCiphering
from flights.lionairthai.config_v2 import LionairthaiConfigV2


AAA_TLS_API_URL = "http://45.192.100.222:9994/api/tls/request"
AAA_TLS_API_KEY = "UUEM3XIA"


class WebScriptV2:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self._proxy_info = proxy_info
        self._tls = None
        self._token = ""
        self.initialize_session()

    def initialize_session(self):
        self._tls = AaaTls(
            api_url=AAA_TLS_API_URL,
            api_key=AAA_TLS_API_KEY,
        )
        self._tls.initialize(self._proxy_info)
        self._token = ""

    @staticmethod
    def _encrypt(data: dict) -> str:
        plaintext = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
        ciphertext = AesCiphering.encrypt(
            plaintext,
            LionairthaiConfigV2.AES_KEY,
            LionairthaiConfigV2.AES_KEY,
            AES.MODE_CBC,
        )
        return base64.b64encode(ciphertext).decode()

    @staticmethod
    def _decrypt(data: str) -> dict:
        plaintext = AesCiphering.decrypt(
            base64.b64decode(data),
            LionairthaiConfigV2.AES_KEY,
            LionairthaiConfigV2.AES_KEY,
            AES.MODE_CBC,
        )
        return json.loads(plaintext.decode())

    def _signature(self, token: Optional[str] = None) -> tuple[str, str]:
        timestamp = str(int(time.time() * 1000))
        current_token = self._token if token is None else token
        source = f"DC_PRD_CLIENT_IDDC_API_PRD_PasswordP{current_token}{timestamp}"
        return timestamp, hashlib.sha256(source.encode()).hexdigest()

    def _headers(self, origin: str, referer: str, content_type: Optional[str] = None) -> dict:
        timestamp, signature = self._signature()
        headers = {
            "sec-ch-ua-platform": '"Windows"',
            "x-token": self._token,
            "x-useragent": "Web",
            "x-timestamp": timestamp,
            "sec-ch-ua": LionairthaiConfigV2.SEC_CH_UA,
            "sec-ch-ua-mobile": "?0",
            "x-hash": signature,
            "x-env": "P",
            "user-agent": LionairthaiConfigV2.USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "origin": origin,
            "referer": referer,
        }
        if content_type:
            headers["content-type"] = content_type
        return headers

    @staticmethod
    def _response_json(response, expected_status: int = 200) -> dict:
        if response.status != expected_status:
            raise ServiceError(
                ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                response.status,
            )
        try:
            data = response.to_dict()
        except Exception as error:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION) from error
        if not isinstance(data, dict):
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION)
        return data

    def initialize_token(self):
        headers = self._headers(
            "https://www.lionairthai.com",
            "https://www.lionairthai.com/",
        )
        response = self._tls.get(
            url="https://search.lionairthai.com/flightrr_api/api/Get/Token",
            headers=headers,
            allow_redirects=False,
        )
        if response.status != 200:
            raise ServiceError(
                ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                response.status,
            )
        self._token = next(
            (
                value for key, value in response.headers.items()
                if key.lower().replace("-", "") == "xtoken"
            ),
            "",
        )
        if not self._token:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION)

    def availability(self, data: dict) -> dict:
        if not self._token:
            self.initialize_token()
        response = self._tls.post(
            url="https://search.lionairthai.com/flightrr_api/api/get/Flights",
            headers=self._headers(
                "https://www.lionairthai.com",
                "https://www.lionairthai.com/",
                "application/json",
            ),
            data={"payload": self._encrypt(data)},
            timeout=90,
            allow_redirects=False,
        )
        encrypted = self._response_json(response).get("response")
        if not encrypted:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION)
        return self._decrypt(encrypted)

    def add_cart(self, data: dict) -> dict:
        response = self._tls.post(
            url="https://cart.lionairthai.com/cartrr_api/api/add/cart",
            headers=self._headers(
                "https://www.lionairthai.com",
                "https://www.lionairthai.com/",
                "application/json",
            ),
            data=data,
            allow_redirects=False,
        )
        return self._response_json(response)

    def get_cart(self) -> dict:
        response = self._tls.get(
            url="https://cart.lionairthai.com/cartrr_api/api/get/cart",
            headers=self._headers(
                "https://www.lionairthai.com",
                "https://www.lionairthai.com/",
            ),
            allow_redirects=False,
        )
        return self._response_json(response)

    def add_passengers(self, data: dict) -> dict:
        response = self._tls.post(
            url="https://book.lionairthai.com/bookrr_api/api/add/pax",
            headers=self._headers(
                "https://www.lionairthai.com",
                "https://www.lionairthai.com/",
                "application/json",
            ),
            data=data,
            allow_redirects=False,
        )
        return self._response_json(response)

    def get_booking_cart(self) -> dict:
        referer = f"https://payment.lionairthai.com/?token={self._token}"
        response = self._tls.get(
            url="https://cart.lionairthai.com/cartrr_api/api/Get/BookingCart",
            headers=self._headers("https://payment.lionairthai.com", referer),
            allow_redirects=False,
        )
        return self._response_json(response)

    def payment(self, data: dict) -> dict:
        referer = f"https://payment.lionairthai.com/?token={self._token}"
        response = self._tls.post(
            url="https://payment.lionairthai.com/payment_api/api/_2c2p/Payment",
            headers=self._headers(
                "https://payment.lionairthai.com",
                referer,
                "application/json",
            ),
            data={"payload": self._encrypt(data)},
            timeout=90,
            allow_redirects=False,
        )
        encrypted = self._response_json(response).get("response")
        if not encrypted:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION)
        return self._decrypt(encrypted)
