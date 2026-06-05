import base64
from typing import Optional
from urllib.parse import urlencode

from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA

from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from flights.vietjet.config import Config
from common.errors.service_error import ServiceError, ServiceStateEnum


class Script:

    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__http_utils = CurlCffiTls()
        self.__ua = Config.USER_AGENT
        self.__http_utils.initialize(proxy_info_data=proxy_info)
        self.__proxy = proxy_info
        self.__timeout = 10
        self.authorization = ''
        self.booking_key = ''

    @staticmethod
    def rsa__encrypt(plaintext: str) -> str:
        # 示例
        pub_key = """-----BEGIN RSA PUBLIC KEY-----
          MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAzzlX85HWtWs9duKm97Dl8gf+ojFq50KobiWL6GNCbw8lcoINCA4pLu2mInC6jaaNK0NY6PvlwfkJIlcTcBf2sczV+2Ju3nad4G7Po9xYkyFAcCsMygGmGvQag9kcmSOEQtMKwNGdqdOe6AR21CMIn0TgRIBejpkw3anfG79GCYkj4vRJPKMNRLoBbJibITrXR2mbzPpNoP9FezoImY9zf4WFhr/6+rv1yjGSbefhXPeUFRauBcYFJl/CeJuDTnW7/QH43tdPQEEzPOiATsTijrBS2eVRlrNkZCieZeDqwArcBug/JjWnImSmuYQDmCB7J+jrCSASjPPrZM6M8fucNQIDAQAB
          -----END RSA PUBLIC KEY-----
        """

        # 导入公钥
        public_key = RSA.import_key(pub_key)

        # 创建 OAEP 加密器（与 node-forge 完全兼容）
        cipher = PKCS1_OAEP.new(public_key)

        # 加密
        encrypted_bytes = cipher.encrypt(plaintext.encode())

        # 转 Base64（等价于 node-forge 的 util.encode64）
        return base64.b64encode(encrypted_bytes).decode()

    def initialize_session(self):
        self.__http_utils.initialize(proxy_info_data=self.__proxy)

    def reset_proxy_ip(self):
        self.__http_utils.initialize(self.__proxy)

    def login_agent(self, username, password):
        """

        Args:
            username:
            password:

        Returns:

        """
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,vi;q=0.7',
            'content-type': 'application/json',
            'languagecode': 'vi',
            'origin': 'https://agents2.vietjetair.com',
            'platform': '3',
            'priority': 'u=1, i',
            'referer': 'https://agents2.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            "User-Agent": self.__ua,
        }
        data = {
            'lang': 'vi',
            'username': username,
            'password': self.rsa__encrypt(password),
        }
        response = self.__http_utils.post(url='https://agentapi.vietjetair.com/api/v14/Auth/login', headers=headers,
                                          data=data, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        self.authorization = response.to_dict()["data"]["token"]
        return response.to_dict()

    def get_agent_info(self):
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,vi;q=0.7',
            'authorization': 'Bearer ' + self.authorization,
            'content-type': 'application/json',
            'languagecode': 'vi',
            'origin': 'https://agents2.vietjetair.com',
            'platform': '3',
            'priority': 'u=1, i',
            'referer': 'https://agents2.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            "User-Agent": self.__ua,
        }

        response = self.__http_utils.get(
            url='https://agentapi.vietjetair.com/api/v14/Auth/getuseragency?userIdOneSignal=',
            headers=headers, timeout=self.__timeout)
        if response.status != 200:
            if response.status == 401 and "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để tiếp tục" in response.text:
                return ''
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_text()

    def search_flight(self, data: dict) -> dict:
        """

        Args:
            data:

        Returns:

        """
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,vi;q=0.7',
            "User-Agent": self.__ua,
            'content-type': 'application/json',
            'languagecode': 'zh-CN',
            'origin': 'https://agents2.vietjetair.com',
            'platform': '3',
            'priority': 'u=1, i',
            'referer': 'https://agents2.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'authorization': 'Bearer ' + self.authorization,

        }
        response = self.__http_utils.get(
            url='https://agentapi.vietjetair.com/api/v14/Booking/findtraveloptions?' + urlencode(data),
            headers=headers,
            timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def verify_price(self, data):

        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,vi;q=0.7',
            "User-Agent": self.__ua,
            'content-type': 'application/json',
            'languagecode': 'zh-CN',
            'origin': 'https://agents2.vietjetair.com',
            'platform': '3',
            'priority': 'u=1, i',
            'referer': 'https://agents2.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'authorization': 'Bearer ' + self.authorization,

        }

        response = self.__http_utils.post(
            url='https://agentapi.vietjetair.com/api/v14/Booking/quotationwithoutpassenger',
            headers=headers, data=data, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def sell_flight_and_add_passenger(self, data: dict):
        headers = {
            "sec-ch-ua-platform": "\"Windows\"",
            "languagecode": "zh-CN",
            "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "User-Agent": self.__ua,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "platform": "3",
            "origin": "https://agents2.vietjetair.com",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://agents2.vietjetair.com/",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "priority": "u=1, i",
            'authorization': 'Bearer ' + self.authorization,

        }

        response = self.__http_utils.post(
            url='https://agentapi.vietjetair.com/api/v14/Booking/insurances',
            headers=headers, data=data, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def get_pay_key(self, data):
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,vi;q=0.7',
            "User-Agent": self.__ua,
            'content-type': 'application/json',
            'languagecode': 'zh-CN',
            'origin': 'https://agents2.vietjetair.com',
            'platform': '3',
            'priority': 'u=1, i',
            'referer': 'https://agents2.vietjetair.com/',
            'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'authorization': 'Bearer ' + self.authorization,

        }
        response = self.__http_utils.get(
            url=f'https://agentapi.vietjetair.com/api/v14/Booking/paymentMethods?{urlencode(data)}',
            headers=headers, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def create_booking(self, data):
        headers = {
            "sec-ch-ua-platform": "\"Windows\"",
            "languagecode": "zh-CN",
            "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "User-Agent": Config.USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "platform": "3",
            "origin": "https://agents2.vietjetair.com",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://agents2.vietjetair.com/",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "priority": "u=1, i",
            'authorization': 'Bearer ' + self.authorization,

        }

        response = self.__http_utils.post(
            url='https://agentapi.vietjetair.com/api/v14/Booking/createbooking',
            headers=headers, data=data, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def quotations(self, data):
        headers = {
            "sec-ch-ua-platform": "\"Windows\"",
            "languagecode": "zh-CN",
            "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "User-Agent": Config.USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "platform": "3",
            "origin": "https://agents2.vietjetair.com",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://agents2.vietjetair.com/",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "priority": "u=1, i",
            'authorization': 'Bearer ' + self.authorization,

        }

        response = self.__http_utils.post(
            url='https://agentapi.vietjetair.com/api/v14/Booking/quotations',
            headers=headers, data=data, timeout=self.__timeout)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_dict()

    def search_pnr(self, pnr):

        headers = {
            "User-Agent": Config.USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
            # 'Accept-Encoding': 'gzip, deflate, br, zstd',
            'sec-ch-ua-platform': '"Windows"',
            'authorization': 'Bearer ' + self.authorization,
            'languagecode': 'vi',
            'sec-ch-ua': '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'content-type': 'application/json',
            'platform': '3',
            'origin': 'https://agents2.vietjetair.com',
            'sec-fetch-site': 'same-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://agents2.vietjetair.com/',
            'accept-language': 'en-US,en;q=0.9',
            'priority': 'u=1, i',
        }

        response = self.__http_utils.get(
            url=f'https://agentapi.vietjetair.com/api/v14/EditBooking/getreservationdetailbylocator?locator={pnr}',
            headers=headers)

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def payment_methods(self, reservation_key: str):

        headers = {
            "User-Agent": Config.USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
            # 'Accept-Encoding': 'gzip, deflate, br, zstd',
            'sec-ch-ua-platform': '"Windows"',
            'authorization': 'Bearer ' + self.authorization,
            'languagecode': 'vi',
            'sec-ch-ua': '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'content-type': 'application/json',
            'platform': '3',
            'origin': 'https://agents2.vietjetair.com',
            'sec-fetch-site': 'same-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://agents2.vietjetair.com/',
            'accept-language': 'en-US,en;q=0.9',
            'priority': 'u=1, i',
        }
        response = self.__http_utils.get(
            url=f'https://agentapi.vietjetair.com/api/v14/EditBooking/paymentMethods?reservationKey={reservation_key}&isChangeJourney=false',
            headers=headers)

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def change_payment(self, data: dict):

        headers = {
            "sec-ch-ua-platform": "\"Windows\"",
            'authorization': 'Bearer ' + self.authorization,
            "languagecode": "zh-CN",
            "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "User-Agent": Config.USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "platform": "3",
            "origin": "https://agents2.vietjetair.com",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://agents2.vietjetair.com/",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "priority": "u=1, i"
        }
        response = self.__http_utils.put(
            url=f'https://agentapi.vietjetair.com/api/v14/EditBooking/getquotationbyreservationkey',
            data=data,
            headers=headers)

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()

    def pay_auth(self, data: dict):

        headers = {
            "sec-ch-ua-platform": "\"Windows\"",
            'authorization': 'Bearer ' + self.authorization,
            "languagecode": "zh-CN",
            "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "User-Agent": Config.USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "platform": "3",
            "origin": "https://agents2.vietjetair.com",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://agents2.vietjetair.com/",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "priority": "u=1, i"
        }
        response = self.__http_utils.put(
            url=f'https://agentapi.vietjetair.com/api/v14/EditBooking/paymentforbooking',
            data=data,
            headers=headers)

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY,
                               response.status)
        return response.to_dict()
