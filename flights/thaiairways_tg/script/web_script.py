import json
import re
import uuid
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.nocaptcha_util import NoCaptchaUtil
from flights.thaiairways_tg.config import ThaiairwaysConfig

API_BASE = "https://api-des.thaiairways.com"
DANLI_CAPTCHA = DanLiCaptchaUtil("m05cmm7ub8vm1pgasjpo8sdp9tl6mkzp")
NO_CAPTCHA = NoCaptchaUtil("e05b056e-3d13-494e-af0d-b934bff84220")
REESE84_URL = (
    "https://ibooking.thaiairways.com/"
    "y-Almost-yet-know-Now-Son-ther-That-swearers-of-/"
    "3nOsRQ8irc_ZtcVNrFJG8gbVR_3mK-NK2L-00vw-NqY"
)


class WebScript:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__proxy_info = proxy_info
        self.__tls = CurlCffiTls()
        self.__ua = ThaiairwaysConfig.UA
        self.__uuid = str(uuid.uuid4())
        self.client_facts = (
            "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
            "eyJzdWIiOiJmYWN0IiwiY291bnRyeUNvZGUiOiJYWCIsIkVYVEVSTkFMX0lEMSI6IkhLX05PUk1BTCIsIkVYVEVSTkFMX0lEOSI6Ikhvbmdrb25nIn0., "
            "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
            "eyJzdWIiOiJmYWN0Iiwia2lzYUxpc3RPZklkcyI6bnVsbCwia2lzYUd1YXJkaWFuVHlwZSI6bnVsbCwia2lzYUd1YXJkaWFuTmFtZXMiOm51bGx9."
        )
        self.__x_d_token = ""
        self.__authorization = ""
        self.__booking_authorization = None
        self.__booking_session_id = None
        self.incapsula_url = None

    def initialize_session(self):
        self.__tls.initialize(self.__proxy_info, impersonate="chrome120")

    def get_reese84(self):
        self.__x_d_token = DANLI_CAPTCHA.incapsula_token_get(
            verify_url=REESE84_URL,
            user_agent=self.__ua,
            host="ibooking.thaiairways.com",
            proxy_data=self.__proxy_info.get_proxy_info_to_string() if self.__proxy_info else None,
            jwt_required=True,
        )

    def initialization(self):
        headers = {
            "Host": "api-des.thaiairways.com",
            "accept": "application/json",
            "accept-language": "zh",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://ibooking.thaiairways.com",
            "referer": "https://ibooking.thaiairways.com",
            "user-agent": self.__ua,
            "x-d-token": self.__x_d_token,
        }
        response = self.__tls.post(
            url=f"{API_BASE}/v1/security/oauth2/token/initialization",
            headers=headers,
            data=urlencode({
                "client_id": "Tvo4Eu9jjEs9T6kDWKVTgM8YsiuStBQb",
                "client_secret": "pEHXXOGeexcbP0xu",
                "fact": json.dumps({
                    "keyValuePairs": [
                        {"key": "originLocationCode1", "value": "CAN"},
                        {"key": "destinationLocationCode1", "value": "BKK"},
                        {"key": "departureDateTime1", "value": "2025-09-21"},
                        {"key": "countryCode", "value": "CN"},
                        {"key": "EXTERNAL_ID1", "value": "CN_NORMAL"},
                        {"key": "EXTERNAL_ID9", "value": "China"},
                    ]
                }),
                "grant_type": "client_credentials",
            }),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        self.__authorization = "Bearer " + response.to_dict()["access_token"]

    def search_flight(self, data: dict) -> dict:
        headers = {
            "Host": "api-des.thaiairways.com",
            "user-agent": self.__ua,
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "referer": "https://ibooking.thaiairways.com/",
            "ama-client-facts": self.client_facts,
            "ama-client-ref": self.__uuid,
            "authorization": self.__authorization,
            "x-d-token": self.__x_d_token,
            "origin": "https://ibooking.thaiairways.com",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "cache-control": "no-cache",
            "pragma": "no-cache",
        }
        response = self.__tls.post(
            url=f"{API_BASE}/v2/search/air-bounds",
            headers=headers,
            data=json.dumps(data),
            timeout=60,
        )
        if "NO FLIGHTS FOUND" in response.to_text():
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def auth_www(self, airport_data: list[tuple[str, str, str]]):
        first_route = airport_data[0]
        headers = {
            "Host": "www.thaiairways.com",
            "user-agent": self.__ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-cn",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "origin": "https://www.thaiairways.com",
            "referer": "https://www.thaiairways.com/booking/select-flight/",
            "source": "website",
            "hostName": "https://www.thaiairways.com",
            "channel": "online",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "ama-client-ref": self.__uuid,
        }
        response = self.__tls.post(
            url='https://www.thaiairways.com/flight/auth',
            headers=headers,
            data=json.dumps({
                "itineraries": [
                    {
                        "id": 1,
                        "originLocationCode": first_route[0],
                        "destinationLocationCode": first_route[1],
                        "departureDateTime": f"{first_route[2]}T00:00:00.000"
                    }
                ],
                "facts": {
                    "EXTERNAL_ID1": "IN_NORMAL",
                    "EXTERNAL_ID9": "India"
                },
                "officeId": None,
                "countryCode": "cn",
                "languageCode": "en",
                "user": "website",
                "userGroup": "online"
            }),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        data = response.to_dict()
        self.__booking_authorization = f"{data['token_type']} {data['access_token']}"
        self.__booking_session_id = next(
            (value for key, value in response.headers.items() if key.lower() == "booking_session_id"),
            None
        )

    def www_search_flight(self, data: dict) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/flight/search/air-bounds',
            headers=self.__www_headers("https://www.thaiairways.com/booking/select-flight/"),
            data=json.dumps(data),
            timeout=60,
        )
        if "NO FLIGHTS FOUND" in response.to_text():
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def sell_flight(self, keys: list[str]) -> dict:
        headers = {
            "Host": "api-des.thaiairways.com",
            "user-agent": self.__ua,
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "referer": "https://ibooking.thaiairways.com/",
            "ama-client-facts": self.client_facts,
            "ama-client-ref": self.__uuid,
            "authorization": self.__authorization,
            "x-d-token": self.__x_d_token,
            "origin": "https://ibooking.thaiairways.com",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0",
            "cache-control": "max-age=0",
            "te": "trailers",
        }
        response = self.__tls.post(
            url=f"{API_BASE}/v2/shopping/carts",
            headers=headers,
            data=json.dumps({"airBoundIds": keys}),
            timeout=60,
        )
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def add_passenger(self, url: str, data: dict) -> dict:
        headers = {
            "user-agent": self.__ua,
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "referer": "https://ibooking.thaiairways.com/",
            "ama-client-facts": self.client_facts,
            "ama-client-ref": self.__uuid,
            "authorization": self.__authorization,
            "x-d-token": self.__x_d_token,
            "origin": "https://ibooking.thaiairways.com",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0",
            "cache-control": "max-age=0",
            "te": "trailers",
        }
        response = self.__tls.patch(
            url=url,
            headers=headers,
            data=json.dumps(data),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def add_contacts(self, cart_id: str, last_name: str, data: list[dict]) -> dict:
        headers = {
            "user-agent": self.__ua,
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "referer": "https://ibooking.thaiairways.com/",
            "ama-client-facts": self.client_facts,
            "ama-client-ref": self.__uuid,
            "authorization": self.__authorization,
            "x-d-token": self.__x_d_token,
            "origin": "https://ibooking.thaiairways.com",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0",
            "cache-control": "max-age=0",
            "te": "trailers",
        }
        response = self.__tls.post(
            url=f"{API_BASE}/v2/shopping/carts/{cart_id}/contacts?lastName={last_name}",
            headers=headers,
            data=json.dumps(data),
            timeout=60,
        )
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def h_getcaptcha(self) -> str:
        captcha_data = NO_CAPTCHA.hcaptcha(
            site_key="e94865c2-4231-4c25-9c6e-2b797b2b56cf",
            referer="http://api-des.thaiairways.com",domain="hcaptcha.com",
            proxy=self.__proxy_info.get_proxy_info_to_string() if self.__proxy_info else None,region=self.__tls.get_proxy_data().region
        )
        if isinstance(captcha_data, str):
            return captcha_data
        if isinstance(captcha_data, (tuple, list)) and captcha_data:
            return captcha_data[0]
        if isinstance(captcha_data, dict):
            data = captcha_data.get("data")
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                for key in ("generated_pass_UUID", "token", "pass_UUID", "gRecaptchaResponse"):
                    if data.get(key):
                        return data[key]
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "hcaptcha")

    def verify(self, token: str):
        if not self.incapsula_url:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "incapsula_url")
        headers = {
            "User-Agent": self.__ua,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "x-spa": "1",
            "x-d-token": self.__x_d_token,
            "Origin": "https://api-des.thaiairways.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        response = self.__tls.post(
            url=self.incapsula_url,
            headers=headers,
            data=urlencode({"g-recaptcha-response": token}),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    def orders(self, cart_id: str) -> dict:
        headers = {
            "user-agent": self.__ua,
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "referer": "https://ibooking.thaiairways.com/",
            "ama-client-facts": self.client_facts,
            "ama-client-ref": self.__uuid,
            "authorization": self.__authorization,
            "x-d-token": self.__x_d_token,
            "origin": "https://ibooking.thaiairways.com",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0",
            "cache-control": "max-age=0",
            "te": "trailers",
        }
        response = self.__tls.post(
            url=f"{API_BASE}/v2/purchase/orders?cartId={cart_id}",
            headers=headers,
            data={},
            timeout=60,
        )
        response_text = response.to_text()
        if response.status == 403:
            raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, response.status)
        if "Incapsula_Resource" in response_text:
            match = re.search(r'<iframe[^>]+src="([^"]+)"', response_text)
            if not match:
                raise ServiceError(ServiceStateEnum.HCAP_RISK_CHECK_FAILED)
            qs = parse_qs(urlparse(match.group(1)).query)
            incident_id = (qs.get("incident_id") or [""])[0]
            cts = (qs.get("cts") or [""])[0]
            if not incident_id or not cts:
                raise ServiceError(ServiceStateEnum.HCAP_RISK_CHECK_FAILED)
            dai = incident_id.split("-")[-1]
            self.incapsula_url = f"{API_BASE}/_Incapsula_Resource?SWCGHOEL=v2&dai={dai}&cts={cts}"
            raise ServiceError(ServiceStateEnum.HCAP_RISK_CHECK_FAILED)
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_sell_flight(self, keys: list[str]) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/',
            headers=self.__www_headers("https://www.thaiairways.com/booking/select-flight/"),
            data=json.dumps({"airBoundIds": keys}),
            timeout=60,
        )
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_retrieve_cart(self, cart_id: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/retrieve',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps({"cartId": cart_id}),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_baggage_policies(self, cart_id: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/flight/baggage/policies',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps({"cartId": cart_id}),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_add_passenger(self, data: dict) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/traveler',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps(data),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_add_contacts(self, data: dict) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/contact',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps(data),
            timeout=60,
        )
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_duplicate_traveler(self, cart_id: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/traveler/duplicate',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps({"cartId": cart_id}),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_orders(self, cart_id: str, travelers: list[dict]) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/order/',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps({
                "cartId": cart_id,
                "travelers": travelers,
            }),
            timeout=60,
        )
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_order_retrieve(self, order_id: str, last_name: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/order/retrieve',
            headers=self.__www_headers("https://www.thaiairways.com/booking/extra-services/"),
            data=json.dumps({
                "lastName": last_name,
                "orderId": order_id,
            }),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_order_baggage_policies(self, order_id: str, last_name: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/flight/baggage/policies',
            headers=self.__www_headers("https://www.thaiairways.com/booking/extra-services/"),
            data=json.dumps({
                "lastName": last_name,
                "orderId": order_id,
            }),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_ancillaries_catalogue(self, order_id: str, last_name: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/ancillaries/service/catalogue',
            headers=self.__www_headers("https://www.thaiairways.com/booking/extra-services/"),
            data=json.dumps({
                "lastName": last_name,
                "orderId": order_id,
            }),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_payment_init(self, order_id: str, last_name: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/order/payment/init',
            headers=self.__www_headers("https://www.thaiairways.com/booking/extra-services/"),
            data=json.dumps({
                "lastName": last_name,
                "orderId": order_id,
                "module": "BOOKING",
            }),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def www_payment_process(self, url: str) -> str:
        response = self.__tls.get(
            url=url,
            headers=self.__www_page_headers(referer="https://payment.paco.2c2p.com/"),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def www_ticketing_payment_status(self, order_number: str, referer: str) -> dict:
        response = self.__tls.post(
            url="https://www.thaiairways.com/ticketing/payment/status",
            headers=self.__www_headers(referer),
            data=json.dumps({"orderNumber": str(order_number)}),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def paco_payment_page_ui(self, payment_id: str) -> dict:
        response = self.__tls.get(
            url=f"https://payment-api.paco.2c2p.com/1.0/Payment/paymentPageUI/{payment_id}",
            headers=self.__paco_headers(),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def paco_server_public_key(self) -> str:
        response = self.__tls.get(
            url="https://payment-api.paco.2c2p.com/1.0/Security/getServerPublicKey",
            headers=self.__paco_headers(),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        try:
            data = response.to_dict()
        except json.JSONDecodeError:
            return response.to_text().strip().strip('"')

        if isinstance(data, str):
            return data.strip().strip('"')
        if isinstance(data, dict):
            server_key = data.get("PublicKey") or data.get("publicKey") or data.get("data")
            if isinstance(server_key, dict):
                server_key = server_key.get("PublicKey") or server_key.get("publicKey")
            if server_key:
                return str(server_key).strip().strip('"')
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "serverPublicKey")

    def paco_check_card(self, office_guid: str, data: dict) -> dict:
        response = self.__tls.post(
            url=f"https://payment-api.paco.2c2p.com/1.0/Office/{office_guid}/checkCard",
            headers=self.__paco_headers(),
            data=data,
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def paco_card_holder_validate(self, data: dict) -> bool:
        response = self.__tls.post(
            url="https://payment-api.paco.2c2p.com/1.0/Payment/paymentPageUI/cardHolderValidate",
            headers=self.__paco_headers(),
            data=data,
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return bool(response.to_dict())

    def paco_payment_non_ui(self, data: dict, api_key: str, api_version: str = "1.0") -> dict:
        response = self.__tls.post(
            url=f"https://payment-api.paco.2c2p.com/{api_version}/Payment/NonUi",
            headers=self.__paco_headers(api_key=api_key),
            data=data,
            timeout=60,
        )
        if response.status not in [200, 400]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return self.__response_to_dict(response)

    def paco_payment_status(self, payment_id: str) -> dict:
        response = self.__tls.get(
            url=f"https://payment-api.paco.2c2p.com/1.0/Payment/status/{payment_id}?language=en",
            headers=self.__paco_headers(),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def __www_headers(self, referer: str, auth: bool = True) -> dict:
        headers = {
            "Host": "www.thaiairways.com",
            "user-agent": self.__ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-cn",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "origin": "https://www.thaiairways.com",
            "referer": referer,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "ama-client-ref": self.__uuid,
        }
        if auth and self.__booking_authorization:
            headers["booking_authorization"] = self.__booking_authorization
        if auth and self.__booking_session_id:
            headers["booking_session_id"] = self.__booking_session_id
        return headers

    def __www_page_headers(self, referer: str) -> dict:
        return {
            "Host": "www.thaiairways.com",
            "user-agent": self.__ua,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "referer": referer,
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "upgrade-insecure-requests": "1",
            "cache-control": "no-cache",
            "pragma": "no-cache",
        }

    def __paco_headers(self, api_key: str = None) -> dict:
        headers = {
            "Host": "payment-api.paco.2c2p.com",
            "user-agent": self.__ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "origin": "https://payment.paco.2c2p.com",
            "referer": "https://payment.paco.2c2p.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "cookie": "",
        }
        if api_key:
            headers["apiKey"] = api_key
        return headers

    @staticmethod
    def __response_to_dict(response) -> dict:
        response_text = response.to_text()
        if not response_text:
            return {"status": response.status}
        try:
            data = response.to_dict()
        except json.JSONDecodeError:
            data = response_text
        return {
            "status": response.status,
            "data": data,
        }
