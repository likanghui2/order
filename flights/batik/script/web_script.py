import json
import random
import re
import time
import uuid
from copy import copy

import requests

from common.decorators.retry_decorator import retry_decorator
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, quote, urlparse

from common.errors.service_error import ServiceStateEnum, ServiceError
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.response_info_model import ResponseInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.ezcaptcha_util import EzCaptcha
from common.utils.rsa_ciphering import RsaCiphering
from flights.batik.config import Config
from flights.batik.flight_common.headers_utlis import HeadersUtlis
from flights.batik.flight_common.utils import Utils
from lxml import etree

DANLI_CAPTCHA = DanLiCaptchaUtil('m05cmm7ub8vm1pgasjpo8sdp9tl6mkzp')


class WebScript:

    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.hhh = {}
        self.__tls = CurlCffiTls()
        self.__tls.initialize(proxy_info_data, impersonate='chrome146')
        self.__proxy = proxy_info_data
        self.__token = ''
        self.pic_id = None
        self.g_token = None
        self.__header_profile = HeadersUtlis.random_header_profile()
        self.__ua = self.__header_profile["user_agent"]
        self.__accept_language = self.__header_profile["accept_language"]
        self.__x_user_agent = self.__header_profile["x_useragent"]

    @property
    def user_agent(self):
        return self.__ua

    @property
    def accept_language(self):
        return self.__accept_language

    @property
    def x_user_agent(self):
        return self.__x_user_agent

    def rotate_header_profile(self, device: Optional[str] = None, chrome_major: Optional[int] = None) -> dict:
        self.__header_profile = HeadersUtlis.random_header_profile(device=device, chrome_major=chrome_major)
        self.__ua = self.__header_profile["user_agent"]
        self.__accept_language = self.__header_profile["accept_language"]
        self.__x_user_agent = self.__header_profile["x_useragent"]
        return self.__header_profile.copy()

    def browser_header_overrides(self, x_user_agent: Optional[str] = None, include_sec_ch: bool = True,
                                 lower_case: bool = True) -> dict:
        return HeadersUtlis.browser_header_overrides(
            profile=self.__header_profile,
            x_user_agent=x_user_agent,
            include_sec_ch=include_sec_ch,
            lower_case=lower_case,
        )

    def solve_cloudflare_cookies(self):
        """
        创建并获取 Cloudflare cf_clearance Cookie 任务

        Args:
            url (str): 目标网站地址

        Returns:
            dict: 包含 Cookie 等字段的任务结果
        """
        task_data = {
            "href": 'https://www.batikair.com.my',
            "proxy": self.__tls.get_proxy_data().get_proxy_info_to_string(),
            'user_agent': self.__ua,

        }
        headers = {
            'User-Token': '00cf3281-7648-4678-8cb1-a03041030f40',
            'Content-Type': 'application/json',
        }
        print(task_data)

        aa = requests.post("http://api.nocaptcha.io/api/wanda/cloudflare/universal", json=task_data, headers=headers)
        print(aa.json())
        self.__tls.cookie_update(aa.json()['data']["cookies"])
        self.hhh = aa.json()['extra']

    @property
    def tls(self):
        return self.__tls

    @property
    def proxy(self):
        """

        Returns:

        """
        return self.__tls.get_proxy_data()

    @retry_decorator([(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, solve_cloudflare_cookies)])
    def home(self):
        headers = {
            "user-agent": self.__ua,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": self.__accept_language,
            "accept-encoding": "gzip, deflate, br, zstd",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "priority": "u=0, i",
            "te": "trailers"
        }
        headers.update(self.hhh)
        response = self.__tls.get(url='https://www.batikair.com.my', headers=headers, timeout=10)
        if response.status != 200:
            if response.status == 403:
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, response.status)
        headers = {
            "user-agent": self.__ua,
            "accept": "*/*",
            "accept-language": self.__accept_language,
            "accept-encoding": "gzip, deflate, br, zstd",
            "origin": "https://www.batikair.com.my",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=4",
            "te": "trailers"
        }
        self.__tls.del_cookie("__cf_bm")
        response = self.__tls.get(url='https://search.batikair.com.my/flightrr_api/api/Get/GeoLocation',
                                  headers=headers)
        return response

    def reset_proxy_ip(self):
        self.__tls.initialize(self.__proxy, impersonate='chrome133a')

    @staticmethod
    def initialize_ez_recaptcha(referer):
        ez_captcha = EzCaptcha(client_key='EZ-861220FA2A2E4D3896FEAAAAD1B61A83')
        token = ez_captcha.solve_recaptcha(website_url=referer,
                                           website_key="6LcrtrAcAAAAAOWiJscHF_0ECvxV6y3Ain1pygXu",
                                           task_type="ReCaptchaV2TaskProxyless")
        return token

    def init_cloudflare(self):
        cookie, ua, proxy, key = DANLI_CAPTCHA.get_cloudflare(host="mmb.batikair.com.my")
        self.__tls.set_proxy_info_str(proxy)
        self.__tls.cookie_update(cookie)
        self.__ua = ua
        self.__header_profile["user_agent"] = ua

    def set_token(self, token):
        self.__token = token

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip), (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip),
         (ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, reset_proxy_ip),
         (ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, reset_proxy_ip), ])
    def init_token(self):
        timestamp, hash_token = Utils.make_header_args("")
        headers = {
            "Host": "search.batikair.com.my",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "accept-language": self.__accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "X-UserAgent": "Mobile-Web",
            "X-TimeStamp": timestamp,
            "X-Env": "P",
            "X-Token": "",
            "X-Hash": hash_token,
            "Origin": "https://www.batikair.com.my",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Priority": "u=0",
            "TE": "trailers"
        }
        response = self.__tls.get(url='https://search.batikair.com.my/flightrr_api/api/Get/Token', headers=headers,
                                  timeout=3)
        if response.status != 200:
            print(response.status)
            if response.status == 429:
                raise ServiceError(ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, response.status)
            if response.status == 403:
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, response.status)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        self.__token = response.headers["x-token"]
        return response.headers["x-token"]

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
                      (ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, reset_proxy_ip),
                      (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)
                      ], retry_max_number=5)
    def availability(self, data: dict) -> ResponseInfoModel:
        timestamp, hash_token = Utils.make_header_args(self.__token)

        headers = {
            "Host": "search.batikair.com.my",
            "user-agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "accept-language": self.__accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "X-UserAgent": "Mobile-Web",
            "x-timestamp": timestamp,
            "X-Env": "P",
            "x-token": self.__token,
            "x-hash": hash_token,
            "Origin": "https://www.batikair.com.my",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "TE": "trailers"
        }

        response = self.__tls.post(url='https://search.batikair.com.my/flightrr_api/api/get/Flights',
                                   headers=headers,
                                   data=data)
        if response.status != 200:
            if response.status == 429:
                raise ServiceError(ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, response.status)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def select_cart(self, fare_ids: List[str], adt_number: int, chd_number: int):
        """

        Args:
            fare_ids: basketHashCode
            adt_number:
            chd_number:

        Returns:

        """
        data = {
            "cartId": "",
            "searchId": "",
            "fareIds": fare_ids,
            "paxNumbers": {
                "numAdults": adt_number,
                "numChildren": chd_number,
                "numInfants": 0
            }
        }

        url = 'https://cart.batikair.com.my/cartrr_api/api/add/cart'
        timestamp, hash_token = Utils.make_header_args(self.__token)

        headers = {
            "accept-language": self.__accept_language,
            "X-Token": self.__token,
            "X-UserAgent": "Web",
            "X-TimeStamp": timestamp,
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "X-Hash": hash_token,
            "X-Env": "P",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.batikair.com.my",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }

        response = self.__tls.post(url=url,
                                   headers=headers,
                                   data=data)

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if not response.to_dict()["status"]:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '选择航班失败')
        return response

    def add_passenger(self, passengers: List, contact_info: dict):
        timestamp, hash_token = Utils.make_header_args(self.__token)

        headers = {
            "host": "booking.batikair.com.my",
            'accept': 'application/json, text/plain, */*',
            "accept-language": self.__accept_language,
            'content-type': 'application/json',
            'origin': 'https://www.batikair.com.my',
            'priority': 'u=1, i',
            'sec-ch-ua-mobile': self.__header_profile["sec_ch_ua_mobile"],
            'sec-ch-ua-platform': self.__header_profile["sec_ch_ua_platform"],
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': self.__ua,
            # 'x-cf-token': aa['token'],
            'x-env': 'P',
            "x-hash": hash_token,
            "x-timestamp": timestamp,
            'x-token': self.__token,
            'x-useragent': 'Web',
        }

        data = {
            "passengers": passengers,
            "contactInfo": contact_info,
            "cartId": "",
            "searchId": "",
            "ipAddress": "",
            "userAgent": "Web",
            "browserNameAndVersion": self.__ua
        }
        response = self.__tls.post(url='https://booking.batikair.com.my/bookrr_api/api/add/pax',
                                   headers=headers,
                                   data=data, timeout=120)
        if response.status != 200:
            if response.status == 429:
                raise ServiceError(ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, response.status)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def get_cart(self):

        timestamp, hash_token = Utils.make_header_args(self.__token)

        headers = {
            "accept-language": self.__accept_language,
            "X-Token": self.__token,
            "X-UserAgent": "Web",
            "X-TimeStamp": timestamp,
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "X-Hash": hash_token,
            "X-Env": "P",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.batikair.com.my",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }

        response = self.__tls.get(url='https://cart.batikair.com.my/cartrr_api/api/get/cart',
                                  headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def get_baggages(self):
        timestamp, hash_token = Utils.make_header_args(self.__token)

        headers = {
            "accept-language": self.__accept_language,
            "X-Token": self.__token,
            "X-UserAgent": "Web",
            "X-TimeStamp": timestamp,
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "X-Hash": hash_token,
            "X-Env": "P",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.batikair.com.my",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        response = self.__tls.get(url='https://search.batikair.com.my/flightrr_api/api/get/ancillaries',
                                  headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def get_img(self):
        url = "https://search.batikair.com.my/flightrr_api/api/Add/CreateCaptcha"
        timestamp, hash_token = Utils.make_header_args(self.__token)
        headers = {
            "accept-language": self.__accept_language,
            "X-Token": self.__token,
            "X-UserAgent": "Web",
            "X-TimeStamp": timestamp,
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "X-Hash": hash_token,
            "X-Env": "P",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.batikair.com.my",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd",
        }
        response = self.__tls.get(url=url, headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    @staticmethod
    def invoke(base64_image):
        print(base64_image)
        r = requests.post("https://orc.l-a-j.com/runtime/text/invoke", json={
            "project_name": "ctc_251128",
            "image": base64_image,

        })
        print(r.json())
        if r.status_code != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, r.status_code)
        if not r.json()['success']:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)

        return r.json()['data']

    def payment_2c2p(self, pay_info: dict):
        timestamp, hash_token = Utils.make_header_args(self.__token)
        print(self.g_token)
        headers = {
            "accept-language": self.__accept_language,
            "X-Token": self.__token,
            "X-UserAgent": "Web",
            "X-TimeStamp": timestamp,
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "X-Hash": hash_token,
            "X-Env": "P",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.batikair.com.my",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "X-GToken": self.g_token
        }
        headers.update(self.hhh)
        submit_data_encrypt = Utils.aes_encrypt(json.dumps(pay_info))

        data = {
            "payload": submit_data_encrypt
        }

        response = self.__tls.post(url='https://booking.batikair.com.my/bookrr_api/api/_2c2p/Payment',
                                   headers=headers,
                                   data=data)
        if response.status != 200:
            if response.status == 401:
                return False
            if response.status != 200:
                raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if response.to_dict().get("isCaptchaRetryAttempt", False):
            return False
        data = response.to_dict()['response']
        result: dict = Utils.aes_decrypt(data)
        print(result)
        if "Session expired" in json.dumps(result):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "速率过快，联系技术调整速率")

        return result

    def pay_callback(self, url):
        headers = {
            "accept-language": self.__accept_language,
            "Upgrade-Insecure-Requests": "1",
            'user-agent': self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        response = self.__tls.get(url=url, headers=headers)
        if response.status != 200 and response.status != 301 and response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    def add_baggage(self, baggages: List, currency):
        timestamp, hash_token = Utils.make_header_args(self.__token)

        headers = {
            "accept-language": self.__accept_language,
            "X-Token": self.__token,
            "X-UserAgent": "Web",
            "X-TimeStamp": timestamp,
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "X-Hash": hash_token,
            "X-Env": "P",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.batikair.com.my",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        data = {
            "cartId": "",
            "searchId": "",
            "baggages": baggages,
            "meals": None,
            "snacks": None,
            "comfykits": None,
            "delayBags": None,
            "kliaExpress": None,
            "fastlanes": None,
            "lngEs": None,
            "smSs": None,
            "insurance": None
        }
        if not baggages:
            return None
        response = self.__tls.post(url='https://search.batikair.com.my/flightrr_api/api/add/Ancillaries',
                                   headers=headers, data=data)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        self.get_map()
        return response.to_dict

    def get_map(self):
        timestamp, hash_token = Utils.make_header_args(self.__token)
        header = {
            "user-agent": self.__ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": self.__accept_language,
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "x-useragent": "Web",
            "x-timestamp": timestamp,
            "x-env": "P",
            "x-token": self.__token,
            "x-hash": hash_token,
            "origin": "https://www.batikair.com.my",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0",
            "te": "trailers"
        }
        response = self.__tls.get(url='https://search.batikair.com.my/flightrr_api/api/get/SeatMap',
                                  headers=header)

    def payment_pub(self, pay_info: dict, fill_customer_ip: bool = False):
        url = 'https://payment.batikair.com.my/payment_api/api/publicBank/payment'
        payment_landing_url = f"https://payment.batikair.com.my/?token={quote(self.__token, safe='')}"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.__accept_language,
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        response = self.__tls.get(url=payment_landing_url, headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        if fill_customer_ip and not pay_info.get("customerIp"):
            client_info = self.public_bank_get_client_info(payment_landing_url)
            customer_ip = client_info.get("ip")
            if not customer_ip:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "get-client-info缺少ip")
            pay_info["customerIp"] = customer_ip

        timestamp, hash_token = Utils.make_header_args(self.__token)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.__accept_language,
            "Content-Type": "application/json",
            "Origin": "https://payment.batikair.com.my",
            "Referer": payment_landing_url,
            "User-Agent": self.__ua,
            "X-Env": "P",
            "X-Hash": hash_token,
            "X-TimeStamp": timestamp,
            "X-Token": self.__token,
            "X-UserAgent": "Web",
        }
        if self.g_token:
            headers["X-GToken"] = self.g_token

        response = self.__tls.post(
            url=url,
            headers=headers,
            data={"payload": Utils.aes_encrypt(json.dumps(pay_info))}
        )
        if response.status != 200:
            if response.status == 429:
                raise ServiceError(ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, response.status)
            if response.status == 401:
                return None
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if response.to_dict().get("isCaptchaRetryAttempt", False):
            return None

        result = Utils.aes_decrypt(response.to_dict()['response'])
        print(result)
        if "Session expired" in json.dumps(result):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "速率过快，联系技术调整速率")
        return result

    def public_bank_get_client_info(self, referer: str) -> dict:

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.__accept_language,
            "Referer": referer,
            "User-Agent": self.__ua,
        }
        response = self.__tls.get(url="https://payment.batikair.com.my/api/get-client-info", headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    @staticmethod
    def __ccavenue_sentry_headers(trace_id: Optional[str] = None) -> dict:
        trace_id = trace_id or uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]
        sample_rand = str(round(random.random(), 16))
        return {
            "sentry-trace": f"{trace_id}-{span_id}-0",
            "baggage": (
                "sentry-environment=production,"
                "sentry-public_key=7bee43c6791b481cbf1c24e7bae5c36b,"
                f"sentry-trace_id={trace_id},"
                "sentry-sampled=false,"
                f"sentry-sample_rand={sample_rand},"
                "sentry-sample_rate=0.1"
            )
        }

    def __cookie_header(self, include: Optional[List[str]] = None, exclude: Optional[List[str]] = None) -> str:
        cookies = self.__tls.get_cookie_dict()
        exclude = set(exclude or [])
        names = include if include is not None else cookies.keys()
        return "; ".join(
            f"{name}={cookies[name]}"
            for name in names
            if name in cookies and name not in exclude
        )

    def __ccavenue_cookie_header(self) -> str:
        return self.__cookie_header(include=["JSESSIONID"])

    def __batik_payment_cookie_header(self) -> str:
        return self.__cookie_header(exclude=["JSESSIONID"])

    def ccavenue_get_client_info(self, referer: str, sentry_headers: Optional[dict] = None) -> dict:
        headers = {
            "user-agent": Config.CCAVENUE_USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "accept-encoding": "gzip, deflate, br, zstd",
            "referer": referer,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "te": "trailers"
        }
        if sentry_headers:
            headers.update(sentry_headers)

        response = self.__tls.get(url="https://payment.batikair.com.my/api/get-client-info", headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def payment_ccavenue(self, pay_info: dict, fill_customer_ip: bool = False):

        payment_landing_url = f"https://payment.batikair.com.my/?token={quote(self.__token, safe='')}"
        sentry_headers = self.__ccavenue_sentry_headers()
        headers = {
            "user-agent": Config.CCAVENUE_USER_AGENT,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "accept-encoding": "gzip, deflate, br, zstd",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-site",
            "sec-fetch-user": "?1",
            "priority": "u=0, i",
            "te": "trailers"
        }
        response = self.__tls.get(url=payment_landing_url, headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        if fill_customer_ip and not pay_info.get("customerIp"):
            client_info = self.ccavenue_get_client_info(payment_landing_url, sentry_headers)
            customer_ip = client_info.get("ip")
            if not customer_ip:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "get-client-info缺少ip")
            pay_info["customerIp"] = customer_ip
        print(pay_info)
        timestamp, hash_token = Utils.make_header_args(self.__token)
        headers = {
            "user-agent": Config.CCAVENUE_USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "x-useragent": "Web",
            "x-timestamp": timestamp,
            "x-env": "P",
            "x-token": self.__token,
            "x-hash": hash_token,
            "origin": "https://payment.batikair.com.my",
            "referer": payment_landing_url,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "priority": "u=0",
            "te": "trailers"
        }
        headers.update(sentry_headers)
        response = self.__tls.post(
            url="https://payment.batikair.com.my/payment_api/api/ccavenue/Payment",
            headers=headers,
            data={"payload": Utils.aes_encrypt(json.dumps(pay_info))}
        )
        if response.status != 200:
            if response.status == 401:
                return None
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        payload = response.to_dict().get("response")
        if not payload:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "CCAvenue支付响应为空")

        result = Utils.aes_decrypt(payload)
        if "Session expired" in json.dumps(result):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "速率过快，联系技术调整速率")
        return result

    def ccavenue_initiate_transaction(self, url: str, form_data: dict) -> str:
        headers = {
            "User-Agent": Config.CCAVENUE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://payment.batikair.com.my",
            "Connection": "keep-alive",
            "Referer": "https://payment.batikair.com.my/",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Priority": "u=0, i",
            "cookie": ""
        }
        response = self.__tls.post(url=url, headers=headers, data=urlencode(form_data, doseq=True))
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def ccavenue_validate_card_bin(self, tracking_id: str, card_bin: str) -> dict:
        headers = {
            "Host": "secure.ccavenue.com",
            "User-Agent": Config.CCAVENUE_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://secure.ccavenue.com",
            "Connection": "keep-alive",
            "Referer": "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "cookie": self.__ccavenue_cookie_header()
        }
        response = self.__tls.post(
            url="https://secure.ccavenue.com/validateCardBin",
            headers=headers,
            data=urlencode({
                "command": "validateCardBin",
                "trackingId": tracking_id,
                "cardBinNumber": card_bin
            })
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def ccavenue_validate_card_type(self, tracking_id: str, card_bin: str) -> dict:
        headers = {
            "Host": "secure.ccavenue.com",
            "User-Agent": Config.CCAVENUE_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://secure.ccavenue.com",
            "Connection": "keep-alive",
            "Referer": "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "cookie": self.__ccavenue_cookie_header()
        }
        response = self.__tls.post(
            url="https://secure.ccavenue.com/transaction.do",
            headers=headers,
            data=urlencode({
                "command": "validateCardType",
                "trackingId": tracking_id,
                "cardNumber": card_bin,
                "settingSeamlessIntegration": "N"
            })
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def ccavenue_get_cvvless_mid(self, form_data: dict) -> dict:
        headers = {
            "Host": "secure.ccavenue.com",
            "User-Agent": Config.CCAVENUE_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://secure.ccavenue.com",
            "Connection": "keep-alive",
            "Referer": "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "cookie": self.__ccavenue_cookie_header()
        }
        response = self.__tls.post(
            url="https://secure.ccavenue.com/getCvvlessMid",
            headers=headers,
            data=urlencode(form_data, doseq=True)
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def ccavenue_get_emi_plan(self, tracking_id: str, card_bin: str) -> dict:
        headers = {
            "Host": "secure.ccavenue.com",
            "User-Agent": Config.CCAVENUE_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://secure.ccavenue.com",
            "Connection": "keep-alive",
            "Referer": "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "cookie": self.__ccavenue_cookie_header()
        }
        response = self.__tls.post(
            url="https://secure.ccavenue.com/getEMIPlan",
            headers=headers,
            data=urlencode({
                "command": "getEMIPlan",
                "trackingId": tracking_id,
                "cardBinNumber": card_bin
            })
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def ccavenue_update_transaction(self, form_data: dict) -> str:
        headers = {
            "Host": "secure.ccavenue.com",
            "User-Agent": Config.CCAVENUE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://secure.ccavenue.com",
            "Connection": "keep-alive",
            "Referer": "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
            "cookie": self.__ccavenue_cookie_header()
        }
        response = self.__tls.post(
            url="https://secure.ccavenue.com/updateTransaction",
            headers=headers,
            data=urlencode(form_data, doseq=True)
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def ccavenue_cardinal_collect(self, url: str, form_data: dict) -> str:
        headers = {
            "user-agent": Config.CCAVENUE_USER_AGENT,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/x-www-form-urlencoded",
            "sec-fetch-storage-access": "none",
            "origin": "https://secure.ccavenue.com",
            "referer": "https://secure.ccavenue.com/",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "priority": "u=4",
            "te": "trailers",
            "cookie": ""
        }
        response = self.__tls.post(url=url, headers=headers, data=urlencode(form_data, doseq=True))
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def ccavenue_cardinal_render(self, url: str, data: str) -> dict:
        headers = {
            "user-agent": Config.CCAVENUE_USER_AGENT,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/x-www-form-urlencoded",
            "sec-fetch-storage-access": "none",
            "origin": "https://centinelapi.cardinalcommerce.com",
            "referer": "https://centinelapi.cardinalcommerce.com/",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-site",
            "priority": "u=4",
            "te": "trailers",
            "cookie": ""
        }
        response = self.__tls.post(url=url, headers=headers, data=data, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        match = re.search(r'profiler\.start\((.*?)\)', response.to_text(), re.S)
        if not match:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "profiler.start")
        return json.loads(match.group(1))

    def ccavenue_cardinal_save_browser_data(self, nonce: str, reference_id: str, org_unit_id: str,
                                            referrer: str, origin: str = "CruiseAPI"):
        headers = {
            "user-agent": Config.CCAVENUE_USER_AGENT,
            "accept": "*/*",
            "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "x-requested-with": "XMLHttpRequest",
            "origin": "https://geo.cardinalcommerce.com",
            "referer": referrer,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "te": "trailers",
            "cookie": ""
        }
        submit_data = {
            "Cookies": {
                "Legacy": True,
                "LocalStorage": True,
                "SessionStorage": True
            },
            "DeviceChannel": "Browser",
            "Extended": {
                "Browser": {
                    "Adblock": True,
                    "AvailableJsFonts": [],
                    "DoNotTrack": "unspecified",
                    "JavaEnabled": False
                },
                "Device": {
                    "ColorDepth": 30,
                    "Cpu": "unknown",
                    "Platform": "MacIntel",
                    "TouchSupport": {
                        "MaxTouchPoints": 0,
                        "OnTouchStartAvailable": False,
                        "TouchEventCreationSuccessful": False
                    }
                }
            },
            "Fingerprint": uuid.uuid4().hex,
            "FingerprintingTime": 68,
            "FingerprintDetails": {"Version": "1.5.1"},
            "Language": "zh-CN",
            "Latitude": None,
            "Longitude": None,
            "OrgUnitId": org_unit_id,
            "Origin": origin,
            "Plugins": [
                "PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "Chrome PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "Chromium PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "Microsoft Edge PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "WebKit built-in PDF::Portable Document Format::application/pdf~pdf,text/pdf~pdf"
            ],
            "ReferenceId": reference_id,
            "Referrer": referrer,
            "Screen": {
                "FakedResolution": False,
                "Ratio": 1800 / 1169,
                "Resolution": "1800x1169",
                "UsableResolution": "1800x1169",
                "CCAScreenSize": "01"
            },
            "CallSignEnabled": None,
            "ThreatMetrixEnabled": False,
            "ThreatMetrixEventType": "PAYMENT",
            "ThreatMetrixAlias": "Default",
            "TimeOffset": -480,
            "UserAgent": Config.CCAVENUE_USER_AGENT,
            "UserAgentDetails": {
                "FakedOS": False,
                "FakedBrowser": False
            },
            "BinSessionId": nonce
        }
        response = self.__tls.post(
            url="https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/SaveBrowserData",
            headers=headers,
            data=json.dumps(submit_data)
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    def ccavenue_cardinal_collect_redirect(self, url: str, form_data: dict) -> str:
        headers = {
            "user-agent": Config.CCAVENUE_USER_AGENT,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/x-www-form-urlencoded",
            "sec-fetch-storage-access": "none",
            "origin": "https://centinelapi.cardinalcommerce.com",
            "referer": "https://centinelapi.cardinalcommerce.com/V1/Cruise/Collect",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "priority": "u=4",
            "te": "trailers",
            "cookie": ""
        }
        response = self.__tls.post(url=url, headers=headers, data=urlencode(form_data, doseq=True))
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def ccavenue_submit_3ds_iframe(self, url: str, form_data: dict) -> str:
        headers = {
            "Host": "secure.ccavenue.com",
            "User-Agent": Config.CCAVENUE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://secure.ccavenue.com",
            "Connection": "keep-alive",
            "Referer": "https://secure.ccavenue.com/updateTransaction",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=0, i",
            "cookie": self.__ccavenue_cookie_header()
        }
        response = self.__tls.post(url=url, headers=headers, data=urlencode(form_data, doseq=True))
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def ccavenue_success(self, url: str, form_data: dict) -> str:
        headers = {
            "user-agent": Config.CCAVENUE_USER_AGENT,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://secure.ccavenue.com",
            "referer": "https://secure.ccavenue.com/",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "priority": "u=0, i",
            "te": "trailers",
            "cookie": self.__batik_payment_cookie_header()
        }
        response = self.__tls.post(url=url, headers=headers, data=urlencode(form_data, doseq=True),
                                   allow_redirects=False)
        if response.status not in [200, 302]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if not response.location:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "CCAvenue回跳支付状态地址为空")
        return response.location

    def payment_doku(self, pay_info: dict):
        payment_landing_url = f"https://payment.batikair.com.my/?token={quote(self.__token, safe='')}"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.__accept_language,
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        response = self.__tls.get(url=payment_landing_url, headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        timestamp, hash_token = Utils.make_header_args(self.__token)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.__accept_language,
            "Content-Type": "application/json",
            "Origin": "https://payment.batikair.com.my",
            "Referer": payment_landing_url,
            "User-Agent": self.__ua,
            "X-Env": "P",
            "X-Hash": hash_token,
            "X-TimeStamp": timestamp,
            "X-Token": self.__token,
            "X-UserAgent": "Web",
        }
        response = self.__tls.post(
            url="https://payment.batikair.com.my/payment_api/api/Doku/Payment",
            headers=headers,
            data={"payload": Utils.aes_encrypt(json.dumps(pay_info, separators=(',', ':')))}
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        payload = response.to_dict().get("response")
        if not payload:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "Doku支付响应为空")
        return Utils.aes_decrypt(payload)

    @staticmethod
    def doku_extract_token_id(redirect_url: str) -> str:
        token_id = urlparse(redirect_url).path.rstrip('/').split('/')[-1]
        if not token_id:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "Doku token为空")
        return token_id

    def doku_open_checkout_page(self, token_id: str):
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.__accept_language,
            "Referer": "https://payment.batikair.com.my/",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        response = self.__tls.get(url=f"https://checkout.doku.com/checkout-link-v2/{token_id}", headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    def doku_get_checkout_data(self, token_id: str) -> dict:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.__accept_language,
            "Referer": f"https://checkout.doku.com/checkout-link-v2/{token_id}",
            "User-Agent": self.__ua,
        }
        response = self.__tls.get(
            url=f"https://checkout.doku.com/checkout/v2/payment/show/{token_id}?isFromEmail=false",
            headers=headers
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def doku_choose_credit_card(self, token_id: str):
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.__accept_language,
            "Content-Type": "application/json; charset=utf-8",
            "Referer": "https://checkout.doku.com/checkout-link-v2/payment/page?paymentChannel=CREDIT_CARD&channelName=CREDIT_CARD&status=single-payment",
            "User-Agent": self.__ua,
        }
        response = self.__tls.get(
            url=f"https://checkout.doku.com/checkout/journey/{token_id}/CUSTOMER_CHOOSE_PAYMENT_CHANNEL/CREDIT_CARD",
            headers=headers
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    def doku_generate_key(self, token_id: str, request_id: str, client_id: str) -> dict:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.__accept_language,
            "Client-Id": client_id,
            "Referer": "https://checkout.doku.com/checkout-link-v2/payment/page?paymentChannel=CREDIT_CARD&channelName=CREDIT_CARD&status=single-payment",
            "Request-Id": request_id,
            "User-Agent": self.__ua,
        }
        response = self.__tls.get(
            url=f"https://checkout.doku.com/checkout/h2h/generate/key/{token_id}",
            headers=headers
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    @staticmethod
    def doku_encrypt_card_payload(public_key: str, pay_info: dict) -> str:
        return RsaCiphering(rsa_public_key=public_key, pkcs=2).encrypt(json.dumps(pay_info, separators=(',', ':')))

    def doku_pay_credit_card(self, token_id: str, request_id: str, client_id: str, encrypted_data: str,
                             payer_account_id: Optional[str] = None) -> dict:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.__accept_language,
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": "https://checkout.doku.com",
            "Referer": "https://checkout.doku.com/checkout-link-v2/payment/page?paymentChannel=CREDIT_CARD&channelName=CREDIT_CARD&status=single-payment",
            "User-Agent": self.__ua,
        }
        response = self.__tls.post(
            url="https://checkout.doku.com/checkout/h2h/payment",
            headers=headers,
            data={
                "token_id": token_id,
                "request_id": request_id,
                "client_id": client_id,
                "data": encrypted_data,
                "retry_payment": False,
                "channel_id": "CREDIT_CARD",
                "payer_account_id": payer_account_id
            }
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def doku_get_public_ip(self) -> str:
        try:
            response = self.__tls.get(
                url="https://api.doku.com/doku-check-ip-address/?format=json",
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": self.__accept_language,
                    "User-Agent": self.__ua
                },
                timeout=15
            )
            if response.status == 200:
                return response.to_dict().get("ip") or "127.0.0.1"
        except Exception:
            pass
        return "127.0.0.1"

    def doku_get_device_info(self) -> dict:
        browser_version_match = re.search(r'Chrome/([\d.]+)', self.__ua)
        browser_version = browser_version_match.group(1) if browser_version_match else "142.0.0.0"
        browser_major_version = browser_version.split('.')[0]
        utc_offset_minutes = int(-time.localtime().tm_gmtoff / 60)
        local_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int((time.time() % 1) * 1000):03d}Z"
        return {
            "local_time": local_time,
            "time_zone": "中国标准时间",
            "timezone_offset": utc_offset_minutes,
            "os": "Windows",
            "os_version": "10",
            "engine": "Blink",
            "engine_version": browser_version,
            "device": None,
            "device_type": None,
            "device_channel": "Browser",
            "browser": "Chrome",
            "browser_version": browser_version,
            "browser_major_version": browser_major_version,
            "ip_address": self.doku_get_public_ip(),
            "mime_types": "Portable Document Format, Portable Document Format, undefined, undefined, undefined",
            "plugins": "PDF Viewer, Chrome PDF Viewer, Chromium PDF Viewer, Microsoft Edge PDF Viewer, WebKit built-in PDF, undefined, item, namedItem, refresh",
            "session_storage": 1,
            "local_storage": 1,
            "indexed_db": 1,
            "do_not_track": None,
            "java_enabled": False,
            "http_browser_javascript_enabled": True,
            "browser_details": {
                "three_d_secure_challange_window_size": "",
                "accept_headers": "application/json",
                "color_depth": 32,
                "java_enabled": False,
                "language": "zh-CN",
                "screen_height": 1080,
                "screen_width": 1920,
                "time_zone": str(utc_offset_minutes),
            },
            "current_resolution": "1920x1080",
            "available_resolution": "1920x1032",
            "color_depth": 32,
            "language": "zh-CN",
            "screen_height": 1080,
            "screen_width": 1920,
            "http_accept": "application/json, text/plain, */*",
            "http_user_accept": "application/json, text/plain, */*",
            "http_user_agent": self.__ua
        }

    def doku_get_three_d_secure_data(self, authentication_id: str, client_id: str) -> dict:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.__accept_language,
            "Content-Type": "application/json",
            "Origin": "https://jokul.doku.com",
            "Referer": f"https://jokul.doku.com/wt-frontend-transaction/three-d-secure?authenticationId={authentication_id}&clientId={client_id}",
            "User-Agent": self.__ua,
        }
        response = self.__tls.post(
            url="https://jokul.doku.com/credit-card/get-three-d-secure-data",
            headers=headers,
            data={
                "authentication_id": authentication_id,
                "device_info": self.doku_get_device_info()
            }
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def doku_submit_mpgs_creq(self, acs_url: str, creq: str) -> str:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.__accept_language,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://jokul.doku.com",
            "Referer": "https://jokul.doku.com/",
            "User-Agent": self.__ua,
        }
        response = self.__tls.post(url=acs_url, headers=headers, data=urlencode({"creq": creq or "e30="}))
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def doku_submit_redirect_back(self, action_url: str, form_data: dict) -> str:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.__accept_language,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://ap.gateway.mastercard.com",
            "Referer": "https://ap.gateway.mastercard.com/",
            "User-Agent": self.__ua,
        }
        response = self.__tls.post(url=action_url, headers=headers, data=urlencode(form_data), allow_redirects=False)
        if response.status not in [200, 302]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if not response.location:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "3DS回跳地址为空")
        return response.location

    def doku_callback_success(self, callback_url: str):
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.__accept_language,
            "Referer": "https://ap.gateway.mastercard.com/",
            "User-Agent": self.__ua,
        }
        response = self.__tls.get(url=callback_url, headers=headers)
        if response.status not in [200, 302]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    def doku_return_batik(self, callback_url: str) -> str:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.__accept_language,
            "Referer": "https://checkout.doku.com/",
            "User-Agent": self.__ua,
        }
        response = self.__tls.get(url=callback_url, headers=headers, allow_redirects=False)
        if response.status not in [200, 302]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if not response.location:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "Batik支付状态地址为空")
        return response.location

    def doku_open_payment_status_page(self, payment_status_url: str, ccavenue_headers: bool = False):
        if ccavenue_headers:
            headers = {
                "user-agent": Config.CCAVENUE_USER_AGENT,
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
                "accept-encoding": "gzip, deflate, br, zstd",
                "referer": "https://secure.ccavenue.com/",
                "upgrade-insecure-requests": "1",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "cross-site",
                "priority": "u=0, i",
                "te": "trailers",
                "cookie": self.__batik_payment_cookie_header()
            }
        else:
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": self.__accept_language,
                "User-Agent": self.__ua,
            }
        response = self.__tls.get(url=payment_status_url, headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    def doku_verify_status(self, payment_token: str, referer: str, ccavenue_headers: bool = False) -> dict:
        timestamp, hash_token = Utils.make_header_args(payment_token)
        if ccavenue_headers:
            headers = {
                "user-agent": Config.CCAVENUE_USER_AGENT,
                "accept": "application/json, text/plain, */*",
                "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
                "accept-encoding": "gzip, deflate, br, zstd",
                "x-useragent": "Web",
                "x-timestamp": timestamp,
                "x-env": "P",
                "x-token": payment_token,
                "x-hash": hash_token,
                "referer": referer,
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "te": "trailers",
                "cookie": self.__batik_payment_cookie_header()
            }
            headers.update(self.__ccavenue_sentry_headers())
        else:
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": self.__accept_language,
                "Referer": referer,
                "User-Agent": self.__ua,
                "X-Env": "P",
                "X-Hash": hash_token,
                "X-TimeStamp": timestamp,
                "X-Token": payment_token,
                "X-UserAgent": "Web",
            }
        response = self.__tls.get(url="https://payment.batikair.com.my/payment_api/api/Enquiry/VerifyStatus",
                                  headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def doku_ticket_status(self, payment_token: str, referer: Optional[str] = None,
                           ccavenue_headers: bool = False) -> dict:
        timestamp, hash_token = Utils.make_header_args(payment_token)
        if ccavenue_headers:
            headers = {
                "user-agent": Config.CCAVENUE_USER_AGENT,
                "accept": "application/json, text/plain, */*",
                "accept-language": Config.CCAVENUE_ACCEPT_LANGUAGE,
                "accept-encoding": "gzip, deflate, br, zstd",
                "x-useragent": "Web",
                "x-timestamp": timestamp,
                "x-env": "P",
                "x-token": payment_token,
                "x-hash": hash_token,
                "origin": "https://payment.batikair.com.my",
                "referer": referer or "https://payment.batikair.com.my/",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "te": "trailers",
                "cookie": self.__batik_payment_cookie_header()
            }
        else:
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": self.__accept_language,
                "Origin": "https://payment.batikair.com.my",
                "Referer": referer or "https://payment.batikair.com.my/",
                "User-Agent": self.__ua,
                "X-Env": "P",
                "X-Hash": hash_token,
                "X-TimeStamp": timestamp,
                "X-Token": payment_token,
                "X-UserAgent": "Web",
            }
        response = self.__tls.get(url="https://booking.batikair.com.my/bookrr_api/api/Get/TicketStatus",
                                  headers=headers)
        if response.status not in [200, 204]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if response.status == 204:
            return {}
        return response.to_dict()

    @staticmethod
    def extract_itinerary_id(location_url: str) -> Optional[str]:
        if not location_url:
            return None
        query = parse_qs(urlparse(location_url).query)
        itinerary_ids = query.get("itineraryId")
        return itinerary_ids[0] if itinerary_ids else None

    def pay_finish_public(self, url: str, form_data: dict):
        headers = {
            "Cache-Control": "max-age=0",
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "accept-language": self.__accept_language,
            "Origin": "https://secureacceptance.cybersource.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://secureacceptance.cybersource.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        response = self.__tls.post(url=url, headers=headers, data=urlencode(form_data), allow_redirects=False)
        if response.status not in [200, 302]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if not response.location:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "PublicBank回跳地址为空")
        return response.location

    def public_bank_confirmation(self, confirmation_token: str) -> Optional[str]:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.__accept_language,
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        response = self.__tls.get(
            url=f"https://www.batikair.com.my/book/confirmation?token={quote(confirmation_token, safe='')}",
            headers=headers,
            allow_redirects=True
        )
        for candidate in [response.url, response.to_text()]:
            itinerary_id = self.extract_itinerary_id(candidate)
            if itinerary_id:
                return itinerary_id
            match = re.search(r'itineraryId(?:=|%3D)([^"&\s<]+)', candidate or '')
            if match:
                return match.group(1)
        return None

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip), (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip),
         (ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, reset_proxy_ip),
         (ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, reset_proxy_ip), ])
    def email_blacklist(self):
        headers = {
            "accept-encoding": "gzip, deflate, br, zstd",
            "user-agent": self.__ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": self.__accept_language,
            "origin": "https://www.batikair.com.my",
            "connection": "keep-alive",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "te": "trailers"
        }

        response = self.__tls.get(
            url="https://cms-cdn.batikair.com/66472e6388f4647bd5f90f87/published/fraud_emails.json", headers=headers)
        if response.status != 200:
            if response.status == 429:
                raise ServiceError(ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, response.status)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_dict()

    def payment(self, pay_info: dict):
        url = 'https://payment.batikair.com.my/payment_api/api/eghl/Payment'
        timestamp, hash_token = Utils.make_header_args(self.__token)
        headers = {
            "accept-language": self.__accept_language,
            "X-Token": self.__token,
            "X-UserAgent": "Web",
            "X-TimeStamp": timestamp,
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "X-Hash": hash_token,
            "X-Env": "P",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.batikair.com.my",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "X-GToken": self.g_token
        }
        submit_data_encrypt = Utils.aes_encrypt(json.dumps(pay_info))

        data = {
            "payload": submit_data_encrypt
        }

        response = self.__tls.post(url=url,
                                   headers=headers,
                                   data=data)
        if response.status != 200:
            if response.status == 401:
                return None
            if response.status != 200:
                raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if response.to_dict().get("isCaptchaRetryAttempt", False):
            return None

        data = response.to_dict()['response']

        result = Utils.aes_decrypt(data)
        if "Session expired" in json.dumps(result):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "速率过快，联系技术调整速率")
        print(result)
        return result

    def pay_finish(self, url: str, form_data: dict):
        """
        接收支付平台传过来的参数
        Args:
            url:
            form_data:

        Returns:

        """

        pnr = form_data['OrderNumber'].split('_')[0]
        headers = {

            "Cache-Control": "max-age=0",
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "accept-language": self.__accept_language,
            "Origin": "https://securepay.e-ghl.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://securepay.e-ghl.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        response = self.__tls.post(url=url,
                                   headers=headers,
                                   data=urlencode(form_data), allow_redirects=False)
        if response.status != 200 and response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        location = response.headers.get('location') or response.headers.get('Location')

        pattern = 'itineraryId=(.*)'
        itinerary_id = re.search(pattern, location).group(1)

        return itinerary_id, pnr

    def get_book_info(self, itinerary_id):
        self.__token = ''
        url = f'https://booking.batikair.com.my/bookrr_api/api/get/Confirmation/?itineraryId={quote(itinerary_id)}'
        timestamp, hash_token = Utils.make_header_args(self.__token)
        headers = {
            "accept-language": self.__accept_language,
            "X-Token": "",
            "X-UserAgent": "Web",
            "X-TimeStamp": timestamp,
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "X-Hash": hash_token,
            "X-Env": "P",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.batikair.com.my",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }

        response = self.__tls.get(url=url, headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_dict()

    def pay_return(self, url, data: dict):
        headers = {
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "sec-ch-ua-mobile": self.__header_profile["sec_ch_ua_mobile"],
            "accept-language": self.__accept_language,
            "Origin": "null",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Accept-Encoding": "gzip, deflate, br, zstd"
        }
        response_post = self.__tls.post(url=url,
                                        data=urlencode(data),
                                        headers=copy(headers))
        if response_post.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response_post.status)
        response_get = self.__tls.get(url=response_post.headers['location'],
                                      headers=headers)
        if response_get.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response_post.status)

    def get_viewstate_data(self):
        headers = {
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": self.__ua,

        }
        response = self.__tls.get(url='https://mmb.batikair.com.my/OD/OnlineAddonBooking.aspx', headers=copy(headers),
                                  allow_redirects=True)
        if response.status != 200:
            if response.status == 403:
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        xpath_data = etree.HTML(response.to_text())
        print(response.url)
        return response.url, {
            "__EVENTTARGET": ''.join(xpath_data.xpath('''//*[@id="__EVENTTARGET"]//@value''')).strip(),
            "__EVENTARGUMENT": ''.join(xpath_data.xpath('''//*[@id="__EVENTARGUMENT"]//@value''')).strip(),
            "__VIEWSTATE": ''.join(xpath_data.xpath('''//*[@id="__VIEWSTATE"]//@value''')).strip(),
            "__VIEWSTATEGENERATOR": ''.join(xpath_data.xpath('''//*[@id="__VIEWSTATEGENERATOR"]//@value''')).strip(),
            "__EVENTVALIDATION": ''.join(xpath_data.xpath('''//*[@id="__EVENTVALIDATION"]//@value''')).strip(),
            "__VIEWSTATEENCRYPTED": ''.join(xpath_data.xpath('''//*[@id="__VIEWSTATEENCRYPTED"]//@value''')).strip(),
        }

    def get_pnr(self, pnr: str, last_name: str, first: str, token: str, view_status_data: dict,
                next_url: str):

        url = next_url
        view_status_data.update({
            'txtPNR': pnr,
            'txtFirstName': first,
            'txtLastName': last_name,
            'btnRetreiveDetails': 'Continue',
            'g-recaptcha-response': token
        })

        headers = {
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "User-Agent": self.__ua,

        }
        response = self.__tls.post(url=url,
                                   headers=copy(headers),
                                   data=urlencode(view_status_data), allow_redirects=True)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        self.t = next_url.split('?')[1]
        print(self.t)
        return response.to_text()

    def get_pnr_addon(self, pnr_info):
        from pyquery import PyQuery

        def get_form_data(form):
            action = form.attr("action")
            inputs = form("input")
            form_data = {}
            for input_tag in inputs.items():
                input_name = input_tag.attr("name") or ""
                input_value = input_tag.attr("value") or ""
                if input_name:
                    form_data[input_name] = input_value

            return action, form_data

        doc = PyQuery(pnr_info)
        form = doc("form")  # 目前抓包，网页内只有一个表单
        action, form_data = get_form_data(form)

        action = f'https://mmb.batikair.com.my/OD/UserProfile/ManageAddons.aspx?{self.t}'
        form_data['__ASYNCPOST'] = 'true'
        form_data['ctl00$ScriptManager1'] = 'ctl00$bodycontent$upnManageBooking|ctl00$bodycontent$btnAddOnPurchase'
        form_data['ctl00$bodycontent$ddlMblCountryCode'] = ''
        if form_data.get('ctl00$bodycontent$btnscndryContactInfo'):
            del form_data['ctl00$bodycontent$btnscndryContactInfo']
        if form_data.get('ctl00$bodycontent$btnChangeFlight'):
            del form_data['ctl00$bodycontent$btnChangeFlight']
        data = urlencode(form_data)

        headers = {
            "Accept": "*/*",
            "accept-language": self.__accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": "https://mmb.batikair.com.my/",
            "X-Requested-With": "XMLHttpRequest",
            "X-MicrosoftAjax": "Delta=true",
            "Cache-Control": "no-cache",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Origin": "https://mmb.batikair.com.my",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=0",
            "TE": "trailers",
            "user-agent": self.__ua
        }
        res = self.__tls.post(url=action, data=data,
                              headers=headers
                              )
        if res.status != 200:
            if res.status == 403:
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, res.status)
        t = re.search('t=(.*)', self.t).group(1)
        headers = {
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "user-agent": self.__ua

        }
        response = self.__tls.get(url=f'https://mmb.batikair.com.my/OD/OptionalAddons.aspx?t={t}',
                                  headers=headers, allow_redirects=True)
        if response.status != 200:
            if response.status == 403:
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_text()

    def installment_fee(self):
        timestamp, hash_token = Utils.make_header_args(self.__token)

        header = {
            "user-agent": self.__ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": self.__accept_language,
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "x-useragent": "Web",
            "x-timestamp": timestamp,
            "x-env": "P",
            "x-token": self.__token,
            "x-hash": hash_token,
            "origin": "https://www.batikair.com.my",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "te": "trailers"
        }
        response = self.__tls.post(url=f'https://cart.batikair.com.my/cartrr_api/api/Add/InstallmentFee',
                                   headers=header,
                                   data={
                                       "searchId": "",
                                       "cartId": "",
                                       "isSelected": False,
                                       "paymentGateway": None,
                                       "paymentMethod": None
                                   })

    def validate_pnr(self, data):
        timestamp, hash_token = Utils.make_header_args(self.__token)
        headers = {
            'accept': 'application/json, text/plain, */*',
            "accept-language": self.__accept_language,
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://mb.batikair.com.my',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://mb.batikair.com.my/manage-booking/login',
            'sec-ch-ua': self.__header_profile["sec_ch_ua"],
            'sec-ch-ua-mobile': self.__header_profile["sec_ch_ua_mobile"],
            'sec-ch-ua-platform': self.__header_profile["sec_ch_ua_platform"],
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self.__ua,
            'x-env': 'P',
            'x-hash': hash_token,
            'x-timestamp': timestamp,
            'x-token': '',
            'x-useragent': 'Web',
        }
        response = self.__tls.post(url='https://mb.batikair.com.my/mmbreadpnr_api/api/ViewBooking/ValidatePNR',
                                   headers=headers,
                                   data=data,
                                   allow_redirects=False, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()
