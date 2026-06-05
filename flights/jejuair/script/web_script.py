import copy
import json
import re
from urllib.parse import urlencode

import requests

from common.decorators.retry_decorator import retry_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.response_info_model import ResponseInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.tls.danli_tls import DanLiTls
from common.utils.chaojiying_utlis import ChaojiyingClient
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.string_util import StringUtil
from ..config import Config

DANLI_UTILS = DanLiCaptchaUtil("7j58fx77bifxt2jhx01pwoek7asgp6xm")


class WebScript:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.page_key = None
        self.book_type = 'Common'
        self.culture_code = 'zh-cn'
        self.sec_ch_ua = f'"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"'
        self.__timeout = 10
        self.__language = self.culture_code
        # self.__tls = CurlCffiTls()
        # self.__tls.initialize(proxy_info_data=proxy_info_data, impersonate="chrome145")
        self.__tls = DanLiTls("7j58fx77bifxt2jhx01pwoek7asgp6xm")
        self.__tls.initialize(proxy_info_data=proxy_info_data)

        self.__proxy = proxy_info_data
        self.__ua = Config.USER_AGENT

    def reset_proxy_ip(self):
        self.__tls.initialize(self.__proxy, )

    def to_cffi_tls(self):
        ck = self.__tls.get_cookie_dict()
        ip = self.__tls.get_proxy_data()
        self.__tls = CurlCffiTls()
        self.__tls.initialize(proxy_info_data=ip, impersonate="chrome145")
        self.__tls.cookie_update(ck)

    def get_akm(self):
        self.reset_proxy_ip()
        akm_info = DANLI_UTILS.akamai_ck_get("jejuair")
        self.__ua = akm_info["ua"]
        if "Chrome/" in self.__ua:
            chrome_version = self.__ua.split("Chrome/")[1].split(".0.0.0")[0]
            self.sec_ch_ua = (
                f'"Chromium";v="{chrome_version}", '
                f'"Google Chrome";v="{chrome_version}", "Not.A/Brand";v="99"'
            )
        self.__tls.cookie_update(akm_info["data"])

    @staticmethod
    def __response_data(response_dict: dict) -> dict:
        data = response_dict.get('data') or {}
        if isinstance(data.get('data'), dict):
            return data.get('data') or {}
        return data

    @retry_decorator([(ServiceStateEnum.AKM_RISK_CHECK_FAILED, None), (ServiceStateEnum.HTTP_EXCEPTION, None),
                      (ServiceStateEnum.CURL_EXCEPTION, None)],
                     retry_max_number=3)
    def prepare_context(self):
        self.get_akm()
        headers = {
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-ch-ua-mobile": "?0",
            "access-control-allow-origin": "*",
            "user-agent": self.__ua,
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "accept": "application/json, text/plain, */*",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.jejuair.com",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "sec-fetch-user": "?1",
            "sec-ch-ua": self.sec_ch_ua,
            "referer": "https://www.jejuair.com/",
            "accept-encoding": "gzip, deflate, br, zstd",
        }
        self.__tls.get(
            url=f'https://www.jejuair.net/{self.__language}/main/base/index.do',
            headers=headers,
            timeout=self.__timeout
        )
        self.__tls.get(
            url=f'https://www.jejuair.net/{self.__language}/main/base/index.do?_R=MQ==',
            headers=headers,
            timeout=self.__timeout
        )

    @retry_decorator([(ServiceStateEnum.AKM_RISK_CHECK_FAILED, get_akm), (ServiceStateEnum.CURL_EXCEPTION, get_akm)],
                     retry_max_number=3)
    def avail_search(self, flight_params: dict):
        headers = {
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-ch-ua-mobile": "?0",
            "access-control-allow-origin": "*",
            "user-agent": self.__ua,
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "accept": "application/json, text/plain, */*",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.jejuair.com",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "sec-fetch-user": "?1",
            "sec-ch-ua": self.sec_ch_ua,
            "referer": "https://www.jejuair.com/",
            "accept-encoding": "gzip, deflate, br, zstd",
        }
        response = self.__tls.post(
            url=f'https://www.jejuair.net/{self.__language}/ibe/booking/AvailSearch.do',
            headers=headers,
            data=urlencode(flight_params),
            timeout=self.__timeout
        )
        if response.status in [403, 428]:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        self.page_key = StringUtil.extract_between(response.to_text(), 'pageKey : "', '"')
        return self.page_key

    @retry_decorator([(ServiceStateEnum.AKM_RISK_CHECK_FAILED, get_akm), (ServiceStateEnum.CURL_EXCEPTION, get_akm)],
                     retry_max_number=3)
    def select_bundle_ancillaries(self, dep_date: str, dom_int_type: str, area_code: str):
        if (self.culture_code or '').lower().startswith('zh'):
            lang_code = (self.culture_code or 'zh-cn')[:5]
        else:
            lang_code = (self.culture_code or 'en')[:2]

        headers = {
            "User-Agent": self.__ua,
            "sec-ch-ua": self.sec_ch_ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Channel-Code": "WPC",
            "User-Id": "",
            "User-Name": "",
            "agentId": "sys_web.us",
            "Origin": "https://www.jejuair.net",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "TE": "trailers"
        }
        response = self.__tls.post(
            url=f'https://sec.jejuair.net/{self.__language}/ibe/booking/selectBundleAncillaries.json',
            headers=headers,
            data=urlencode({
                'depdate': re.sub(r'[^0-9]', '', dep_date or ''),
                'langCode': lang_code,
                'domIntType': dom_int_type,
                'areaCode': area_code,
            }),
            timeout=self.__timeout
        )
        if response.status in [403, 428]:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        response_data = self.__response_data(response.to_dict())
        return response_data.get('mtxTt', [])

    @retry_decorator([(ServiceStateEnum.AKM_RISK_CHECK_FAILED, get_akm), (ServiceStateEnum.CURL_EXCEPTION, get_akm)],
                     retry_max_number=3)
    def search_flight(self, flight_params: dict):
        headers = {
            "User-Agent": self.__ua,
            "sec-ch-ua": self.sec_ch_ua,
            "Accept": "text/html, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Channel-Code": "WPC",
            "User-Id": "",
            "User-Name": "",
            "agentId": "sys_web.us",
            "Origin": "https://www.jejuair.net",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "TE": "trailers"
        }
        response = self.__tls.post(
            url=f'https://sec.jejuair.net/{self.__language}/ibe/booking/getAvailSchedule.json',
            headers=headers,
            data=urlencode(flight_params),
            timeout=self.__timeout
        )
        if response.status in [403, 428]:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if "预订时间已超时" in response.to_text():
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    @retry_decorator([(ServiceStateEnum.AKM_RISK_CHECK_FAILED, get_akm), (ServiceStateEnum.CURL_EXCEPTION, get_akm)],
                     retry_max_number=3)
    def direct_avail_pass_input(self, submit_data: dict) -> ResponseInfoModel:
        headers = {
            "User-Agent": self.__ua,
            "sec-ch-ua": self.sec_ch_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
                      "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.jejuair.net",
            "Connection": "keep-alive",
            "Referer": f"https://www.jejuair.net/{self.__language}/ibe/booking/AvailSearch.do",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        response = self.__tls.post(
            url=f'https://www.jejuair.net/{self.__language}/ibe/booking/directAvailPassInput.do',
            headers=headers,
            data=urlencode(submit_data),
            timeout=self.__timeout
        )
        if response.status == 403:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status not in (200, 302):
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    @retry_decorator([(ServiceStateEnum.ROBOT_CHECK, get_akm)], retry_max_number=10)
    def direct_avail_pass_input_login_success(self, submit_data: dict, referer_url: str) -> str:
        headers = {
            "User-Agent": self.__ua,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": referer_url,
            "Origin": "https://www.jejuair.net",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=0, i",
            "TE": "trailers"
        }
        response = self.__tls.post(
            url=f'https://www.jejuair.net/{self.__language}/ibe/booking/directAvailPassInput.do?loginSuccess=Y',
            headers=headers,
            data=urlencode(submit_data),
            timeout=self.__timeout
        )
        if response.status == 403:
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
        if response.status != 200:
            if response.status == 302:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "价格为缓存")
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def login_page(self, security: str) -> str:
        headers = {
            "User-Agent": self.__ua,
            "sec-ch-ua": self.sec_ch_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
                      "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Referer": f"https://www.jejuair.net/{self.__language}/ibe/booking/AvailSearch.do",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        response = self.__tls.get(
            url=f'https://www.jejuair.net/{self.__language}/member/auth/login.do?{urlencode({"security": security})}',
            headers=headers,
            timeout=self.__timeout
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def non_user_login_page(self, security: str) -> str:
        headers = {
            "User-Agent": self.__ua,
            "sec-ch-ua": self.sec_ch_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
                      "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Referer": f'https://www.jejuair.net/{self.__language}/member/auth/login.do?{urlencode({"security": security})}',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        response = self.__tls.get(
            url=f'https://www.jejuair.net/{self.__language}/member/auth/nonUserLogin.do?{urlencode({"security": security})}',
            headers=headers,
            timeout=self.__timeout
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def captcha_image(self, security: str) -> bytes:
        headers = {
            "User-Agent": self.__ua,
            "sec-ch-ua": self.sec_ch_ua,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Referer": (
                f'https://www.jejuair.net/{self.__language}/member/auth/nonUserLogin.do?'
                f'{urlencode({"security": security})}'
            ),
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
        }
        if isinstance(self.__tls, CurlCffiTls):
            response = self.__tls.get(
                url=f'https://www.jejuair.net/{self.__language}/member/memberJoin/captchaImg.do',
                headers=headers,
                timeout=self.__timeout
            )
            if response.status != 200:
                raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
            return response.data_bytes

        proxy_data = self.__tls.get_proxy_data()
        proxies = None
        if proxy_data:
            proxy_url = proxy_data.get_proxy_info_to_string()
            proxies = {
                'http': proxy_url,
                'https': proxy_url,
            }
        response = requests.get(
            url=f'https://www.jejuair.net/{self.__language}/member/memberJoin/captchaImg.do',
            headers=headers,
            timeout=self.__timeout,
            cookies=self.__tls.get_cookie_dict(),
            proxies=proxies,
        )
        if response.status_code != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status_code)
        self.__tls.cookie_update(response.cookies.get_dict())
        return response.content

    def captcha_solver(self, captcha_image: bytes):
        chaojiying = ChaojiyingClient('odsf001', '660otzqe', '972694')
        result = chaojiying.solve_captcha(captcha_image, 6004)
        return result['pic_str']

    def captcha_check_answer(self, answer: str, security: str) -> str:
        headers = {
            "User-Agent": self.__ua,
            "sec-ch-ua": self.sec_ch_ua,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "Origin": "https://www.jejuair.net",
            "Connection": "keep-alive",
            "Referer": (
                f'https://www.jejuair.net/{self.__language}/member/auth/nonUserLogin.do?'
                f'{urlencode({"security": security})}'
            ),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        }
        response = self.__tls.post(
            url=f'https://www.jejuair.net/{self.__language}/member/memberJoin/captchaChkAnswer.do',
            headers=headers,
            data=json.dumps({"answer": answer}, ensure_ascii=False),
            timeout=self.__timeout
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text().strip()

    @retry_decorator([(ServiceStateEnum.ROBOT_CHECK, get_akm), (ServiceStateEnum.CURL_EXCEPTION, get_akm)], retry_max_number=10)
    def login_action(self, security: str, captcha_answer: str, user_email: str) -> ResponseInfoModel:
        proxy_data = self.__tls.get_proxy_data()
        proxy_url = proxy_data.get_proxy_info_to_string() if proxy_data else ''
        cookie_data = self.__tls.get_cookie_dict().copy()
        proxy_info_data = None
        if proxy_data:
            proxy_info_data = copy.deepcopy(proxy_data)
            proxy_info_data.format = proxy_url
        self.__tls = CurlCffiTls()
        self.__tls.initialize(proxy_info_data=proxy_info_data, impersonate="chrome145")
        self.__tls.cookie_update(cookie_data)

        headers = {
            "User-Agent": self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.jejuair.net",
            "Referer": f'https://www.jejuair.net/{self.__language}/member/auth/nonUserLogin.do?{urlencode({"security": security})}',
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
            "TE": "trailers"
        }
        data = urlencode({
            "apiRequestType": "3",
            "targetUrl": "",
            "nonTargetUrl": "",
            "security": security,
            "capchaAnswer": captcha_answer,
            "userEmail": (user_email or '').strip(),
            "emailAgree": "on",
        })
        response = self.__tls.post(
            url='https://www.jejuair.net/member/auth/loginAction.do',
            headers=headers,
            data=data,
            timeout=self.__timeout
        )
        if response.status == 403:
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
        if response.status not in (200, 302):
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def gateway_login_page(self, location_url: str, security: str) -> str:
        if not location_url.startswith('http'):
            location_url = f'https://www.jejuair.net{location_url}'

        headers = {
            "User-Agent": self.__ua,
            "sec-ch-ua": self.sec_ch_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
                      "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Referer": (
                f'https://www.jejuair.net/{self.__language}/member/auth/nonUserLogin.do?'
                f'{urlencode({"security": security})}'
            ),
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        response = self.__tls.get(
            url=location_url,
            headers=headers,
            timeout=self.__timeout
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()
    @retry_decorator([(ServiceStateEnum.AKM_RISK_CHECK_FAILED, get_akm), (ServiceStateEnum.CURL_EXCEPTION, get_akm)], retry_max_number=3)
    def add_passengers(self, data: dict, pss_token: str) -> dict:
        headers = {
            'User-Agent': self.__ua,
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5',
            'Referer': f'https://www.jejuair.net/{self.__language}/ibe/booking/directAvailPassInput.do?loginSuccess=Y',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'PssToken': pss_token,
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://www.jejuair.net',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Priority': 'u=0',
        }

        response = self.__tls.post(
            url=f'https://www.jejuair.net/{self.__language}/ibe/booking/savePassengers.json',
            headers=headers,
            data=urlencode(data),
            timeout=self.__timeout,
        )
        if response.status in [403, 428]:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def find_pnr(self, pss_token: str, pnr: str) -> dict:
        headers = {
            'User-Agent': self.__ua,
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5',
            'Referer': f'https://www.jejuair.net/{self.__language}/ibe/booking/directAvailPassInput.do?loginSuccess=Y',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'PssToken': pss_token,
            'Pnr': pnr,
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://www.jejuair.net',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }

        data = {
            'bookingReq': json.dumps({"cultureCode": self.culture_code}),
            'bookType': self.book_type,
        }

        response = self.__tls.post(
            url=f'https://www.jejuair.net/{self.__language}/ibe/booking/findBookingPnr.json',
            headers=headers,
            data=urlencode(data),
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if response.to_dict().get('data') == {}:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "PNR数据为空")
        return response.to_dict()
