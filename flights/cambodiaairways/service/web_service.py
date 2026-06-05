import copy
from decimal import Decimal
from typing import Optional

from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from flights.cambodiaairways.config import Config
from flights.cambodiaairways.flight_common.flight_info_parser import FlightInfoParser
from flights.cambodiaairways.flight_common.parameter_construct import ParameterConstruct
from flights.cambodiaairways.script.web_script import WebScript


class WebService:
    def __init__(self, proxy_info_data: Optional[ProxyInfoModel]):
        self.__script = WebScript(proxy_info_data)

    @staticmethod
    def __check_airport(airport_code: str):
        if not any(item.get('airportCode') == airport_code for item in Config.AIRPORTS):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, f'机场[{airport_code}]不存在')

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               currency_code: str,
               ret_date: Optional[str] = None,
               cabin_grade: str = Config.DEFAULT_CABIN_GRADE):
        self.__check_airport(dep_airport)
        self.__check_airport(arr_airport)
        # buyTicket decides fare currency by route; keep this argument for the common service signature.
        _ = currency_code

        search_data = ParameterConstruct.build_search_data(
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_date=dep_date,
            adt_number=adt_number,
            chd_number=chd_number,
            ret_date=ret_date,
            cabin_grade=cabin_grade,
        )
        response = self.__script.search(search_data)
        journeys = FlightInfoParser.journey_info_parser(
            flight_data=response,
            dep_date=dep_date,
            ret_date=ret_date,
            group_id=search_data['_plain']['groupId'],
        )
        if not journeys:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        return journeys

    def booking(self,
                journey: FlightJourneyModel,
                passengers: list[PassengerInfoModel],
                contact_info: ContactInfoModel,
                bundle: FlightBundleModel,
                response_order_data: ResponseOrderInfoModel) -> ResponseOrderInfoModel:
        group_id = (bundle.ext or {}).get('groupId') or (journey.ext or {}).get('groupId')
        if not group_id:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'groupId缺失')

        kind = '0'
        first_segment = journey.segments[0]
        flight_number = first_segment.flight_number
        cabin = bundle.cabin or bundle.code
        adt_number = sum(1 for passenger in passengers if passenger.type == PassengerTypeEnum.ADT)
        chd_number = sum(1 for passenger in passengers if passenger.type == PassengerTypeEnum.CHD)
        inf_number = sum(1 for passenger in passengers if passenger.type == PassengerTypeEnum.INF)

        self.__check_flight_schedule(
            kind=kind,
            group_id=group_id,
            flight_number=flight_number,
            dep_airport=journey.dep_airport,
            arr_airport=journey.arr_airport,
            dep_date=journey.dep_time.strftime('%Y-%m-%d'),
        )
        price_response = self.__script.compute_price({
            'adultNum': str(adt_number),
            'childNum': str(chd_number),
            'babyNum': str(inf_number),
            'groupId': group_id,
            'kind': kind,
            'leaveCabin': cabin,
            'leaveFlightNum': flight_number,
            'returnCabin': '',
            'returnFlightNum': '',
        })
        self.__reserve_selected_flight(
            kind=kind,
            group_id=group_id,
            dep_airport=journey.dep_airport,
            arr_airport=journey.arr_airport,
        )
        passenger_submit_data = self.__passenger_submit_data(
            kind=kind,
            group_id=group_id,
            passengers=passengers,
            contact_info=contact_info,
        )
        order_price_state = self.__script.write_incrservice_next([
            {
                'groupId': group_id,
                'serve': [],
                'passenger': [passenger_submit_data],
            }
        ])
        order_result = self.__save_ticket_order_with_captcha(group_id)

        pnr = order_result.get('pnr')
        if str(order_result.get('status')) != '200' or not pnr:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, order_result.get('message') or '押位未返回PNR')

        total_amount = self.__extract_total_amount(order_result, order_price_state, price_response)
        response_order_data.order_number = order_result.get('orderNumber')
        response_order_data.order_state = OrderStateEnum.HOLD
        response_order_data.pnr = pnr
        response_order_data.passengers = passengers
        response_order_data.journeys = [journey]
        response_order_data.journeys[0].bundles = [bundle]
        response_order_data.contact_info = contact_info
        response_order_data.total_amount = total_amount
        response_order_data.currency_code = bundle.price_info.currency
        return response_order_data

    def __check_flight_schedule(self,
                                kind: str,
                                group_id: str,
                                flight_number: str,
                                dep_airport: str,
                                arr_airport: str,
                                dep_date: str):
        response = self.__script.check_flight_schedule({
            'leaveFlightNum': flight_number,
            'returnFlightNumber': '',
            'kind': kind,
            'leaveDepAirport': dep_airport,
            'leaveArrAirport': arr_airport,
            'leaveDepDate': dep_date,
            'returnDepDate': '',
            'groupId': group_id,
        })
        if str(response.get('status')) != '200':
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, response.get('message') or '航班变更校验失败')
        if (response.get('data') or {}).get('isChange'):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, (response.get('data') or {}).get('message') or '航班已变更')

    def __reserve_selected_flight(self,
                                  kind: str,
                                  group_id: str,
                                  dep_airport: str,
                                  arr_airport: str) -> list:
        reserve_state = self.__script.reserve_flight(kind=kind, group_id=group_id)
        if not reserve_state or not reserve_state[0].get('flight'):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '航班预留失败')

        selected_flight = copy.deepcopy(reserve_state[0]['flight'][0])
        selected_flight['from'] = Config.get_airport_route_label(dep_airport)
        selected_flight['to'] = Config.get_airport_route_label(arr_airport)
        selected_flight['token'] = ''
        reserve_airport_state = self.__script.reserve_airport([selected_flight])
        if not reserve_airport_state or not reserve_airport_state[0].get('flight'):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '机场预留失败')
        return reserve_airport_state

    @classmethod
    def __passenger_submit_data(cls,
                                kind: str,
                                group_id: str,
                                passengers: list[PassengerInfoModel],
                                contact_info: ContactInfoModel) -> dict:
        contact_user = cls.__clean_name(f'{contact_info.first_name} {contact_info.last_name}')[:28]
        return {
            'kind': kind,
            'man': str(sum(1 for passenger in passengers if passenger.type == PassengerTypeEnum.ADT)),
            'child': str(sum(1 for passenger in passengers if passenger.type == PassengerTypeEnum.CHD)),
            'baby': str(sum(1 for passenger in passengers if passenger.type == PassengerTypeEnum.INF)),
            'flag': '1',
            'groupId': group_id,
            'incrserviceNo': [],
            'incrserviceName': [],
            'contactEmail': contact_info.email_address,
            'contactMobile': f'{contact_info.phone_code}{contact_info.phone_number}',
            'contactUser': contact_user,
            'passenger': [
                cls.__passenger_payload(passenger, index, contact_info)
                for index, passenger in enumerate(passengers, start=1)
            ],
        }

    @classmethod
    def __passenger_payload(cls,
                            passenger: PassengerInfoModel,
                            passenger_no: int,
                            contact_info: ContactInfoModel) -> dict:
        document_info = passenger.document_info
        nationality = document_info.nationality if document_info else 'US'
        nation = Config.get_nation(nationality)
        passenger_type = '成人'
        if passenger.type == PassengerTypeEnum.CHD:
            passenger_type = '儿童'
        elif passenger.type == PassengerTypeEnum.INF:
            passenger_type = '婴儿'

        return {
            'birthday': passenger.birthday,
            'documentType': '2',
            'email': contact_info.email_address,
            'idcard': document_info.number if document_info else '',
            'mobile': f'{contact_info.phone_code}{contact_info.phone_number}',
            'nation': nation,
            'passengerCall': 'Mr' if passenger.gender == GenderEnum.M else 'Ms',
            'passengerMing': cls.__clean_name(passenger.first_name),
            'passengerName': '',
            'passengerNo': passenger_no,
            'passengerType': passenger_type,
            'passengerXing': cls.__clean_name(passenger.last_name),
            'passportExpiredate': document_info.expire_date if document_info else '',
            'sex': '0' if passenger.gender == GenderEnum.M else '1',
            'address': '',
            'city': '',
            'province': '',
            'country': None,
            'postalCode': '',
        }

    @staticmethod
    def __clean_name(value: str) -> str:
        return ''.join(ch for ch in (value or '').upper() if ch.isalpha() or ch == ' ').strip()

    def __save_ticket_order_with_captcha(self, group_id: str) -> dict:
        last_response = {}
        for _ in range(Config.CAPTCHA_RETRY_COUNT):
            code_data = self.__script.create_code(group_id)
            captcha_image = self.__script.captcha_image(code_data['url'])
            verify_code = self.__script.captcha_solver(captcha_image)
            last_response = self.__script.save_ticket_order({
                'promoCode': '',
                'groupId': group_id,
                'language': Config.DEFAULT_LANGUAGE,
                'verifyCode': verify_code,
                'apiBkSource': 'CA-PC',
                'token': '',
            })
            if str(last_response.get('status')) == '200' and last_response.get('pnr'):
                return last_response
            if str(last_response.get('status')) == '602':
                continue
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, last_response.get('message') or '押位失败')
        raise ServiceError(ServiceStateEnum.ROBOT_CHECK)

    @staticmethod
    def __extract_total_amount(order_result: dict, order_price_state: list, price_response: dict) -> Decimal:
        if order_result.get('priceAll'):
            return Decimal(str(order_result['priceAll']))
        if order_price_state and order_price_state[0].get('price'):
            return Decimal(str(order_price_state[0]['price'][0].get('priceAll') or '0'))
        price_total = (price_response.get('data') or {}).get('priceTotal') or {}
        return Decimal(str(price_total.get('total') or '0'))
