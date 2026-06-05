import urllib.parse

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.log_util import LogUtil


class ApiScript:

    def __init__(self):
        self.__log = LogUtil("webScript")
        self.__http_utils = CurlCffiTls(auth_manage_cookie=False)
        self.__http_utils.initialize(None)
        self.__timeout = 60
        self.__token = ''
        # 转发
        # self.__url = "https://otaapi.batikair.com.my"
        self.__url = 'https://b2b-otaapi.batikair.com.my'
        # self.__url = "http://47.242.240.244:5009"
        # {
        #     "loginName": "itsupport",
        #     "password": "KydsOD980544@@@"
        # }

    def init_token(self):
        data = {
            "loginName": "liuanyi",
            "password": "Liuanyi2026888@"
        }
        headers = {
            'Content-Type': 'application/json',
        }
        response = self.__http_utils.post(url=f"{self.__url}/agm/tokens", data=data, headers=headers)
        response_json = response.to_dict()
        if response.status != 200:
            if response_json["message"] == 'Invalid Credentials':
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "用户名或密码错误")
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        self.__token = response.to_dict()['data']['token']
        return response.to_dict()

    def set_toke(self, token):
        self.__token = token

    def search(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/srch/v1.1/search/GetFlightSearchFixeddc", data=data,
                                          headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def select_price(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/ibedc/select", data=data,
                                          headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def get_baggage(self):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.get(url=f"{self.__url}/ibedc/addon",
                                         headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def after_get_baggage(self, pnr):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.get(url=f"{self.__url}/mmb/AddOn?pnr={pnr}",
                                         headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def add_baggage(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/ibedc/addon", data=data,
                                          headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def after_add_baggage(self, pnr, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/mmb/AddOn?pnr={pnr}", data=data,
                                          headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def add_passenger(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/ibedc/passenger", data=data,
                                          headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def get_pay_type(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.get(url=f"{self.__url}/ibedc/pnr/GetPaymentOptions?{urllib.parse.urlencode(data)}",
                                         headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def create_pnr(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/ibedc/pnr/createpnr", data=data,
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def pay(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/ops/TicketingQueue/IssueTicket", data=data,
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def order_detail(self, pnr):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/mmb/GetBooking",
                                          headers=headers, data={"pnr": pnr
                                                                 })
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def get_booking(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/mmb/Void", data=data,
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def refund(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/mmb/Void", data=data,
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def special_refund(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/mmb/SpecialRefund/Create", data=data,
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def cancel(self, pnr):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/ops/TicketingQueue/CancelBooking?reloc={pnr}", data="",
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def search_exchange(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/srch/search/GetFlightSearchFixeddc", data=data,
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def detail_exchange(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/mmb/Exchange/detail", data=data,
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def confirm_exchange(self, data):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/mmb/Exchange/confirm", data=data,
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def logout(self):
        headers = {
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.__token}"
        }
        response = self.__http_utils.post(url=f"{self.__url}/agm/tokens/logout", data={

        },
                                          headers=headers, timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()
