import json
import uuid
from typing import Optional, Tuple

from bs4 import BeautifulSoup

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.cardinalcommerce_util import CardinalcommerceUtil
from common.utils.string_util import StringUtil
from flights.cebupacificair_5j.config import CebupacificairConfig


class CebupacificairPaymentUtils:
    def __init__(self,
                 proxy_info: Optional[ProxyInfoModel] = None,
                 user_agent: str = CebupacificairConfig.USER_AGENT):
        self.__proxy_info = proxy_info.model_copy(deep=True) if proxy_info else None
        self.__tls = CurlCffiTls()
        self.__user_agent = user_agent
        try:
            self.__tls.initialize(self.__proxy_info, impersonate='chrome136')
        except Exception:
            self.__tls.initialize(self.__proxy_info, impersonate='chrome133a')
        self.__proxy_str = self.__proxy_info.get_proxy_info_to_string() if self.__proxy_info else None
        self.__cardinal = CardinalcommerceUtil(
            proxy_str=self.__proxy_str,
            agent=self.__user_agent,
            accept_language="en-US,en;q=0.9",
        )

    @staticmethod
    def __hidden_inputs(response_text: str) -> dict:
        soup = BeautifulSoup(response_text, "html.parser")
        result = {}
        for input_tag in soup.find_all("input"):
            key = input_tag.get("id") or input_tag.get("name")
            if key:
                result[key] = input_tag.get("value") or ""
        return result

    def collect_post(self, data: str) -> dict:
        headers = {
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Origin": "https://pop.cellpointdigital.net",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "iframe",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = self.__tls.post(
            url="https://centinelapi.cardinalcommerce.com/V1/Cruise/Collect",
            headers=headers,
            data=data,
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return self.__hidden_inputs(response.to_text())

    def render_post(self, url: str, data: str) -> dict:
        headers = {
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Origin": "https://centinelapi.cardinalcommerce.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "iframe",
            "Referer": "https://centinelapi.cardinalcommerce.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = self.__tls.post(url=url, headers=headers, data=data, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        result_text = StringUtil.extract_between(response.to_text(), "profiler.start(", ")")
        if not result_text:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "profiler.start")
        return json.loads(result_text)

    def save_browser_data(self,
                          nonce: str,
                          reference_id: str,
                          org_unit_id: str,
                          referrer: str) -> None:
        self.__cardinal.cardinalcommerce_save_browser_data(
            nonce=nonce,
            reference_id=reference_id,
            org_unit_id=org_unit_id,
            user_agent=self.__user_agent,
            referrer=referrer,
        )

    def method_url(self, method_data: str) -> Tuple[Optional[str], Optional[str]]:
        headers = {
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Origin": "https://geo.cardinalcommerce.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "iframe",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = self.__tls.post(
            url="https://trip-challenge.triplinkintl.com/challenge/brw/methodUrl",
            headers=headers,
            data=f"threeDSMethodData={method_data}",
            timeout=60,
            allow_redirects=True,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        response_text = response.to_text()
        data = StringUtil.extract_between(response_text, 'name="threeDSMethodData" type="hidden" value="', '"')
        url = StringUtil.extract_between(response_text, '<form action="', '"')
        return url, data

    def collect_redirect(self, reference_id: str) -> None:
        headers = {
            "Host": "centinelapi.cardinalcommerce.com",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "sec-ch-ua-platform": '"Windows"',
            "Origin": "https://centinelapi.cardinalcommerce.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "iframe",
            "Referer": "https://centinelapi.cardinalcommerce.com/V1/Cruise/Collect",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = self.__tls.post(
            url="https://centinelapi.cardinalcommerce.com/V1/Cruise/CollectRedirect",
            headers=headers,
            data=f"McsId={reference_id}&State=true&Error=",
            timeout=60,
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    @staticmethod
    def collect_nonce(bin_value: Optional[str]) -> str:
        nonce = f"nonce={uuid.uuid4()}"
        return f"bin={bin_value}&{nonce}" if bin_value else nonce
