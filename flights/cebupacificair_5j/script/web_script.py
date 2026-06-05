import base64
import json
import math
import random
import time
import uuid
from copy import copy
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import urlencode

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.tls.danli_unlock_tls import DanliUnlockTls
from common.utils import log_util
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.string_util import StringUtil
from flights.cebupacificair_5j.config import CebupacificairConfig
from flights.cebupacificair_5j.flight_common.message_utils import MessageUtils

DANLI_APPID = "m05cmm7ub8vm1pgasjpo8sdp9tl6mkzp"
DANLI_UTILS = DanLiCaptchaUtil(DANLI_APPID)


class WebScript:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__proxy_info = proxy_info.model_copy(deep=True) if proxy_info else None
        if self.__proxy_info:
            self.__proxy_info.region = "hk"

        self.__tls = (
            DanliUnlockTls(DANLI_APPID, site="cebupacificair", auth_manage_cookie=False)
            if self.__proxy_info
            else CurlCffiTls()
        )
        self.__payment_tls = CurlCffiTls()
        self.__ua = CebupacificairConfig.USER_AGENT
        self.__timeout = 60
        self.__unique_id = None
        self.__authorization = None
        self.__x_auth_token = None
        self.__sec_ch_ua = '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"'
        self.__log = log_util.LogUtil("cebupacificairWebScript")

    @property
    def proxy_info(self) -> Optional[ProxyInfoModel]:
        return self.__proxy_info.model_copy(deep=True) if self.__proxy_info else None

    @property
    def proxy(self) -> Optional[ProxyInfoModel]:
        return self.proxy_info

    def __initialize_payment_session(self):
        try:
            self.__payment_tls.initialize(self.__proxy_info, impersonate='chrome136')
        except Exception:
            self.__payment_tls.initialize(self.__proxy_info, impersonate='chrome133a')

    def initialize_session(self):
        if isinstance(self.__tls, DanliUnlockTls):
            self.__tls.initialize(proxy_info_data=self.__proxy_info)
            self.__initialize_payment_session()
            return

        try:
            self.__tls.initialize(self.__proxy_info, impersonate='chrome136')
        except Exception:
            self.__tls.initialize(self.__proxy_info, impersonate='chrome133a')
        self.__initialize_payment_session()

    def get_akm(self):
        if isinstance(self.__tls, DanliUnlockTls):
            self.initialize_session()
            return

        self.initialize_session()
        akm_info = DANLI_UTILS.akamai_ck_get("cebupacificair")
        self.__ua = akm_info["ua"]
        if "Chrome/" in self.__ua:
            chrome_version = self.__ua.split("Chrome/")[1].split(".0.0.0")[0]
            self.__sec_ch_ua = (
                f'"Chromium";v="{chrome_version}", '
                f'"Google Chrome";v="{chrome_version}", "Not.A/Brand";v="99"'
            )
        self.__tls.cookie_update(akm_info["data"])

    def close(self):
        for tls in (self.__tls, self.__payment_tls):
            session = tls.get_session()
            if session:
                session.close()

    def __exchange_string(self, string: str) -> str:
        result_string = string
        p = math.floor(random.random() * len(result_string))
        result_string = string[:p] + self.__authorization + string[p:]
        p = math.floor(random.random() * len(result_string))
        result_string = result_string[:p] + self.__x_auth_token + result_string[p:]
        return result_string

    def __get_message_data(self, url: str, data: dict, method: str) -> Tuple[str, str]:
        message_util = MessageUtils(
            authorization=self.__authorization,
            x_auth_token=self.__x_auth_token,
            park=CebupacificairConfig.PARK,
        )
        url_encrypt = self.__exchange_string(message_util.encrypt_message(url))
        if method == 'POST':
            data_encrypt = self.__exchange_string(
                message_util.encrypt_message(json.dumps(data, separators=(',', ':')))
            )
        else:
            data_encrypt = ""
        return url_encrypt, data_encrypt

    def initialize_html_session(self):
        self.__unique_id = str(uuid.uuid4())
        now_time = int(round(time.time() * 1000))
        message = f"{self.__unique_id}{CebupacificairConfig.XAT}{now_time}"
        data = {
            'message': MessageUtils.hash_utils(key=CebupacificairConfig.SECR, message=message),
            'uniqueId': self.__unique_id,
            'nonce': str(now_time),
        }

        message_util = MessageUtils(None, None, CebupacificairConfig.PARK)
        content_data = message_util.encrypt_message(json.dumps(data, separators=(',', ':')))
        path = message_util.encrypt_message("/v2/accessToken", CebupacificairConfig.AESK)

        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'es,zh-CN;q=0.9,zh;q=0.8',
            'authorization': f'Bearer {CebupacificairConfig.XAT}',
            'content-type': 'application/json',
            'origin': 'https://www.cebupacificair.com',
            'priority': 'u=1, i',
            'referer': 'https://www.cebupacificair.com/',
            'sec-ch-ua': self.__sec_ch_ua,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'uniqueid': self.__unique_id,
            'user-agent': self.__ua,
            'x-path': path,
        }

        response = self.__tls.post(
            url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/v2/accessToken",
            headers=headers,
            data={'content': content_data},
            timeout=self.__timeout,
        )
        if response.status == 403 and 'Access Denied' in response.to_text():
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        response_json = response.to_dict()
        if 'Authorization' not in response_json or 'X-Auth-Token' not in response_json:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "Authorization Or X-Auth-Token")

        self.__authorization = response_json['Authorization']
        self.__x_auth_token = response_json['X-Auth-Token']

    def availability(self,
                     airport_data: List[Tuple[str, str, str]],
                     adult_count: int,
                     child_count: int,
                     promo_code: str = "",
                     currency: Optional[str] = None) -> dict:
        routes = [
            {
                "origin": dep_airport,
                "destination": arr_airport,
                "beginDate": datetime.strptime(dep_date, '%Y-%m-%d').strftime('%m/%d/%Y').lstrip('0').replace('/0', '/'),
                "daysToLeft": 0,
                "daysToRight": 0,
            }
            for dep_airport, arr_airport, dep_date in airport_data
        ]
        nonce = str(round(time.time() * 1000))
        submit_data = {
            "ssrs": [] if airport_data[0][0] == "HKG" else ["WAFI"],
            "routes": routes,
            "daysToLeft": 0,
            "daysToRight": 0,
            "adultCount": adult_count,
            "childCount": child_count,
            "infantCount": {
                "lap": 0,
                "seat": 0,
            },
            "promoCode": promo_code,
            "currency": currency,
            "version": 2,
            "lffMode": False,
            "rebook": False,
            "hash": MessageUtils.hash_utils(
                key=CebupacificairConfig.HASH_KEY,
                message=f"{self.__unique_id}/availability{nonce}{self.__authorization}",
            ),
            "nonce": nonce,
        }
        self.__log.info(submit_data, "availability请求参数")
        _, content_data = self.__get_message_data(
            url="availability",
            data=submit_data,
            method="POST",
        )

        message_util = MessageUtils(None, None, CebupacificairConfig.PARK)
        path = message_util.encrypt_message("/availability", CebupacificairConfig.AESK)
        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "en-US,en;q=0.9,fr-FR;q=0.8,fr;q=0.7",
            "cache-control": "max-age=0",
            "pragma": "no-cache",
            "origin": "https://www.cebupacificair.com",
            "referer": "https://www.cebupacificair.com",
            "uniqueid": self.__unique_id,
            "x-path": path,
            "authorization": f"Bearer {self.__authorization}",
            "x-auth-token": self.__x_auth_token,
            "content-type": "application/json; charset=utf-8",
            "user-agent": self.__ua,
            "sec-ch-ua": self.__sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "Sec-Fetch-User": "?1",
            "upgrade-insecure-requests": "1",
        }
        response = self.__tls.post(
            url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/availability",
            headers=copy(headers),
            data={'content': content_data},
            timeout=10,
        )
        response_text = response.to_text()
        if response.status == 403 and 'Access Denied' in response_text:
            response = self.__tls.post(
                url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/availability",
                headers=headers,
                data={'content': content_data},
                timeout=10,
            )
            response_text = response.to_text()

        if response.status == 451 and "Invalid IP Address" in response_text:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "异常IP地址")
        if response.status == 403 and 'Access Denied' in response_text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_dict()

    def trip(self,
             routes: List[Tuple[str, str, str]],
             adult_count: int,
             child_count: int,
             bundles: List[dict],
             currency: str,
             ssrs: List[str],
             promo_code: str = "") -> dict:
        nonce = str(round(time.time() * 1000))
        submit_data = {
            "ssrs": ssrs,
            "routes": [
                {
                    "journeyKey": journey_key,
                    "fareAvailabilityKey": fare_key,
                    "bundleCode": bundle_code,
                }
                for journey_key, fare_key, bundle_code in routes
            ],
            "adultCount": adult_count,
            "childCount": child_count,
            "infantCount": {
                "lap": 0,
                "seat": 0,
            },
            "promoCode": promo_code,
            "currency": currency,
            "bundles": bundles,
            "isRebookEnable": False,
            "insider": {
                "userID": "17491077930255818c6bb2d.9ad0d452",
                "sessionIDInsider": "01di36k8-jn4x-x8e4-f8lx-57qg77drtl8x_1749107793",
                "variationID": "c503",
            },
            "hash": MessageUtils.hash_utils(
                key=CebupacificairConfig.HASH_KEY,
                message=f"{self.__unique_id}/v3/trip{nonce}{self.__authorization}",
            ),
            "nonce": nonce,
        }
        self.__log.info(submit_data, "trip请求参数")
        _, content_data = self.__get_message_data(
            url="v3/trip",
            data=submit_data,
            method="POST",
        )

        message_util = MessageUtils(None, None, CebupacificairConfig.PARK)
        path = message_util.encrypt_message("/v3/trip", CebupacificairConfig.AESK)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh-TW;q=0.7,zh;q=0.6,ar;q=0.5",
            "Authorization": f"Bearer {self.__authorization}",
            "Cache-Control": "no-cache",
            "x-path": path,
            "Content-Type": "application/json",
            "Origin": "https://www.cebupacificair.com",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Referer": "https://www.cebupacificair.com/",
            "Sec-Ch-Ua": self.__sec_ch_ua,
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Uniqueid": self.__unique_id,
            "User-Agent": self.__ua,
            "X-Auth-Token": self.__x_auth_token,
        }

        response = self.__tls.post(
            url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/v3/trip",
            headers=copy(headers),
            data={"content": content_data},
            timeout=self.__timeout,
        )
        response_text = response.to_text()
        if response.status== 400 and "nsk-server:ClassNotAvailable" in response_text:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "该座位已售完")
        if response.status == 504 and "Gateway Timeout" in response_text:
            raise ServiceError(ServiceStateEnum.HTTP_TIMEOUT, response.status)
        if response.status == 403 and "Access Denied" in response_text:
            response = self.__tls.post(
                url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/v3/trip",
                headers=headers,
                data={"content": content_data},
                timeout=self.__timeout,
            )
            response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_dict()

    def guest_details(self,
                      passengers: List[dict],
                      contact: dict) -> dict:
        nonce = str(round(time.time() * 1000))
        submit_data = {
            "passengers": passengers,
            "contacts": [contact],
            "version": 2,
            "hash": MessageUtils.hash_utils(
                key=CebupacificairConfig.HASH_KEY,
                message=f"{self.__unique_id}/guestdetails{nonce}{self.__authorization}",
            ),
            "nonce": nonce,
        }
        self.__log.info(submit_data, "guestdetails请求参数")
        _, content_data = self.__get_message_data(
            url="guestdetails",
            data=submit_data,
            method="POST",
        )
        message_util = MessageUtils(None, None, CebupacificairConfig.PARK)
        path = message_util.encrypt_message("/guestdetails", CebupacificairConfig.AESK)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "x-path": path,
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh-TW;q=0.7,zh;q=0.6,ar;q=0.5",
            "Authorization": f"Bearer {self.__authorization}",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "Origin": "https://www.cebupacificair.com",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Referer": "https://www.cebupacificair.com/",
            "Sec-Ch-Ua": self.__sec_ch_ua,
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Uniqueid": self.__unique_id,
            "User-Agent": self.__ua,
            "X-Auth-Token": self.__x_auth_token,
        }
        response = self.__tls.post(
            url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/guestdetails",
            headers=copy(headers),
            data={"content": content_data},
            timeout=self.__timeout,
        )
        response_text = response.to_text()
        if response.status == 504 and "Gateway Timeout" in response_text:
            raise ServiceError(ServiceStateEnum.HTTP_TIMEOUT, response.status)
        if response.status == 403 and "Access Denied" in response_text:
            response = self.__tls.post(
                url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/guestdetails",
                headers=headers,
                data={"content": content_data},
                timeout=self.__timeout,
            )
            response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_dict()

    def commit(self, sell_addon_infos: List[dict]) -> dict:
        current_time = datetime.now(timezone.utc)
        nonce = str(round(time.time() * 1000))
        submit_data = {
            "holdExpiration": (
                datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                + f".{current_time.microsecond // 1000:03d}Z"
            ),
            "sellAddons": sell_addon_infos,
            "queues": [],
            "hash": MessageUtils.hash_utils(
                key=CebupacificairConfig.HASH_KEY,
                message=f"{self.__unique_id}/v3/booking/commit{nonce}{self.__authorization}",
            ),
            "nonce": nonce,
        }
        self.__log.info(submit_data, "commit请求参数")
        _, content_data = self.__get_message_data(
            url="v3/booking/commit",
            data=submit_data,
            method="POST",
        )
        message_util = MessageUtils(None, None, CebupacificairConfig.PARK)
        path = message_util.encrypt_message("/v3/booking/commit", CebupacificairConfig.AESK)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh-TW;q=0.7,zh;q=0.6,ar;q=0.5",
            "Authorization": f"Bearer {self.__authorization}",
            "Cache-Control": "no-cache",
            "x-path": path,
            "Content-Type": "application/json",
            "Origin": "https://www.cebupacificair.com",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Referer": "https://www.cebupacificair.com/",
            "Sec-Ch-Ua": self.__sec_ch_ua,
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Uniqueid": self.__unique_id,
            "User-Agent": self.__ua,
            "X-Auth-Token": self.__x_auth_token,
        }
        response = self.__tls.post(
            url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/v3/booking/commit",
            headers=copy(headers),
            data={"content": content_data},
            timeout=self.__timeout,
        )
        response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            response = self.__tls.post(
                url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/v3/booking/commit",
                headers=headers,
                data={"content": content_data},
                timeout=self.__timeout,
            )
            response_text = response.to_text()
        if response.status == 504 and "Gateway Timeout" in response_text:
            raise ServiceError(ServiceStateEnum.HTTP_TIMEOUT, response.status)
        if response.status == 403 and "Access Denied" in response_text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_dict()

    def init_payment(self) -> str:
        nonce = str(round(time.time() * 1000))
        submit_data = {
            "account": "100770",
            "stepper": "1",
            "txnType": "1",
            "isPartialPayment": False,
            "language": "en",
            "hash": MessageUtils.hash_utils(
                key=CebupacificairConfig.HASH_KEY,
                message=f"{self.__unique_id}/cpd/hpp{nonce}{self.__authorization}",
            ),
            "nonce": nonce,
        }
        self.__log.info(submit_data, "init_payment请求参数")
        _, content_data = self.__get_message_data(
            url="cpd/hpp",
            data=submit_data,
            method="POST",
        )
        message_util = MessageUtils(None, None, CebupacificairConfig.PARK)
        path = message_util.encrypt_message("/cpd/hpp", CebupacificairConfig.AESK)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh-TW;q=0.7,zh;q=0.6,ar;q=0.5",
            "Authorization": f"Bearer {self.__authorization}",
            "Cache-Control": "no-cache",
            "accept-encoding": "gzip, deflate, br, zstd",
            "x-path": path,
            "Content-Type": "application/json",
            "Origin": "https://www.cebupacificair.com",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Referer": "https://www.cebupacificair.com/",
            "Sec-Ch-Ua": self.__sec_ch_ua,
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Uniqueid": self.__unique_id,
            "User-Agent": self.__ua,
            "X-Auth-Token": self.__x_auth_token,
        }
        response = self.__tls.post(
            url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/cpd/hpp",
            headers=copy(headers),
            data={"content": content_data},
            timeout=self.__timeout,
        )
        response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            response = self.__tls.post(
                url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/cpd/hpp",
                headers=headers,
                data={"content": content_data},
                timeout=self.__timeout,
            )
            response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response_text

    def web(self, data: dict) -> str:
        headers = {
            "Host": "pop.cellpointdigital.net",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Origin": "https://www.cebupacificair.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://www.cebupacificair.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = self.__payment_tls.post(
            url="https://pop.cellpointdigital.net/views/web.php",
            headers=copy(headers),
            data=urlencode(data),
            timeout=self.__timeout,
        )
        response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            response = self.__payment_tls.post(
                url="https://pop.cellpointdigital.net/views/web.php",
                headers=headers,
                data=urlencode(data),
                timeout=self.__timeout,
            )
            response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response_text

    def initialize(self,
                   order_id: str,
                   operator: int,
                   client_id: str,
                   account: str,
                   email: str,
                   mobile_country: int,
                   mobile: str,
                   country: int,
                   amount: str,
                   accept_url: str,
                   cancel_url: str,
                   callback_url: str,
                   order_data: str,
                   currency: int,
                   auth_token: str,
                   hmac: str,
                   additional_data,
                   init_token: str,
                   nonce: str,
                   profile_id: str,
                   gtm_id: str,
                   time_token: str,
                   json_converted_request_data: str,
                   encryptedauthhash: str) -> dict:
        submit_data = {
            "country": country,
            "mobilecountry": mobile_country,
            "clientid": client_id,
            "account": account,
            "language": "en",
            "orderid": order_id,
            "mobile": mobile,
            "operator": operator,
            "email": email,
            "name": "Test Name",
            "customerref": email,
            "accounts": "",
            "markup": "HTML5",
            "amount": amount,
            "fees": "",
            "accepturl": accept_url,
            "cancelurl": cancel_url,
            "callbackurl": callback_url,
            "orderdata": order_data,
            "sessionid": "",
            "currency": currency,
            "authtoken": auth_token,
            "deviceid": "",
            "hmac": hmac,
            "additionaldata": additional_data,
            "initToken": init_token,
            "iframe": False,
            "nonce": nonce,
            "txntype": "1",
            "locale": "",
            "hppAppVersion": "2.0.0",
            "logourl": "https://storage.googleapis.com/bkt-cp-prod-ehpp2/10077/logo.png",
            "cssurl": "https://storage.googleapis.com/bkt-cp-prod-ehpp2/10077",
            "assetsurl": "https://storage.googleapis.com/bkt-cp-prod-ehpp2/10077",
            "profileid": profile_id,
            "gtmdata": None,
            "gtmid": gtm_id,
            "responsecontenttype": "1",
            "paymentgroupcode": None,
            "authversion": None,
            "jsonconvertedrequestdata": json_converted_request_data,
            "themeversion": None,
            "minifyversion": None,
            "timetoken": time_token,
            "mitdata": None,
            "producttype": None,
            "flow": None,
            "mesbhost": "5j.velocity.cellpointmobile.net",
            "surcharge": None,
        }
        headers = {
            "Host": "pop.cellpointdigital.net",
            "Connection": "keep-alive",
            "Nonce": nonce,
            "sec-ch-ua-platform": '"Windows"',
            "User-Agent": self.__ua,
            "Content-Type": "application/json",
            "Token": init_token,
            "sec-ch-ua-mobile": "?0",
            "Accept": "*/*",
            "Origin": "https://pop.cellpointdigital.net",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://pop.cellpointdigital.net/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "x-encrypted-auth": encryptedauthhash,
        }
        response = self.__payment_tls.post(
            url="https://pop.cellpointdigital.net/api/initialize",
            headers=copy(headers),
            data=submit_data,
            timeout=self.__timeout,
        )
        response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            response = self.__payment_tls.post(
                url="https://pop.cellpointdigital.net/api/initialize",
                headers=headers,
                data=submit_data,
                timeout=self.__timeout,
            )
            response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_dict()

    def authorize(self,
                  last_name: str,
                  first_name: str,
                  card_number: str,
                  card_vcc: str,
                  card_expiry_date: str,
                  card_type: str,
                  amount: str,
                  currency: int,
                  country: int,
                  mobile_country: int,
                  operator: int,
                  client_id: str,
                  account: str,
                  mobile: str,
                  email: str,
                  profile_id: str,
                  auth_token: str,
                  hmac: str,
                  transaction: str,
                  expired: bool = False) -> dict:
        card_type_code = (card_type or "").upper()
        card_type_id = 7 if card_type_code in {"CA", "MC", "MASTERCARD"} else 8
        submit_data = {
            "cardname": f"{last_name} {first_name}",
            "decktoken": base64.b64encode(card_number.encode()).decode(),
            "termination": base64.b64encode(card_expiry_date.encode()).decode(),
            "validfrom": "",
            "verificationcode": base64.b64encode(card_vcc.encode()).decode(),
            "cardtypeid": card_type_id,
            "paymenttype": False,
            "token": "",
            "network": "",
            "storecard": "false",
            "accountconfirmpassword": "",
            "accountpassword": "",
            "accouontname": "",
            "typeid": "10091",
            "mitdata": None,
            "fxservicetypeid": "12",
            "additionaldata": {
                "param": [
                    {"name": "margin_percentage", "text": "8.5"},
                    {"name": "BrowserScreenHeight", "text": 923},
                    {"name": "BrowserScreenWidth", "text": 1266},
                    {"name": "BrowserLanguage", "text": "en-US"},
                    {"name": "BrowserJavaEnabled", "text": "false"},
                    {"name": "BrowserJavascriptEnabled", "text": "true"},
                    {"name": "BrowserColorDepth", "text": 24},
                    {"name": "BrowserTimeZoneOffset", "text": -480},
                    {"name": "UserAgent", "text": self.__ua},
                    {"name": "BrowserScreenType", "text": "desktop"},
                    {"name": "BrowserOrientation", "text": "landscape"},
                ]
            },
            "cfxid": "30518917",
            "amount": amount,
            "currency": currency,
            "hmac": hmac,
            "paymentgroupcode": None,
            "country": country,
            "clientid": client_id,
            "mobilecountry": mobile_country,
            "account": account,
            "mobile": mobile,
            "operator": operator,
            "email": email,
            "language": "en",
            "customerref": email,
            "markup": "HTML5",
            "profileid": profile_id,
            "transaction": transaction,
            "authtoken": auth_token,
            "billingaddress": {
                "fullname": f"{last_name} {first_name}",
                "email": "",
                "address1": StringUtil.generate_random_string(10),
                "address2": StringUtil.generate_random_string(10),
                "street": StringUtil.generate_random_string(5),
                "countryid": str(country),
                "city": StringUtil.generate_random_string(10),
                "state": "",
                "postalcode": str(random.randint(100000, 999999)),
                "mobilecontrycode": mobile_country,
                "mobilenumber": mobile,
                "cardholderemail": email,
                "firstName": last_name,
                "lastName": first_name,
            },
            "cardid": "",
            "checkouturl": "",
            "euaid": "-1",
            "mvault": "false",
            "verifier": "",
            "externalCall": "true",
            "hppAppVersion": "2.0.0",
        }
        if expired:
            submit_data["expired"] = True
            submit_data["collectionTime"] = "8000"

        headers = {
            "Host": "pop.cellpointdigital.net",
            "Connection": "keep-alive",
            "sec-ch-ua-platform": '"Windows"',
            "User-Agent": self.__ua,
            "Content-Type": "application/json",
            "sec-ch-ua-mobile": "?0",
            "Accept": "*/*",
            "Origin": "https://pop.cellpointdigital.net",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://pop.cellpointdigital.net/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = self.__payment_tls.post(
            url="https://pop.cellpointdigital.net/api/authorize",
            headers=copy(headers),
            data=submit_data,
            timeout=self.__timeout,
        )
        response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            response = self.__payment_tls.post(
                url="https://pop.cellpointdigital.net/api/authorize",
                headers=headers,
                data=submit_data,
                timeout=self.__timeout,
            )
            response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            self.__log.error(
                f"authorize失败，status[{response.status}]，amount[{amount}]，currency[{currency}]，"
                f"cardtypeid[{card_type_id}]，expired[{expired}]，response[{response_text[:800]}]",
                "支付请求"
            )
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        self.__log.info(
            f"authorize成功，amount[{amount}]，currency[{currency}]，cardtypeid[{card_type_id}]，expired[{expired}]",
            "支付请求"
        )
        return response.to_dict()

    def payment_complete(self, transaction_id: str, token: str) -> dict:
        submit_data = {
            "transactionId": transaction_id,
            "clientId": "10077",
            "pollingTimeout": "60",
            "minPollingInterval": "5",
            "maxPollingInterval": "15",
            "secure": "false",
            "token": token,
            "sessiontime": "13",
        }
        headers = {
            "Host": "pop.cellpointdigital.net",
            "Connection": "keep-alive",
            "sec-ch-ua-platform": '"Windows"',
            "User-Agent": self.__ua,
            "Content-Type": "application/json",
            "sec-ch-ua-mobile": "?0",
            "Accept": "*/*",
            "Origin": "https://pop.cellpointdigital.net",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://pop.cellpointdigital.net/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = self.__payment_tls.post(
            url="https://pop.cellpointdigital.net/api/paymentcomplete",
            headers=headers,
            data=submit_data,
            timeout=self.__timeout,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def session_complete(self, transaction_id: str, token: str, session_id: str, status_code: str) -> dict:
        submit_data = {
            "transactionId": transaction_id,
            "clientId": "10077",
            "pollingTimeout": "60",
            "minPollingInterval": "5",
            "maxPollingInterval": "15",
            "sessionId": session_id,
            "mode": "1",
            "secure": "false",
            "statusCode": status_code,
            "token": token,
            "sessiontime": "13",
        }
        headers = {
            "Host": "pop.cellpointdigital.net",
            "Connection": "keep-alive",
            "sec-ch-ua-platform": '"Windows"',
            "User-Agent": self.__ua,
            "Content-Type": "application/json",
            "sec-ch-ua-mobile": "?0",
            "Accept": "*/*",
            "Origin": "https://pop.cellpointdigital.net",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://pop.cellpointdigital.net/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = self.__payment_tls.post(
            url="https://pop.cellpointdigital.net/api/sessioncomplete",
            headers=headers,
            data=submit_data,
            timeout=120,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def itinerary(self) -> dict:
        content_headers, _ = self.__get_message_data(url="itinerary", data={}, method="GET")
        message_util = MessageUtils(None, None, CebupacificairConfig.PARK)
        path = message_util.encrypt_message("/itinerary", CebupacificairConfig.AESK)
        headers = {
            "Host": "soar.cebupacificair.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh-TW;q=0.7,zh;q=0.6,ar;q=0.5",
            "Authorization": f"Bearer {self.__authorization}",
            "Cache-Control": "no-cache",
            "Content": content_headers,
            "x-path": path,
            "Content-Type": "application/json",
            "Origin": "https://www.cebupacificair.com",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Referer": "https://www.cebupacificair.com/",
            "Sec-Ch-Ua": self.__sec_ch_ua,
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": self.__ua,
            "X-Auth-Token": self.__x_auth_token,
        }
        response = self.__tls.get(
            url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/itinerary",
            headers=copy(headers),
            timeout=self.__timeout,
        )
        response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            response = self.__tls.get(
                url="https://soar.cebupacificair.com/ceb-omnix-proxy-v3/itinerary",
                headers=headers,
                timeout=self.__timeout,
            )
            response_text = response.to_text()
        if response.status == 403 and "Access Denied" in response_text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_dict()
