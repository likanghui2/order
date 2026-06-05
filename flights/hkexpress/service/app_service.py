import base64
import copy
import decimal
import hashlib
import time
import uuid
from datetime import datetime, timezone, timedelta

import jwt
from typing import Optional, List

from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.order.payment_info_model import PaymentInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import log_util
from common.utils.cardinalcommerce_util import CardinalcommerceUtil
from common.utils.flight_util import FlightUtil
from common.utils.rsa_ciphering import RsaCiphering
from flights.hkexpress.flight_common.utils import Utils
from flights.hkexpress.flight_common.flight_info_parser import FlightInfoParser
from flights.hkexpress.flight_common.parameter_construct import ParameterConstruct
from flights.hkexpress.script.app_script import AppScript

LOG = log_util.LogUtil('hkexpressAppService')


class AppService:

    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__script = AppScript(proxy_info_data)

    def get_ip(self):
        return self.__script.get_ip()

    def init_token(self):
        self.__script.init_token()

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               infant_count: int,
               currency_code: str,
               ret_date: Optional[str] = None):

        response = self.__script.search(
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_date=dep_date,
            adt_number=adt_number,
            chd_number=chd_number,
            infant_count=infant_count,
            currency_code=currency_code,
            ret_date=ret_date
        )

        response_dict = response.to_dict()


        journey_list = FlightInfoParser.journey_info_parser(response_dict['trip'], 0)

        return journey_list

    def ssr_baggage(self, journey):
        ssr_booking_response = self.__script.ssr_booking({
            journey.journey_key: [[x.segment_key, x.ext['legs'][0]['leg_key']] for x in journey.segments]
        },
            currency_code=journey.bundles[0].price_info.currency
        )

        passenger_baggage_data = {}

        for i in ssr_booking_response.to_dict()['journeys'][0]['ssrs']:
            if i['type'] != 'BAGGAGE':
                break

            for k in i['product']:
                ssr_code = k['ssr_code']
                for j in k['ssr_by_passengers']:
                    if j['passenger_key'] not in passenger_baggage_data:
                        passenger_baggage_data[j['passenger_key']] = []
                    passenger_baggage_data[j['passenger_key']].append(FlightBaggageModel(
                        type=SsrTypeEnum.HAULING_BAGGAGE,
                        code=ssr_code,
                        price=j['price'],
                        number=1,
                        weight=int(ssr_code[2:]),
                        limit=k['limit_per_passenger'],
                        key=j['ssr_key'],
                    ))

        return passenger_baggage_data

    def trip(self, journey, passengers, bundle):

        p = copy.deepcopy(passengers)

        for i in p:
            i.key = None

        trip_response = self.__script.trip(
            fare_key_list=[[journey.journey_key, bundle.fare_key]],
            adt_number=sum([1 for x in passengers if x.type == PassengerTypeEnum.ADT]),
            chd_number=sum([1 for x in passengers if x.type == PassengerTypeEnum.CHD]),
            currency_code=journey.bundles[0].price_info.currency,
        )

        for i in trip_response.to_dict()['passenger_info']:
            j = next((j for j in p if j.type.value == i['type'] and not j.key), None)
            j.key = i['passenger_key']

        for i in p:
            if i.key is None or i.key == '':
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f'{i.get_passenger_name()},key缺失')

        return p

    def compute_baggage(self,
                        passengers: List[PassengerInfoModel],
                        passenger_baggage_data, bundle_list):

        # 得出行李所需价格，重量
        baggage_data_array = [(x.weight, x.price, x.limit) for x in
                              passenger_baggage_data[list(passenger_baggage_data.keys())[0]]]
        max_limit = min([x[2] for x in baggage_data_array])
        baggage_data_array = [(x[0], x[1]) for x in baggage_data_array]

        combination_data = []
        for bundle_info in bundle_list:
            bundle_baggage_weight = sum(
                [x.weight * x.number for x in bundle_info.ssr_info.baggage if x.type == SsrTypeEnum.HAULING_BAGGAGE])
            total_price = 0
            temp_passengers = copy.deepcopy(passengers)

            for i in temp_passengers:
                s = FlightUtil.find_min_luggage_cost(baggage_data_array,
                                                     i.ext['buyBaggageWeight'] - bundle_baggage_weight,
                                                     max_limit - (1 if bundle_baggage_weight > 0 else 0), True)
                if i.type == PassengerTypeEnum.ADT:
                    total_price += s[
                                       0] + bundle_info.price_info.adult_ticket_price + bundle_info.price_info.adult_tax_price
                elif i.type == PassengerTypeEnum.CHD:
                    total_price += s[0] + bundle_info.price_info.chd_ticket_price + bundle_info.price_info.chd_tax_price
                i.bag_combination = list(s[1])

            combination_data.append((bundle_info.code, total_price, temp_passengers))

        result_combination_passenger_data = min(combination_data, key=lambda x: x[1])
        return result_combination_passenger_data

    def validation(self,
                   passengers: List[PassengerInfoModel],
                   bundle_info: FlightBundleModel,
                   journey_info: FlightJourneyModel,
                   contact_info: ContactInfoModel):

        passenger_data = ParameterConstruct.passenger_construct(passengers)
        journey_data = ParameterConstruct.journey_construct([journey_info], bundle_info, passengers)
        contact_data = ParameterConstruct.contact_construct(contact_info)
        ssr_data = ParameterConstruct.ssr_construct(passengers)
        response = self.__script.validation(journey_data, passenger_data, contact_data, ssr_data,
                                            bundle_info.price_info.currency,journey_info.ext['origin']['market'])
        response_dict = response.to_dict()
        quote_id = response_dict['carbon_quote']['quote_id']

        return passenger_data, journey_data, contact_data, ssr_data, quote_id

    def order(self,
              passengers: List[PassengerInfoModel],
              origin_market: str,
              origin_port: str,
              bundle_info: FlightBundleModel,
              passenger_data: List[dict],
              journey_data: List[dict],
              contact_data: dict,
              ssr_data: List[dict],
              quote_id: str):

        total_amount = decimal.Decimal(0)

        adt_number = sum([1 for x in passengers if x.type == PassengerTypeEnum.ADT])
        chd_number = sum([1 for x in passengers if x.type == PassengerTypeEnum.CHD])

        total_amount += adt_number * (
                bundle_info.price_info.adult_tax_price + bundle_info.price_info.adult_ticket_price)
        total_amount += chd_number * (
                bundle_info.price_info.child_tax_price + bundle_info.price_info.child_ticket_price)
        total_amount += sum(
            [sum((j.price * j.number for j in x.buy_baggage)) if len(x.buy_baggage) > 0 else decimal.Decimal('0') for x
             in passengers])

        order_data = ParameterConstruct.order_construct(total_amount=total_amount,
                                                        origin_market=origin_market,
                                                        origin_port=origin_port,
                                                        currency_code=bundle_info.price_info.currency,
                                                        journeys=journey_data,
                                                        passengers=passenger_data,
                                                        contact_info=contact_data,
                                                        ssr=ssr_data,
                                                        cancel_quote_id=quote_id)

        response = self.__script.order(order_data)
        return response.to_dict()['order_id'], total_amount

    def trigger_payment_check(self):
        jwt_response = self.__script.get_payment_jwt()
        payment_jwt = jwt_response.to_dict()['jwt']
        pay_util = CardinalcommerceUtil(self.__script.get_proxy_str(), 'Android')
        jwt_response = pay_util.jwt_init(payment_jwt)
        jwt_data = jwt_response['CardinalJWT']

        pay_load = jwt.decode(
            jwt_data,
            options={"verify_signature": False},
            algorithm='HS256',
        )

        reference_id = pay_load['Payload']['URLs']['DeviceFingerprint']['QueryParameters']['referenceId']
        org_unit_id = pay_load['Payload']['URLs']['DeviceFingerprint']['QueryParameters']['orgUnitId']
        pay_util.save_browser_data(reference_id=reference_id, org_unit_id=org_unit_id)

        return reference_id, org_unit_id

    def create_payment_card(self,
                            total_amount,
                            order_number,
                            reference_id,
                            payment_info: PaymentInfoModel,
                            journey: FlightJourneyModel,
                            contact_info: ContactInfoModel):

        response = self.__script.get_key_discovery()
        payment_key = response.to_dict()
        rsa_n = Utils.base64url_to_hex(payment_key['n'])
        rsa_e = Utils.base64url_to_hex(payment_key['e'])

        exp_month = payment_info.card_expiry_date.split('/')[0]
        exp_year = payment_info.card_expiry_date.split('/')[1]

        card_number = base64.b64encode(RsaCiphering.rsa_encrypt(rsa_n, rsa_e, payment_info.card_number)).decode('utf-8')
        card_expiry = base64.b64encode(RsaCiphering.rsa_encrypt(rsa_n, rsa_e, payment_info.card_expiry_date)).decode(
            'utf-8')
        card_cvv = base64.b64encode(RsaCiphering.rsa_encrypt(rsa_n, rsa_e, payment_info.card_cvv)).decode('utf-8')

        tz_offset = timezone(timedelta(hours=-6))
        now: datetime = datetime.now(tz=tz_offset)

        nonce = str(uuid.uuid4())
        # 格式化为自定义格式
        formatted_time: str = now.strftime('%Y-%m-%dT%H:%M:%S%z')
        formatted_time: str = formatted_time[:-2] + ':' + formatted_time[-2:]
        sig = payment_info.card_number + payment_info.card_expiry_date + payment_info.card_cvv + nonce + formatted_time

        o = hashlib.sha256(sig.encode('utf-8')).hexdigest()
        sig = hashlib.sha256(o.encode('utf-8')).hexdigest()

        response = self.__script.look_up(order_number=order_number,
                                         exp_month=exp_month,
                                         exp_year=exp_year,
                                         card_number=payment_info.card_number,
                                         currency_code=journey.bundles[0].price_info.currency,
                                         last_name=contact_info.last_name,
                                         first_name=contact_info.first_name,
                                         total_amount=total_amount,
                                         reference_id=reference_id)

        data = {
            "order_id": order_number,
            "device_type": "APP",
            "os": "android",
            "locale": "en_HK",
            "success_url": "http://localhost:8080/success",
            "failure_url": "http://localhost:8080/failure",
            "payment_option": "MC",
            "cc_payload": {
                "card_number": card_number,
                "card_expiry": card_expiry,
                "card_cvc": card_cvv,
                "card_holder_name": f"{contact_info.last_name} {contact_info.first_name}",
                "nonce": nonce,
                "timestamp": formatted_time,
                "sig": sig,
                "tds_md": response.to_dict()['md'],
                "afy_tid": "123456",
                "dcc_key": None,
                "dcc_accept_offer": False,
            },
            "convenience_fee": 0
        }

        response = self.__script.create_payment(data)

    def create_payment_ali_pay(self, order_number: str):

        data = {
            "order_id": order_number,
            "device_type": "APP",
            "locale": "en_HK",
            "success_url": "https://mybooking.hkexpress.com/payment/success",
            "failure_url": "https://mybooking.hkexpress.com/payment/fail",
            "payment_option": "AP",
            "convenience_fee": 0
        }
        response = self.__script.create_payment(data)

    def booking(self,
                journey: FlightJourneyModel,
                passengers: List[PassengerInfoModel],
                bundle: FlightBundleModel,
                contact_info: ContactInfoModel,
                response_order_data: ResponseOrderInfoModel,
                check_booking: Optional[bool] = False):

        temp_passenger = self.trip(journey, passengers, bundle)
        if check_booking:
            return None

        total_baggage_weight = sum([sum(j.weight for j in x.ssr.baggage) for x in passengers])
        bundle_baggage = sum(
            [x.weight * x.number for x in bundle.ssr_info.baggage if x.type == SsrTypeEnum.HAULING_BAGGAGE])

        if total_baggage_weight != 0:
            baggage_data = self.ssr_baggage(journey)
            for i in passengers:
                total_buy_baggage_weight = sum(
                    [x.weight * x.number for x in i.ssr.baggage if x.type == SsrTypeEnum.HAULING_BAGGAGE])
                i.ext = {
                    'buyBaggageWeight': total_buy_baggage_weight + bundle_baggage,
                }
            compute_data = self.compute_baggage(passengers, baggage_data, journey.bundles)
            bundle = next((x for x in journey.bundles if x.code == compute_data[0]), None)
            temp_passenger = self.trip(journey, compute_data[2], bundle)
            baggage_data = self.ssr_baggage(journey)
            for i in temp_passenger:
                baggage_passenger_data = next((value for key, value in baggage_data.items() if key == i.key), None)
                if baggage_passenger_data is None:
                    raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f'{i.get_passenger_name()}获取行李数据异常')

                buy_bag = i.bag_combination
                for j in buy_bag:
                    bag_data = next((x for x in baggage_passenger_data if x.weight == j), None)

                    t_bag = copy.deepcopy(bag_data)
                    t_bag.number = 1
                    if bag_data is None:
                        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR,
                                           f'{i.get_passenger_name()}指定行李数据获取异常')
                    i.buy_baggage.append(t_bag)
        else:
            pass

        passenger_data, journey_data, contact_data, ssr_data, quote_id = self.validation(temp_passenger, bundle,
                                                                                         journey, contact_info)

        order_number, total_amount = self.order(
            passengers=temp_passenger,
            origin_port=journey.dep_airport,
            origin_market=journey.ext['origin']['market'],

            passenger_data=passenger_data,
            journey_data=journey_data,
            contact_data=contact_data,
            ssr_data=ssr_data,
            quote_id=quote_id,
            bundle_info=bundle
        )

        for i in temp_passenger:
            i.ssr.baggage = i.buy_baggage

            for x in bundle.ssr_info.baggage:
                if x.type in [SsrTypeEnum.HAULING_BAGGAGE, SsrTypeEnum.HAND_BAGGAGE]:
                    i.ssr.baggage.append(x)

        response_order_data.order_number = order_number
        response_order_data.passengers = temp_passenger
        response_order_data.journeys = [journey]
        response_order_data.journeys[0].bundles = [bundle]
        response_order_data.contact_info = contact_info
        response_order_data.total_amount = total_amount

    def polling_status(self, response_order_data: ResponseOrderInfoModel):

        err_number = 0
        t = 0
        while True:
            t += 1

            if t > 10:
                response_order_data.order_state = OrderStateEnum.UNKNOWN
                raise ServiceError(ServiceStateEnum.ORDER_STATE_CHECK_LIMIT)

            try:
                response = self.__script.polling_status(response_order_data.order_number)
                response_dict = response.to_dict()
                LOG.info(response.to_text())
                pay_state = response_dict.get('cash_payment_status')
                if pay_state is None or pay_state == "P_AUTH":
                    time.sleep(5)
                    continue

                if pay_state == 'F_AUTH':
                    if response_dict.get('form_value') is not None:
                        if response_dict.get('form_value').find('failure') != -1:
                            response_order_data.order_state = OrderStateEnum.HOLD
                            raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)
                    else:
                        response_order_data.order_state = OrderStateEnum.UNKNOWN
                        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "未知订单状态")
                elif pay_state == 'S_AUTH':
                    if response_dict.get('sales_reference') is None:
                        response_order_data.order_state = OrderStateEnum.ABNORMAL
                        continue
                        # raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '缺失PNR信息')
                    else:
                        response_order_data.pnr = response_dict.get('sales_reference')
                        response_order_data.order_state = OrderStateEnum.OPEN_FOR_USE
                    break
                else:
                    response_order_data.order_state = OrderStateEnum.UNKNOWN
                    raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '未知订单状态')
            except ServiceError as e:
                raise e
            except Exception as e:
                err_number += 1

        return self.order_info(last_name=response_order_data.passengers[0].last_name,
                               first_name=response_order_data.passengers[0].first_name,
                               pnr=response_order_data.pnr)

    def order_info(self, last_name: str, first_name: str, pnr: str):
        t = self.__script.retrieve(last_name=last_name, first_name=first_name, pnr=pnr)
        order_data = t.to_dict()
        return FlightInfoParser.parse_order(order_data['trips'])
