from typing import Optional

from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.nocaptcha_util import NoCaptchaUtil
from flights.garuda.config import Config


class WebScript:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__proxy_info_data = proxy_info_data
        self.__ga_session = None
        self.__timeout = 60
        self.__tls = CurlCffiTls()
        self.__ua = Config.USER_AGENT
        self.initialize_http_util()

    def initialize_http_util(self):
        self.__tls.initialize(self.__proxy_info_data, impersonate="chrome136")

    def check_promocode(self, dep_date: str, promo_code: str = ""):
        headers = {
            'accept': 'application/json, text/plain, */*',
            "Accept-Language": "en-US,en;q=0.5",
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://www.garuda-indonesia.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.garuda-indonesia.com/',
            'sec-ch-ua': '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': self.__ua,
        }
        data = {
            'parameter': {
                'data': {
                    'code': promo_code,
                    'departureDate': dep_date,
                },
            },
        }
        response = self.__tls.post(
            url='https://web-api.garuda-indonesia.com/ga/revamp/v1.0/promocode/airFare/checkPromocode',
            headers=headers,
            data=data,
            timeout=self.__timeout
        )

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def search(self, flight_params: dict, location: Optional[str], route_index: int = 1) -> dict:
        headers = {
            'accept': 'application/json, text/plain, */*',
            "Accept-Language": "en-US,en;q=0.5",
            'content-type': 'application/json',
            'lang': 'en',
            'origin': 'https://ibe.garuda-indonesia.com',
            'priority': 'u=1, i',
            'referer': 'https://ibe.garuda-indonesia.com/',
            'sec-ch-ua': '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': self.__ua,
        }
        if location:
            headers.update({"location": location})

        response = self.__tls.post(
            url='https://web-api.garuda-indonesia.com/ga/revamp/v1.0/dapi/airFare',
            headers=headers,
            data=flight_params,
            timeout=self.__timeout
        )

        if response.status != 200:
            if "No flights available for your selected dates and destinations. Please try different options" in response.to_text():
                raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        result = response.to_dict()
        flight_result = result.get("result") or {}
        if not flight_result.get("flightData"):
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        self.__ga_session = flight_result.get("sessionId")
        result["routeIndex"] = route_index
        return result

    def get_cf_code(self, referer: str = 'https://ibe.garuda-indonesia.com/booking/passenger') -> str:
        return DanLiCaptchaUtil("m05cmm7ub8vm1pgasjpo8sdp9tl6mkzp").cloudflare_turnstile(
            host=referer, sitekey='0x4AAAAAACjFnflcy2fLxq0T')
        # no_captcha = NoCaptchaUtil(api_key='00cf3281-7648-4678-8cb1-a03041030f40')
        # return no_captcha.solve_cf_turnstile(
        #     url=referer,
        #     sitekey='0x4AAAAAACjFnflcy2fLxq0T',
        # )

    def booking_request(self, booking_params: dict) -> dict:
        headers = {
            "Host": "web-api.garuda-indonesia.com",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "GASession": self.__ga_session,
            "Lang": "en",
            "Origin": "https://ibe.garuda-indonesia.com",
            "Connection": "keep-alive",
            "Referer": "https://ibe.garuda-indonesia.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Priority": "u=0",
            "TE": "trailers",
        }
        response = self.__tls.post(
            url="https://web-api.garuda-indonesia.com/ga/revamp/v1.0/dapi/booking/cart",
            headers=headers,
            data=booking_params,
            timeout=self.__timeout,
        )

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def add_passenger(self, booking_params: dict) -> dict:
        headers = {
            "Host": "web-api.garuda-indonesia.com",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "GASession": self.__ga_session,
            "Lang": "en",
            "Origin": "https://ibe.garuda-indonesia.com",
            "Connection": "keep-alive",
            "Referer": "https://ibe.garuda-indonesia.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Priority": "u=0",
            "TE": "trailers",
        }
        response = self.__tls.post(
            url="https://web-api.garuda-indonesia.com/ga/revamp/v1.0/dapi/booking",
            headers=headers,
            data=booking_params,
            timeout=self.__timeout,
        )

        if response.status != 200:
            if response.status == 500:
                response_data = response.to_dict()
                response_desc = response_data.get("status", {}).get("responseDesc", "")
                if response_desc in ["Can't process your booking for now", "Captcha turnstile validation failed"]:
                    raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()
