import base64
import decimal
import json
import os
import random
import re
import time
import uuid
from typing import Optional, List
from urllib.parse import parse_qs, urlparse, urlencode

from common.decorators.retry_decorator import retry_decorator
from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.order.payment_info_model import PaymentInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils.cardinalcommerce_util import CardinalcommerceUtil
from common.utils.chaojiying_utlis import ChaojiyingClient
from common.utils.secureacceptance_util import SecureAcceptance
from common.utils.securepay_util import Securepay
from common.utils.string_util import StringUtil
from common.utils.visa_util import Visa
from ..config import Config
from ..flight_common.flight_info_parser import FlightInfoParser
from ..flight_common.order_detail_parser import OrderDetailParser
from ..flight_common.order_detail_parser_v2 import OrderDetailParserV2
from ..flight_common.utils import Utils
from ..script.web_script import WebScript


class WebService:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__script = WebScript(proxy_info_data)
        self.chaojiying = ChaojiyingClient('likanghui', 'likanghui', '971092')

    def init_token(self):
        return self.__script.init_token()

    def set_token(self, token):
        return self.__script.set_token(token)

    def init(self):
        self.__script.reset_proxy_ip()

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               infant_count: int,
               currency_code: str,
               ret_date: Optional[str] = None):
        country_code = Utils.get_country_by_currency(currency_code)
        date_list = [dep_date, ret_date] if ret_date else [dep_date]
        itinerary_parts = [
            {
                "depDate": dep_time,
                "depPort": {
                    "airportCode": dep_airport,
                    "countryCode": Utils.get_country(dep_airport)
                },
                "arrPort": {
                    "airportCode": arr_airport,
                    "countryCode": Utils.get_country(arr_airport)
                }

            }
            for dep_time in date_list
        ]

        if not country_code:
            dep_airport = itinerary_parts[0]['depPort']['airportCode']
            country_code = Utils.get_country(dep_airport)

        submit_data = {
            "language": 'zh_CN',
            "tripType": 0 if ret_date in [None, ''] else 1,
            "itineraryParts": itinerary_parts,
            "paxNumbers": {
                "numAdults": adt_number,
                "numChildren": chd_number,
                "numInfants": infant_count
            },
            "promoCode": os.environ.get("PROMO_CODE", 'NEXTTRIP26'),
            "cabinClass": 0,
            "pointOfSale": country_code,
            "searchType": 0,
            "cartId": "",
            "searchId": "",
            "userAgent": "Web",
            "sort": 2
        }
        submit_data_encrypt = Utils.aes_encrypt(json.dumps(submit_data))
        response = self.__script.availability(
            data={
                "payload": submit_data_encrypt
            }
        )

        response_dict = response.to_dict()
        encrypted_data = Utils.aes_decrypt(data=response_dict['response'])
        journey_list = FlightInfoParser.journey_info_parser(flight_data=encrypted_data)
        return journey_list

    def verify_email(self, email):
        email_blacklist = self.__script.email_blacklist()
        for email_ in email_blacklist['data']:
            if email_['email'] in email:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f'邮箱域名[{email_["email"]}]被封禁，请更换域名重试')

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, init)], retry_max_number=10)
    def __add_passenger(self, passenger_infos: List[PassengerInfoModel], contact_info: ContactInfoModel):
        """

        Args:
            passenger_infos:
            contact_info:

        Returns:

        """
        passengers = []
        self.verify_email(contact_info.email_address)
        for passenger_info in passenger_infos:
            title = Config.PASSENGER_TITLE.get(
                f'{passenger_info.type.value}_{passenger_info.gender.value}')
            passengers.append({
                "passengerInfo": {
                    "title": title,
                    "givenName": passenger_info.first_name.capitalize(),
                    "surname": passenger_info.last_name.capitalize(),
                    "gender": 0 if passenger_info.gender == GenderEnum.M else 1,
                    "birthDate": passenger_info.birthday,
                    "nationality": passenger_info.document_info.nationality,
                    "passport": None,
                    "middleName": None
                },
                "paxCode": 0 if passenger_info.type.value == 'ADT' else 1
            })
        contact = {
            "phone": {
                "countryCode": f"+{contact_info.phone_code}",
                "locationCityCode": f"KUL00{contact_info.phone_code}",
                "number": contact_info.phone_number,
                "type": "HOME"
            },
            "email": contact_info.email_address,
            "confirmEmail": contact_info.email_address,
            "title": "MR",
            "givenName": contact_info.first_name.capitalize(),
            "surname": contact_info.last_name.capitalize()
        }

        add_result = self.__script.add_passenger(passengers, contact)
        if not add_result.to_dict().get('status'):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '添加乘客失败')

    def __get_ssr_baggage(self):
        # self.__script.get_cart().to_dict()
        return self.__script.get_baggages()

    def booking(self,
                journey: FlightJourneyModel,
                passengers: List[PassengerInfoModel],
                bundle: FlightBundleModel,
                contact_info: ContactInfoModel,
                response_order_data: ResponseOrderInfoModel,
                check_booking: Optional[bool] = False):
        self.__script.select_cart(fare_ids=bundle.fare_key.split("^"),
                                  adt_number=sum([1 for x in passengers if x.type == PassengerTypeEnum.ADT]),
                                  chd_number=sum([1 for x in passengers if x.type == PassengerTypeEnum.CHD]))
        if check_booking:
            return None
        self.__add_passenger(passengers, contact_info)

        total_baggage_weight = sum([sum(j.weight for j in x.ssr.baggage) for x in passengers])
        baggages = []
        if total_baggage_weight != 0:
            # raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "占不支持行李出票")
            baggage_data = self.__get_ssr_baggage()
            for i in passengers:
                total_buy_baggage_weight = sum(
                    [x.weight * x.number for x in i.ssr.baggage if x.type == SsrTypeEnum.HAULING_BAGGAGE])
                if total_buy_baggage_weight > 0:
                    baggage_list = []
                    for z in baggage_data["fares"][0]["paxBags"]:
                        if i.last_name.lower() == z["lastName"].lower() and i.first_name.lower() == z[
                            "firstName"].lower():
                            for f in z['baggages']:
                                if f["bagUnit"]["weight"] == total_buy_baggage_weight:
                                    baggage_list.append({
                                        "code": f['code'],
                                        "price": f['priceBreakDown']['totalPrice'],
                                        "name": f'{f["bagUnit"]["weight"]}-KG',
                                        "segment": {
                                            "depPort": baggage_data["fares"][0]['depPort'],
                                            "arrPort": baggage_data["fares"][0]['arrPort'],
                                            "depTime": baggage_data["fares"][0]['depTime']
                                        },
                                        "paxs": [
                                            {
                                                "index": z['index'],
                                                "quantity": 1,
                                                "firstName": z["firstName"],
                                                "lastName": z["lastName"]
                                            }
                                        ]
                                    })
                    if len(baggage_list) == 0:
                        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "行李匹配错误")
                    baggages += baggage_list

        self.__script.add_baggage(baggages, currency=bundle.price_info.currency)
        booking_data = self.__script.get_cart().to_dict()
        total_amount = decimal.Decimal(booking_data["totalCost"])
        response_order_data.order_number = ""
        response_order_data.passengers = passengers
        response_order_data.currency_code = booking_data['cartTotalFareCost']['currency']
        response_order_data.journeys = [journey]
        response_order_data.journeys[0].bundles = [bundle]
        response_order_data.contact_info = contact_info
        response_order_data.total_amount = total_amount
        return response_order_data

    # @retry_decorator([(ServiceStateEnum.API_RESPONSE_FAILED, None)], retry_max_number=3)
    # def solve_gtoken(self):
    #
    #     img_bytes1 = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xdb\x00C\x01\t\t\t\x0c\x0b\x0c\x18\r\r\x182!\x1c!22222222222222222222222222222222222222222222222222\xff\xc0\x00\x11\x08\x002\x00\x96\x03\x01"\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02w\x00\x01\x02\x03\x11\x04\x05!1\x06\x12AQ\x07aq\x13"2\x81\x08\x14B\x91\xa1\xb1\xc1\t#3R\xf0\x15br\xd1\n\x16$4\xe1%\xf1\x17\x18\x19\x1a&\'()*56789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xf7\xfa+\x8a\xf17\xc45\xf0\xf7\x8a \xf0\xfc\x1a\x0e\xa5\xaa^\xcdh.\xd5l\xc2\x9f\x93s/Bs\xc6\xdf\xd6\xaa\x7f\xc2\xc7\xd5\xbf\xe8\x9ex\x9b\xfe\xfc\xa7\xf8\xd0\x07\xa0Q^\x7f\xff\x00\x0b\x1fV\xff\x00\xa2y\xe2o\xfb\xf2\x9f\xe3]\'\x86u\xfb\x9d~\xdaynt-GHh\x9c \x8e\xf9\x02\xb3\x8cg#\x1d\xa8\x03r\x8a\xaf\x7f}o\xa6i\xd77\xf7r\x08\xed\xad\xa2ies\xd9Td\x9a\xe7\xf4\xcf\x18>\xb5\xe0\x16\xf1E\x86\x8ft\xcc`y\xa2\xb2\x95\x82\xbc\xbbs\xc2\x91\x9e\x0e\x0e\x0e9\xf4\xe6\x80:\x8a+\x17\xc2~$\xb4\xf1o\x86l\xb5\xab<\x04\xb8L\xbc{\xb2bq\xc3!\xfa\x1c\xfdx=\xebj\x80\n(\xaeW@\xf1\x93\xeb~2\xf1\x07\x87\xce\x9d\xe4\x8d\x1d\x90\x1b\x8f;w\x9b\xbf\x91\xf2\xed\x18\xe0\x1e\xe6\x80:\xaa(\xa2\x80\n)\xae\xc5#f\x03$\x02q\xeb\\\xdf\x80|X\xfe6\xf0\x9c\x1a\xdb\xd9\x0b3,\x8e\x9eH\x93~6\xb1\x19\xce\x07\xa7\xa5\x00t\xd4Q\\\x86\xbf\xf1\'B\xf0\xe6\xb8t{\xc8\xef\xe5\xbd\x11,\xc5-\xadZ\\!\xe0\x1e(\x03\xaf\xa2\xb8\x0f\xf8[\xfe\x1e\xff\x00\x9f\rw\xff\x00\x05\xb2Q\xff\x00\x0b\x7f\xc3\xdf\xf3\xe1\xae\xff\x00\xe0\xb6J\x00\xef\xe8\xae\x7f\xc2\xbe2\xd2\xbcc\r\xdc\xba_\xda@\xb4\x94E2\xdcBcelg\x184P\x07)}\xff\x00\'\x1b\xa6\xff\x00\xd8\xbc\xdf\xfa5\xe9\xfe#\xf1g\x8a\xbc\x11\xe29\xf5\rZ\xc6=G\xc2\x132\x815\x9ab[\x1e\x00\xcb\x8e\xe0\x9e\xa7\xa7\xa1\x1ft\xb2\xfb\xfeN7M\xff\x00\xb1y\xbf\xf4k\xd5\x9f\x1ax\xef3\xbf\x85<+\x14z\xaf\x88\xee\xd4\xc6\xd1\xa8\x0f\x15\xa2\x9e\x19\xe5=8\xcf\xdd?\x8f`@2\xfcC\xe3K\xbf\x18x\x8fF\xf0\xdf\x80\xb5`\xac\xc5oo\xb5(F\xe5\x82\x11\xd1H<\x12s\xca\x9e\xfbA\xef\x8fTE+\x1a\xab9v\x00\x02\xc4\x0c\x9f~8\xaf\t\x1e\r\xf1\x0f\xc1x\xe2\xf1\x1e\x87puk\x03\x12\x8dj\xcc\xa0\\\x81\x9c\xbaz(\xc9\xe7\xa8\xear\t\xc7\xb3\xe8Z\xdd\x97\x88\xf4;M_N\x90\xbd\xad\xd2oB\xc3\x04v \x8fPA\x07\xe9@\x1eS\xf1\x13\xc56\x9e/\xd7b\xf0E\x9e\xabme\xa4G2\x9dkR\x96e\x8e1\x83\x91\x02\xb18,v\x9e=G\xa2\xb5z-\xa7\x8a\xbc\x1bcg\x05\xa5\xaf\x88\xb4H\xad\xe0\x8dc\x8e5\xbf\x8b\n\xa0`\x01\xf3z\nI<\r\xe11\xa7Mi&\x85`,\xe4\xb87rFc\x01<\xcc\x11\xb8\xfa`\x13\xec3^m\xf0\xaf\xc1~\x19\xf1\x1c~"\xd6\xeet;9\xac.5I\x13OI"\x04$+\xd3h\xec>l\x7f\xc0h\x02\xbd\xd6\xb3\x07\xc3\x8f\x15]\xeb\x1e\x15\xbf\xb1\xd6|5\xa81\x9a\xff\x00K\xb3\xbaI$\xb5o\xe2\x95\x14\x1e\x17\xf4\xecq\x80G\xa8\xdbx\xb6\ro\xc1\xb2\xf8\x83\xc3V\xef\xaa\x1d\x84\xc3ns\x13H\xe3\xaad\x8e\x0f\xbf"\xb8_\x0fh:V\x9f\xfb@jv\xda^\x9foiig\xa2\xa8h\xa1@\x17{\xba\x9c\x91\xee\xa4\xd7\xab\xdaZ[XZ\xa5\xad\x9d\xbcV\xf6\xf1\x8c$Q U^\xfc\x01\xc0\xa0\x0f=_\x1d\xf8\xf0\x8e~\x17\\\xe7\xdbU\x8f\xff\x00\x88\xae\x17\xc1\xfe1\xf1\x1c\x1f\x10<gse\xe0\xa9oo\xae\xe5\x84\xdc\xda.\xa0\x88mv\x06\\\x16+\xf3d\x9e\xdd1^\xc7\xe3/\x16X\xf87\xc3w\x1a\xad\xe3\x02\xca6\xdb\xc3\x9f\x9aiO\xddQ\xfd}\x06My%\x8f\x87\xf5\x9f\x876z_\xc4+\x85\x9ak\xbb\x97\x91\xbcEn2[\xca\x99\x83\x06\x03\xd5\x0e\t\xf7\xf6\xcd\x00v_\xf0\x9d\xf8\xec\xba\xaf\xfc+\x0b\x95\x04\x80X\xeahp=p\x12\xbd\x1d\x98*\x96b\x00\x03$\x9e\xd5\x05\x85\xfd\xae\xa9a\x05\xf5\x8c\xe9=\xac\xe8\x1e)P\xe42\x9e\xf5\xc6|\\\xf1\x04\xfa\x1f\x81.a\xb2\x8eI/\xf56\x166\xe25$\x83\'\x04\xfbq\x90=\xc8\xa0\x0b~\x01\xf1\x94\xfe7\xd25\rI\xac\x16\xda\xd2+\xb9 \xb6\x909>z/F\xc1\x1cp@\xeay\xcfJ\xe3\xfe\x18jW\xda7\xc0#\xa9i\xb6K{wm\xf6\x89R\xdd\x98\xa8|Hs\xd0s\x81\x93\x8e\xf8\xc7z\xf4/\x08\xf8}<-\xe0\xdd7FLn\xb6\xb7\x02B:4\x87\x97?\x8b\x13\\\xa7\xc0\x8f\xf9%6\x1f\xf5\xda\x7f\xfd\x18h\x03\xb1\xf0\xaf\x88\xad|W\xe1\x9b\x1dj\xd3\x88\xeec\x0c\xc9\x9c\x98\xdcp\xca~\x84\x11U\xbf\xe1\x1a\xb5\xb4\xf1\xad\xd7\x8b\xda\xe6S;\xe9\xff\x00chH\x1b\x15\x03\x07\xcf\xaex\xaeK\xc0\xbam\xff\x00\x84>"x\x8b\xc3q\xd9\xcet\x0b\xa05\x1b)\x963\xe5B\xccp\xd1\xe7\xa0\xee\x00\xff\x00\xa6~\xf5\xdc\xebW\xbap\xb3\xb9\xd3\xaeu[K)\xee e_6U\x0c\xa1\x81\x01\xb6\x9223\x9f\xca\x80<\xa7\xe1\xa7\x8c\xfc\\<\x19\x0c\xaf\xe1\x9d_^\x13M#\xad\xf3\xdf!\xdc7ch\xdes\x80A\x1f\x9du\xe3\xc6\xde*\xdc\xa0\xfc9\xd4\xc0\'\x04\x9b\xc8x\xfc\x8ds\xba/\x875?\x0fi\x16\xfaV\x97\xf1r\xc2\xde\xca\xdc\x11\x14_\xd9\xf6\xad\xb7$\xb1\xe5\x9c\x93\xc9\'\x93W.\xed|_\x16\x89\xa9jV\x7f\x15`\xbd\x166\xef;\xa4:M\xab}\xd5-\x82A8\xce\r\x00w:\'\x86l4\x0b\xddZ\xea\xcd\xa62j\x97F\xeaq#\x02\x03\x9e\xbbx\x18\x1f\x9d\x15C\xe1\xd6\xab\xa8k~\x00\xd1\xf5=Vo>\xf6\xe6"\xf2\xc9\xb1Ww\xcc\xd8\xe1@\x03\x8ct\x14P\x071\xe2\x9bO\x10\xd8|\\\xb2\xf1&\x99\xe1\xc9\xf5k(\xf4\x8f\xb28\x8ah\xe3\xf9\xcc\x8eH\xf9\x8f`Gn\xf4\xcd\x16\xfbS\xf0\xeb\\\xb6\x91\xf0\x96\xe2\xcd\xae\xa42Lb\xbc\x80n?\x9f\x03\xd0\x0e\x07a^\xa5E\x00pM\xe3/\x16:2?\xc3mA\x95\x86\n\x9b\xe8\x08#\xf3\xad\x8f\nj\xda\x9d\xf2\xcbk{\xe1I\xb4\x1b{h\xd1`\x0f4n\xac9\x1bT\'@\x00\x1f\x9dt\xb4P\x07\x99x\xad<k\xe3=^\xeb\xc2\xd66\r\xa2h \xec\xbc\xd5%p\xcfq\x19\xfe\x18\x80\xecG_\xc8\x91\xc8=d\x962x?\xc1B\xcf\xc3\x1aR\xdd\xbd\x8cAm\xec\xdaM\x86^~o\x9b\x1fx\xe4\x9fs]\r\x14\x01\xe7\x9f\x0f\xf4\x1f\x10\x8f\x13x\x83\xc5\x9e&\xb3\x86\xc6\xf3U\x11G\x15\x9cr\t\x0cQ\xa2\xe3\x9229\xc2\xfeG\xa5u~(\xbd\xd6t\xff\x00\x0f\xdc\xddh\x1atZ\x86\xa1\x18\xccv\xf2HT0\xef\x8fS\xed\x91\x9fZ\xd8\xa2\x80<\xc7\xc3?\x0f\xb5\x8dS[\x83\xc5?\x10/\x16\xf7S\x87\xe6\xb4\xd3\xe3\xc7\x91i\xdf8\x1c\x16\x1ct\xf4\xceX\xe0\x8fK\x9a\x18\xae \x92\t\xe3Y"\x91J:8\xca\xb2\x91\x82\x08\xee)\xf4P\x07\x92\xc1\xe1\x0f\x17\xfc>\xf1\n\x1f\x064Z\x8f\x87/\'\x1en\x9bw.>\xc8X\xf2\xca\xddv\x8fQ\x93\xea\x1b\x19\xafY*\x18a\x80<\x83\x83\xcf"\x96\x8a\x00\xe6\xfce\xae\xeb:\x0e\x9d\x04\xda7\x87e\xd6\xe5\x9aC\x13E\x14\xbb\x0c|\x12\x18\xfc\xa7+\xc6\x0fN\xde\xb5\x9f\xf0\xa3\xc3\xda\x87\x86>\x1ei\xfan\xa9\x10\x86\xf1ZI$\x880m\x9b\x9c\x90\t\x1cg\x18\xae\xd2\x8a\x00+\x0bY\xf0_\x86\xfcCz\xb7\x9a\xbe\x8fkyr\xb1\x88\x96IW$($\x81\xf9\x93\xf9\xd6\xed\x14\x01\xc9\x7f\xc2\xaf\xf0?\xfd\x0b\x1a\x7f\xfd\xfb\xae;\xc4ZV\xad\xa5\xc3\xad\xf8W\xc1>\x00\x8e\x18u8\x042jkr\x12"\x8c\xa4\x13\xb4\x81\xc8\x0c\xc3\xaf\xbf=+\xd7\xa8\xa0\x0c\x9f\x0ch\xff\x00\xf0\x8f\xf8[K\xd27\x87k;h\xe1f\x1d\x19\x82\x8c\x91\xf594V\xb5\x14\x00QE\x14\x00QE\x14\x00QE\x14\x00QE\x14\x00QE\x14\x00QE\x14\x00QE\x14\x00QE\x14\x00QE\x14\x00QE\x14\x01\xff\xd9'
    #
    #     img_data = self.__script.get_img()
    #     img_base64 = img_data['data']
    #     img_id = img_data['id']
    #     base64_str = StringUtil.extract_between(img_base64, 'base64,', '\"')
    #     print(base64_str)
    #
    #     img_bytes2 = base64.b64decode(base64_str)
    #
    #     result_bytes = Utils.concat_images_vertically_transparent_bytes([img_bytes1, img_bytes2])
    #     img_token = self.chaojiying.solve_captcha(result_bytes, 6004)
    #     if img_token['err_str'] != "OK":
    #         print(img_token['err_str'])
    #         raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)
    #     self.__script.pic_id = img_token['pic_id']
    #     img_token = img_token['pic_str']
    #     print(img_token)
    #     self.__script.g_token = base64.b64encode(f"{img_id}|{img_token}|".encode('utf-8')).decode('utf-8')

    @retry_decorator([(ServiceStateEnum.API_RESPONSE_FAILED, None)], retry_max_number=3)
    def solve_gtoken(self):
        self.__script.g_token = ""
        img_data = self.__script.get_img()
        img_base64 = img_data['data']
        img_id = img_data['id']
        base64_str = StringUtil.extract_between(img_base64, 'base64,', '\"')
        img_token = self.__script.invoke(base64_str)
        self.__script.g_token = base64.b64encode(f"{img_id}|{img_token}|".encode('utf-8')).decode('utf-8')

    def home(self):
        self.__script.home()

    def solve_cloudflare_cookies(self):
        self.__script.solve_cloudflare_cookies()

    @staticmethod
    def __public_bank_card_type(card_type: str) -> int:
        card_type = (card_type or "").upper()
        if card_type in ["VI", "VISA"]:
            return 0
        if card_type in ["CA", "MC", "MASTERCARD"]:
            return 1
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"不支持的卡类型[{card_type}]")

    @staticmethod
    def __build_public_bank_billing_info() -> dict:
        return {
            "billingAddress": StringUtil.generate_random_string(10),
            "billingCity": "hong kong",
            "billingState": "",
            "billingCountry": "HK",
            "billingPostCode": "",
        }

    @staticmethod
    def __ccavenue_card_name(card_type: str) -> str:
        card_type = (card_type or "").upper()
        if card_type in ["VI", "VISA"]:
            return "Visa"
        if card_type in ["CA", "MC", "MASTERCARD"]:
            return "MasterCard"
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"不支持的卡类型[{card_type}]")

    @staticmethod
    def __ccavenue_billing_info() -> dict:
        return {
            "billingAddress": 'Beijing DAXING',
            "billingCity": "Beijing",
            "billingState": "Beijing",
            "billingCountry": "CN",
            "billingCountryName": "China",
            "billingPostCode": "100010",
            "billingMobileCountryCode": "86",
        }

    @staticmethod
    def __format_ccavenue_amount(amount) -> str:
        try:
            return f"{decimal.Decimal(str(amount)):,.2f}"
        except Exception:
            return str(amount or "")

    @staticmethod
    def __ccavenue_page_error_summary(html_content: str) -> str:
        if not html_content or "Oops Transaction" not in html_content:
            return ""
        error_code = re.search(r'<h3[^>]*class="errorCode"[^>]*>\s*([^<]+)', html_content, re.I)
        order_no = re.search(r'Order No:\s*#?([^<\s]+)', html_content, re.I)
        message = re.search(r'<h2[^>]*>\s*(.*?)\s*</h2>', html_content, re.I | re.S)
        parts = []
        if error_code:
            parts.append(f"code={error_code.group(1).strip()}")
        if order_no:
            parts.append(f"order={order_no.group(1).strip()}")
        if message:
            parts.append(re.sub(r'\s+', ' ', message.group(1)).strip())
        return "; ".join(parts) or "Oops Transaction"

    def __finalize_payment_status(self, payment_result_url: str, allow_confirmation_token: bool = False,
                                  ccavenue_headers: bool = False) -> str:
        itinerary_id = self.__script.extract_itinerary_id(payment_result_url)
        if itinerary_id:
            return itinerary_id

        if 'payment-status' not in payment_result_url:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"支付结果地址异常[{payment_result_url}]")

        self.__script.doku_open_payment_status_page(payment_result_url, ccavenue_headers=ccavenue_headers)
        payment_token = parse_qs(urlparse(payment_result_url).query).get('token', [None])[0]
        if not payment_token:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "支付状态token为空")

        verify_status = self.__script.doku_verify_status(payment_token, payment_result_url,
                                                          ccavenue_headers=ccavenue_headers)
        if not verify_status.get('isPaymentSuccess'):
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED,
                               verify_status.get('message') or verify_status.get('reason') or "支付未成功")

        ticket_status = {}
        for _ in range(24):
            ticket_status = self.__script.doku_ticket_status(payment_token, payment_result_url,
                                                             ccavenue_headers=ccavenue_headers)
            redirect_url = ticket_status.get('redirectURL')
            if redirect_url:
                itinerary_id = self.__script.extract_itinerary_id(redirect_url)
                if itinerary_id:
                    return itinerary_id

            if ticket_status.get('isTicketSuccess'):
                if ticket_status.get('itineraryId'):
                    return str(ticket_status['itineraryId'])
                if allow_confirmation_token and ticket_status.get('token'):
                    itinerary_id = self.__script.public_bank_confirmation(ticket_status['token'])
                    if itinerary_id:
                        return itinerary_id
            else:
                if "has been processing" in ticket_status.get('message'):
                    time.sleep(5)
                else:
                    raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, ticket_status.get('message'))
            time.sleep(5)

        raise ServiceError(ServiceStateEnum.PAYMENT_EXCEPTION,
                           ticket_status.get('message') or "获取出票结果失败，人工确认是否扣款成功")

    def __get_proxy_str(self) -> Optional[str]:
        proxy = self.__script.proxy
        return proxy.get_proxy_info_to_string() if proxy else None

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.ROBOT_CHECK, None)], retry_max_number=15)
    def payment_2c2p(self, vcc_info: PaymentInfoModel, cust_name: str, cust_email: str,
                     sham_booking: bool = False):

        card_expire_arr = vcc_info.card_expiry_date.split('/')
        year = f'20{card_expire_arr[1]}'
        month = card_expire_arr[0]

        card_info = {
            "cardnumber": vcc_info.card_number,
            "cvv": vcc_info.card_cvv,
            "month": month,
            "year": year,
        }
        secure_pay_token = Utils.pay_encrypt(card_info)['encryptedCardInfo']
        pay_data = {
            "cartId": "",
            "searchId": "",
            "customerIp": "",
            "securePayToken": secure_pay_token,
            "currency": "AED",
            "custName": cust_name,
            "custEmail": cust_email
        }
        # self.solve_gtoken()

        pay_res = self.__script.payment_2c2p(pay_info=pay_data)
        if not pay_res:
            self.chaojiying.report_error(self.__script.pic_id)
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
        if sham_booking:
            return '111111'
        # if "Error coming Invalid Card Number" in pay_res['message'] and sham_booking:
        #     return '111111'
        # elif "Transaction is completed, please do payment inquiry request for full payment informatio" in pay_res[
        #     'message'] and sham_booking:
        #     return '111111'
        # elif 'Do not honor' in pay_res['message']:
        #     return '111111'
        redirect_url = pay_res['redirectUrl']
        self.__script.pay_callback(redirect_url)
        pattern = 'itineraryId=(.*)'
        itinerary_id = re.search(pattern, redirect_url).group(1)
        return itinerary_id

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.ROBOT_CHECK, None),
                                               (ServiceStateEnum.AKM_RISK_TWO_CHECK_FAILED, init)], retry_max_number=15)
    def payment_public_bank(self, vcc_info: PaymentInfoModel, cust_name: str, cust_email: str, contact_mobile: str,
                            response_order_data: ResponseOrderInfoModel, sham_booking: bool = False):
        card_expire_arr = vcc_info.card_expiry_date.split('/')
        year = f'20{card_expire_arr[1]}'
        month = card_expire_arr[0]
        last_name = cust_name.split(' ')[-1].upper()
        first_name = ' '.join(cust_name.split(' ')[0:-1]).upper()
        billing_info = self.__build_public_bank_billing_info()
        pay_data = {
            "cartId": "",
            "searchId": "",
            "customerIp": "",
            "card": {
                "number": re.sub(r'[\s-]+', '', vcc_info.card_number),
                "expDate": f"{month}-{year}",
                "cardType": self.__public_bank_card_type(vcc_info.card_type)
            },
            "billingName": first_name,
            "billingSurname": last_name,
            "billingAddress": billing_info["billingAddress"],
            "billingCity": billing_info["billingCity"],
            "billingState": billing_info["billingState"],
            "billingCountry": billing_info["billingCountry"],
            "billingPostCode": billing_info["billingPostCode"],
            "billingMobile": contact_mobile,
            "billingEmail": cust_email
        }

        pay_res = self.__script.payment_pub(pay_info=pay_data)
        if not pay_res:
            self.chaojiying.report_error(self.__script.pic_id)
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
        pay_data_silent = {
            k: v for k, v in pay_res['postData'].items()
            if k not in ['publicbankURL', 'submit']
        }
        transaction_uuid = pay_data_silent.get('transaction_uuid', '')
        if transaction_uuid:
            response_order_data.pnr = transaction_uuid.split('_')[0]
        if sham_booking:
            return response_order_data.pnr

        secure_pay_utlis = SecureAcceptance(proxy_info=self.__script.proxy,
                                            user_agent=Config.USER_AGENT,
                                            accept_language=Config.ACCEPT_LANGUAGE)
        cardinalcommerce_pay_utlis = CardinalcommerceUtil(proxy_str=self.__get_proxy_str(),
                                                          agent=Config.USER_AGENT,
                                                          accept_language=Config.ACCEPT_LANGUAGE)
        payment_data3 = secure_pay_utlis.silent_pay(pay_data_silent)
        if 'PublicBank/Complete' in payment_data3:
            pay_url2, pay_data2 = Utils.extract_form_data(payment_data3)
        else:
            authenticity_token = StringUtil.extract_between(payment_data3, '"authenticityToken":', ',').replace('"', '').replace(' ', '')
            reference_id = StringUtil.extract_between(payment_data3, '"referenceId":', ',').replace('"', '').replace(' ', '')
            server_jwt = StringUtil.extract_between(payment_data3, '"jwt":', ',').replace('"', '').replace(' ', '')

            cardinalcommerce_pay_utlis.jwt_init(jwt=server_jwt)
            rander_response_data = cardinalcommerce_pay_utlis.render_post(
                url=f"https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/Render?threatmetrix=true&alias=Default&orgUnitId=60644821ae04af5182b895bc&tmEventType=PAYMENT&referenceId={reference_id}&geolocation=false&origin=Songbird",
                data=f"nonce={uuid.uuid4()}")
            cardinalcommerce_pay_utlis.save_browser_data_windows(
                nonce=rander_response_data['nonce'],
                reference_id=rander_response_data['referenceId'],
                org_unit_id=rander_response_data['orgUnitId'],
                referrer=""
            )
            secure_pay_utlis.hybrid(cca_session_id=reference_id, authenticity_token=authenticity_token)
            hybrid_data = secure_pay_utlis.hybrid_2(authenticity_token=authenticity_token)
            pay_url2, pay_data2 = Utils.extract_form_data(hybrid_data)

        if not pay_url2 or not pay_data2:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)

        payment_result_url = self.__script.pay_finish_public(url=pay_url2, form_data=pay_data2)
        return self.__finalize_payment_status(payment_result_url, allow_confirmation_token=True)

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.ROBOT_CHECK, None)], retry_max_number=15)
    def payment_cny(self, vcc_info: PaymentInfoModel, cust_name: str, cust_email: str, contact_mobile: str,
                    response_order_data: ResponseOrderInfoModel, sham_booking= False):
        card_expire_arr = vcc_info.card_expiry_date.split('/')
        year = f'20{card_expire_arr[1]}'
        month = card_expire_arr[0]
        last_name = cust_name.split(' ')[-1].upper()
        first_name = ' '.join(cust_name.split(' ')[0:-1]).upper()
        billing_info = self.__build_public_bank_billing_info()
        browser_fonts = [
            "Arial", "Arial Black", "Calibri", "Cambria", "Cambria Math", "Comic Sans MS", "Consolas",
            "Courier", "Courier New", "Georgia", "Helvetica", "Impact", "Lucida Console",
            "Lucida Sans Unicode", "Microsoft Sans Serif", "MS Gothic", "MS PGothic", "MS Sans Serif",
            "MS Serif", "Palatino Linotype", "Segoe Print", "Segoe Script", "Segoe UI", "Segoe UI Light",
            "Segoe UI Semibold", "Segoe UI Symbol", "Tahoma", "Times", "Times New Roman", "Trebuchet MS",
            "Verdana", "Wingdings"
        ]
        pay_data = {
            "cartId": "",
            "searchId": "",
            "customerIp": "",
            "card": {
                "number": re.sub(r'[\s-]+', '', vcc_info.card_number),
                "expDate": f"{month}-{year}",
                "cardType": self.__public_bank_card_type(vcc_info.card_type)
            },
            "billingName": first_name,
            "billingSurname": last_name,
            "billingAddress": billing_info["billingAddress"],
            "billingCity": billing_info["billingCity"],
            "billingState": billing_info["billingState"],
            "billingCountry": billing_info["billingCountry"],
            "billingPostCode": billing_info["billingPostCode"],
            "billingMobile": contact_mobile,
            "billingEmail": cust_email
        }

        self.__script.g_token = ''
        pay_res = self.__script.payment_pub(
            pay_info=pay_data,
            fill_customer_ip=True,
        )
        if not pay_res:
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
        response_order_data.pnr = pay_res["postData"]["reference_number"][:6]
        if sham_booking:
            return pay_res["postData"]["reference_number"][:6]
        pay_data_silent = {
            k: v for k, v in pay_res['postData'].items()
            if k not in ['publicbankURL', 'submit']
        }
        transaction_uuid = pay_data_silent.get('transaction_uuid', '')
        if transaction_uuid:
            response_order_data.pnr = transaction_uuid.split('_')[0]

        secure_pay_utlis = SecureAcceptance(proxy_info=self.__script.proxy,
                                            user_agent=self.__script.user_agent,
                                            accept_language=self.__script.accept_language)
        silent_pay_result = secure_pay_utlis.silent_pay_entry(pay_data_silent)
        payment_data3 = silent_pay_result.get('html') or ''

        if 'PublicBank/Complete' in payment_data3:
            pay_url2, pay_data2 = Utils.extract_form_data(payment_data3)
        else:
            hybrid_load_url = silent_pay_result.get('redirect_url')
            if not hybrid_load_url:
                raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, "CNY支付主链既未直出Complete也未返回3DS跳转")

            payment_data3 = secure_pay_utlis.hybrid_load(hybrid_load_url)
            match = re.search(r'window\.ccaOptions\s*=\s*(\{.*?\})\s*;', payment_data3, re.S)
            if not match:
                raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, "CNY VISA缺少3DS页面配置")

            try:
                cca_options = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"CNY VISA 3DS配置解析失败[{exc}]")

            authenticity_token = cca_options.get('authenticityToken')
            reference_id = cca_options.get('referenceId')
            server_jwt = cca_options.get('jwt')
            ddc_delay_ms = int(cca_options.get('ddcDelay') or 5000)
            if not authenticity_token or not reference_id or not server_jwt:
                raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, "CNY VISA 3DS参数不完整")

            org_unit_id = "60644821ae04af5182b895bc"
            if '.' in server_jwt:
                try:
                    payload = server_jwt.split('.')[1]
                    payload += '=' * (-len(payload) % 4)
                    org_unit_id = json.loads(base64.urlsafe_b64decode(payload).decode()).get('OrgUnitId') or org_unit_id
                except Exception:
                    pass

            cardinalcommerce_pay_utlis = CardinalcommerceUtil(proxy_str=self.__get_proxy_str(),
                                                             agent=self.__script.user_agent,
                                                             accept_language=self.__script.accept_language)
            visa_pay_util = Visa(proxy_info=self.__script.proxy, accept_language=self.__script.accept_language)
            cardinal_init_result = cardinalcommerce_pay_utlis.cardinaltrusted_init_jwt(
                jwt=server_jwt,
                user_agent=self.__script.user_agent,
                headers_options={
                    "referer": "https://secureacceptance.cybersource.com/",
                    "origin": "https://secureacceptance.cybersource.com",
                    "accept-language": self.__script.accept_language,
                },
                client_version='2.1.0'
            )
            cardinal_client_session_id = None
            cardinal_jwt = cardinal_init_result.get('CardinalJWT')
            if cardinal_jwt and '.' in cardinal_jwt:
                try:
                    payload = cardinal_jwt.split('.')[1]
                    payload += '=' * (-len(payload) % 4)
                    cardinal_payload = json.loads(base64.urlsafe_b64decode(payload).decode())
                    cardinal_client_session_id = cardinal_payload.get('ConsumerSessionId')
                    reference_id = cardinal_payload.get('ReferenceId') or reference_id
                except Exception:
                    pass
            if not cardinal_client_session_id:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "CNY VISA缺少ccaClientSessionId")

            browser_fingerprint = uuid.uuid4().hex
            rander_response_data = cardinalcommerce_pay_utlis.render_post(
                url=f"https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/Render?threatmetrix=true&alias=Default&orgUnitId={org_unit_id}&tmEventType=PAYMENT&referenceId={reference_id}&geolocation=false&origin=Songbird",
                data=f"nonce={uuid.uuid4()}",
                headers_options={
                    "Origin": "https://secureacceptance.cybersource.com",
                    "Referer": "https://secureacceptance.cybersource.com/",
                    "Accept-Language": self.__script.accept_language,
                    "User-Agent": self.__script.user_agent,
                }
            )
            render_features = rander_response_data.get('features', {}) or {}
            vcdi_data = render_features.get('vcdi', {}) or {}
            method_urls = render_features.get('merchantMethodUrlCollection', {}).get('methodUrls', []) or []
            vcdi_timeout_ms = int(vcdi_data.get('Timeout') or 4000)

            cardinalcommerce_pay_utlis.cardinalcommerce_save_browser_data(
                nonce=rander_response_data['nonce'],
                reference_id=reference_id,
                org_unit_id=org_unit_id,
                user_agent=self.__script.user_agent,
                referrer="https://secureacceptance.cybersource.com/",
                headers_options={
                    "Referer": f"https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/Render?threatmetrix=true&alias=Default&orgUnitId={org_unit_id}&tmEventType=PAYMENT&referenceId={reference_id}&geolocation=false&origin=Songbird",
                    "Accept-Language": self.__script.accept_language,
                    "User-Agent": self.__script.user_agent
                },
                origin="Songbird",
                fingerprint=browser_fingerprint,
                fingerprinting_time=106,
                available_js_fonts=browser_fonts,
                do_not_track="unspecified",
                adblock=False,
                usable_resolution="2560x1392",
                screen_resolution="2560x1440",
                vcdi_client_request_id=vcdi_data.get('ClientRequestId')
            )
            time.sleep(max(vcdi_timeout_ms / 1000, 4))

            if method_urls:
                method_url_info = method_urls[0]
                hidden_inputs = visa_pay_util.render_method_url(
                    url=method_url_info['MethodURL'],
                    payload=method_url_info['Payload'],
                    user_agent=self.__script.user_agent,
                    headers_options={"accept-language": self.__script.accept_language},
                )
                if hidden_inputs.get('vcdiUrl') and vcdi_data.get('ClientId'):
                    visa_pay_util.vcdi(
                        url=hidden_inputs['vcdiUrl'],
                        client_id=vcdi_data['ClientId'],
                        product_code=vcdi_data['ProductCode'],
                        client_request_id=vcdi_data['ClientRequestId'],
                        user_agent=self.__script.user_agent,
                    )
                if hidden_inputs.get('authToken'):
                    visa_pay_util.save_browser_data(
                        params={'authToken': hidden_inputs['authToken']},
                        ua=self.__script.user_agent,
                        org_unit_id=hidden_inputs.get('orgUnitId') or org_unit_id,
                        reference_id=hidden_inputs.get('referenceId') or method_url_info.get('ThreeDSServerTransactionId'),
                        headers_options={
                            "referer": method_url_info['MethodURL'],
                            "accept-language": self.__script.accept_language,
                        },
                        fingerprint=browser_fingerprint,
                        fingerprinting_time=75,
                        available_js_fonts=browser_fonts,
                        do_not_track="unspecified",
                        adblock=False,
                        platform="Win32",
                        screen_resolution="2560x1440",
                        usable_resolution="2560x1392"
                    )
                if hidden_inputs.get('notificationUrl') and hidden_inputs.get('base64payload'):
                    cardinalcommerce_pay_utlis.notification_post(
                        url=hidden_inputs['notificationUrl'].replace('&amp;', '&'),
                        data=urlencode({'threeDSMethodData': hidden_inputs['base64payload']}),
                        headers_options={
                            "Origin": "https://methodurl.vcas.visa.com",
                            "Referer": "https://methodurl.vcas.visa.com/",
                            "Accept-Language": self.__script.accept_language,
                            "User-Agent": self.__script.user_agent,
                        }
                    )

            time.sleep(max(ddc_delay_ms / 1000, 5))
            secure_pay_utlis.hybrid(
                cca_session_id=reference_id,
                authenticity_token=authenticity_token,
                cca_client_session_id=cardinal_client_session_id,
                data_options={
                    "ccaTiming": "5675",
                    "customer_browser_color_depth": "24",
                    "customer_browser_language": "zh-CN",
                    "__inner_width": "667",
                    "__inner_height": "1307"
                },
                headers_options={"Accept-Language": self.__script.accept_language},
            )
            time.sleep(3)
            hybrid_data = secure_pay_utlis.hybrid_2(
                authenticity_token=authenticity_token,
                headers_options={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": self.__script.accept_language,
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin"
                }
            )
            pay_url2, pay_data2 = Utils.extract_form_data(hybrid_data)

        if not pay_url2 or not pay_data2:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)

        payment_result_url = self.__script.pay_finish_public(url=pay_url2, form_data=pay_data2)
        return self.__finalize_payment_status(payment_result_url, allow_confirmation_token=True)

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.HTTP_TIMEOUT, None),
                                               (ServiceStateEnum.CURL_EXCEPTION, None)],
                     retry_max_number=3)
    def payment_ccavenue(self, vcc_info: PaymentInfoModel, cust_name: str, cust_email: str, contact_mobile: str,
                         response_order_data: ResponseOrderInfoModel, sham_booking=False):
        card_number = re.sub(r'[\s-]+', '', vcc_info.card_number)
        expiry_digits = re.sub(r'\D', '', vcc_info.card_expiry_date)
        if len(expiry_digits) == 4:
            month = expiry_digits[:2]
            year = "20" + expiry_digits[-2:]
        elif len(expiry_digits) == 6:
            month = expiry_digits[:2]
            year = expiry_digits[-4:]
        else:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"CCAvenue卡有效期格式异常[{vcc_info.card_expiry_date}]")

        billing_info = self.__ccavenue_billing_info()
        card_name = self.__ccavenue_card_name(vcc_info.card_type)
        mobile=contact_mobile
        update_form = None
        tracking_id = None
        last_init_error = ""
        for init_attempt in range(3):
            pay_res = self.__script.payment_ccavenue(
                pay_info={
                    "cartId": "",
                    "searchId": "",
                    "customerIp": "",
                    "billingName": cust_name,
                    "billingAddress": billing_info["billingAddress"],
                    "billingCity": billing_info["billingCity"],
                    "billingState": billing_info["billingState"],
                    "billingCountry": billing_info["billingCountry"],
                    "billingZip": billing_info["billingPostCode"],
                    "billingPostCode": billing_info["billingPostCode"],
                    "billingMobile": mobile,
                    "billingEmail": cust_email,
                },
                fill_customer_ip=True,
            )
            if not pay_res or not pay_res.get("status"):
                raise ServiceError(ServiceStateEnum.PAYMENT_FAILED,
                                   (pay_res or {}).get("message") or "CCAvenue支付初始化失败")

            redirect_url = pay_res.get("redirectUrl")
            post_data = pay_res.get("postData") or {}
            if not redirect_url or not post_data:
                raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, "CCAvenue支付跳转参数为空")

            entry_html = self.__script.ccavenue_initiate_transaction(redirect_url, post_data)
            forms = Utils.extract_forms_data(entry_html)
            if forms:
                form_action, update_form = forms[0]
                tracking_id = update_form.get("trackingId")
                if tracking_id and "updateTransaction" in (form_action or ""):
                    break
            last_init_error = self.__ccavenue_page_error_summary(entry_html) or "入口表单缺少updateTransaction/trackingId"
            if init_attempt < 2:
                time.sleep(1)
        else:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"CCAvenue交易初始化失败[{last_init_error}]")

        card_bin = card_number[:8]
        card_bin_res = self.__script.ccavenue_validate_card_bin(tracking_id, card_bin)
        if card_bin_res.get("data"):
            card_name = card_bin_res["data"]

        card_type = "CRDC"
        card_type_res = self.__script.ccavenue_validate_card_type(tracking_id, card_bin)
        card_type_data = (card_type_res.get("data") or "").split("|")
        if card_type_data and card_type_data[0]:
            card_type = card_type_data[0]
        if len(card_type_data) > 3 and card_type_data[3]:
            card_name = card_type_data[3]
        if len(card_type_data) > 2 and card_type_data[2] == "Y":
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, "CCAvenue卡OTP支付链暂未接入")

        payment_option = "OPTDBCRD" if card_type == "DBCRD" else "OPTCRDC"
        self.__script.ccavenue_get_cvvless_mid({
            "command": "getCvvlessMid",
            "trackingId": tracking_id,
            "cardType": card_type,
            "paymentOption": payment_option,
            "cardNumber": card_number,
            "netAmt": update_form.get("netAmt", ""),
            "cardName": card_name,
            "currency": update_form.get("currency", response_order_data.currency_code or "INR"),
            "enableCVVLessTransaction": "Y",
            "tokenNumber": "",
        })
        self.__script.ccavenue_get_emi_plan(tracking_id, card_bin)

        encrypted_card_number = Utils.rsa_encrypt(card_number, Config.CCAVENUE_RSA_KEY)
        encrypted_month = Utils.rsa_encrypt(month, Config.CCAVENUE_RSA_KEY)
        encrypted_year = Utils.rsa_encrypt(year, Config.CCAVENUE_RSA_KEY)
        encrypted_cvv = Utils.rsa_encrypt(vcc_info.card_cvv, Config.CCAVENUE_RSA_KEY)
        invoice_amount = self.__format_ccavenue_amount(update_form.get("netAmt"))
        update_form.remove("cardNo", "cardexpiry", "cvvnumber", "nocostSelect")
        update_form.insert_after("custCvvNumber", "netBankingBank", "default")
        update_form.insert_after("flexiPayMobileNumber", "neftBank", "default")
        update_form.update({
            "command": "updateTransaction",
            "cardType": card_type,
            "paymentOption": payment_option,
            "cardNumber": encrypted_card_number,
            "expiryMonth": encrypted_month,
            "expiryYear": encrypted_year,
            "expiryDate": "",
            "cvvNumber": encrypted_cvv,
            "cardName": card_name,
            "cardBinNumber": card_bin,
            "browserData": Config.CCAVENUE_BROWSER_DATA,
            "enableCVVLessTransaction": "N",
            "isCvvlessMid": "N",
            "tokenNumber": "",
            "mobileNumber": "",
            "billName": cust_name,
            "billEmail": cust_email,
            "billTel": mobile,
            "billAddress": billing_info["billingAddress"],
            "billZip": billing_info["billingPostCode"],
            "billCity": billing_info["billingCity"],
            "billState": billing_info["billingState"],
            "billCountry": billing_info["billingCountryName"],
            "custMobIsdCode": billing_info["billingMobileCountryCode"],
            "invoiceAmt": invoice_amount,
            "netBankingBank": "default",
            "eNachBankNameDisplay": "Select Bank",
            "UPIQR": "",
            "creditCardEmiBanks": "null",
            "cardless-select": "null",
            "hdfc-emi-option": "on",
            "neftBank": "default",
            "eNachCustName": cust_name,
            "eNachCustEmail": cust_email,
            "eNachCustMob": mobile,
            "eNachBankName": "",
            "eNachCustAccType": "",
            "radio-c": "on",
            "enachAuthMode": "Netbanking",
        })

        if sham_booking:
            return tracking_id

        update_html = self.__script.ccavenue_update_transaction(update_form)
        update_forms = Utils.extract_forms_data(update_html)
        if len(update_forms) < 2:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, "CCAvenue 3DS设备采集表单为空")

        collect_url, collect_data = update_forms[0]
        redirect_3ds_url, redirect_3ds_data = update_forms[1]
        collect_html = self.__script.ccavenue_cardinal_collect(collect_url, collect_data)
        collect_forms = Utils.extract_forms_data(collect_html)
        if collect_forms:
            collect_redirect_url, collect_redirect_data = collect_forms[0]
            collect_redirect_data["State"] = "true"
            collect_redirect_data["Error"] = collect_redirect_data.get("Error", "")

            collect_inputs = Utils.extract_inputs_data(collect_html)
            render_url = collect_inputs.get("dfUrlFullValue")
            reference_id = collect_inputs.get("referenceId")
            org_unit_id = collect_inputs.get("orgUnitId")
            if render_url and reference_id and org_unit_id:
                if "origin=" not in render_url:
                    render_url = f"{render_url}&origin=CruiseAPI"
                render_response = self.__script.ccavenue_cardinal_render(url=render_url, data=f"nonce={uuid.uuid4()}")
                self.__script.ccavenue_cardinal_save_browser_data(
                    nonce=render_response.get("nonce") or str(uuid.uuid4()),
                    reference_id=render_response.get("referenceId") or reference_id,
                    org_unit_id=render_response.get("orgUnitId") or org_unit_id,
                    referrer=render_url,
                    origin="CruiseAPI",
                )
            self.__script.ccavenue_cardinal_collect_redirect(collect_redirect_url, collect_redirect_data)

        confirm_html = self.__script.ccavenue_submit_3ds_iframe(redirect_3ds_url, redirect_3ds_data)
        success_url, success_data = Utils.extract_form_data(confirm_html)
        if not success_url or not success_data:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, "CCAvenue成功回跳表单为空")
        payment_status_url = self.__script.ccavenue_success(success_url, success_data)
        return self.__finalize_payment_status(payment_status_url, ccavenue_headers=True)

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.HTTP_TIMEOUT, None),
                                               (ServiceStateEnum.CURL_EXCEPTION, None)],
                     retry_max_number=3)
    def payment_doku(self, vcc_info: PaymentInfoModel, cust_name: str, cust_email: str, contact_mobile: str,
                     response_order_data: ResponseOrderInfoModel, sham_booking= False):
        pay_res = self.__script.payment_doku(pay_info={
            "cartId": "",
            "searchId": "",
            "paymentMethod": 4,
            "paymentChannel": 21
        })
        print(pay_res)
        redirect_url = pay_res.get('dokuRedirectUrl')
        pnr = pay_res["orderId"][:6]
        response_order_data.pnr = pnr
        if sham_booking:
            return pnr
        if not redirect_url:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, pay_res.get('message') or "Doku支付跳转地址为空")

        if pay_res.get('orderId') and not response_order_data.pnr:
            response_order_data.pnr = pay_res['orderId'].split('_')[0]

        token_id = self.__script.doku_extract_token_id(redirect_url)
        self.__script.doku_open_checkout_page(token_id)
        checkout_data = self.__script.doku_get_checkout_data(token_id)

        invoice_number = checkout_data.get('invoice_number') or ''
        if invoice_number and not response_order_data.pnr:
            response_order_data.pnr = invoice_number.split('_')[0]

        request_id = checkout_data.get('request_id')
        client_id = checkout_data.get('client_id')
        if not request_id or not client_id:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "Doku checkout缺少request_id/client_id")

        self.__script.doku_choose_credit_card(token_id)
        public_key = self.__script.doku_generate_key(token_id, request_id, client_id).get('public_key')
        if not public_key:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "Doku公钥为空")

        expiry_digits = re.sub(r'\D', '', vcc_info.card_expiry_date)
        if len(expiry_digits) == 6:
            expiry_digits = expiry_digits[:2] + expiry_digits[-2:]
        if len(expiry_digits) != 4:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"Doku卡有效期格式异常[{vcc_info.card_expiry_date}]")

        card_payload = {
            "number": re.sub(r'[\s-]+', '', vcc_info.card_number),
            "expiry": expiry_digits,
            "cvv": vcc_info.card_cvv
        }
        if checkout_data.get('name_on_card'):
            card_payload['cardholder_name'] = (vcc_info.card_holder_name or cust_name).replace('/', ' ')

        encrypted_data = self.__script.doku_encrypt_card_payload(public_key, card_payload)
        pay_result = self.__script.doku_pay_credit_card(
            token_id=token_id,
            request_id=request_id,
            client_id=client_id,
            encrypted_data=encrypted_data
        )
        three_ds_url = pay_result.get('url')
        if not three_ds_url:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, pay_result.get('message') or "Doku支付下单失败")

        pay_query = parse_qs(urlparse(three_ds_url).query)
        authentication_id = pay_query.get('authenticationId', [None])[0]
        client_id = pay_query.get('clientId', [client_id])[0] or client_id
        if not authentication_id:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "Doku authenticationId为空")

        three_ds_data = self.__script.doku_get_three_d_secure_data(authentication_id, client_id)
        if three_ds_data.get('acs_url'):
            creq_html = self.__script.doku_submit_mpgs_creq(
                three_ds_data['acs_url'],
                three_ds_data.get('auth_jwt') or "e30="
            )
            action_url, form_data = Utils.extract_form_data(creq_html)
            if not action_url or not form_data:
                raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, "3DS回跳表单为空")
            callback_url = self.__script.doku_submit_redirect_back(action_url, form_data)
            self.__script.doku_callback_success(callback_url)
        elif three_ds_data.get('callback_url_success'):
            self.__script.doku_callback_success(three_ds_data['callback_url_success'])
        else:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED, three_ds_data.get('message') or "3DS验证失败")

        callback_url = checkout_data.get('callback_url_result') or checkout_data.get('callback_url')
        if not callback_url:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "Doku商户回跳地址为空")

        payment_status_url = self.__script.doku_return_batik(callback_url)
        return self.__finalize_payment_status(payment_status_url)

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.ROBOT_CHECK, None)], retry_max_number=15)
    def payment(self, vcc_info: PaymentInfoModel, order_data: ResponseOrderInfoModel, sham_booking=False):
        card_expire_arr = vcc_info.card_expiry_date.split('/')
        year = f'20{card_expire_arr[1]}'
        month = card_expire_arr[0]
        pay_data = {
            "cartId": "",
            "searchId": "",
            "customerIp": "",
            "paymentMethod": 3,
            "issuingBank": None,
            "cardHolderName": vcc_info.card_holder_name.replace('/', ' '),
            "cardNo": vcc_info.card_number,
            "cardCvv": vcc_info.card_cvv,
            "cardExpiry": year + month,  # "202808",
            "billAddress": StringUtil.generate_random_string(10),
            "billPostal": str(random.randint(100000, 999999)),
            "billCity": StringUtil.generate_random_string(10),
            "billCountry": random.choice(["HK", "US", "GB", "AU", "CA", "IN", "JP", "SG", "ZA", "NZ"]),
        }
        self.solve_gtoken()
        pay_res = self.__script.payment(pay_info=pay_data)
        if not pay_res:
            self.chaojiying.report_error(self.__script.pic_id)
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK)
        pay_url = pay_res['eghlUrl']
        pnr = pay_res['paymentID'][:6]
        order_data.pnr = pnr
        if sham_booking:
            return None
        pay_data2 = {
            'TransactionType': pay_res['transactionType'],
            'PymtMethod': pay_res['pymtMethod'],
            'ServiceID': pay_res['serviceID'],
            'PaymentID': pay_res['paymentID'],
            'OrderNumber': pay_res['orderNumber'],
            'PaymentDesc': pay_res['paymentDesc'],
            'MerchantName': pay_res['merchantName'],
            'MerchantReturnURL': pay_res['merchantReturnURL'],
            'MerchantApprovalURL': pay_res['merchantApprovalURL'],
            'MerchantUnApprovalURL': pay_res['merchantUnApprovalURL'],
            'MerchantCallbackURL': pay_res['merchantCallbackURL'],
            'Amount': pay_res['amount'],
            'CurrencyCode': pay_res['currencyCode'],
            'CustIP': pay_res['custIP'],
            'CustName': pay_res['custName'],
            'CustEmail': pay_res['custEmail'],
            'CustPhone': pay_res['custPhone'],
            'HashValue': pay_res['hashValue'],
            'LanguageCode': pay_res['languageCode'],
            'Param6': pay_res['param6'],
            'CardHolder': pay_res['cardHolder'],
            'CardNo': pay_res['cardNo'],
            'CardCvv2': pay_res['cardCvv2'],
            'CardExp': pay_res['cardExp'],
            'BillAddr': pay_res['billAddr'],
            'BillPostal': pay_res['billPostal'],
            'BillCity': pay_res['billCity'],
            'BillRegion': pay_res['billRegion'],
            'BillCountry': pay_res['billCountry']
        }
        pnr = pay_res['paymentID'].split('_')[0]
        order_data.pnr = pnr
        sp = Securepay(self.__script.tls, user_agent=Config.USER_AGENT, dest_url='booking.batikair.com.my')
        pay_res2 = sp.payment_entrance(url=pay_url, form_data=pay_data2)

        if not pay_res2:
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)
        pay_url2 = pay_res2[0]
        pay_data2 = pay_res2[1]
        if 'success' not in pay_url2:
            if 'token=' in pay_url2:
                itinerary_id = self.__finalize_payment_status(pay_url2, allow_confirmation_token=True)
                return itinerary_id, pnr
            self.__script.pay_return(pay_url2, pay_data2)
            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)

        pnr = pay_data2['OrderNumber'].split('_')[0]
        order_data.pnr = pnr
        result = self.pay_finish(pay_url2, pay_data2)
        itinerary_id, pnr = result
        return itinerary_id, pnr

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.HTTP_TIMEOUT, None)])
    def pay_finish(self, pay_url2, pay_data2):
        time.sleep(2)
        result = self.__script.pay_finish(pay_url2, pay_data2)
        return result

    def get_pnr_info_by_id(self, itinerary_id):

        i = 10
        while i > 0:
            res = self.__script.get_book_info(itinerary_id)
            if res:
                if res.get('isTicketed'):
                    return res
            time.sleep(5)
            i -= 1
        raise ServiceError(ServiceStateEnum.PAYMENT_EXCEPTION, "获取票号失败，人工确认是否扣款成功")

    def init_cloudflare(self):
        self.__script.init_cloudflare()

    @retry_decorator(retry_service_error_list=[
        (ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, None),
        (ServiceStateEnum.API_RESPONSE_FAILED, None)
    ])
    def get_order_info(self, pnr: str, last_name: str, first_name: str):

        # 增加ez google v2验证
        token = self.__script.initialize_ez_recaptcha(
            referer='https://mmb.batikair.com.my/OD/OnlineAddonBooking.aspx?t=2C9')
        # 请求格式改为viewstate表单格式
        next_url, view_status_data = self.__script.get_viewstate_data()
        pnr_info = self.__script.get_pnr(pnr=pnr, last_name=last_name, first=first_name,
                                         token=token, view_status_data=view_status_data, next_url=next_url)
        order_detail = OrderDetailParser().parse_order_detail(pnr_info)

        return order_detail

    def get_pnr_info(self, pnr, last_name, first_name):
        json_data = {
            'pnr': pnr,
            'firstName': first_name,
            'lastName': last_name,
        }
        response = self.__script.validate_pnr(json_data)
        order_detail = OrderDetailParserV2.parse_order_detail(response)
        return order_detail
