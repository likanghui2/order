import base64
import hashlib
import hmac
import random
import re
import string
import time
from typing import Optional
from urllib.parse import urlencode, urljoin
from uuid import uuid4

import requests
from Crypto.Cipher import AES

from common.decorators.retry_decorator import retry_decorator
from common.global_variable import GlobalVariable
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.tls.danli_unlock_tls import DanliUnlockTls
from common.utils import redis_util
from common.utils.aes_ciphering import AesCiphering
from common.utils.ezcaptcha_util import EzCaptcha
from common.utils.nocaptcha_util import NoCaptchaUtil
from common.utils.string_util import StringUtil
from flights.vietjet.config import Config
from common.errors.service_error import ServiceError, ServiceStateEnum

REDIS = redis_util.RedisUtil(
    host=GlobalVariable.REDIS_HOST,
    port=GlobalVariable.REDIS_PORT,
    username=GlobalVariable.REDIS_USERNAME,
    password=GlobalVariable.REDIS_PASSWORD,
)
VJ_DEVICE_ID_PREFIX_KEY = "vj:web:x_device_id_prefix"
VJ_DEVICE_ID_PREFIX_RENDER_KEY = "vj:web:x_device_id_prefix_render"
VJ_DEVICE_ID_PREFIX_RENDER_AES_KEY = "vj:web:x_device_id_prefix_render_aes_key"
VJ_DEVICE_ID_PREFIX_TTL = 6 * 3600
VJ_HOME_URL = "https://www.vietjetair.com"
VJ_ORIGIN_URL = "https://www.vietjetair.com"


class WebScript:

    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__aws_token = None
        self.__http_utils = CurlCffiTls()
        self.__ua = Config.USER_AGENT
        self.__http_utils.initialize(proxy_info_data=proxy_info)
        self.__proxy = proxy_info
        self.__timeout = 10
        self.__vj_device_uuid = str(uuid4())
        self.__zero_trust_config = None
        self.__danli_unlock = DanliUnlockTls("7j58fx77bifxt2jhx01pwoek7asgp6xm", site="vietjetair",
                                             auth_manage_cookie=False)
        self.__danli_unlock.initialize(proxy_info_data=self.__proxy)

    def device_id(self):
        prefix = self.__get_device_id_prefix()
        render_prefix = self.__get_device_id_prefix_render()
        device_id_value, suffix = self.__build_device_id_value(render_prefix, self.__vj_device_uuid)
        x_device_id = f"{prefix}-{device_id_value}"
        if suffix:
            x_device_id = f"{x_device_id}-{suffix}"
        return x_device_id

    def z(self):
        self.___get_device_id_prefix(),
        self.___get_device_id_prefix_render()

    def zero_trust_headers(self, url):
        if not self.__zero_trust_config:
            self.__zero_trust_config = (
                self.__get_device_id_prefix(),
                self.__get_device_id_prefix_render()
            )
        prefix, render_prefix = self.__zero_trust_config
        device_id_value, suffix = self.__build_device_id_value(render_prefix, self.__vj_device_uuid)
        x_device_id = f"{prefix}-{device_id_value}"
        if suffix:
            x_device_id = f"{x_device_id}-{suffix}"

        request_time = str(int(time.time() * 1000))
        request_nonce = str(uuid4())
        signature_text = f"{url}:{request_time}:{self.__vj_device_uuid}:{request_nonce}"
        signature = hmac.new(render_prefix.encode("utf-8"),
                             signature_text.encode("utf-8"),
                             hashlib.sha256).hexdigest()
        return {
            "X-Device-ID": x_device_id,
            "X-Client-Machine-ID": hashlib.sha256(
                f"{self.__vj_device_uuid}{render_prefix}".encode("utf-8")
            ).hexdigest(),
            "X-Request-Time": request_time,
            "X-Request-Nonce": request_nonce,
            "X-Signature": signature
        }

    @staticmethod
    def __build_device_id_value(render_prefix, device_uuid):
        parts = device_uuid.split("-")
        parts = [part for part in parts if part]
        if not parts:
            return device_uuid, render_prefix

        replace_index = min(len(parts) - 1, random.randrange(len(parts)))
        if not render_prefix:
            return device_uuid, parts[replace_index]

        device_id_parts = list(parts)
        device_id_parts[replace_index] = render_prefix
        return "-".join(device_id_parts), render_prefix

    def __get_device_id_prefix(self):
        prefix = self.__get_cache_value(VJ_DEVICE_ID_PREFIX_KEY)
        if prefix:
            return prefix

        url = "https://vietjetcms-api.vietjetair.com/api/v1/cms-config/DEVICE_ID_PREFIX"
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) Gecko/20100101 Firefox/150.0",
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "origin": "https://www.vietjetair.com",
            "sec-gpc": "1",
            "referer": "https://www.vietjetair.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0"
        }
        rep = self.__http_utils.get(url=url, headers=headers, timeout=self.__timeout)
        prefix = rep.to_dict().get("cmsConfig")['value']
        self.__set_cache_value(VJ_DEVICE_ID_PREFIX_KEY, prefix)
        return prefix

    def ___get_device_id_prefix(self):
        url = "https://vietjetcms-api.vietjetair.com/api/v1/cms-config/DEVICE_ID_PREFIX"
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) Gecko/20100101 Firefox/150.0",
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "origin": "https://www.vietjetair.com",
            "sec-gpc": "1",
            "referer": "https://www.vietjetair.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0"
        }
        rep = self.__http_utils.get(url=url, headers=headers, timeout=self.__timeout)
        prefix = rep.to_dict().get("cmsConfig")['value']
        self.__set_cache_value(VJ_DEVICE_ID_PREFIX_KEY, prefix)
        return prefix

    def ___get_device_id_prefix_render(self):
        url = "https://vietjetcms-api.vietjetair.com/api/v1/cms-config/DEVICE_ID_PREFIX_RENDER"
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) Gecko/20100101 Firefox/150.0",
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "origin": "https://www.vietjetair.com",
            "sec-gpc": "1",
            "referer": "https://www.vietjetair.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0"
        }
        rep = self.__http_utils.get(url=url, headers=headers, timeout=self.__timeout)
        encrypted_prefix = rep.to_dict().get("cmsConfig")['value']
        aes_key = self.__get_device_id_prefix_render_aes_key()
        prefix = self.__decrypt_device_id_prefix_render(encrypted_prefix, aes_key)
        self.__set_cache_value(VJ_DEVICE_ID_PREFIX_RENDER_KEY, prefix)
        return prefix

    def __get_device_id_prefix_render(self):
        prefix = self.__get_cache_value(VJ_DEVICE_ID_PREFIX_RENDER_KEY)
        if prefix:
            return prefix

        url = "https://vietjetcms-api.vietjetair.com/api/v1/cms-config/DEVICE_ID_PREFIX_RENDER"
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) Gecko/20100101 Firefox/150.0",
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "origin": "https://www.vietjetair.com",
            "sec-gpc": "1",
            "referer": "https://www.vietjetair.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=0"
        }
        rep = self.__http_utils.get(url=url, headers=headers, timeout=self.__timeout)
        encrypted_prefix = rep.to_dict().get("cmsConfig")['value']
        aes_key = self.__get_device_id_prefix_render_aes_key()
        prefix = self.__decrypt_device_id_prefix_render(encrypted_prefix, aes_key)
        self.__set_cache_value(VJ_DEVICE_ID_PREFIX_RENDER_KEY, prefix)
        return prefix

    def __get_device_id_prefix_render_aes_key(self):
        aes_key = self.__get_cache_value(VJ_DEVICE_ID_PREFIX_RENDER_AES_KEY)
        if aes_key:
            return aes_key

        main_js_url = self.__get_main_js_url()
        js = self.__http_utils.get(
            url=main_js_url,
            headers={'accept': '*/*'},
            timeout=20,
        ).to_text()

        patterns = [
            r'REACT_APP_DEVICE_ID_PREFIX_RENDER_AES_KEY\|\|["\']([^"\']+)["\']',
            r'REACT_APP_DEVICE_ID_PREFIX_RENDER_AES_KEY\s*:\s*["\']([^"\']+)["\']',
            r'REACT_APP_DEVICE_ID_PREFIX_RENDER_KEY\s*:\s*["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, js)
            if match:
                aes_key = match.group(1).strip()
                self.__set_cache_value(VJ_DEVICE_ID_PREFIX_RENDER_AES_KEY, aes_key)
                return aes_key

        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "获取 VietJet DEVICE_ID_PREFIX_RENDER AES key 失败")

    def __get_main_js_url(self):
        html = self.__http_utils.get(
            url=VJ_HOME_URL,
            headers={
                "Host": "www.vietjetair.com",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) Gecko/20100101 Firefox/150.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Priority": "u=0, i"
            },
            timeout=20,
        )
        if html.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, html.status)
        html = html.to_text()
        pattern = r'["\']((?:https://www\.vietjetair\.com)?/static/js/main\.[^"\']+\.chunk\.js)["\']'
        match = re.search(pattern, html)
        if not match:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "获取 VietJet main chunk 失败")
        return urljoin(VJ_ORIGIN_URL, match.group(1))

    @staticmethod
    def __decrypt_device_id_prefix_render(encrypted_prefix, aes_key):
        encrypted_data = base64.b64decode(encrypted_prefix.replace(" ", ""))
        key_bytes_list = [WebScript.__device_id_render_key_by_utf8(aes_key)]
        hex_key = WebScript.__device_id_render_key_by_hex(aes_key)
        if hex_key:
            key_bytes_list.append(hex_key)

        for key_bytes in key_bytes_list:
            try:
                return AesCiphering.decrypt(
                    data=encrypted_data,
                    key=key_bytes,
                    iv=None,
                    mode=AES.MODE_ECB,
                ).decode("utf-8")
            except Exception:
                continue

        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "解密 VietJet DEVICE_ID_PREFIX_RENDER 失败")

    @staticmethod
    def __device_id_render_key_by_utf8(aes_key):
        key_hex = aes_key.encode("utf-8").hex()[:32].ljust(32, "0")
        return bytes.fromhex(key_hex)

    @staticmethod
    def __device_id_render_key_by_hex(aes_key):
        key_hex = re.sub(r"\s", "", aes_key).removeprefix("0x").removeprefix("0X")
        if not key_hex or len(key_hex) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", key_hex):
            return None
        return bytes.fromhex(key_hex[:32].ljust(32, "0"))

    @staticmethod
    def __get_cache_value(key):
        try:
            value = REDIS.get_value(key)
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return value
        except Exception:
            return None

    @staticmethod
    def __set_cache_value(key, value):
        try:
            REDIS.set_value_ex(key, value, VJ_DEVICE_ID_PREFIX_TTL)
        except Exception:
            pass

    def initialize_session(self):
        self.__http_utils.initialize(proxy_info_data=self.__proxy)
        self.__zero_trust_config = None

    def token_macie(self):
        token_data = self.aws()
        token = token_data['data']['token']
        self.initialize_session()
        self.__ua = token_data['data']['ua']
        self.__aws_token = token

    def reset_proxy_ip(self):
        self.__http_utils.initialize(self.__proxy)

    @retry_decorator(
        [(ServiceStateEnum.API_RESPONSE_FAILED, None), (ServiceStateEnum.RESPONSE_STATE_ERROR, None)])
    def aws(self):
        try:
            token_info = requests.post('http://api.zjdanli.com/aws/token', json={
                "appid": "7j58fx77bifxt2jhx01pwoek7asgp6xm",
                "siteUrl": "www.vietjetair.com"
            }).json()
            print(token_info)
            if token_info['code'] == '0':
                return token_info
            else:
                raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, token_info['message'])
        except Exception as e:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED, str(e))

    @staticmethod
    def delete_device_id_prefix_cache():
        try:
            REDIS.delete_key(VJ_DEVICE_ID_PREFIX_KEY)
            REDIS.delete_key(VJ_DEVICE_ID_PREFIX_RENDER_KEY)
            REDIS.delete_key(VJ_DEVICE_ID_PREFIX_RENDER_AES_KEY)
            return True
        except Exception:
            return False

    # @retry_decorator(
    #     [(ServiceStateEnum.ROBOT_CHECK, token_macie), (ServiceStateEnum.AWS_CHECK_FAILURE, token_macie),
    #      (ServiceStateEnum.CURL_EXCEPTION, token_macie)])
    def search_flight(self, data):
        # if not self.__aws_token:
        #     self.token_macie()
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-cn',
            'cache-control': 'no-cache',
            'content-language': 'zh-cn',
            'content-type': 'application/json',
            'origin': 'https://www.vietjetair.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': self.__ua,
            # "X-Aws-Waf-Token": self.__aws_token,
        }
        # headers.update(self.zero_trust_headers('/booking/api/v1/search-flight'))
        params = {"encrypted": data}
        response = self.__danli_unlock.patch(url='https://vietjet-api.vietjetair.com/booking/api/v1/search-flight',
                                             headers=headers, data=params, timeout=self.__timeout)

        if response.status in [202, 201]:
            raise ServiceError(ServiceStateEnum.AWS_CHECK_FAILURE)
        if response.status == 405 or response.to_dict().get('travelOptions') or response.to_dict() == {}:
            raise ServiceError(ServiceStateEnum.AWS_CHECK_FAILURE)
        if response.status != 200:
            if response.status == 403:
                raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
         (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def baggage_search(self, request_id):
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-cn',
            'cache-control': 'no-cache',
            'content-language': 'zh-cn',
            'content-type': 'application/json',
            'origin': 'https://www.vietjetair.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': self.__ua,
        }
        response = self.__http_utils.get(
            url=f'https://vietjetcms-api.vietjetair.com/api/v1/ticket?languageId={Config.LANGUAHE_ID}&requestId={request_id}',
            headers=headers, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def search_flight_min(self, data: dict):
        headers = {"Connection": "keep-alive",
                   "terminal": "10",
                   "User-Agent": self.__ua,
                   "xweb_xhr": "1",
                   "Content-Type": "application/json",
                   "tenant-id": "1",
                   "Accept": "*/*",
                   "Sec-Fetch-Site": "cross-site",
                   "Sec-Fetch-Mode": "cors",
                   "Sec-Fetch-Dest": "empty",
                   "Accept-Encoding": "gzip, deflate, br",
                   "Accept-Language": "zh-CN,zh;q=0.9"
                   }
        response = self.__http_utils.get(
            url=f'https://miniprogram.vietjetair.com.cn/app-api/yuejie/vietjet/searchFlight?{urlencode(data)}',
            headers=headers, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()['data']

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
         (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def journey_config(self, request_id, city_code):
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-cn',
            'cache-control': 'no-cache',
            'content-language': 'zh-cn',
            'content-type': 'application/json',
            'origin': 'https://www.vietjetair.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': self.__ua,
        }
        response = self.__http_utils.get(
            url=f'https://vietjetcms-api.vietjetair.com/api/v1/journey-config?languageId={Config.LANGUAHE_ID}&cityCode={city_code}&requestId={request_id}',
            headers=headers, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
         (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def insurances(self, data):
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-cn',
            'cache-control': 'no-cache',
            'content-language': 'zh-cn',
            'content-type': 'application/json',
            'origin': 'https://www.vietjetair.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': Config.USER_AGENT,
            "X-Aws-Waf-Token": self.__aws_token,
        }
        headers.update(self.zero_trust_headers('/booking/api/v1/insurances'))
        params = {"encrypted": data}
        response = self.__http_utils.post(url=f'https://vietjet-api.vietjetair.com/booking/api/v1/insurances',
                                          headers=headers, data=params, timeout=self.__timeout)
        if response.status != 200 and response.status != 400:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def seat_selection_options(self, data):
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-cn',
            'cache-control': 'no-cache',
            'content-language': 'zh-cn',
            'content-type': 'application/json',
            'origin': 'https://www.vietjetair.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': Config.USER_AGENT,
            "X-Aws-Waf-Token": self.__aws_token,
        }
        headers.update(self.zero_trust_headers('/booking/api/v1/seatSelectionOptions'))
        params = {"encrypted": data}
        response = self.__http_utils.patch(url='https://vietjet-api.vietjetair.com/booking/api/v1/seatSelectionOptions',
                                           headers=headers, data=params, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def methods_by_booking(self, data):
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-cn',
            'cache-control': 'no-cache',
            'content-language': 'zh-cn',
            'content-type': 'application/json',
            'origin': 'https://www.vietjetair.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': Config.USER_AGENT,
            "X-Aws-Waf-Token": self.__aws_token,
        }
        headers.update(self.zero_trust_headers('/booking/api/v1/payment/methods-by-bookingKey'))
        params = {"encrypted": data}
        response = self.__http_utils.patch(
            url='https://vietjet-api.vietjetair.com/booking/api/v1/payment/methods-by-bookingKey',
            headers=headers, data=params, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def ancillary_options(self, data):
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-cn',
            'cache-control': 'no-cache',
            'content-language': 'zh-cn',
            'content-type': 'application/json',
            'origin': 'https://www.vietjetair.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': Config.USER_AGENT,
            "X-Aws-Waf-Token": self.__aws_token,
        }
        headers.update(self.zero_trust_headers('/booking/api/v1/ancillaryOptions'))
        params = {"encrypted": data}
        response = self.__http_utils.patch(url='https://vietjet-api.vietjetair.com/booking/api/v1/ancillaryOptions',
                                           headers=headers, data=params, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    @staticmethod
    def initialize_ez_recaptcha(referer):
        ez_captcha = EzCaptcha(client_key='EZ-861220FA2A2E4D3896FEAAAAD1B61A83')
        token = ez_captcha.solve_recaptcha(website_url=referer,
                                           website_key="6Lerzd8mAAAAAJlSDAZvOv0nXJAmXxKRmY8TkRM6",
                                           task_type="ReCaptchaV2TaskProxyless")
        return token

    def get_google_token_no(self, referer: str):
        no_captcha = NoCaptchaUtil(api_key='00cf3281-7648-4678-8cb1-a03041030f40', )
        token = no_captcha.solve_recaptcha(referer=referer,
                                           sitekey="6Lerzd8mAAAAAJlSDAZvOv0nXJAmXxKRmY8TkRM6",
                                           title='',
                                           size="normal")
        return token

    def get_google_token_danli(self, referer: str):
        try:
            import requests

            headers = {
                'Content-Type': 'application/json',
            }

            json_data = {
                'appid': '7j58fx77bifxt2jhx01pwoek7asgp6xm',
                'host': 'https://www.vietjetair.com',
                'sitekey': '6Lerzd8mAAAAAJlSDAZvOv0nXJAmXxKRmY8TkRM6',
            }

            response = requests.post('http://api.zjdanli.com/recaptcha/getTokenV2', headers=headers, json=json_data)
            print(response.json())
            return response.json()['data']
        except Exception as e:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)

    def quotations_summary(self, data):
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-cn',
            'cache-control': 'no-cache',
            'content-language': 'zh-cn',
            'content-type': 'application/json',
            'origin': 'https://www.vietjetair.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': Config.USER_AGENT,
            "X-Aws-Waf-Token": self.__aws_token,
        }
        headers.update(self.zero_trust_headers('/booking/api/v1/quotations/summary'))
        params = {"encrypted": data}
        response = self.__http_utils.post(url=f'https://vietjet-api.vietjetair.com/booking/api/v1/quotations/summary',
                                          headers=headers, data=params, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def aws_v2(self):
        import requests
        import json

        url = "http://api.zjdanli.com/aws/token"

        payload = json.dumps({
            "appid": "7j58fx77bifxt2jhx01pwoek7asgp6xm",
            "siteUrl": "vietjet-api.vietjetair.com"
        })
        headers = {
            'Content-Type': 'application/json'
        }

        response = requests.request("POST", url, headers=headers, data=payload)

        verify_token = response.json()["data"]["token"]
        return verify_token

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
         (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def reservations(self, data, authorization):
        # self.__aws_token = self.aws_v2()
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-cn',
            'cache-control': 'no-cache',
            'content-language': 'zh-cn',
            'content-type': 'application/json',
            'origin': 'https://www.vietjetair.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': Config.USER_AGENT,
            "Authorization": f"Bearer {authorization}" if authorization else "",
            # "X-Aws-Waf-Token": self.__aws_token,
        }
        # headers.update(self.zero_trust_headers('/booking/api/v1/reservations'))
        params = {"encrypted": data}
        response = self.__danli_unlock.post(url=f'https://vietjet-api.vietjetair.com/booking/api/v1/reservations',
                                          headers=headers, data=params, timeout=60)
        if response.status != 200:
            if response.status == 401:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "Invalid authorization")
            if response.status == 400 and response.to_dict()["detail"]["errorKey"] == "LIMIT_PAYLATER_BOOKING":
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "达到最大占位限制")
            if response.status == 400 and response.to_dict()["detail"]["errorKey"] == "FARE_OR_SEAT_NOT_AVAILABLE":
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "抢位失败")
            if response.status == 400 and response.to_dict().get("message"):
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, response.to_dict().get("message"))
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    @staticmethod
    def _galaxy_traceparent():
        return f", 00-{uuid4().hex}-{uuid4().hex[:16]}-01"

    def galaxy_checkout(self, endpoint):
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "referer": "https://www.vietjetair.com/",
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "upgrade-insecure-requests": "1",
            "user-agent": Config.USER_AGENT,
        }
        response = self.__http_utils.get(url=endpoint, headers=headers, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def galaxy_antiforgery_token(self, referer):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "referer": referer,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "traceparent": self._galaxy_traceparent(),
            "user-agent": Config.USER_AGENT,
        }
        response = self.__http_utils.get(
            url="https://paymentv2.galaxypay.vn/antiforgery/token",
            headers=headers,
            timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def galaxy_query_checkout(self, data, referer, request_token, cookie_token):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "content-type": "application/json",
            "origin": "https://paymentv2.galaxypay.vn",
            "referer": referer,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "traceparent": self._galaxy_traceparent(),
            "user-agent": Config.USER_AGENT,
            "X-XSRF-TOKEN": request_token,
            "X-XSRF-COOKIE": cookie_token,
        }
        response = self.__http_utils.post(
            url="https://paymentv2.galaxypay.vn/api/v1.0/secure/QueryCheckout",
            headers=headers,
            data=data,
            timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def galaxy_create_payment(self, data, referer, request_token, cookie_token):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
            "content-type": "application/json",
            "origin": "https://paymentv2.galaxypay.vn",
            "referer": referer,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "traceparent": self._galaxy_traceparent(),
            "user-agent": Config.USER_AGENT,
            "X-XSRF-TOKEN": request_token,
            "X-XSRF-COOKIE": cookie_token,
        }
        response = self.__http_utils.post(
            url="https://paymentv2.galaxypay.vn/api/v1.0/secure/CreatePayment",
            headers=headers,
            data=data,
            timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def auth(self, client_id, state, nonce, code_challenge):
        url = "https://skyjoy-id.vietjetair.com/realms/loyalty/protocol/openid-connect/auth?"
        headers = {
            "user-agent": self.__ua,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
            "referer": "https://skyjoy-authen.vietjetair.com/",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-site",
            "sec-fetch-user": "?1",
            "priority": "u=4",
            "te": "trailers",
        }
        params = {
            "client_id": client_id,
            "redirect_uri": f"https://skyjoy-authen.vietjetair.com?client_id={client_id}",
            "action": "signin",
            "lang": "en",
            "ui_locales": "en",
            "state": state,
            "response_mode": "fragment",
            "response_type": "code",
            "scope": "openid address phone",
            "nonce": nonce,
            "prompt": "login",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }

        response = self.__http_utils.get(url=url + urlencode(params), headers=headers, timeout=self.__timeout,
                                         allow_redirects=False)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_text()

    def login_actions(self, url, phone_number: str, device_id: str):

        headers = {
            "user-agent": self.__ua,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "null",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "priority": "u=4",
            "te": "trailers"
        }
        data = {
            "action": "phone_number",
            "countryDialCode": phone_number.split(' ')[0],
            "phoneUI": phone_number.split(' ')[1],
            "deviceInfo": device_id,
            "phoneNumber": f"+{phone_number.replace(' ', '')}",
            "g-recaptcha-response": "undefined"
        }
        response = self.__http_utils.post(url=url,
                                          headers=headers, data=urlencode(data))
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_text()

    def login_actions2(self, url, password: str, device_id: str):

        headers = {
            "user-agent": self.__ua,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "null",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "priority": "u=4",
            "te": "trailers"
        }
        data = {
            "password": password,
            "credentialId": "",
            "deviceInfo": device_id
        }

        response = self.__http_utils.post(url=url,
                                          headers=headers, data=urlencode(data), allow_redirects=True)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.url

    def connect_token(self, code, client_id, code_verifier):
        url = "https://skyjoy-id.vietjetair.com/realms/loyalty/protocol/openid-connect/token"

        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) Gecko/20100101 Firefox/144.0",
            "accept": "*/*",
            "accept-language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://skyjoy-authen.vietjetair.com",
            "referer": "https://skyjoy-authen.vietjetair.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "te": "trailers"
        }
        data = {
            "code": code,
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": f"https://skyjoy-authen.vietjetair.com?client_id={client_id}",
            "code_verifier": code_verifier
        }

        response = self.__http_utils.post(url=url,
                                          headers=headers, data=urlencode(data), allow_redirects=True)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def get_login_token(self, access_token, refresh_token):

        headers = {
            "user-agent": self.__ua,
            "accept": "application/json",
            "accept-language": "zh-cn",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "referer": "https://www.vietjetair.com/",
            "content-language": "zh-cn",
            "origin": "https://www.vietjetair.com",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "te": "trailers"
        }

        def gen_custom_id():
            """
            生成类似 II9S5ZK2FBKE-1762137591524 的随机ID
            前缀：12位随机大写字母+数字
            后缀：当前毫秒级时间戳
            """
            prefix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            timestamp = str(int(time.time() * 1000))
            return f"{prefix}-{timestamp}"

        request_id = gen_custom_id()

        def random_os_info():
            """随机生成操作系统信息"""
            systems = {
                "Windows": ["10", "11", "8.1", "7"],
                "Mac OS": ["10.14", "10.15", "11.0", "12.1", "13.3"],
                "Android": ["9", "10", "11", "12", "13"],
                "iOS": ["14.8", "15.6", "16.4", "17.0"]
            }

            os_name = random.choice(list(systems.keys()))
            os_version = random.choice(systems[os_name])
            return {"osName": os_name, "osVersion": os_version}

        data = {
            "deviceType": "browser",
            "imei": StringUtil.generate_random_string(12, add_digits=True, force_alpha_first=False).upper(),
            "type": "Skyjoy",
            "token": access_token,
            "refreshToken": refresh_token,
            "expired": str(int(time.time())),
            "clientId": '6f05594c-bdc0-11ed-afa1',
            "requestId": request_id
        }
        data.update(random_os_info())
        response = self.__http_utils.post(
            url=f"https://vietjet-api.vietjetair.com/user/api/v1/login?requestId={request_id}",
            headers=headers, data=data)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()
