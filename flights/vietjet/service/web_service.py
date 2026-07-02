import base64
import copy
import decimal
import hashlib
import json
import random
import time
import uuid
from typing import Optional, List
from urllib.parse import unquote, urlparse

from common.decorators.retry_decorator import retry_decorator
from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceStateEnum, ServiceError
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import log_util
from common.utils.string_util import StringUtil
from ..config import Config
from ..flight_common.account_manager import AccountManager
from ..flight_common.utils import VietjetSearchUtils
from ..flight_common.web_flight_parse import FlightParser
from ..script.web_script import WebScript


class WebService:

    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__t: dict = {}
        self.__session_id: str = ''
        self.__web_script = WebScript(proxy_info=proxy_info)
        self.manager = AccountManager()
        self.__log = log_util.LogUtil('vietjetWebService')

    def initialize_session(self):
        self.__web_script.initialize_session()

    def request_id_get(self):
        now = int(time.time() * 1000)
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        rnd = "".join(random.choice(chars) for _ in range(12))
        request_id = f"{rnd}-{now}"
        return request_id

    def get_seesion_cached(self, departure_place, arrival):
        return self.__web_script.get_seesion_cached(departure_place, arrival)

    def get_seesion(self, departure_place, arrival):
        request_id = self.request_id_get()
        return self.__web_script.get_seesion(request_id, departure_place, arrival)

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               infant_count: int,
               currency_code: str,
               ret_date: Optional[str] = None, is_hold: bool = False):
        self.__t = VietjetSearchUtils.get_t()
        request_id = self.request_id_get()
        oneway = 1
        return_date = None
        if ret_date:
            return_date = ret_date
            oneway = 0
        o_data = {
            "currency": currency_code,
            "departureDate": dep_date,
            "daysBeforeDeparture": 0,
            "daysAfterDeparture": 0,
            "departurePlace": dep_airport,
            "arrival": arr_airport,
            "oneway": oneway,
            "adultCount": adt_number,
            "childCount": chd_number,
            "promoCode": '',
            "infantCount": 0,
            "returnDate": return_date,
            "daysBeforeReturn": 0,
            "daysAfterReturn": 0,
            "requestId": request_id,
            "sessionId": self.__web_script.x_session_id,
            "user-agent-ls-data": self.__t["user-agent-ls-data"],
            "x-power-web-s-d": self.__t["x-power-web-s-d"],
        }
        self.airline_pors = f"{o_data['departurePlace']}-{o_data['arrival']}"

        add_signature = VietjetSearchUtils.add_signature(o_data)
        data = VietjetSearchUtils.encrypt(add_signature)
        city_code = dep_airport + '-' + arr_airport
        if not is_hold:
            special_baggage_data = self.__web_script.journey_config(request_id=request_id, city_code=city_code)
        flight_data = self.__web_script.search_flight(data)
        new_session_id = flight_data['sessionId']
        if (self.__session_id
                and self.__session_has_client_machine_id(self.__session_id)
                and not self.__session_has_client_machine_id(new_session_id)):
            self.__log.info("保留已有带机器绑定的sessionId")
        else:
            self.__session_id = new_session_id
        if is_hold:
            baggage_data = {}
        else:
            baggage_data = self.__web_script.baggage_search(request_id=request_id)
            baggage_data['special_baggage_data'] = special_baggage_data
        journey_info_model = FlightParser.journey_info_parser(flight_data=flight_data,
                                                              baggage_data=baggage_data)
        if chd_number == 0:
            for i in journey_info_model:
                for z in i.bundles:
                    z.price_info.child_tax_price = z.price_info.adult_tax_price
                    z.price_info.child_ticket_price = z.price_info.adult_ticket_price

        return journey_info_model

    @staticmethod
    def __session_has_client_machine_id(session_id):
        try:
            payload = session_id.split('.')[1]
            payload += '=' * (-len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload))
            return bool(data.get('XClientMachineId'))
        except Exception:
            return False

    def search_min(self,
                   dep_airport: str,
                   arr_airport: str,
                   dep_date: str,
                   adt_number: int,
                   chd_number: int,
                   infant_count: int,
                   currency_code: str,
                   ret_date: Optional[str] = None, is_hold: bool = False):
        o_data = {
            "cityPair": f"{dep_airport}-{arr_airport}",
            "departure": dep_date,
            "returnDate": '',
            "adultCount": str(adt_number),
            "childCount": "0",
            "infantCount": "0",
            "promoCode": ""
        }

        flight_data = self.__web_script.search_flight_min(o_data)
        from flights.vietjet.flight_common.app_flight_parse import AppFlightParser
        journey_info_model = AppFlightParser.journey_info_parser(flight_data=flight_data)
        if chd_number == 0:
            for i in journey_info_model:
                for z in i.bundles:
                    z.price_info.child_tax_price = z.price_info.adult_tax_price
                    z.price_info.child_ticket_price = z.price_info.adult_ticket_price

        return journey_info_model

    def passengers_add(self, passengers: List[PassengerInfoModel], key, contact_info: ContactInfoModel):
        passenger_list = []
        phone = '+' + contact_info.phone_code + contact_info.phone_number
        email = contact_info.email_address
        for index, value in enumerate(passengers):
            if value.type == PassengerTypeEnum.ADT:
                title = 'Mr' if value.gender == GenderEnum.M else 'Mrs'
                passenger_type = 'adult'
            else:
                title = 'Master' if value.gender == GenderEnum.M else 'Miss'
                passenger_type = 'child'
            country = Config.NATION_DICT.get(value.document_info.nationality)
            last_name = value.last_name
            first_name = value.first_name
            birthday = value.birthday
            card_number = value.document_info.number
            p_dict = {
                "passengerMobilePhone": phone,
                "isPrimaryPassenger": True if index == 0 else False,
                "passengerNationality": "",
                "passengerType": passenger_type,
                "passengerTitle": title,
                "passengerCountry": country,
                "passengerFamilyName": last_name,
                "passengerMiddleGivenName": first_name,
                "passengerBirthday": birthday,
                "passengerEmail": email,
                "passengerPassportNationality": "",
                "passengerPhone": "",
                "passengerAddress": "",
                "passengerProvince": "",
                "passengerPassportNumber": card_number,
                "passengerPassportExpiredDate": None,
                "seats": [],
                "ancillary": [],
                "infants": [],
                "skyclubCode": ""
            }
            if passenger_type == 'child':
                p_dict['passengerGender'] = 'Male' if value.gender.value == 'M' else 'Female'
            passenger_list.append(p_dict)
        request_id = self.request_id_get()
        booking_key = key.split('^')
        data = {
            "passengers": passenger_list,
            "bookingKey": booking_key[0],
            "requestId": request_id,
            "bookingKeyReturn": "",
            "sessionId": self.__session_id,
            "user-agent-ls-data": self.__t["user-agent-ls-data"],
            "x-power-web-s-d": self.__t["x-power-web-s-d"],
        }
        if len(booking_key) > 1:
            data['bookingKeyReturn'] = booking_key[-1]
        print(data)
        add_signature = VietjetSearchUtils.add_signature(data)
        request_data = VietjetSearchUtils.encrypt(add_signature)
        self.__web_script.insurances(request_data)
        return data

    def seat(self, add_passengers_info):
        request_data = {
            "bookingKey": add_passengers_info['bookingKey'],
            "bookingKeyReturn": add_passengers_info['bookingKeyReturn'],
            "requestId": self.request_id_get(),
            "sessionId": add_passengers_info['sessionId'],
            "x-power-web-s-d": add_passengers_info['x-power-web-s-d'],
            "user-agent-ls-data": add_passengers_info['user-agent-ls-data']
        }
        add_signature = VietjetSearchUtils.add_signature(request_data)
        request_data = VietjetSearchUtils.encrypt(add_signature)
        response = self.__web_script.seat_selection_options(request_data)
        return response

    def methods_by_booking(self, data, currency, is_paylater: bool):
        request_data = {
            "languageId": Config.LANGUAHE_ID,
            "bookingKey": data['bookingKey'],
            "bookingKeyReturn": data['bookingKeyReturn'],
            "currency": currency,
            "flightCode": 'VJ',  # "VJ",
            "requestId": self.request_id_get(),
            "sessionId": data['sessionId']
        }
        add_signature = VietjetSearchUtils.add_signature(request_data)
        request_data = VietjetSearchUtils.encrypt(add_signature)
        methods = self.__web_script.methods_by_booking(request_data)
        paylater = False
        for i in methods["payments"]:
            if i['threadPayment'] == 'Paylater':
                paylater = True
        if is_paylater:
            if not paylater:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "No pay later method")

    def verify(self, data, flight_number):
        """

        Args:
            data:
            flight_number:
        Returns:

        """
        request_data = {
            "bookingKey": data['bookingKey'],
            "bookingKeyReturn": data['bookingKeyReturn'],
            "languageId": Config.LANGUAHE_ID,
            "isChangeJourney": False,
            "requestId": self.request_id_get(),
            "sessionId": data['sessionId'],
            "x-power-web-s-d": data['x-power-web-s-d'],
            "user-agent-ls-data": data['user-agent-ls-data']
        }
        add_signature = VietjetSearchUtils.add_signature(request_data)
        request_data = VietjetSearchUtils.encrypt(add_signature)
        ancillary_info = self.__web_script.ancillary_options(request_data)
        bag_list = []  # TODO:行李数据后面处理
        # for i in ancillary_info["ancillary"]['Baggage']:
        #     total_weight = i['ancillaryItem']['name']
        #     if "Oversize" in total_weight:
        #         continue
        #     else:
        #         total_weight = total_weight.replace("Bag ", "").replace("kgs", "").replace("kgs", "").replace(
        #             "kg only 1pc", "").replace(" (VZ)", "")
        #     bag_list.append(BaggageInfoModel.model_validate({
        #         'baggageType': BaggageTypeEnum.HAULING_BAGGAGE,
        #         'pieces': 1,
        #         'totalWeight': total_weight,
        #         'flightNumber': flight_number,
        #         'sellKey': i["purchaseKey"],
        #         'amount': i["ancillaryCharges"][0]["currencyAmounts"][0]["totalAmount"],
        #         'code': i["requirementLocation"]["cityPair"]["identifier"],
        #         'currency': i["ancillaryCharges"][0]["currencyAmounts"][0]["currency"]["code"]
        #     }))
        return [bag_list]

    @staticmethod
    def add_ancillary(passenger_infos: List[PassengerInfoModel], add_passengers_info: dict, flight_number):
        """

        Args:
            flight_number:
            passenger_infos:乘机人模型
            add_passengers_info:

        Returns:

        """
        add_passengers = copy.deepcopy(add_passengers_info['passengers'])
        for add_passenger_info in add_passengers:
            ancillary = []  # TODO:添加辅营待处理
            # for passenger_info in passenger_infos:
            #     if passenger_info.last_name == add_passenger_info[
            #         'passengerFamilyName'] and passenger_info.first_name == add_passenger_info[
            #         'passengerMiddleGivenName']:
            #         baggage_infos = passenger_info.get_ancillaries(AncillariesTypeEnum.LUGGAGE)
            #         for baggage_info in baggage_infos:
            #             segment_type = flight_dict[baggage_info.code][1]
            #             if segment_type == SegmentTypeEnum.TRIP:
            #                 is_departure = True
            #                 is_return = False
            #             else:
            #                 is_departure = False
            #                 is_return = True
            #             ancillary.append({
            #                 "purchaseKey": baggage_info.sell_key,
            #                 "isDeparture": is_departure,
            #                 "isReturn": is_return
            #             }
            #             )
            add_passenger_info['ancillary'] = ancillary
        return add_passengers

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.API_RESPONSE_EXCEPTION, None),
                                               (ServiceStateEnum.API_RESPONSE_FAILED, None)],
                     retry_max_number=10)
    def recaptcha_feeling(self):
        referer = "https://www.vietjetair.com"

        # 定义验证码解决方案的优先级列表
        # 如果将来有新方案，直接追加到这里即可
        if self.airline_pors in ['SGN-CAN', 'CAN-SGN']:
            strategies = [
                # self.__web_script.get_google_token_no,  # 优先级 2: Google Token (降级)
                self.__web_script.get_google_token_danli,  # 优先级 1: EZ
            ]
        else:
            strategies = [
                # self.__web_script.get_google_token_no,  # 优先级 2: Google Token (降级)
                self.__web_script.get_google_token_danli,  # 优先级 1: EZ
            ]

        last_exception = None

        for strategy in strategies:
            try:
                # 尝试当前策略，成功则直接返回 token
                return strategy(referer=referer)
            except Exception as e:
                # 捕获异常，记录并在循环结束后抛出
                last_exception = e
                # 建议：在这里加一行日志，方便调试是哪个方案挂了
                continue

                # 循环结束仍未返回，说明所有策略都失败了
        # 抛出最后一次捕获的异常，触发装饰器的重试机制
        if last_exception:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION, last_exception)
        else:
            # 防御性代码：防止 strategies 列表为空的情况
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED, "No captcha strategies defined.")

    def insurance_del(self, data, journey_segments: list[FlightSegmentModel], adult_count, child_count,
                      currency, product_tag,
                      needpay: bool = None, flag=None, is_gpay: bool = False):
        request_id = self.request_id_get()
        data['requestId'] = request_id
        del data['_signature']
        data['passenger'] = data['passengers']
        del data['passengers']
        if data['bookingKeyReturn'] == "":
            del data['bookingKeyReturn']
        data['payment'] = {
            "identifier": "",
            "body": {},
            "bank": "",
            "threadPayment": None
        }
        if needpay is not None:
            recaptcha_token = ''
            if needpay:
                # 走谷歌验证
                data['payment'] = {
                    "identifier": "VJPMC",
                    "body": {},
                    "bank": "MASTER",
                    "threadPayment": "GPAY"
                }
                action = str(uuid.uuid4()).replace('-', '')
            else:
                data['payment'] = {
                    "identifier": "VJVNQR",
                    "body": {},
                    "bank": "",
                    "threadPayment": "PaymentController"
                }
                action = str(uuid.uuid4()).replace('-', '')
            # data['captcha-data'] = {
            #     'action': f'quotation_{action}',
            #     'token': recaptcha_token,
            # }
        duration_depature = journey_segments[0].ext['flight_time']
        departure_ticket_type = product_tag
        dep_airport = journey_segments[0].dep_airport
        data['oneway'] = 1
        data['currency'] = currency
        data['isInsurance'] = False
        data['isPrefetch'] = True
        data['returnPlace'] = dep_airport
        data['departurePlace'] = dep_airport
        data['adultCount'] = adult_count
        data['childCount'] = child_count
        data['infantCount'] = 0
        data['durationDepature'] = duration_depature  # 去程飞行时间
        data['durationReturn'] = 0  # 回程飞行时间
        data['insurancePolicies'] = []
        data['departureTicketType'] = departure_ticket_type  # 去程套餐
        data['returnTicketType'] = ''  # 回程套餐
        data['isEsim'] = False
        data['isWhatsapp'] = True
        data['isGpayInternational'] = True  # 是否国际线
        if flag:
            del data['isGpayInternational']
            data['isPrefetch'] = False
        data['isPaylater'] = True  # 是否稍后支付
        print(data)
        add_signature = VietjetSearchUtils.add_signature(data)
        request_data = VietjetSearchUtils.encrypt(add_signature)
        response = self.__web_script.quotations_summary(request_data)
        return response, add_signature

    def del_login(self):
        self.manager.delete_authorization(self.account)
        self.login_account()

    @staticmethod
    def _random_billing_address():
        city, province_code, postal_prefix = random.choice([
            ("NEW YORK", "NY", "100"),
            ("LOS ANGELES", "CA", "900"),
            ("CHICAGO", "IL", "606"),
            ("HOUSTON", "TX", "770"),
            ("MIAMI", "FL", "331"),
            ("SEATTLE", "WA", "981"),
            ("BOSTON", "MA", "021"),
            ("DENVER", "CO", "802"),
            ("PHOENIX", "AZ", "850"),
            ("ATLANTA", "GA", "303"),
            ("DALLAS", "TX", "752"),
            ("AUSTIN", "TX", "787"),
            ("PORTLAND", "OR", "972"),
            ("LAS VEGAS", "NV", "891"),
            ("SAN DIEGO", "CA", "921"),
            ("ORLANDO", "FL", "328"),
            ("CHARLOTTE", "NC", "282"),
            ("NASHVILLE", "TN", "372"),
            ("COLUMBUS", "OH", "432"),
            ("SALT LAKE CITY", "UT", "841"),
        ])
        street_name = random.choice([
            "OAK", "MAPLE", "PINE", "CEDAR", "ELM", "WASHINGTON", "LINCOLN", "MADISON",
            "JEFFERSON", "LAKE", "HIGHLAND", "RIVER", "PARK", "MARKET", "MAIN", "CENTER",
            "BROADWAY", "SUNSET", "HILLCREST", "MEADOW"
        ])
        street_type = random.choice(["ST", "AVE", "RD", "BLVD", "DR", "LN", "CT", "WAY"])
        unit = random.choice(["", f" APT {random.randint(1, 999)}", f" STE {random.randint(100, 999)}"])
        return {
            "address": f"{random.randint(1, 9999)} {street_name} {street_type}{unit}",
            "city": city,
            "provinceCode": province_code,
            "postalCode": f"{postal_prefix}{random.randint(0, 99):02d}",
        }

    # @retry_decorator(retry_service_error_list=[(ServiceStateEnum.BUSINESS_ERROR, del_login)],
    #                  retry_max_number=3)
    def pay_later(self, add_signature_data, need_pay, payment_info=None, contact_info=None, is_gpay: bool = False):
        data = copy.deepcopy(add_signature_data)
        del data['_signature']
        del data['isEsim']
        del data['isPaylater']
        del data['isPrefetch']
        data.pop('isGpayInternational', None)
        data.pop('isWhatsapp', None)
        captcha_data = data.get('captcha-data') or {}
        if not captcha_data.get('token'):
            data.pop('captcha-data', None)
        session_id = data.get('sessionId')
        request_id = self.request_id_get()
        data['requestId'] = request_id
        if need_pay is False:
            # data['payment'] = {
            #     "body": {},
            #     "identifier": "PL6",
            #     "threadPayment": "Paylater"
            # } if not is_gpay else {
            #     "body": {},
            #     "identifier": "VJPGGLE",
            #     "threadPayment": "GPAY"
            # }
            data['payment'] = {
                "identifier": "VJVNQR",
                "threadPayment": "PaymentController",
                "body": {}
            }
        else:
            card_number = payment_info.card_number
            card_expire = payment_info.card_expire
            security_code = payment_info.security_code
            email = contact_info.email
            mobile = contact_info.mobile
            name = payment_info.card_holder.replace('/', '')
            billing_address = self._random_billing_address()
            data['payment'] = {
                "identifier": "VJPMC",
                "threadPayment": "GPAY",
                "body": {
                    "cardNumber": card_number,
                    "cardHolder": name,
                    "expireDate": card_expire,
                    "cvvCode": security_code,
                    "address": billing_address["address"],
                    "city": billing_address["city"],
                    "countryCode": 'USA',
                    "provinceCode": billing_address["provinceCode"],
                    "postalCode": billing_address["postalCode"],
                    "phoneNumber": mobile,
                    "email": email
                }
            }
        data['customerToken'] = ""
        add_signature = VietjetSearchUtils.add_reservations_signature(data)
        request_data = VietjetSearchUtils.encrypt(add_signature)
        response = self.__web_script.reservations(request_data,
                                                  authorization=self.authorization if not is_gpay else None,
                                                  request_id=request_id,
                                                  session_id=session_id)
        return response, add_signature

    @staticmethod
    def _galaxy_request_datetime():
        return time.strftime("%Y%m%d%H%M%S", time.localtime())

    @staticmethod
    def _parse_galaxy_checkout_endpoint(endpoint):
        parsed = urlparse(endpoint)
        parts = [part for part in parsed.path.split("/") if part]
        if not parsed.scheme or not parsed.netloc or len(parts) < 5 or parts[0] != "checkout":
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "GalaxyPay checkout endpoint invalid")

        offset = 2 if parts[1] == "hub" else 1
        if len(parts) <= offset + 3:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "GalaxyPay checkout endpoint invalid")
        try:
            date_time_expire = int(parts[offset + 1])
        except ValueError:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "GalaxyPay checkout endpoint invalid")

        return {
            "base_url": f"{parsed.scheme}://{parsed.netloc}",
            "transaction_id": parts[offset],
            "date_time_expire": date_time_expire,
            "signature": parts[offset + 2],
            "language": parts[offset + 3],
        }

    def _build_galaxy_payment_data(self, checkout_info, payment_method=None, source_of_fund=None):
        request_data = {
            "transactionID": checkout_info["transaction_id"],
            "dateTimeExpire": checkout_info["date_time_expire"],
            "signature": checkout_info["signature"],
        }
        if payment_method:
            request_data["paymentMethod"] = payment_method
        if source_of_fund:
            request_data["sourceOfFund"] = source_of_fund

        return {
            "requestID": uuid.uuid4().hex,
            "requestDateTime": self._galaxy_request_datetime(),
            "requestData": request_data,
            "language": "en",
            "fingerprint": {},
        }

    def create_payment(self, reservation_response=None):
        reservation = (reservation_response or {}).get("reservation") or {}
        result_checkout = reservation.get("resultCheckout") or {}
        checkout_endpoint = result_checkout.get("endpoint")
        if not checkout_endpoint:
            return None

        checkout_info = self._parse_galaxy_checkout_endpoint(checkout_endpoint)
        self.__web_script.galaxy_checkout(checkout_endpoint)
        antiforgery_data = self.__web_script.galaxy_antiforgery_token(checkout_endpoint)
        token_data = antiforgery_data.get("responseData") or {}
        request_token = token_data.get("requestToken")
        cookie_token = token_data.get("cookieToken")
        if not request_token or not cookie_token:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)

        query_data = self._build_galaxy_payment_data(checkout_info)
        query_response = self.__web_script.galaxy_query_checkout(
            data=query_data,
            referer=checkout_endpoint,
            request_token=request_token,
            cookie_token=cookie_token)
        if query_response.get("responseCode") != "200":
            raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, query_response.get("responseMessage"))

        payment_method = (
                ((query_response.get("responseData") or {}).get("payment") or {}).get("paymentMethod")
                or "HUB"
        )
        create_data = self._build_galaxy_payment_data(
            checkout_info,
            payment_method=payment_method,
            source_of_fund="NONE")
        hub_referer = (
            f'{checkout_info["base_url"]}/checkout/hub/{checkout_info["transaction_id"]}/'
            f'{checkout_info["date_time_expire"]}/{checkout_info["signature"]}/{checkout_info["language"]}'
        )
        create_response = self.__web_script.galaxy_create_payment(
            data=create_data,
            referer=hub_referer,
            request_token=request_token,
            cookie_token=cookie_token)
        if create_response.get("responseCode") != "200":
            raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, create_response.get("responseMessage"))
        return create_response

    @staticmethod
    def _passenger_counts(passenger_infos: List[PassengerInfoModel]):
        adult_count = sum(1 for passenger in passenger_infos if passenger.type == PassengerTypeEnum.ADT)
        child_count = sum(1 for passenger in passenger_infos if passenger.type == PassengerTypeEnum.CHD)
        return adult_count, child_count

    @staticmethod
    def _fill_response_order(response_order_data: ResponseOrderInfoModel,
                             passenger_infos: List[PassengerInfoModel],
                             journey: FlightJourneyModel,
                             use_bundle: FlightBundleModel,
                             total_amount):
        response_order_data.order_number = ""
        response_order_data.passengers = passenger_infos
        response_order_data.currency_code = use_bundle.price_info.currency
        response_order_data.journeys = [journey]
        response_order_data.journeys[0].bundles = [use_bundle]
        response_order_data.total_amount = total_amount

    def _prepare_booking_quote(self,
                               journey: FlightJourneyModel,
                               passenger_infos: List[PassengerInfoModel],
                               use_bundle: FlightBundleModel,
                               response_order_data: ResponseOrderInfoModel,
                               contact_info: ContactInfoModel,
                               need_pay: bool = None,
                               is_paylater: bool = True,
                               is_gpay: bool = False):
        add_passengers_info = self.passengers_add(passenger_infos, use_bundle.fare_key, contact_info)
        self.seat(add_passengers_info)
        self.verify(add_passengers_info, flight_number=journey.segments[0].flight_number)
        self.methods_by_booking(add_passengers_info, use_bundle.price_info.currency, is_paylater=is_paylater)

        passengers_web_data = self.add_ancillary(
            passenger_infos,
            add_passengers_info,
            flight_number=journey.segments[0].flight_number)
        add_passengers_info['passengers'] = passengers_web_data

        adult_count, child_count = self._passenger_counts(passenger_infos)
        quote_response, add_signature = self.insurance_del(
            data=add_passengers_info,
            journey_segments=journey.segments,
            adult_count=adult_count,
            child_count=child_count,
            currency=use_bundle.price_info.currency,
            product_tag=use_bundle.product_tag,
            needpay=need_pay,
            flag=True,
            is_gpay=is_gpay)

        total_amount = decimal.Decimal(quote_response["reservationFee"]['totalAmount'])
        self._fill_response_order(response_order_data, passenger_infos, journey, use_bundle, total_amount)
        return quote_response, add_signature

    def booking(self, journey: FlightJourneyModel, passenger_infos: List[PassengerInfoModel],
                use_bundle: FlightBundleModel, response_order_data: ResponseOrderInfoModel,
                contact_info: ContactInfoModel, need_pay: bool = None, vcc_info=None, ):
        _, add_signature = self._prepare_booking_quote(
            journey=journey,
            passenger_infos=passenger_infos,
            use_bundle=use_bundle,
            response_order_data=response_order_data,
            contact_info=contact_info,
            need_pay=need_pay,
            is_paylater=True,
            is_gpay=False)
        self.login_account()
        later_response, add_signature = self.pay_later(add_signature_data=add_signature, need_pay=need_pay,
                                                       payment_info=vcc_info, contact_info=contact_info)
        locator = (later_response.get("reservation") or {}).get("locator")
        if locator:
            self.manager.save_pnr(self.account, locator)
        return later_response, add_signature

    def booking_gls(self, journey: FlightJourneyModel, passenger_infos: List[PassengerInfoModel],
                    use_bundle: FlightBundleModel, response_order_data: ResponseOrderInfoModel,
                    contact_info: ContactInfoModel, need_pay: bool = None, vcc_info=None, ):
        quote_response, add_signature = self._prepare_booking_quote(
            journey=journey,
            passenger_infos=passenger_infos,
            use_bundle=use_bundle,
            response_order_data=response_order_data,
            contact_info=contact_info,
            need_pay=need_pay,
            is_paylater=False,
            is_gpay=True)
        later_response, add_signature = self.pay_later(add_signature_data=add_signature, need_pay=need_pay,
                                                       payment_info=vcc_info, contact_info=contact_info, is_gpay=True)
        create_payment_response = self.create_payment(later_response)
        if create_payment_response:
            quote_response["createPayment"] = create_payment_response
            payment_endpoint = (create_payment_response.get("responseData") or {}).get("endpoint")
            if payment_endpoint:
                quote_response["paymentEndpoint"] = payment_endpoint

        return later_response, add_signature

    def login_account(self):
        result = self.manager.get_one_account()
        self.__log.info(f"获取账号成功：{result}")
        self.account = result['account']
        self.authorization = result.get('authorization', None)
        self.password = result['password']
        if not self.authorization:
            self.authorization = self.login()
            self.manager.save_authorization(self.account, self.authorization)
            self.__log.info(f"保存账号成功：{self.account} {self.authorization}")

    def login(self):
        device_id = f"sk{StringUtil.generate_random_string(24)}"
        client_id = 'c83cfb2b-443f-4982-90de-2a895928c5f9'
        code_verifier = StringUtil.generate_random_string(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).rstrip(b'=').decode()
        state = str(uuid.uuid4())
        nonce = str(uuid.uuid4())
        response = self.__web_script.auth(client_id, state, nonce, code_challenge)
        url = StringUtil.extract_between(response, "resetUrl = '", "'")
        login_actions_response = self.__web_script.login_actions(url, self.account, device_id)
        url = StringUtil.extract_between(login_actions_response, "resetUrl = '", "'")
        login_actions2_url = self.__web_script.login_actions2(url, self.password, device_id)
        code = unquote(login_actions2_url.split("code=")[1].split("&")[0])
        connect_token_data = self.__web_script.connect_token(code, client_id, code_verifier)
        access_token = connect_token_data['access_token']
        refresh_token = connect_token_data['refresh_token']
        login_token = self.__web_script.get_login_token(access_token, refresh_token)
        return login_token["data"]["token"]
