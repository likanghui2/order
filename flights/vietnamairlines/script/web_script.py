import base64
import json
import re
import urllib
import uuid
from typing import Optional
from urllib.parse import urlencode

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.danli_captcha_util import DanLiCaptchaUtil

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"

DANLI_CAPTCHA = DanLiCaptchaUtil('7j58fx77bifxt2jhx01pwoek7asgp6xm')

API_BASE = "https://api-des.vietnamairlines.com"


class WebScript:
    """
    越南航空 Web 端脚本
    基于 Amadeus DES (Digital Experience Suite) 平台
    认证流程: Incapsula reese84 -> OAuth2 client_credentials -> API 调用
    """

    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None, country_code: str = "US", language: str = "en-GB"):
        self.__tls = CurlCffiTls()
        self.__tls.initialize(proxy_info_data=proxy_info)
        self.__proxy = proxy_info
        self.__authorization = ''
        self.__x_d_token = ''
        self.__ama_client_facts = self.__build_ama_client_facts(country_code, language)
        # 同一会话复用 UUID，请求计数器递增(base36)，模拟浏览器行为
        self.__session_id = str(uuid.uuid4())
        self.__request_count = 0

    def __next_client_ref(self) -> str:
        """生成 ama-client-ref，格式: {sessionUUID}:{requestCount_base36}"""
        ref = f"{self.__session_id}:{self.__base36(self.__request_count)}"
        self.__request_count += 1
        return ref

    @staticmethod
    def __base36(n: int) -> str:
        if n == 0:
            return "0"
        digits = ""
        while n:
            digits = "0123456789abcdefghijklmnopqrstuvwxyz"[n % 36] + digits
            n //= 36
        return digits

    @staticmethod
    def __build_ama_client_facts(country_code: str, language: str) -> str:
        """构造无签名 JWT: header.payload. (Amadeus RefX 前端逻辑)"""
        header = base64.b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}, separators=(',', ':')).encode()).decode().rstrip('=')
        payload = base64.b64encode(json.dumps({"sub": "fact", "countryCode": country_code, "language": language},
                                              separators=(',', ':')).encode()).decode().rstrip('=')
        return f"{header}.{payload}."

    def init_incapsula_token(self):
        """通过丹里 API 解决 Incapsula reese84 挑战，获取 x-d-token"""
        incapsula_token = DANLI_CAPTCHA.incapsula_token_get(
            verify_url="https://booking.vietnamairlines.com/Put-and-I-pull-their-Light-I-go-woman-O-the-viol/OKH9SC3iqYKBQuit1BFulwBSToX748kxZM6TsL6An5E",
            user_agent=USER_AGENT,
            host="booking.vietnamairlines.com",
            proxy_data=self.__proxy.get_proxy_info_to_string(),
            jwt_required=True)
        self.__x_d_token = incapsula_token

    def __api_headers(self) -> dict:
        """构造 Amadeus DES API 通用请求头"""
        return {
            "Host": "api-des.vietnamairlines.com",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "ama-client-ref": self.__next_client_ref(),
            "authorization": self.__authorization,
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "ama-client-facts": self.__ama_client_facts,
            "x-d-token": self.__x_d_token,
            "User-Agent": USER_AGENT,
            "accept": "application/json",
            "content-type": "application/json",
            "Origin": "https://booking.vietnamairlines.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://booking.vietnamairlines.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        }

    def reset_proxy_ip(self):
        self.__tls.initialize(self.__proxy)

    def init_oauth_token(self, origin: str, destination: str, departure_date: str,country_code: str = "US",language: str = "en-GB"):
        """OAuth2 client_credentials 获取 Bearer token，每次搜索前调用（token 与航线绑定）"""
        headers = {
            "Host": "api-des.vietnamairlines.com",
            "Connection": "keep-alive",
            "sec-ch-ua-platform": "\"Windows\"",
            "User-Agent": USER_AGENT,
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "sec-ch-ua-mobile": "?0",
            "Origin": "https://booking.vietnamairlines.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://booking.vietnamairlines.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7"
        }

        search_data = {
            "keyValuePairs": [{"key": "originLocationCode1", "value": origin},
                              {"key": "destinationLocationCode1", "value": destination},
                              {"key": "departureDateTime1", "value": departure_date},
                              {"key": "countryCode", "value": country_code},
                              {"key": "language", "value": language}]
        }

        data = urllib.parse.urlencode({
            'client_id': '7yA9XUB34tvB8vahz5O3CFVdGmdKT9au',
            'client_secret': 'vlaA0atz4fjdyEQZ',
            'fact': json.dumps(search_data, separators=(',', ':')),
            'grant_type': 'client_credentials'
        })
        response = self.__tls.post(
            url=f"{API_BASE}/v1/security/oauth2/token/initialization",
            headers=headers,
            data=data
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        token_data = response.to_dict()
        self.__authorization = f"Bearer {token_data['access_token']}"

    def search_air_bounds(self, origin: str, destination: str, departure_date: str,
                          pax_type: str = "ADT", pax_count: int = 1):
        """
        搜索航班
        Args:
            origin: 出发机场 IATA 代码
            destination: 到达机场 IATA 代码
            departure_date: 出发日期 YYYY-MM-DD
            pax_type: 旅客类型 ADT/CHD
            pax_count: 旅客数量
        """
        self.init_oauth_token(origin=origin, destination=destination, departure_date=departure_date)

        data = {
            "commercialFareFamilies": ["WEB"],
            "itineraries": [
                {
                    "departureDateTime": f"{departure_date}T00:00:00.000",
                    "originLocationCode": origin,
                    "destinationLocationCode": destination,
                    "isRequestedBound": True
                }
            ],
            "travelers": [{"passengerTypeCode": pax_type} for _ in range(pax_count)],
            "searchPreferences": {
                "showMilesPrice": False
            }
        }

        response = self.__tls.post(
            url=f"{API_BASE}/v2/search/air-bounds",
            headers=self.__api_headers(),
            data=data
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def create_cart(self, air_bound_ids: list):
        """
        创建购物车，选定航班报价
        Args:
            air_bound_ids: 航班报价 ID 列表，来自 search_air_bounds 返回的 airBoundId
        """
        response = self.__tls.post(
            url=f"{API_BASE}/v2/shopping/carts",
            headers=self.__api_headers(),
            data={"airBoundIds": air_bound_ids}
        )
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def update_travelers(self, cart_id: str, travelers: list):
        """
        批量填写旅客信息，逐个 PATCH
        Args:
            cart_id: 购物车 ID
            travelers: 旅客列表，每项包含:
                traveler_id: 旅客 ID，如 SKH-1-EXT
                last_name: 姓
                first_name: 名
                title: 称谓 MR/MRS/MS/MSTR/MISS
                pax_type: 旅客类型 ADT/CHD/INF
                date_of_birth: 出生日期 YYYY-MM-DD
        """
        last_resp = None
        for t in travelers:
            data = {
                "id": t["traveler_id"],
                "passengerTypeCode": t["pax_type"],
                "names": [
                    {
                        "firstName": t["first_name"],
                        "lastName": t["last_name"],
                        "middleName": "",
                        "title": t["title"]
                    }
                ],
                "dateOfBirth": t["date_of_birth"],
                "nationalityCountryCodes": []
            }
            response = self.__tls.patch(
                url=f"{API_BASE}/v2/shopping/carts/{cart_id}/travelers/{t['traveler_id']}?lastName={t['last_name']}&includeWaitlist=false",
                headers=self.__api_headers(),
                data=data
            )
            if response.status != 200:
                raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
            last_resp = response
        return last_resp

    def add_contacts(self, cart_id: str, last_name: str, traveler_ids: list,
                     email: str, phone_code: str, phone_number: str):
        """
        填写联系方式
        Args:
            cart_id: 购物车 ID
            last_name: 姓（用于 URL query，取第一位旅客的姓）
            traveler_ids: 所有旅客 ID 列表，如 ["SKH-1-EXT", "SKH-2-EXT"]
            email: 邮箱地址
            phone_code: 电话区号，如 +852
            phone_number: 电话号码
        """
        data = [
            {"id": "", "travelerIds": [], "category": "personal",
             "contactType": "Email", "purpose": "standard", "address": email, "lang": "ja"},
            {"id": "", "travelerIds": traveler_ids, "category": "personal",
             "contactType": "Email", "purpose": "notification", "address": email, "lang": "ja"},
            {"id": "", "travelerIds": [], "category": "personal",
             "contactType": "Phone", "purpose": "standard", "deviceType": "mobile",
             "countryPhoneExtension": phone_code, "number": phone_number, "lang": "ja"},
            {"id": "", "travelerIds": traveler_ids, "category": "personal",
             "contactType": "Phone", "purpose": "notification", "deviceType": "mobile",
             "countryPhoneExtension": phone_code, "number": phone_number, "lang": "ja"},
        ]
        response = self.__tls.post(
            url=f"{API_BASE}/v2/shopping/carts/{cart_id}/contacts?lastName={last_name}",
            headers=self.__api_headers(),
            data=data
        )
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def create_order(self, cart_id: str):
        """
        创建订单（提交预订）
        Returns:
            响应中 data[0].id 为 PNR 编码（如 FP7J9A）
            data[0].paymentTimeLimit 为支付截止时间
        """
        response = self.__tls.post(
            url=f"{API_BASE}/v2/purchase/orders?cartId={cart_id}",
            headers=self.__api_headers(),
            data={}
        )
        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def get_payment_methods(self, order_id: str, last_name: str):
        """
        获取支付方式列表（下单后调用）
        Args:
            order_id: PNR 编码，来自 create_order 响应
            last_name: 旅客姓
        Returns:
            响应中 data.remainingAmount 为待支付金额
            data.availablePaymentMethods 为可用支付方式列表
        """
        data = {
            "orderId": order_id,
            "paymentRequests": [
                {
                    "paymentMethod": {
                        "paymentType": "CheckoutFormPayment",
                        "parameters": {
                            "links": [
                                {
                                    "rel": "postRedirection",
                                    "href": "https://booking.vietnamairlines.com/booking/payment"
                                }
                            ]
                        }
                    }
                }
            ]
        }
        response = self.__tls.post(
            url=f"{API_BASE}/v2/purchase/payment-methods?lastName={last_name}",
            headers=self.__api_headers(),
            data=data
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    @staticmethod
    def __pay_headers() -> dict:
        """Amadeus PayPages 支付网关请求头"""
        return {
            "Host": "paypages.payment.amadeus.com",
            "Connection": "keep-alive",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "Amadeus-Checkout-Sdk-Version": "WEB/5.7.0/1cb83a3",
            "Amadeus-Checkout-Sdk-Flavor": "Core-Sdk",
            "sec-ch-ua-mobile": "?0",
            "Amadeus-Checkout-Sdk-Host": "booking.vietnamairlines.com",
            "User-Agent": USER_AGENT,
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "*/*",
            "Origin": "https://prd.payment.amadeus.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://prd.payment.amadeus.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        }

    def payment_load(self, ppid: str):
        """
        加载支付页面，获取可用支付方式
        Args:
            ppid: CheckoutFormPayment ID，来自 get_payment_methods 响应中的 availablePaymentMethods
        """
        response = self.__tls.post(
            url="https://paypages.payment.amadeus.com/1ASIATP/ARIAPP/pay",
            headers=self.__pay_headers(),
            data=json.dumps({"PPID": ppid, "action": "load"})
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def payment_add(self, ppid: str, mop_id: str = "amop01"):
        """
        选择支付方式，获取 actionToken
        Args:
            ppid: CheckoutFormPayment ID
            mop_id: 支付方式 ID (amop0=paypal, amop01=alipay, amop02=wechat, amop03=cup, creditcard)
        """
        data = {
            "PPID": ppid,
            "data": {
                "mopid": mop_id,
                "mopdata": {"mopid": mop_id},
                "fingerprint": f"{ppid}-RUYD2J9M69"
            },
            "action": "add"
        }
        response = self.__tls.post(
            url="https://paypages.payment.amadeus.com/1ASIATP/ARIAPP/pay",
            headers=self.__pay_headers(),
            data=json.dumps(data)
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def payment_records(self, order_id: str, last_name: str, ppid: str,
                        action_token: str, email: str, contact_id: str,
                        language: str = "ja-JP"):
        """
        提交支付，获取第三方支付跳转链接
        Args:
            order_id: PNR 编码
            last_name: 旅客姓
            ppid: CheckoutFormPayment ID
            action_token: 来自 payment_add 响应
            email: 通知邮箱
            contact_id: 联系人 ID，来自 create_order 响应中的 contacts
            language: 语言代码
        Returns:
            响应 202 Accepted，data.links[0].href 为第三方支付跳转 URL
        """
        data = {
            "paymentRequests": [
                {
                    "paymentMethod": {
                        "paymentType": "CheckoutFormPayment",
                        "id": ppid,
                        "actionToken": action_token
                    }
                }
            ],
            "userNotifications": [
                {
                    "emailAddresses": [email],
                    "contactIds": [contact_id],
                    "layoutId": "RFXBCNFVN",
                    "lang": language.split("-")[0].upper()
                }
            ]
        }
        response = self.__tls.post(
            url=f"{API_BASE}/v2/purchase/orders/{order_id}/payment-records?lastName={last_name}&lang={language}",
            headers=self.__api_headers(),
            data=data
        )
        if response.status not in [200, 202]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def hold_order(self, order_id: str, last_name: str):
        """
        保留订单（延长支付时限）
        Args:
            order_id: PNR 编码
            last_name: 旅客姓
        Returns:
            响应中 data.paymentTimeLimit / data.issuanceTimeLimit 为更新后的截止时间
        """
        response = self.__tls.post(
            url=f"{API_BASE}/v2/purchase/orders/{order_id}/on-hold?lastName={last_name}",
            headers=self.__api_headers(),
            data=""
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response


if __name__ == '__main__':
    import random
    from flights.vietnamairlines.flight_common.flight_info_parser import FlightInfoParser

    def test():
        proxy_info = ProxyInfoModel(
            host='pr-na.roxstar.cn',
            port=4600,
            username='ciwei001',
            password='ciwei001',
            region='jp',
            session_time=15,
            format='http://user-{username}-region-{region}-sessid-aaaa{sessId}-sesstime-{sessionTime}-keep-true:{password}@{host}:{port}',
        )
        proxy_info.sess_id = str(random.randint(100000, 999999))

        ws = WebScript(proxy_info)

        # 1. Incapsula 初始化
        print("1. init incapsula token...")
        ws.init_incapsula_token()

        # 2. 搜索航班（2成人）
        print("2. search air bounds (2 ADT)...")
        search_resp = ws.search_air_bounds("HKG", "HAN", "2026-05-23", pax_count=2)
        journeys = FlightInfoParser.journey_info_parser(search_resp.to_dict())
        print(f"   找到 {len(journeys)} 个航程")
        for j in journeys:
            segs = ' -> '.join([f'{s.flight_number} {s.dep_airport}-{s.arr_airport}' for s in j.segments])
            print(f"   [{segs}]")
            for b in j.bundles:
                print(f"     {b.code} {b.cabin_level} seat={b.seat} {b.price_info.adult_ticket_price}+{b.price_info.adult_tax_price} {b.price_info.currency}")

        # 选第一个航程的最便宜票价
        target_bundle = journeys[0].bundles[0]
        print(f"\n   选定: {journeys[0].segments[0].flight_number} {target_bundle.code} {target_bundle.price_info.adult_ticket_price} {target_bundle.price_info.currency}")

        # 3. 创建购物车
        print("3. create cart...")
        cart_resp = ws.create_cart([target_bundle.fare_key])
        cart_data = cart_resp.to_dict()
        cart_id = cart_data["data"]["id"]
        cart_travelers = cart_data["data"]["travelers"]
        print(f"   cart_id={cart_id}")
        for ct in cart_travelers:
            print(f"   traveler: id={ct['id']} type={ct['passengerTypeCode']}")

        # 4. 批量填写旅客信息
        print("4. update travelers...")
        traveler_infos = [
            {"traveler_id": cart_travelers[0]["id"], "last_name": "ZHANG", "first_name": "SAN",
             "title": "MR", "pax_type": "ADT", "date_of_birth": "1990-01-01"},
            {"traveler_id": cart_travelers[1]["id"], "last_name": "LI", "first_name": "SI",
             "title": "MRS", "pax_type": "ADT", "date_of_birth": "1992-06-15"},
        ]
        ws.update_travelers(cart_id=cart_id, travelers=traveler_infos)
        for t in traveler_infos:
            print(f"   {t['traveler_id']}: {t['title']} {t['first_name']} {t['last_name']}")

        # 5. 填写联系方式（关联所有旅客）
        print("5. add contacts...")
        all_traveler_ids = [ct["id"] for ct in cart_travelers]
        ws.add_contacts(
            cart_id=cart_id,
            last_name=traveler_infos[0]["last_name"],
            traveler_ids=all_traveler_ids,
            email="TESTUSER@GMAIL.COM",
            phone_code="+852",
            phone_number="12345678"
        )
        print("   联系方式已填写")

        # 6. 创建订单
        print("6. create order...")
        order_resp = ws.create_order(cart_id)
        order_data = order_resp.to_dict()
        order = order_data["data"][0]
        pnr = order["id"]
        last_name = traveler_infos[0]["last_name"]
        print(f"   PNR={pnr}")
        print(f"   paymentTimeLimit={order.get('paymentTimeLimit')}")

        # 7. 保留订单
        print("7. hold order...")
        hold_resp = ws.hold_order(order_id=pnr, last_name=last_name)
        hold_data = hold_resp.to_dict()["data"]
        print(f"   paymentTimeLimit={hold_data.get('paymentTimeLimit')}")
        print(f"   issuanceTimeLimit={hold_data.get('issuanceTimeLimit')}")
        print(f"   占座成功 PNR={pnr}")

    test()
