import random
import random
import time
from typing import Optional, List

from common.decorators.retry_decorator import retry_decorator
from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.utils import log_util
from ..config import Config
from ..flight_common.agent_flight_parse import FlightParser
from ..script.agent_script import Script


class Service:

    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__t: dict = {}
        self.__session_id: str = ''
        self.__web_script = Script(proxy_info=proxy_info)
        self.__log = log_util.LogUtil('vietjetWebService')

    def initialize_session(self):
        self.__web_script.initialize_session()

    def login_agent(self):
        self.__web_script.login_agent(username='CH330321A1QX14', password='Vj110112@@')
        self.__web_script.get_agent_info()

    def search_flight(self,
                      dep_airport: str,
                      arr_airport: str,
                      dep_date: str,
                      adt_number: int,
                      chd_number: int,
                      infant_count: int,
                      currency_code: str,
                      ret_date: Optional[str] = None, promo_code: Optional[str] = None):
        # if self.agent_curreny != currency:
        #     raise ServiceError(ServiceStateEnum.SERVICE_ERROR, "币种不支持")

        data = {
            "cityPair": f"{dep_airport}-{arr_airport}",
            "departurePlace": dep_airport,
            "returnPlace": arr_airport,
            "departure": dep_date,
            "currency": currency_code,
            "adultCount": adt_number,
            "childCount": chd_number,
            "infantCount": "0",
            "promoCode": promo_code if promo_code else '',
            "greaterNumberOfStops": "0"
        }
        if ret_date:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "暂不支持返程")

        flight_data = self.__web_script.search_flight(data=data)
        if flight_data['resultcode'] == -88:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "查询航线存在错误")
        if flight_data['resultcode'] == 0:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)

        flights_info = FlightParser.journey_info_parser(flight_data)
        return flights_info

    def verify_price(self, use_bundle: FlightBundleModel, adult_count, child_count, currency):

        key_list = use_bundle.fare_key.split("^")
        data = {
            'journeys': [
                {'index': index, 'bookingKey': key}
                for index, key in enumerate(key_list, start=1)
            ],
            'numberOfAdults': adult_count,
            'numberOfChilds': child_count,
            'numberOfInfants': 0,
        }
        verify_price_resp = self.__web_script.verify_price(data)
        use_bundle.price_info = FlightParser.verify_price_parse(verify_price_resp, adult_count, child_count, currency)

    def sell_flight_and_add_passenger(self, use_bundle_data: FlightBundleModel,
                                      passenger_infos: List[PassengerInfoModel], contact_info: ContactInfoModel,
                                      journey_segments: list[FlightSegmentModel]):
        # --- 1. 代理人基础配置 ---
        agent_email = "1461954581@qq.com"
        agent_name = 'BEIJING RUIANKANGDA AVIATION SERVICES CO.. LTD'
        agent_extension = '86'
        agent_phone = '16680451241'
        agent_isocode = 'CN'

        # --- 2. 初始化核心变量 ---
        key_list = use_bundle_data.fare_key.split("^")
        self.__web_script.booking_key = use_bundle_data.fare_key

        passenger_list = []

        # 动态生成 journeys_list，适配任意数量的 bookingKey
        journeys_list = [
            {"index": i + 1, "passengerJourneyDetails": []}
            for i in range(len(key_list))
        ]

        # --- 3. 遍历乘机人列表构建数据 ---
        for index, p in enumerate(passenger_infos):
            p_index = index + 1
            p.key = str(p_index)
            is_adt = p.type == PassengerTypeEnum.ADT
            is_chd = p.type == PassengerTypeEnum.CHD

            # 3.1 提取成人和儿童的“基础共享字段”
            passenger_info = {
                "index": p_index,
                "sendmail": True,
                "passengerSuffix": "",
                "fareApplicability": {
                    "child": is_chd,
                    "adult": is_adt
                },
                "reservationProfile": {
                    "lastName": p.last_name.upper(),
                    "firstName": p.first_name.upper(),
                    "title": ('Mr' if p.gender == GenderEnum.M else 'Mrs') if is_adt else None,
                    "gender": "Male" if p.gender == GenderEnum.M else "Female",
                    "birthDate": p.birthday,
                    "address": {"location": {}},  # 默认儿童格式，成人在下面覆盖
                    "personalContactInformation": {},  # 默认儿童格式，成人在下面覆盖
                    "passport": {
                        "number": p.document_info.number,
                    },
                    "loyaltyProgram": {}
                }
            }

            # 3.2 针对成人 (ADT) 补充特有字段
            if is_adt:
                country_info = {
                    "code": Config.ISO2_MAP[p.document_info.nationality]['isoCode1'],
                    "name": Config.ISO2_MAP[p.document_info.nationality]['country']
                }
                mobile_iso = Config.Country_Code_Dict[contact_info.phone_code]['isoCode']

                passenger_info['reservationProfile'].update({
                    "nationCountry": country_info,
                    "address": {
                        "address1": "",
                        "location": {"country": country_info}
                    },
                    "personalContactInformation": {
                        "number": contact_info.phone_number,
                        "mobileIsoCode": mobile_iso,
                        "mobileNumber": contact_info.phone_number,
                        "extension": contact_info.phone_code,
                        "isoCode": mobile_iso,
                        "phoneNumber": contact_info.phone_number,
                        "email": contact_info.email_address
                    }
                })

            # 3.3 护照附加信息 (成人/儿童通用)
            if p.document_info.issuing_country:
                passenger_info['reservationProfile']['passport']['issuingCountry'] = {
                    "code": Config.ISO2_MAP[p.document_info.issuing_country]['isoCode1'],
                    "name": Config.ISO2_MAP[p.document_info.issuing_country]['country']
                }
            if p.document_info.expire_date:
                passenger_info['reservationProfile']['passport']['expiryDate'] = p.document_info.expire_date

            passenger_list.append(passenger_info)

            # 3.4 动态填充 journeys_list 详情
            for i, key in enumerate(key_list):
                journeys_list[i]['passengerJourneyDetails'].append({
                    "passenger": {"index": p_index},
                    "bookingKey": key
                })

        # --- 4. 构建最终请求 JSON ---
        data = {
            "languagecode": "zh-CN",
            "bookingInformation": {
                "contactInformation": {
                    "isoCode": agent_isocode,
                    "extension": agent_extension,
                    "phoneNumber": agent_phone,
                    "name": agent_name,
                    "email": agent_email
                }
            },
            "departureAirportCode": journey_segments[0].dep_airport,
            "passengers": passenger_list,
            "journeys": journeys_list,
            "seatSelections": [],
            "ancillaryPurchases": [],
            "paymentTransactions": []
        }

        # --- 5. 发送请求与结果校验 ---
        sell_flight_data = self.__web_script.sell_flight_and_add_passenger(data)

        # 推荐使用 .get() 防止 resultcode 键丢失报错
        if sell_flight_data.get('resultcode') not in (1, -997):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '选航班或添加乘机人异常')

        self.global_flight_data = data
        return sell_flight_data

    def get_pay_key(self):
        data = {
            "bookingkeydeparture": self.__web_script.booking_key.split("^")[0]
        }
        if len(self.__web_script.booking_key.split("^")) > 1:
            data['bookingkeyarrival'] = self.__web_script.booking_key.split("^")[1]

        pay_key_data = self.__web_script.get_pay_key(data)
        if pay_key_data['resultcode'] != 1:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '获取支付key失败')

        return pay_key_data

    def quotations(self):
        quotations_data = self.__web_script.quotations(self.global_flight_data)
        return quotations_data

    def create_order(self, _pay_key, identifier, currency):
        payment_transactions = [
            {
                "allPassengers": True,
                "paymentMethod": {
                    "key": _pay_key,
                    "identifier": identifier
                },
                "currencyAmounts": [
                    {
                        "totalAmount": 0,
                        "exchangeRate": 1,
                        "currency": {
                            "code": currency
                        }
                    }
                ]
            }
        ]
        self.global_flight_data['paymentTransactions'] = payment_transactions
        create_booking_resp = self.__web_script.create_booking(data=self.global_flight_data)
        if create_booking_resp['resultcode'] == 1:
            return create_booking_resp['data']['locator']
        elif create_booking_resp['resultcode'] == -101:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '余额不足')
        else:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '生单失败')

    def get_order_detail(self, pnr: str):
        order_detail = self.__web_script.search_pnr(pnr=pnr)
        if order_detail['resultcode'] != 1:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '获取支付key失败')
        return order_detail

    def pay_and_pnr(self, pnr: str, order_detail: Optional[dict] = None):
        if order_detail is None:
            order_detail = self.get_order_detail(pnr)
        reservation_key = order_detail['data']['key']

        reservation_data = self.__web_script.payment_methods(reservation_key=reservation_key)
        if reservation_data['resultcode'] != 1:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '获取支付key失败')

        _pay_key = next(i['key'] for i in reservation_data['data'] if i['identifier'] == "AG")

        change_payment_data = {
            "reservationKey": reservation_key,
            "paymentTransactions": [
                {
                    "paymentMethod": {
                        "key": _pay_key,
                        "identifier": "AG"
                    },
                    "currencyAmounts": [
                        {
                            "totalAmount": 0,
                            "exchangeRate": 0,
                            "currency": {
                                "code": "USD",
                                "description": "USD",
                                "baseCurrency": False
                            }
                        }
                    ]
                }
            ],
            "isGpayInternational": False
        }

        change_payment_resp = self.__web_script.change_payment(data=change_payment_data)
        if change_payment_resp['resultcode'] != 1:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '获取支付key失败')

        currency = change_payment_resp['data']['currencyCode']

        pay_auth_data = {
            "reservationKey": reservation_key,
            "paymentTransactions": [
                {
                    "paymentMethod": {
                        "key": _pay_key,
                        "identifier": "AG"
                    },
                    "currencyAmounts": [
                        {
                            "totalAmount": 0,
                            "exchangeRate": 0,
                            "currency": {
                                "code": currency,
                                "description": currency,
                                "baseCurrency": False
                            }
                        }
                    ]
                }
            ]
        }
        pay_auth_resp = self.__web_script.pay_auth(data=pay_auth_data)

        if pay_auth_resp['resultcode'] != 1:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '获取支付key失败')

        return pay_auth_resp, currency
