import base64
import json
import re
import urllib.parse
import uuid
from typing import Optional

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.nocaptcha_util import NoCaptchaUtil
from flights.sunphuquocairways_9g.config import Config


class WebScript:
    def __init__(
        self,
        proxy_info: Optional[ProxyInfoModel] = None,
        tls=None,
        captcha=None,
        hcaptcha=None,
    ):
        self._proxy_info = proxy_info
        self._tls = tls or CurlCffiTls()
        self._captcha = captcha or DanLiCaptchaUtil(Config.INCAPSULA_APP_ID)
        self.hcaptcha = hcaptcha or NoCaptchaUtil(Config.WEB_HCAPTCHA_API_KEY)
        self.authorization = ""
        self.country_code = ""
        self.currency = ""
        self.client_facts = ""
        self.x_d_token = ""
        self.incapsula_url = ""
        self._client_id = str(uuid.uuid4())
        self._request_counter = 0
        self.timeout = 60

    @property
    def tls(self):
        return self._tls

    @property
    def proxy_info(self):
        return self._proxy_info

    def initialize_session(self) -> None:
        self._tls.initialize(self._proxy_info, impersonate="chrome146")

    @staticmethod
    def compact_json(value) -> str:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def build_client_facts(country_code: str) -> str:
        payload = base64.urlsafe_b64encode(
            WebScript.compact_json({"sub": "fact", "countryCode": country_code}).encode()
        ).decode().rstrip("=")
        return f"eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.{payload}."

    def authenticate(self, currency: str) -> dict:
        context = Config.web_currency_context(currency)
        self.currency = context["currency"]
        self.country_code = context["country_code"]
        self.client_facts = self.build_client_facts(self.country_code)
        if not self.x_d_token:
            self.x_d_token = self._captcha.incapsula_token_get(
                verify_url=Config.INCAPSULA_URL,
                proxy_data=self._proxy_string(),
                host="fly.sunphuquocairways.com",
                jwt_required=False,
                user_agent=Config.USER_AGENT,
            )
        fact = self.compact_json(
            {"keyValuePairs": [{"key": "countryCode", "value": self.country_code}]}
        )
        body = urllib.parse.urlencode(
            {
                "client_id": Config.WEB_OAUTH_CLIENT_ID,
                "client_secret": Config.WEB_OAUTH_CLIENT_SECRET,
                "fact": fact,
                "grant_type": "client_credentials",
            }
        )
        response = self._tls.post(
            url=f"{Config.WEB_API_BASE}/v1/security/oauth2/token/initialization",
            headers=self._oauth_headers(),
            data=body,
            timeout=self.timeout,
        )
        data = self._response_json(response, 200)
        access_token = data.get("access_token")
        if not access_token:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "9GWEB鉴权响应缺少access_token")
        self.authorization = f"Bearer {access_token}"
        return data

    def search(
        self,
        airport_data: list[tuple[str, str, str]],
        adult_count: int,
        child_count: int,
        promo_code: str = "",
    ) -> dict:
        payload = {
            "commercialFareFamilies": ["9GBUZ", "9GECO"],
            "itineraries": [
                {
                    "departureDateTime": flight_date,
                    "originLocationCode": departure,
                    "destinationLocationCode": arrival,
                    "isRequestedBound": True,
                }
                for departure, arrival, flight_date in airport_data
            ],
            "travelers": [
                *({"passengerTypeCode": "ADT"} for _ in range(adult_count)),
                *({"passengerTypeCode": "CHD"} for _ in range(child_count)),
            ],
            "promotion": {"code": promo_code or ""},
            "searchPreferences": {"showSoldOut": False, "showMilesPrice": False},
        }
        return self._json_request(
            "post",
            "/v2/search/air-bounds",
            payload,
            200,
        )

    def create_cart(self, air_bound_ids: list[str]) -> dict:
        return self._json_request(
            "post",
            "/v2/shopping/carts",
            {"airBoundIds": air_bound_ids},
            201,
        )

    def update_traveler(
        self,
        cart_id: str,
        traveler_id: str,
        traveler: dict,
        last_name: str,
    ) -> dict:
        query = urllib.parse.urlencode({"lastName": last_name, "includeWaitlist": "false"})
        return self._json_request(
            "patch",
            f"/v2/shopping/carts/{urllib.parse.quote(cart_id)}/travelers/"
            f"{urllib.parse.quote(traveler_id)}?{query}",
            traveler,
            200,
        )

    def add_contacts(self, cart_id: str, contacts: list[dict], last_name: str) -> dict:
        query = urllib.parse.urlencode({"lastName": last_name})
        return self._json_request(
            "post",
            f"/v2/shopping/carts/{urllib.parse.quote(cart_id)}/contacts?{query}",
            contacts,
            201,
        )

    def purchase_order(self, cart_id: str) -> dict:
        query = urllib.parse.urlencode({"cartId": cart_id})
        return self._json_request("post", f"/v2/purchase/orders?{query}", {}, 201)

    def services_by_order(self, pnr: str, last_name: str) -> dict:
        query = urllib.parse.urlencode(
            {"orderId": pnr, "lastName": last_name, "showMilesPrice": "false"}
        )
        return self._json_request("get", f"/v2/shopping/services/by-order?{query}", None, 200)

    def add_services(self, pnr: str, last_name: str, services: list[dict]) -> dict:
        query = urllib.parse.urlencode({"lastName": last_name})
        return self._json_request(
            "post",
            f"/v2/purchase/orders/{urllib.parse.quote(pnr)}/services?{query}",
            {"services": services},
            201,
        )

    def payment_methods(self, pnr: str, last_name: str) -> dict:
        payload = {
            "orderId": pnr,
            "paymentRequests": [
                {
                    "paymentMethod": {
                        "paymentType": "CheckoutFormPayment",
                        "parameters": {
                            "links": [
                                {
                                    "rel": "postRedirection",
                                    "href": f"{Config.WEB_ORIGIN}/booking/payment",
                                }
                            ]
                        },
                    }
                }
            ],
        }
        query = urllib.parse.urlencode({"lastName": last_name})
        return self._json_request(
            "post", f"/v2/purchase/payment-methods?{query}", payload, 200
        )

    def payment_action(self, payload: dict) -> dict:
        response = self._tls.post(
            url="https://paypages.payment.amadeus.com/1ASIATP/ARIAPP/pay",
            headers=self._payment_headers(),
            data=self.compact_json(payload),
            timeout=self.timeout,
        )
        return self._response_json(response, 200)

    def payment_records(self, pnr: str, last_name: str, payload: dict) -> dict:
        query = urllib.parse.urlencode({"lastName": last_name})
        return self._json_request(
            "post",
            f"/v2/purchase/orders/{urllib.parse.quote(pnr)}/payment-records?{query}",
            payload,
            (200, 201),
        )

    def get_itinerary(self, pnr: str, last_name: str) -> dict:
        query = urllib.parse.urlencode(
            {
                "lastName": last_name,
                "showOrderEligibilities": "true",
                "checkServicesAndSeatsIssuanceCurrency": "false",
            }
        )
        return self._json_request(
            "get", f"/v2/purchase/orders/{urllib.parse.quote(pnr)}?{query}", None, 200
        )

    def get_baggage(self, pnr: str, last_name: str) -> dict:
        query = urllib.parse.urlencode({"orderId": pnr, "lastName": last_name, "lang": "GB"})
        return self._json_request("get", f"/v2/shopping/baggage-policies?{query}", None, 200)

    def solve_hcaptcha(self) -> None:
        if not self.incapsula_url:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "9GWEB缺少人机验证地址")
        result = self.hcaptcha.hcaptcha(
            site_key=Config.WEB_HCAPTCHA_SITE_KEY,
            referer="https://api-des.sunphuquocairways.com",
            proxy=self._proxy_string(),
        )
        token = self._find_token(result)
        if not token:
            raise ServiceError(ServiceStateEnum.HCAP_RISK_CHECK_FAILED)
        response = self._tls.post(
            url=self.incapsula_url,
            headers={
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": Config.WEB_API_BASE,
                "User-Agent": Config.USER_AGENT,
                "x-d-token": self.x_d_token,
                "x-spa": "1",
            },
            data=urllib.parse.urlencode({"g-recaptcha-response": token}),
            timeout=self.timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    def _json_request(self, method: str, path: str, payload, expected_status) -> dict:
        request = getattr(self._tls, method)
        kwargs = {
            "url": f"{Config.WEB_API_BASE}{path}",
            "headers": self._api_headers(),
            "timeout": self.timeout,
        }
        if method != "get":
            kwargs["data"] = self.compact_json(payload)
        response = request(**kwargs)
        return self._response_json(response, expected_status)

    def _api_headers(self) -> dict[str, str]:
        self._request_counter += 1
        headers = {
            "Accept": "application/json",
            "Accept-Language": "es,en-US;q=0.9,en;q=0.8",
            "ama-client-ref": f"{self._client_id}:{self._request_counter}",
            "authorization": self.authorization,
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "Origin": Config.WEB_ORIGIN,
            "Referer": f"{Config.WEB_ORIGIN}/",
            "User-Agent": Config.USER_AGENT,
            "x-d-token": self.x_d_token,
            "x-spa": "1",
        }
        if self.client_facts:
            headers["ama-client-facts"] = self.client_facts
        return headers

    def _oauth_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": Config.WEB_ORIGIN,
            "Referer": f"{Config.WEB_ORIGIN}/",
            "User-Agent": Config.USER_AGENT,
            "x-d-token": self.x_d_token,
            "x-spa": "1",
        }

    @staticmethod
    def _payment_headers() -> dict[str, str]:
        return {
            "Accept": "*/*",
            "amadeus-checkout-sdk-flavor": "Core-Sdk",
            "amadeus-checkout-sdk-host": "fly.sunphuquocairways.com",
            "amadeus-checkout-sdk-version": "WEB/5.7.0/1cb83a3",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://prd.payment.amadeus.com",
            "Referer": "https://prd.payment.amadeus.com/",
            "User-Agent": Config.USER_AGENT,
        }

    def _response_json(self, response, expected_status, allow_empty: bool = False) -> dict:
        text = response.to_text()
        upper_text = text.upper()
        if "NO FLIGHTS FOUND" in upper_text or "NO AVAILABLE FLIGHT" in upper_text:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        if "INCAPSULA_RESOURCE" in upper_text or "INCAPSULA INCIDENT ID" in upper_text:
            self._remember_challenge_url(text)
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
        statuses = (expected_status,) if isinstance(expected_status, int) else tuple(expected_status)
        if response.status not in statuses:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if allow_empty and not text.strip():
            return {}
        try:
            data = response.to_dict()
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            if allow_empty and not text.strip():
                return {}
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "9GWEB响应不是有效JSON")
        if not isinstance(data, dict):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "9GWEB响应不是JSON对象")
        if data.get("errors") or data.get("error") or data.get("success") is False:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)
        return data

    def _remember_challenge_url(self, text: str) -> None:
        match = re.search(r'<iframe[^>]+src=["\']([^"\']+)', text, re.IGNORECASE)
        if not match:
            return
        source = urllib.parse.urljoin(Config.WEB_API_BASE, match.group(1))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(source).query)
        incident_id = query.get("incident_id", [""])[0]
        cts = query.get("cts", [""])[0]
        if incident_id and cts:
            dai = incident_id.split("-")[-1]
            self.incapsula_url = (
                f"{Config.WEB_API_BASE}/_Incapsula_Resource?SWCGHOEL=v2"
                f"&dai={urllib.parse.quote(dai)}&cts={urllib.parse.quote(cts)}"
            )

    def _proxy_string(self) -> Optional[str]:
        if not self._proxy_info:
            return None
        return self._proxy_info.get_proxy_info_to_string()

    @classmethod
    def _find_token(cls, value) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (tuple, list)):
            for item in value:
                token = cls._find_token(item)
                if token:
                    return token
        if isinstance(value, dict):
            direct = value.get("token") or value.get("generated_pass_UUID")
            if direct:
                return str(direct)
            for key in ("data", "result"):
                token = cls._find_token(value.get(key))
                if token:
                    return token
        return ""
