import urllib.parse
import uuid
from typing import Optional

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls


class SecureAcceptance:
    def __init__(self, proxy_info: Optional[ProxyInfoModel], user_agent: str,
                 accept_language: str = "en-US,en;q=0.9"):
        self.__http_utils = CurlCffiTls()
        self.__http_utils.initialize(proxy_info_data=proxy_info, impersonate="chrome136")
        self.user_agent = user_agent
        self.accept_language = accept_language
        self.timeout = 60

    def silent_pay(self, data):
        headers = {
            "Host": "secureacceptance.cybersource.com",
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://payment.batikair.com.my",
            "Referer": "https://payment.batikair.com.my/",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
        }
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data)
        response = self.__http_utils.post(
            url="https://secureacceptance.cybersource.com/silent/pay",
            data=data,
            headers=headers,
            allow_redirects=True,
            timeout=self.timeout
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def silent_pay_redirect(self, data, headers_options: dict = None):
        if headers_options is None:
            headers_options = {}
        headers = {
            "Host": "secureacceptance.cybersource.com",
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://payment.batikair.com.my",
            "Referer": "https://payment.batikair.com.my/",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
        }
        headers.update(headers_options)
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data)
        response = self.__http_utils.post(
            url="https://secureacceptance.cybersource.com/silent/pay",
            data=data,
            headers=headers,
            allow_redirects=False,
            timeout=self.timeout
        )
        if response.status not in [302, 303]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        if not response.location:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "silent/pay 缺少重定向地址")
        return response.location

    def silent_pay_entry(self, data, headers_options: dict = None):
        if headers_options is None:
            headers_options = {}
        headers = {
            "Host": "secureacceptance.cybersource.com",
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://payment.batikair.com.my",
            "Referer": "https://payment.batikair.com.my/",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
        }
        headers.update(headers_options)
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data)
        response = self.__http_utils.post(
            url="https://secureacceptance.cybersource.com/silent/pay",
            data=data,
            headers=headers,
            allow_redirects=False,
            timeout=self.timeout
        )
        if response.status == 200:
            return {
                "html": response.to_text(),
                "redirect_url": None
            }
        if response.status in [302, 303]:
            if not response.location:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "silent/pay 缺少重定向地址")
            return {
                "html": "",
                "redirect_url": response.location
            }
        raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    def hybrid_load(self, load_url: str, headers_options: dict = None):
        if headers_options is None:
            headers_options = {}
        headers = {
            "Host": "secureacceptance.cybersource.com",
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": "https://payment.batikair.com.my/",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
        }
        headers.update(headers_options)
        response = self.__http_utils.get(
            url=load_url,
            headers=headers,
            allow_redirects=False,
            timeout=self.timeout
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def hybrid(self, cca_session_id, authenticity_token, cca_client_session_id: str = None,
               data_options: dict = None, headers_options: dict = None):
        if data_options is None:
            data_options = {}
        if headers_options is None:
            headers_options = {}
        headers = {
            "Host": "secureacceptance.cybersource.com",
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": "https://secureacceptance.cybersource.com/silent/payer_authentication/hybrid?ccaAction=load",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://secureacceptance.cybersource.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TE": "trailers"
        }
        headers.update(headers_options)
        data = {
            "ccaAction": "check",
            "ccaSessionId": cca_session_id,
            "ccaClientSessionId": cca_client_session_id or f"0_{uuid.uuid4()}",
            "ccaTiming": "4336",
            "authenticity_token": authenticity_token,
            "customer_browser_color_depth": "30",
            "customer_browser_language": "en-US",
            "customer_browser_java_enabled": "false",
            "customer_browser_screen_height": "1440",
            "customer_browser_screen_width": "2560",
            "customer_browser_time_difference": "-480",
            "__inner_width": "1043",
            "__inner_height": "1302",
        }
        data.update(data_options)
        response = self.__http_utils.post(
            url="https://secureacceptance.cybersource.com/silent/payer_authentication/hybrid",
            data=urllib.parse.urlencode(data),
            headers=headers,
            timeout=self.timeout
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        response_text = response.to_text()
        if response_text and "CompleteEarly" not in response_text:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)
        return response_text

    def hybrid_2(self, authenticity_token, headers_options: dict = None):
        if headers_options is None:
            headers_options = {}
        headers = {
            "Host": "secureacceptance.cybersource.com",
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": "https://secureacceptance.cybersource.com/silent/payer_authentication/hybrid?ccaAction=load",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://secureacceptance.cybersource.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TE": "trailers"
        }
        headers.update(headers_options)
        data = {
            "authenticity_token": authenticity_token,
            "ccaAction": "completeEarly",
            "ccaErrorsHandled": "[]",
        }
        response = self.__http_utils.post(
            url="https://secureacceptance.cybersource.com/silent/payer_authentication/hybrid",
            data=urllib.parse.urlencode(data),
            headers=headers,
            timeout=self.timeout
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()
