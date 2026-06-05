from typing import Optional

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.chaojiying_utlis import ChaojiyingClient
from flights.cambodiaairways.config import Config


class WebScript:
    def __init__(self, proxy_info_data: Optional[ProxyInfoModel]):
        self.__timeout = 20
        self.__tls = CurlCffiTls()
        self.__tls.initialize(proxy_info_data)

    def get_airports(self):
        response = self.__tls.get(
            url=f'{Config.BASE_URL}/getFlightAirport',
            headers=self.__headers(),
            timeout=self.__timeout,
        )
        self.__check_response(response)
        return response.to_dict()

    def get_arrival_airports(self, dep_airport: str):
        response = self.__tls.get(
            url=f'{Config.BASE_URL}/getFlightByDepartCity?departingAirport={dep_airport}',
            headers=self.__headers(),
            timeout=self.__timeout,
        )
        self.__check_response(response)
        return response.to_dict()

    def search(self, search_data: dict) -> dict:
        submit_data = {key: value for key, value in search_data.items() if not key.startswith('_')}
        response = self.__tls.post(
            url=f'{Config.BASE_URL}/buyTicket',
            headers=self.__headers(content_type='application/json'),
            data=submit_data,
            timeout=self.__timeout,
        )
        self.__check_response(response)
        response_dict = response.to_dict()
        if str(response_dict.get('status')) != '200':
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, response_dict.get('message') or response.to_text())
        return response_dict

    def check_flight_schedule(self, data: dict) -> dict:
        response = self.__tls.post(
            url=f'{Config.BASE_URL}/checkFlightSchedule',
            headers=self.__headers(content_type='application/json'),
            data=data,
            timeout=self.__timeout,
        )
        self.__check_response(response)
        return response.to_dict()

    def compute_price(self, data: dict) -> dict:
        response = self.__tls.post(
            url=f'{Config.BASE_URL}/computePrice',
            headers=self.__headers(content_type='application/json'),
            data=data,
            timeout=self.__timeout,
        )
        self.__check_response(response)
        response_dict = response.to_dict()
        if str(response_dict.get('status')) != '200':
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, response_dict.get('message') or response.to_text())
        return response_dict

    def reserve_flight(self, kind: str, group_id: str) -> list:
        response = self.__tls.post(
            url=f'{Config.BASE_URL}/reserveFlight',
            headers=self.__headers(content_type='application/json'),
            data={
                'kind': kind,
                'groupId': group_id,
            },
            timeout=self.__timeout,
        )
        self.__check_response(response)
        return response.to_dict()

    def reserve_airport(self, data: list) -> list:
        response = self.__tls.post(
            url=f'{Config.BASE_URL}/reserveAirportHX',
            headers=self.__headers(content_type='application/json'),
            data=data,
            timeout=self.__timeout,
        )
        self.__check_response(response)
        return response.to_dict()

    def write_incrservice_next(self, data: list) -> list:
        response = self.__tls.post(
            url=f'{Config.BASE_URL}/writeIncrserviceNextHX',
            headers=self.__headers(content_type='application/json'),
            data=data,
            timeout=self.__timeout,
        )
        self.__check_response(response)
        return response.to_dict()

    def create_code(self, group_id: str) -> dict:
        response = self.__tls.get(
            url=f'{Config.BASE_URL}/createCode?groupId={group_id}',
            headers=self.__headers(),
            timeout=self.__timeout,
        )
        self.__check_response(response)
        response_dict = response.to_dict()
        if str(response_dict.get('status')) != '200' or not response_dict.get('url'):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, response_dict.get('message') or response.to_text())
        return response_dict

    def captcha_image(self, image_name: str) -> bytes:
        response = self.__tls.get(
            url=f'{Config.IMAGE_URL}/{image_name}',
            headers=self.__image_headers(),
            timeout=self.__timeout,
        )
        self.__check_response(response)
        return response.data_bytes

    def captcha_solver(self, captcha_image: bytes) -> str:
        chaojiying = ChaojiyingClient('odsf001', '660otzqe', '972694')
        result = chaojiying.solve_captcha(captcha_image, 6004)
        print( result)
        pic_str = result.get('pic_str')
        if not pic_str:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)
        return pic_str

    def save_ticket_order(self, data: dict) -> dict:
        response = self.__tls.post(
            url=f'{Config.BASE_URL}/savaTicketOrderHX',
            headers=self.__headers(content_type='application/json'),
            data=data,
            timeout=self.__timeout,
        )
        self.__check_response(response)
        return response.to_dict()

    @staticmethod
    def __check_response(response):
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

    @staticmethod
    def __headers(content_type: Optional[str] = None) -> dict:
        headers = {
            'User-Agent': Config.USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5',
            'Origin': Config.ORIGIN,
            'Referer': Config.REFERER,
            'token': '',
            'language': Config.DEFAULT_LANGUAGE,
        }
        if content_type:
            headers['Content-Type'] = content_type
        return headers

    @staticmethod
    def __image_headers() -> dict:
        return {
            'User-Agent': Config.USER_AGENT,
            'Accept': 'image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5',
            'Accept-Language': 'zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5',
            'Referer': Config.REFERER,
        }
