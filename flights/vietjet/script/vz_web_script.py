import base64
import json
import random
import re
import string
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import requests

from common.decorators.retry_decorator import retry_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.string_util import StringUtil


class VZWebScript:
    BASE_URL = "https://th.vietjetair.com"
    RECAPTCHA_SITE_KEY = "6LduffQhAAAAAOGAwKT8RY4PHTR6qA-3ub1hP6U3"

    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__http_utils = CurlCffiTls()
        self.__proxy = proxy_info
        random_impersonate = random.choice(
            ["chrome119", "chrome120", "chrome123", "chrome131_android",
             "safari155", "safari153", "safari180",
             "firefox133", 'tor145', "safari", "safari_ios"])

        self.__http_utils.initialize(proxy_info_data=proxy_info, impersonate=random_impersonate)
        self.__timeout = 30
        self.__ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) Gecko/20100101 Firefox/150.0"
        self.csrf_token = None

    def initialize_session(self):
        self.__http_utils.initialize(proxy_info_data=self.__proxy)
        self.csrf_token = None

    def reset_proxy_ip(self):
        self.__http_utils.initialize(proxy_info_data=self.__proxy)
        self.csrf_token = None

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def initialize_csrf_token(self):
        d_str = (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")
        headers = {
            "accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
                "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
            ),
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "max-age=0",
            "user-agent": self.__ua,
        }
        response = self.__http_utils.get(
            url=(
                f"{self.BASE_URL}/flight?tripType=onewaytrip&currency=thb&from_where=BKK"
                f"&start={d_str}&to_where=HKT&end={d_str}&adultCount=1&childCount=0"
                f"&infantCount=0&promoCode=&findLowestFare="
            ),
            headers=headers,
            timeout=self.__timeout,
        )
        if response.status == 405:
            raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        html = response.to_text()
        match = re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)', html)
        if not match:
            match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']csrf-token["\']', html)
        if not match:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "VZ csrf token not found")
        self.csrf_token = match.group(1)
        return html

    def ensure_csrf_token(self):
        if not self.csrf_token:
            self.initialize_csrf_token()

    def update_csrf_token_from_html(self, html: str):
        match = re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)', html or "")
        if not match:
            match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']csrf-token["\']', html or "")
        if match:
            self.csrf_token = match.group(1)

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def search_flight(self, data: dict):
        self.ensure_csrf_token()
        params = {
            "tripType": data["tripType"],
            "from_where": data["from_where"],
            "to_where": data["to_where"],
            "start": data["start"],
            "end": data["end"],
            "adultCount": data["adultCount"],
            "childCount": data["childCount"],
            "infantCount": data["infantCount"],
            "promoCode": data["promoCode"],
            "currency": data["currency"],
        }
        referer = f"{self.BASE_URL}/flight?{urlencode({**params, 'findLowestFare': ''})}"
        encoded = base64.b64encode(json.dumps(params, separators=(",", ":")).encode("utf-8")).decode("utf-8")
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": self.BASE_URL,
            "referer": referer,
            "user-agent": self.__ua,
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest",
        }
        response = self.__http_utils.post(
            url=f"{self.BASE_URL}/flight/getFlights?{urlencode(params)}",
            headers=headers,
            data=urlencode({"data": encoded}, doseq=True),
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        result = response.to_dict()
        if result.get("status") == 0:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, result.get("message"))
        return result

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def add_to_cart(self, data: list[tuple], referer: str):
        self.aws()
        self.ensure_csrf_token()
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": self.BASE_URL,
            "referer": referer,
            "user-agent": self.__ua,
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest",
        }
        response = self.__http_utils.post(
            url=f"{self.BASE_URL}/booking/addToCart",
            headers=headers,
            data=urlencode(data, doseq=True),
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        result = response.to_dict()
        if not result.get("status"):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, result.get("message"))
        return result

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def passenger_page(self, booking_code: str, referer: Optional[str] = None):
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "referer": referer or f"{self.BASE_URL}/flight",
            "upgrade-insecure-requests": "1",
            "user-agent": self.__ua,
        }
        response = self.__http_utils.get(
            url=f"{self.BASE_URL}/booking/{booking_code}/passenger",
            headers=headers,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        html = response.to_text()
        self.update_csrf_token_from_html(html)
        return html

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def check_status(self, booking_code: str, referer_path: str = "passenger"):
        self.ensure_csrf_token()
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "referer": f"{self.BASE_URL}/booking/{booking_code}/{referer_path}",
            "user-agent": self.__ua,
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest",
        }
        response = self.__http_utils.get(
            url=f"{self.BASE_URL}/booking/{booking_code}/check-status?_={int(datetime.now().timestamp() * 1000)}",
            headers=headers,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        result = response.to_dict()
        if result.get("error"):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, result.get("message") or result)
        return result

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def get_countries(self, booking_code: str):
        self.ensure_csrf_token()
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "referer": f"{self.BASE_URL}/booking/{booking_code}/passenger",
            "user-agent": self.__ua,
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest",
        }
        response = self.__http_utils.get(
            url=f"{self.BASE_URL}/booking/getCountries",
            headers=headers,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def get_ssr(self, booking_code: str):
        self.ensure_csrf_token()
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "referer": f"{self.BASE_URL}/booking/{booking_code}/passenger",
            "user-agent": self.__ua,
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest",
        }
        response = self.__http_utils.get(
            url=f"{self.BASE_URL}/booking/getSSR?{urlencode({'code': booking_code})}",
            headers=headers,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        result = response.to_dict()
        if result.get("status") == 0:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, result.get("message"))
        return result

    @retry_decorator([(ServiceStateEnum.API_RESPONSE_EXCEPTION, None)])
    def aws(self):
        TOKEN_API_URL = "http://api.zjdanli.com/aws/token"
        APP_ID = "7j58fx77bifxt2jhx01pwoek7asgp6xm"
        TARGET_SITE = "th.vietjetair.com"
        payload = {
            "appid": APP_ID,
            "siteUrl": TARGET_SITE
        }
        headers = {'Content-Type': 'application/json'}
        try:
            A = requests.post(TOKEN_API_URL, headers=headers, json=payload)
            a = A.json()["data"]["token"]
            self.__http_utils.cookie_update({"aws-waf-token": a})
            self.__ua = A.json()["data"]["ua"]
        except Exception as e:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION, e)

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def checkout_page(self, booking_code: str):
        headers = {
            "Host": "th.vietjetair.com",
            "User-Agent": self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": f"https://th.vietjetair.com/booking/{booking_code}/passenger",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i"
        }
        response = self.__http_utils.get(
            url=f"{self.BASE_URL}/booking/{booking_code}/checkout",
            headers=headers,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        html = response.to_text()
        self.update_csrf_token_from_html(html)
        return html

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def payment_page(self, booking_code: str):
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "referer": f"{self.BASE_URL}/booking/{booking_code}/checkout",
            "upgrade-insecure-requests": "1",
            "user-agent": self.__ua,
        }
        response = self.__http_utils.get(
            url=f"{self.BASE_URL}/booking/{booking_code}/payment",
            headers=headers,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        html = response.to_text()
        self.update_csrf_token_from_html(html)
        return html

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def booking_detail_page(self, booking_code: str):
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "referer": f"{self.BASE_URL}/booking/{booking_code}/payment",
            "upgrade-insecure-requests": "1",
            "user-agent": self.__ua,
        }
        response = self.__http_utils.get(
            url=f"{self.BASE_URL}/booking/{booking_code}",
            headers=headers,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        html = response.to_text()
        self.update_csrf_token_from_html(html)
        return html

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def quotation(self, data: list[tuple], booking_code: str):
        self.ensure_csrf_token()
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": self.BASE_URL,
            "referer": f"{self.BASE_URL}/booking/{booking_code}/passenger",
            "user-agent": self.__ua,
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest",
        }
        response = self.__http_utils.post(
            url=f"{self.BASE_URL}/booking/quotation",
            headers=headers,
            data=urlencode(data, doseq=True),
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        result = response.to_dict()
        if not result.get("status"):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, result.get("message"))
        return result

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def do_checkout(self, booking_code: str):
        self.ensure_csrf_token()

        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": self.BASE_URL,
            "referer": f"{self.BASE_URL}/booking/{booking_code}/checkout",
            "user-agent": self.__ua,
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest",
        }
        response = self.__http_utils.post(
            url=f"{self.BASE_URL}/booking/doCheckout",
            headers=headers,
            data=urlencode({"code": booking_code}, doseq=True),
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        result = response.to_dict()
        if not result.get("status"):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, result.get("message"))
        return result

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def check_payment_fee(self, booking_code: str, payment_method: dict, funcoin_limit):
        self.ensure_csrf_token()
        data = {
            "code": booking_code,
            "payment_selected[group]": payment_method["group"],
            "payment_selected[fee]": payment_method.get("fee", 0),
            "payment_selected[key]": payment_method["key"],
            "payment_selected[identifier]": payment_method["identifier"],
            "payment_selected[gateway]": payment_method["gateway"],
            "payment_selected[code]": payment_method["code"],
            "payment_selected[total]": payment_method.get("total", ""),
            "funcoin_limit": funcoin_limit or 0,
        }
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": self.BASE_URL,
            "referer": f"{self.BASE_URL}/booking/{booking_code}/payment",
            "user-agent": self.__ua,
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest",
        }
        response = self.__http_utils.post(
            url=f"{self.BASE_URL}/booking/check-payment-fee",
            headers=headers,
            data=urlencode(data, doseq=True),
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    @retry_decorator([(ServiceStateEnum.BUSINESS_ERROR, None), (ServiceStateEnum.API_RESPONSE_EXCEPTION, None)])
    def get_recaptcha_token(self):
        try:
            import requests

            response = requests.post(
                "http://api.zjdanli.com/recaptcha/getTokenV2",
                headers={"Content-Type": "application/json"},
                json={
                    "appid": "7j58fx77bifxt2jhx01pwoek7asgp6xm",
                    "host": self.BASE_URL,
                    "sitekey": self.RECAPTCHA_SITE_KEY,
                },
                timeout=120,
            )
            result = response.json()
            if result.get("data"):
                return result["data"]
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, result)
        except ServiceError:
            raise
        except Exception as e:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION, e)

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def do_payment(self, booking_code: str, recaptcha_token: str, funcoin_config: dict, payment_group: str):
        self.ensure_csrf_token()
        data = {
            "code": booking_code,
            "payment-group": payment_group,
            "g-recaptcha-response": recaptcha_token,
            "applyVoucher": "false",
            "funcoin_selected[using_money]": 0,
            "funcoin_selected[using_coin]": 0,
            "funcoin_selected[maximum]": 0,
            "funcoin_selected[minimum]": funcoin_config.get("payment_minimum", 100),
            "funcoin_selected[exchange_rate]": funcoin_config.get("exchange_rate", 10),
            "credit": 0,
            "auto": 0,
        }
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": self.BASE_URL,
            "referer": f"{self.BASE_URL}/booking/{booking_code}/payment",
            "user-agent": self.__ua,
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest",
        }
        response = self.__http_utils.post(
            url=f"{self.BASE_URL}/booking/doPayment",
            headers=headers,
            data=urlencode(data, doseq=True),
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        result = response.to_dict()
        if not result.get("status"):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, result.get("message"))
        return result

    @staticmethod
    def parse_form_security_names(html: str):
        return re.findall(r'name="([a-f0-9]{40})"', html or "")

    @staticmethod
    def __parse_funcoin_limit(payment_html: str) -> str:
        funcoin_config_text = StringUtil.extract_between(
            payment_html, "var _FUNCOIN_CONFIG =", "var _CREDIT_CONFIG"
        )
        if not funcoin_config_text:
            return "0"
        funcoin_config_text = funcoin_config_text.strip().split(';', 1)[0]
        funcoin_config = json.loads(funcoin_config_text)
        return str(funcoin_config.get('funcoin_limit', '0'))

    def later_parse_payment_data(self, html: str, is_today: bool = False):
        methods_match = re.search(r"var\s+_PAYMENT_METHODs\s*=\s*(\[.*?\]);", html or "", re.S)
        funcoin_match = re.search(r"var\s+_FUNCOIN_CONFIG\s*=\s*(\{.*?\});", html or "", re.S)
        if not methods_match:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "VZ payment method config not found")
        methods = json.loads(methods_match.group(1))
        funcoin_config = json.loads(funcoin_match.group(1)) if funcoin_match else {}
        if is_today:
            free_key_data = json.loads(
                StringUtil.extract_between(html, "var _PAYMENT_METHODs =", "var _PAYMENT_GROUPs").strip().rstrip(
                    ';'))
            funcoin_limit = self.__parse_funcoin_limit(html)

            card_key_data = [i for i in free_key_data if i['name'] == 'Credit Card' or i['name'] == 'Global Card'][0]
            card_key_data['_funcoin_limit'] = funcoin_limit
            gateway = card_key_data.get("gateways")[0]
            config = card_key_data.get("amelia_payment_config")

            return {
                "group": "PL30",
                "identifier": config.get("identifier"),
                "key": config.get("key"),
                "gateway": gateway.get("gateway"),
                "code": gateway.get("code"),
                "fee": 0,
                "total": "",
            }, funcoin_config
        pay_later_method = next(
            (method for method in methods if method.get("amelia_payment_identifier") == "PL"),
            None,
        )
        if not pay_later_method:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "VZ pay later method not found")

        gateway = (pay_later_method.get("gateways") or [{}])[0]
        config = pay_later_method.get("amelia_payment_config") or {}
        return {
            "group": "PL",
            "identifier": config.get("identifier") or "PL",
            "key": config.get("key"),
            "gateway": gateway.get("gateway") or "2c2p",
            "code": gateway.get("code") or "LATER",
            "fee": 0,
            "total": "",
        }, funcoin_config

    @staticmethod
    def parse_reservation_code(html: str):
        match = re.search(r'class="reservation-code">\s*([^<\s]+)', html or "")
        return match.group(1).strip() if match else None

    @staticmethod
    def add_to_cart_payload(journey: dict, fare: dict, search_context: dict):
        detail = {key: value for key, value in journey.items() if not key.startswith("_")}
        api_uuid = journey.get("_api_uuid") or journey.get("api_uuid")
        if not api_uuid:
            alphabet = string.ascii_letters + string.digits
            api_uuid = "".join(random.choice(alphabet) for _ in range(40))
        exclude_fare_keys = {"description", "order", "title_color", "background_color", "logo", "content"}
        cart_fare = {key: value for key, value in fare.items() if key not in exclude_fare_keys}
        flight_parts = []
        for flight in journey.get("flights") or []:
            dep_date = (flight.get("departure_date_html") or "")[:10].replace("-", "")
            flight_parts.append(f"{flight.get('airline_code') or ''}{flight.get('flight_number') or ''}{dep_date}")
        fare_uuid = f"departure-fare-info-{''.join(flight_parts)}-{fare.get('name') or fare.get('code') or ''}"

        def flatten_nested(prefix: str, value):
            items = []
            if isinstance(value, dict):
                for key, nested_value in value.items():
                    items.extend(flatten_nested(f"{prefix}[{key}]", nested_value))
            elif isinstance(value, list):
                for nested_value in value:
                    items.extend(flatten_nested(f"{prefix}[]", nested_value))
            elif value is None:
                items.append((prefix, ""))
            elif isinstance(value, bool):
                items.append((prefix, str(value).lower()))
            else:
                items.append((prefix, value))
            return items

        data = [
            ("api_uuid", api_uuid),
            ("service_type", "flight"),
            ("duration", journey.get("duration") or 0),
            ("from_where", search_context["dep_airport"]),
            ("to_where", search_context["arr_airport"]),
            ("departure_date", search_context["dep_date"]),
            ("return_date", search_context.get("ret_date") or ""),
            ("tripType", search_context["trip_type"]),
            ("adultCount", search_context["adult_count"]),
            ("childCount", search_context["child_count"]),
            ("infantCount", search_context["infant_count"]),
            ("departure[service_id]", journey.get("id") or ""),
        ]
        first_flight = (journey.get("flights") or [{}])[0]
        data.extend([
            ("departure[departure_date]", first_flight.get("departure_date_html") or ""),
            ("departure[return_date]", first_flight.get("arrival_date_html") or ""),
            ("departure[duration]", journey.get("duration") or 0),
            ("departure[detail]", json.dumps(detail, ensure_ascii=False, separators=(",", ":"))),
            ("departure[channel_provider]", journey.get("channel_provider") or "AMELIA"),
        ])
        data.extend(flatten_nested("departure[flight_seat]", cart_fare))
        data.append(("departure[flight_seat][uuid]", fare_uuid))
        data.extend([
            ("return", ""),
            ("expiredTime", (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")),
            ("term_conditions", "on"),
            ("currency", search_context["currency"]),
            ("promoCode", ""),
            ("promoCodeDiscount", ""),
            ("memberPromoCode", ""),
        ])
        return data
