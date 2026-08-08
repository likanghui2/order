import base64
import gzip
import json
import random
import re
import urllib.parse
import uuid
from typing import Optional
from urllib.parse import parse_qs, urlparse

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.nocaptcha_util import NoCaptchaUtil
from flights.malaysiaairlines_mh.config import MalaysiaAirlinesConfig

API_BASE = "https://api-des.malaysiaairlines.com"
WEB_BASE = "https://online.malaysiaairlines.com"
REESE84_URL = (
    f"{WEB_BASE}/eyward-both-in-good-milld-Ile-his-shough-them-th/"
    "1C6gqW7DCJxcjna2gXOHEpZ86Z_N1PlOqK21enI-F7g"
)


class WebScript:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self._proxy_info = proxy_info
        self._tls = CurlCffiTls()
        self._timeout = 60
        self._ua = MalaysiaAirlinesConfig.USER_AGENT
        chrome_version = re.search(r"Chrome/(\d+)", self._ua).group(1)
        self._sec_ch_ua = (
            f'"Google Chrome";v="{chrome_version}", '
            f'"Chromium";v="{chrome_version}", "Not A(Brand";v="24"'
        )
        self._x_d_token = ""
        self._authorization = ""
        self._client_facts = ""
        self._currency = ""
        self._client_ref = f"{uuid.uuid4()}:1"
        self.incapsula_url = ""

    @property
    def currency(self) -> str:
        return self._currency

    def initialize_session(self):
        self._tls.initialize(self._proxy_info, impersonate="chrome146")

    def close(self):
        session = self._tls.get_session()
        if session is not None:
            session.close()

    def __incapsula_get_jwt_token(self, verify_url: str):
        headers = {
            "Connection": "keep-alive",
            "sec-ch-ua-platform": "\"Windows\"",
            "User-Agent": self._ua,
            "Accept": "application/json; charset=utf-8",
            "Content-Type": "text/plain; charset=utf-8",
            "sec-ch-ua-mobile": "?0",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "es,en-US;q=0.9,en;q=0.8"
        }

        response = self._tls.post(url=verify_url, headers=headers, json={"f": "gpc"})
        return response.to_text().strip('"')

    def reese84(self):
        try:
            import requests

            ua_vision = random.randint(145, 145)
            self._ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ua_vision}.0.0.0 Safari/537.36"
            sec_ch_ua = f"\"Not:A-Brand\";v=\"99\", \"Google Chrome\";v=\"{ua_vision}\", \"Chromium\";v=\"{ua_vision}\""

            script_url = REESE84_URL

            headers = {
                "pragma": "no-cache",
                "cache-control": "no-cache",
                "sec-ch-ua-platform": "\"Windows\"",
                "user-agent": self._ua,
                "sec-ch-ua": sec_ch_ua,
                "sec-ch-ua-mobile": "?0",
                "accept": "*/*",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "no-cors",
                "sec-fetch-dest": "script",
                "accept-language": "en-US,en;q=0.9",
            }
            r = requests.get(url=script_url, headers=headers, timeout=60)
            incapsula_js = r.text

            captcha_url = f"{script_url}?d=online.malaysiaairlines.com"

            service_url = f'http://156.225.30.65:9994/api/UUEM3XIA/get_reese84V2'
            KEY = 'UUEM3XIA'
            headers = {
                "apiKey": KEY,
                "Content-Encoding": "gzip",  # 多了这个
            }
            json_data = {"captcha_url": captcha_url,
                         "ua": self._ua,
                         "incapsula_js": incapsula_js,
                         "jwtToken": self.__incapsula_get_jwt_token(captcha_url),
                         # "appVersion": appVersion,  # 多了这个
                         # "ua": UA,  # 多了这个
                         }
            json_data = gzip.compress(json.dumps(json_data).encode('utf-8'))  # 添加这一行代码进行压缩
            resp = requests.post(service_url, headers=headers, data=json_data)  # json=json_data变为data=json_data
            submit_data_84 = resp.json()['result']

            headers = {
                "sec-ch-ua-platform": "\"Windows\"",
                "user-agent": self._ua,
                # "sec-ch-ua": self.,
                "sec-ch-ua-mobile": "?0",
                "accept": "*/*",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "no-cors",
                "sec-fetch-dest": "script",
                "accept-language": 'en-US,en;q=0.9'
            }
            response = self._tls.post(
                url=captcha_url,
                headers=headers,
                data=submit_data_84,
                timeout=10
            )
            self._x_d_token = response.to_dict()['token']
        except Exception as e:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION)

    def get_reese84(self):
        proxy = (
            self._proxy_info.get_proxy_info_to_string()
            if self._proxy_info is not None
            else None
        )
        self._x_d_token = DanLiCaptchaUtil(
            MalaysiaAirlinesConfig.DANLI_APP_ID
        ).incapsula_token_get(
            verify_url=REESE84_URL,
            user_agent=self._ua,
            host="online.malaysiaairlines.com",
            proxy_data=proxy,
            jwt_required=True,
        )

    def init_facts(self, data: dict):
        response = self._tls.post(
            url="https://www.malaysiaairlines.com/bin/mh/revamp/flightSearch",
            headers=self._portal_headers(),
            data=data,
            timeout=self._timeout,
        )
        self._expect(response, 200)
        self._client_facts = (response.to_dict().get("payload") or {}).get("privateFacts") or ""

    def promo_code_search(self, data: dict):
        response = self._tls.post(
            url="https://www.malaysiaairlines.com/bin/mh/revamp/flightSearch",
            headers=self._portal_headers(),
            data=data,
            timeout=self._timeout,
        )
        self._expect(response, 200)
        payload = response.to_dict().get("payload") or {}
        facts = {"sub": "fact"}
        for item in json.loads(payload.get("portalFacts") or "[]"):
            facts[item["key"]] = item["value"]
        public_facts = base64.b64encode(
            json.dumps(facts, ensure_ascii=False, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        self._client_facts = (
            f"eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.{public_facts}., "
            f"{payload.get('privateFacts') or ''}"
        )

    def initialization(self, currency: str):
        office_id = MalaysiaAirlinesConfig.CURRENCY_KEY.get(currency)
        if not office_id:
            raise ServiceError(
                ServiceStateEnum.BUSINESS_ERROR,
                f"MH 暂不支持币种 {currency}",
            )
        response = self._tls.post(
            url=f"{API_BASE}/v1/security/oauth2/token/initialization",
            headers={
                "User-Agent": self._ua,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": f"{WEB_BASE}/",
                "content-type": "application/x-www-form-urlencoded",
                "x-d-token": self._x_d_token,
                "Origin": WEB_BASE,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
            },
            data=urllib.parse.urlencode({
                "client_id": MalaysiaAirlinesConfig.OAUTH_CLIENT_ID,
                "client_secret": MalaysiaAirlinesConfig.OAUTH_CLIENT_SECRET,
                "fact": json.dumps({
                    "keyValuePairs": [{"key": "officeId", "value": office_id}]
                }),
                "grant_type": "client_credentials",
            }),
            timeout=self._timeout,
        )
        self._expect(response, 200)
        self._authorization = f"Bearer {response.to_dict()['access_token']}"
        self._currency = currency

    def search_flight(
            self,
            airport_data: list[tuple[str, str, str]],
            adult_count: int,
            child_count: int,
            requested_bound: int = 0,
            promo_code: str = "",
            selected_bound_id: Optional[str] = None,
    ) -> dict:
        travelers = []
        for count, code in ((adult_count, "ADT"), (child_count, "CHD")):
            travelers.extend({"passengerTypeCode": code} for _ in range(count))
        data = {
            "commercialFareFamilies": ["CFFECO"],
            "itineraries": [
                {
                    "departureDateTime": route[2],
                    "originLocationCode": route[0],
                    "destinationLocationCode": route[1],
                    "isRequestedBound": index == requested_bound,
                }
                for index, route in enumerate(airport_data)
            ],
            "travelers": travelers,
            "searchPreferences": {"showMilesPrice": False},
            "promotion": {"code": promo_code},
        }
        if selected_bound_id:
            data["selectedBoundId"] = selected_bound_id
        response = self._tls.post(
            url=f"{API_BASE}/airlines/MH/v2/search/air-bounds",
            headers=self._api_headers(),
            data=data,
            timeout=self._timeout,
        )
        text = response.to_text()
        if "Request unsuccessful. Incapsula incident" in text:
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
        if "NO FLIGHTS FOUND" in text:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        self._expect(response, 200)
        return response.to_dict()

    def select_flight(self, air_bound_ids: list[str]) -> dict:
        response = self._tls.post(
            url=f"{API_BASE}/airlines/MH/v2/shopping/carts",
            headers=self._api_headers(),
            data={"airBoundIds": air_bound_ids},
            timeout=self._timeout,
        )
        self._expect(response, 201)
        return response.to_dict()

    def add_passengers(self, cart_id: str, last_name: str, data: dict) -> dict:
        query = urllib.parse.urlencode({
            "lastName": last_name,
            "lang": "zh",
            "includeWaitlist": "false",
        })
        response = self._tls.patch(
            url=f"{API_BASE}/airlines/MH/v2/shopping/carts/{cart_id}?{query}",
            headers=self._api_headers(),
            data=data,
            timeout=self._timeout,
        )
        self._expect(response, 200)
        return response.to_dict()

    def purchase_order(self, cart_id: str) -> dict:
        query = urllib.parse.urlencode({"cartId": cart_id, "lang": "en"})
        response = self._tls.post(
            url=f"{API_BASE}/airlines/MH/v2/purchase/orders?{query}",
            headers=self._api_headers(),
            data={},
            timeout=self._timeout,
        )
        text = response.to_text()
        if "Incapsula_Resource" in text:
            match = re.search(r'<iframe[^>]+src="([^"]+)"', text)
            if match:
                query_data = parse_qs(urlparse(match.group(1)).query)
                incident_id = query_data.get("incident_id", [""])[0]
                dai = incident_id.split("-")[-1]
                cts = query_data.get("cts", [""])[0]
                self.incapsula_url = (
                    f"{API_BASE}/_Incapsula_Resource?SWCGHOEL=v2"
                    f"&dai={dai}&cts={cts}"
                )
            raise ServiceError(ServiceStateEnum.HCAP_RISK_CHECK_FAILED)
        self._expect(response, 201)
        return response.to_dict()

    def solve_purchase_captcha(self):
        if not self.incapsula_url:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "incapsula_url")
        result = NoCaptchaUtil(
            MalaysiaAirlinesConfig.NOCAPTCHA_API_KEY
        ).hcaptcha(
            site_key="e94865c2-4231-4c25-9c6e-2b797b2b56cf",
            referer="http://api-des.malaysiaairlines.com",
        )
        data = result.get("data") or {}
        token = (
                data.get("generated_pass_UUID")
                or data.get("token")
                or data.get("response")
        )
        if not token:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)
        response = self._tls.post(
            url=self.incapsula_url,
            headers={
                "User-Agent": self._ua,
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded",
                "x-spa": "1",
                "x-d-token": self._x_d_token,
                "Origin": API_BASE,
            },
            data=urllib.parse.urlencode({"g-recaptcha-response": token}),
            timeout=self._timeout,
        )
        self._expect(response, 200)

    def _portal_headers(self) -> dict:
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://www.malaysiaairlines.com",
            "Referer": "https://www.malaysiaairlines.com/cn/zh_CN/home.html",
            "User-Agent": self._ua,
            "sec-ch-ua": self._sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

    def _api_headers(self) -> dict:
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": self._ua,
            "Referer": f"{WEB_BASE}/",
            "ama-client-ref": self._client_ref,
            "authorization": self._authorization,
            "content-type": "application/json",
            "x-d-token": self._x_d_token,
            "x-spa": "1",
            "Origin": WEB_BASE,
            "sec-ch-ua": self._sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        if self._client_facts:
            headers["ama-client-facts"] = self._client_facts
        return headers

    @staticmethod
    def _expect(response, expected_status: int):
        if response.status != expected_status:
            raise ServiceError(
                ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                response.status,
            )
