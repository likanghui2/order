import copy
import json
import uuid
from typing import Optional
from urllib.parse import urlencode

from common.decorators.retry_decorator import retry_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls


class AppScript:

    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__http_utils = CurlCffiTls()
        self.__proxy = proxy_info
        self.__proxy_candidates = self.__build_proxy_candidates(proxy_info)
        self.__proxy_index = 0
        self.__timeout = 60
        self.initialize_session()

    def initialize_session(self):
        self.__http_utils.initialize(proxy_info_data=self.__current_proxy())

    def __current_proxy(self):
        if not self.__proxy_candidates:
            return self.__proxy
        return self.__proxy_candidates[self.__proxy_index]

    def get_ip(self):
        return self.__http_utils.get_ip().strip()

    @classmethod
    def __build_proxy_candidates(cls, proxy_info: Optional[ProxyInfoModel]):
        if proxy_info is None:
            return [None]

        regions = cls.__ordered_regions(proxy_info.region)
        if not regions:
            return [copy.deepcopy(proxy_info)]

        candidates = []
        for region in regions:
            proxy_candidate = copy.deepcopy(proxy_info)
            proxy_candidate.region = region
            if proxy_candidate.format and "country-US" in proxy_candidate.format:
                proxy_candidate.format = proxy_candidate.format.replace("country-US", f"country-{region.upper()}")
            candidates.append(proxy_candidate)
        return candidates or [copy.deepcopy(proxy_info)]

    @staticmethod
    def __ordered_regions(region_text: Optional[str]):
        if not region_text:
            return []
        regions = [region.strip() for region in region_text.split(",") if region.strip()]
        preferred_regions = ["sg", "my", "id"]
        ordered = []
        for preferred_region in preferred_regions:
            for region in regions:
                if region.lower() == preferred_region and region not in ordered:
                    ordered.append(region)
        for region in regions:
            if region not in ordered:
                ordered.append(region)
        return ordered

    def reset_proxy_ip(self):
        if self.__proxy_candidates:
            self.__proxy_index = (self.__proxy_index + 1) % len(self.__proxy_candidates)
        self.initialize_session()

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
         (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def payment_methods(self, params: dict):
        response = self.__http_utils.get(
            url=f"https://mobileapp-api.vietjetair.com/api/paymentMethod?{urlencode(params)}",
            headers={
                "User-Agent": "Vietjet Air/7 CFNetwork/3860.400.51 Darwin/25.3.0",
                "Connection": "keep-alive",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/json",
                "x-app-timezone": "+08:00",
                'uuid': f"AppCenter {str(uuid.uuid4()).upper()}",

                'x-app-uuid': f"vjadevice_{uuid.uuid4()}",
                "priority": "u=3, i",
                "accept-language": "vi-VN",
                "x-app-build": "500098",
                "x-app-version": "5.9.0",
            },
            timeout=self.__timeout,
        )
        if response.status not in [200, 400]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        response_data = response.to_dict()
        if response.status == 400:
            message = (
                    response_data.get("message")
                    or response_data.get("errorCode")
                    or response_data.get("error")
                    or response_data
            )
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, message)
        return response_data

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
         (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def processing_fee(self, data: dict):
        response = self.__http_utils.put(
            url="https://mobileapp-api.vietjetair.com/api/reserve/quotationsV2",
            headers={
                'User-Agent': "Vietjet%20Air/17 CFNetwork/3860.600.12 Darwin/25.5.0",
                'Accept': "application/json",
                'Content-Type': "application/json",
                'x-app-timezone': "+08:00",
                'uuid': f"AppCenter {str(uuid.uuid4()).upper()}",
                'x-platform': "ios",
                'content-language': "en-US",
                'priority': "u=3, i",
                'accept-language': "en-US",
                'x-app-uuid': f"vjadevice_{uuid.uuid4()}",
                'lang': "en-US",
                'x-app-build': "17",
                'x-app-version': "5.9.1",
            },
            data=data,
            timeout=self.__timeout,
        )
        if response.status not in [200, 400]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        response_data = response.to_dict()
        if response.status == 400:
            message = (
                    response_data.get("message")
                    or response_data.get("errorCode")
                    or response_data.get("error")
                    or response_data
            )
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, message)
        return response_data

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
         (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def reserve_v2(self, data: dict):
        response = self.__http_utils.post(
            url="https://mobileapp-api.vietjetair.com/api/reserveV2",
            headers={
                "User-Agent": "Vietjet Air/7 CFNetwork/3860.400.51 Darwin/25.3.0",
                "Connection": "keep-alive",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/json",
                "x-app-timezone": "+08:00",
                'uuid': f"AppCenter {str(uuid.uuid4()).upper()}",

                'x-app-uuid': f"vjadevice_{uuid.uuid4()}",
                "priority": "u=3, i",
                "accept-language": "vi-VN",
                "x-app-build": "500098",
                "x-app-version": "5.9.0",
                "auth-user": "",
                "Authorization": "Bearer ",

            },
            data=data,
            timeout=self.__timeout,
        )
        if response.status not in [200, 400]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        response_data = response.to_dict()
        if response.status == 400:
            message = (
                    response_data.get("message")
                    or response_data.get("errorCode")
                    or response_data.get("error")
                    or response_data
            )
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, message)
        return response_data

    @retry_decorator(
        [(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),
         (ServiceStateEnum.HTTP_TIMEOUT, reset_proxy_ip)])
    def travel_option(self, data: dict):
        response = self.__http_utils.post(
            url="https://mobileapp-api.vietjetair.com/api/travelOption",
            headers={
    "User-Agent": "Vietjet%20Air/17 CFNetwork/3860.600.12 Darwin/25.5.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "x-app-timezone": "+08:00",
    "uuid": "AppCenter 7F530332-216E-45ED-9368-1F7F0E0B4E6C",
    "x-platform": "ios",
    "content-language": "en-US",
    "priority": "u=3, i",
    "accept-language": "en-US",
    "x-app-uuid": "vjadevice_8febd33a-06c3-48e7-9c0a-88af2fc213f8",
    "lang": "en-US",
    "x-app-build": "17",
    "x-app-version": "5.9.1"
},
            data=json.dumps(data),
            timeout=self.__timeout,
        )
        if response.status not in [200, 400]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        response_data = response.to_dict()
        if response.status == 400:
            message = (
                    response_data.get("message")
                    or response_data.get("errorCode")
                    or response_data.get("error")
                    or response_data
            )
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, message)
        return response_data
