import copy
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils.string_util import StringUtil
from ..config import Config
from ..flight_common.flight_info_parser import FlightInfoParser
from ..script.web_script import WebScript


class WebService:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__script = WebScript(proxy_info_data)

    @staticmethod
    def __find_station(stations: List[Dict], airport_code: str) -> Dict:
        for station in stations:
            if station.get('stationCode') == airport_code:
                return station
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, f'机场[{airport_code}]不存在')

    def init_web_service(self):
        self.__script.prepare_context()

    def __build_search_data(self,
                            dep_airport: str,
                            arr_airport: str,
                            dep_date: str,
                            adt_number: int,
                            chd_number: int,
                            currency_code: str,
                            ret_date: Optional[str] = None,
                            promo_code: Optional[str] = None):
        dep_station = self.__find_station(Config.DEPARTURE_STATIONS, dep_airport)
        arr_station = self.__find_station(Config.DEPARTURE_STATIONS, arr_airport)

        dep_country_code = dep_station.get('countryCode')
        arr_country_code = arr_station.get('countryCode')
        dom_int_type = 'D' if dep_country_code == 'KR' and arr_country_code == 'KR' else 'I'
        trip_type = 'OW'
        trip_route = [
            {
                "originAirport": dep_airport,
                "originCountryCode": dep_country_code,
                "originName": dep_station.get('stationName') or dep_station.get('macName') or dep_airport,
                "destinationAirport": arr_airport,
                "destinationCountryCode": arr_country_code,
                "destinationName": arr_station.get('stationName') or arr_station.get('macName') or arr_airport,
                "flightDate": dep_date,
                "sortOptions": "EarliestDeparture,EarliestArrival",
                "depMac": dep_station.get('mac', 'N'),
                "arrMac": arr_station.get('mac', 'N'),
            }
        ]
        route_info_list = [(dep_station, arr_station, dep_date)]

        if ret_date:
            trip_type = 'RT'
            trip_route.append({
                "originAirport": arr_airport,
                "originCountryCode": arr_country_code,
                "originName": arr_station.get('stationName') or arr_station.get('macName') or arr_airport,
                "destinationAirport": dep_airport,
                "destinationCountryCode": dep_country_code,
                "destinationName": dep_station.get('stationName') or dep_station.get('macName') or dep_airport,
                "flightDate": ret_date,
                "sortOptions": "EarliestDeparture,EarliestArrival",
                "depMac": arr_station.get('mac', 'N'),
                "arrMac": dep_station.get('mac', 'N'),
            })
            route_info_list.append((arr_station, dep_station, ret_date))

        passengers = [{"type": "ADT", "count": str(adt_number)}]
        if chd_number > 0:
            passengers.append({"type": "CHD", "count": str(chd_number)})

        avail_search_data = {
            "tripRoute": trip_route,
            "passengers": passengers,
            "tripType": trip_type,
            "bookType": self.__script.book_type,
            "domIntType": dom_int_type,
            "cultureCode": self.__script.culture_code,
            "currencyCode": currency_code,
            "lowfareIncludeTaxesAndFee": 'false',
            "discountInfo": {"promotionCode": promo_code} if promo_code else {},
            "voucherInfo": {}
        }

        return {
            "dep_station": dep_station,
            "arr_station": arr_station,
            "dom_int_type": dom_int_type,
            "route_info_list": route_info_list,
            "avail_search_data": avail_search_data,
            "submit_data": {
                "availSearchData": json.dumps(avail_search_data, ensure_ascii=False)
            }
        }

    def __get_route_ancillary_groups(self, route_info_list: List, dom_int_type: str) -> List[List[Dict[str, Any]]]:
        route_ancillary_groups = []
        for dep_station, arr_station, dep_date in route_info_list:
            area_code = dep_station.get('areaCode')
            if area_code != 'RGTP000004':
                area_code = arr_station.get('areaCode') or area_code

            ancillary_list = []
            if area_code and dep_date:
                try:
                    ancillary_list = self.__script.select_bundle_ancillaries(
                        dep_date=dep_date,
                        dom_int_type=dom_int_type,
                        area_code=area_code,
                    )
                except ServiceError:
                    ancillary_list = []
            route_ancillary_groups.append(ancillary_list)
        return route_ancillary_groups

    @staticmethod
    def __parse_form(form_html: str):
        soup = BeautifulSoup(form_html, 'html.parser')
        form = soup.find('form')
        if not form:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, '网关表单不存在')

        form_data = {}
        for field in form.find_all(['input', 'textarea', 'select']):
            name = field.get('name')
            if not name:
                continue

            if field.name == 'select':
                selected_option = field.find('option', selected=True) or field.find('option')
                form_data[name] = selected_option.get('value', '') if selected_option else ''
                continue

            if field.name == 'textarea':
                form_data[name] = field.text or ''
                continue

            input_type = (field.get('type') or '').lower()
            if input_type in {'checkbox', 'radio'} and not field.has_attr('checked'):
                continue
            form_data[name] = field.get('value', '')

        return form.get('action') or '', form_data

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               currency_code: str,
               ret_date: Optional[str] = None,
               promo_code: Optional[str] = None):
        search_data = self.__build_search_data(
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_date=dep_date,
            adt_number=adt_number,
            chd_number=chd_number,
            currency_code=currency_code,
            ret_date=ret_date,
            promo_code=promo_code,
        )
        submit_data = search_data["submit_data"]
        page_key = self.__script.avail_search(dict(submit_data))
        submit_data.update({
            "userData": json.dumps({
                "agentId": ""
            }),
            "pageKey": page_key
        })
        flights = self.__script.search_flight(submit_data)
        route_ancillary_groups = self.__get_route_ancillary_groups(
            route_info_list=search_data["route_info_list"],
            dom_int_type=search_data["dom_int_type"],
        )

        journey_list = FlightInfoParser.journey_info_parser(
            flight_data=flights,
            route_ancillary_groups=route_ancillary_groups,
        )
        return journey_list

    def booking(self,
                journey: FlightJourneyModel,
                passengers: List[PassengerInfoModel],
                contact_info: ContactInfoModel,
                bundle: FlightBundleModel,
                response_order_data: ResponseOrderInfoModel, ) -> ResponseOrderInfoModel:
        self.__script.to_cffi_tls()

        adt_number = sum(1 for passenger in passengers if passenger.type.value == 'ADT')
        chd_number = sum(1 for passenger in passengers if passenger.type.value == 'CHD')

        dep_date = journey.dep_time.strftime('%Y-%m-%d')
        search_data = self.__build_search_data(
            dep_airport=journey.dep_airport,
            arr_airport=journey.arr_airport,
            dep_date=dep_date,
            adt_number=adt_number,
            chd_number=chd_number,
            currency_code=bundle.price_info.currency,
        )
        page_key = self.__script.page_key
        connect_flight_data = {"flag": "N"}
        if len(journey.segments) > 1:
            connect_flight_data["flag"] = "Y"

        bundle_ext = bundle.ext or {}
        selected_pax_fares = copy.deepcopy(bundle_ext.get('selectedPaxFares') or [])
        selected_bundle_data = copy.deepcopy(bundle_ext.get('selectedBundleData') or [])
        selected_flights_no = copy.deepcopy(bundle_ext.get('selectedFlightsNo') or {})
        journey_key = bundle_ext.get('journeyKey') or journey.journey_key
        fare_availability_key = bundle_ext.get('fareAvailabilityKey') or bundle.fare_key or ''

        if not selected_flights_no:
            first_segment = journey.segments[0]
            flight_number = first_segment.flight_number or ''
            carrier_code = first_segment.carrier or ''
            selected_flights_no = {
                'carrierCode': carrier_code,
                'identifier': (
                    flight_number[len(carrier_code):]
                    if carrier_code and flight_number.startswith(carrier_code)
                    else flight_number
                )
            }

        for temp_fare_data in selected_pax_fares:
            temp_fare_data.setdefault('bundleInfos', {})
        selection_data = {
            "journeyKey": journey_key,
            "fareAvailabilityKey": fare_availability_key,
            "selectedPaxFares": selected_pax_fares,
            "selectedFlightsNo": selected_flights_no,
            "selectedBundleData": selected_bundle_data,
            "connectFlightData": connect_flight_data,
        }

        avail_search_data = copy.deepcopy(search_data["avail_search_data"])
        avail_search_data["tripRoute"][0]["journeyKey"] = selection_data["journeyKey"]
        avail_search_data["tripRoute"][0]["fareAvailabilityKey"] = selection_data["fareAvailabilityKey"]
        direct_submit_data = {
            "availSearchData": json.dumps(avail_search_data, ensure_ascii=False),
            "selectedBundleData": json.dumps([selection_data["selectedBundleData"]], ensure_ascii=False),
            "selectedFareBundleData": json.dumps([{}], ensure_ascii=False),
            "connectFlightData": json.dumps([selection_data["connectFlightData"]], ensure_ascii=False),
            "selectedPaxFares": json.dumps([selection_data["selectedPaxFares"]], ensure_ascii=False),
            "selectedFlightsNo": json.dumps([selection_data["selectedFlightsNo"]], ensure_ascii=False),
            "bundleSkipFlag": "N",
            "nonUserLogoutFlag": "N",
            "nonUserPopupFlag": "N",
            "nonUserNotDCFlag": "N",
            "waitBookFlag": "false",
            "pageKey": page_key,
        }
        response = self.__script.direct_avail_pass_input(direct_submit_data)
        if response.status != 302 or not response.location:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        security = parse_qs(urlparse(response.location).query).get('security', [''])[0]
        if not security:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'security缺失')
        self.__script.login_page(security)
        self.__script.non_user_login_page(security)

        captcha_image = self.__script.captcha_image(security)
        captcha_answer = self.__script.captcha_solver(captcha_image)

        captcha_check_result = self.__script.captcha_check_answer(captcha_answer, security)
        if captcha_check_result != '200':
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '验证码校验失败')

        login_response = self.__script.login_action(
            security=security,
            captcha_answer=captcha_answer,
            user_email=contact_info.email_address,
        )
        if login_response.status != 302 or not login_response.location:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '非会员登录失败')
        if 'error=error' in login_response.location:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f'非会员登录失败: {login_response.location}')

        gateway_html = self.__script.gateway_login_page(login_response.location, security)
        _, gateway_form_data = self.__parse_form(gateway_html)
        gateway_referer_url = login_response.location
        if not gateway_referer_url.startswith('http'):
            gateway_referer_url = f'https://www.jejuair.net{gateway_referer_url}'
        final_html = self.__script.direct_avail_pass_input_login_success(
            submit_data=gateway_form_data,
            referer_url=gateway_referer_url,
        )
        if 'txtLastName' not in final_html or 'txtFirstName' not in final_html or 'txtContactPhone' not in final_html:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '进入乘机人页失败')

        final_page_soup = BeautifulSoup(final_html, 'html.parser')
        new_page_key = ''
        tl_amount_text = ''
        for input_tag in final_page_soup.select('input[name="pageKey"]'):
            value = (input_tag.get('value') or '').strip()
            if value:
                new_page_key = value
                break
        for input_tag in final_page_soup.select('input[name="tlAmount"]'):
            value = (input_tag.get('value') or '').strip()
            if value:
                tl_amount_text = value
                break

        self.__script.page_key = new_page_key or page_key
        adult_total = bundle.price_info.adult_ticket_price + bundle.price_info.adult_tax_price
        child_total = bundle.price_info.child_ticket_price + bundle.price_info.child_tax_price
        total_amount = adult_total * adt_number + child_total * chd_number
        if tl_amount_text:
            tl_amount_text = re.sub(r'[^0-9.-]', '', tl_amount_text.replace(',', ''))
            if tl_amount_text:
                total_amount = Decimal(tl_amount_text)

        pss_token = StringUtil.extract_between(final_html, '"token":"', '"')
        if not pss_token:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'PssToken缺失')

        passenger_containers = final_page_soup.select('div[id^="psgrContainer"][data-passengerkey]')
        if len(passenger_containers) != len(passengers):
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                f'乘机人数量不匹配, 页面[{len(passenger_containers)}], 入参[{len(passengers)}]'
            )

        am_flag_match = re.search(r'\bamFlag\s*=\s*(true|false)\b', final_html, re.IGNORECASE)
        am_flag = bool(am_flag_match and am_flag_match.group(1).lower() == 'true')
        if am_flag:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, '暂不支持当前航线的AM乘机人信息提交')

        passenger_list = []
        for index, (container, passenger_info) in enumerate(zip(passenger_containers, passengers)):
            passenger_key = (container.get('data-passengerkey') or '').strip()
            if not passenger_key:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED,
                                   f'第[{index + 1}]位乘机人的passengerKey缺失')

            passenger_type = (container.get('data-passenger-type') or '').strip().upper()
            if passenger_type != passenger_info.type.value:
                raise ServiceError(
                    ServiceStateEnum.DATA_VALIDATION_FAILED,
                    f'第[{index + 1}]位乘机人类型不匹配, 页面[{passenger_type}], 入参[{passenger_info.type.value}]'
                )

            first_name = (passenger_info.first_name or '').strip().upper()
            last_name = (passenger_info.last_name or '').strip().upper()
            if not first_name or not last_name:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, f'第[{index + 1}]位乘机人姓名缺失')

            birthday_text = (passenger_info.birthday or '').strip()
            birthday_digits = re.sub(r'[^0-9]', '', birthday_text)
            if len(birthday_digits) != 8:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, f'第[{index + 1}]位乘机人生日格式错误')
            try:
                birthday = datetime.strptime(birthday_digits, '%Y%m%d').strftime('%Y-%m-%d')
            except ValueError as exc:
                raise ServiceError(
                    ServiceStateEnum.DATA_VALIDATION_FAILED,
                    f'第[{index + 1}]位乘机人生日无效[{birthday_text}]'
                ) from exc

            if passenger_info.gender.value == 'M':
                gender = '1'
            elif passenger_info.gender.value == 'F':
                gender = '2'
            else:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, f'第[{index + 1}]位乘机人性别无效')

            nationality_input = container.select_one('input[name="hidNationality"]')
            nationality = ''
            if passenger_info.document_info and passenger_info.document_info.nationality:
                nationality = passenger_info.document_info.nationality.strip().upper()
            if not nationality and nationality_input:
                nationality = (nationality_input.get('value') or '').strip().upper()
            if nationality_input and not nationality:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, f'第[{index + 1}]位乘机人国籍缺失')

            passenger_data = {
                'passengerKey': passenger_key,
                'customerNumber': '',
                'programLevelCode': '',
                'first': first_name,
                'last': last_name,
                'gender': gender,
                'passengerNumber': index,
                'dateOfBirth': birthday,
            }
            if nationality:
                passenger_data['nationality'] = nationality
            passenger_list.append(passenger_data)

        contact_first_name = (contact_info.first_name or '').strip().upper()
        contact_last_name = (contact_info.last_name or '').strip().upper()
        contact_email = (contact_info.email_address or '').strip()
        if not contact_first_name or not contact_last_name or not contact_email:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, '联系人姓名或邮箱缺失')

        phone_code = re.sub(r'[^0-9]', '', contact_info.phone_code or '')
        phone_number = re.sub(r'[^0-9]', '', contact_info.phone_number or '')
        if not phone_code or not phone_number:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, '联系人手机号缺失')

        passenger_payload = {
            'passengerReq': json.dumps({
                'passengers': passenger_list,
                'contact': [{
                    'phone': f'{phone_code}-{phone_number}',
                    'emailAddress': contact_email,
                    'customerNumber': '',
                    'firstName': contact_first_name,
                    'lastName': contact_last_name,
                }],
                'cultureCode': self.__script.culture_code,
                'bookType': self.__script.book_type,
                'amFlag': False,
            }, ensure_ascii=False),
            'pageKey': self.__script.page_key,
        }
        pass_info = self.__script.add_passengers(passenger_payload, pss_token)
        if pass_info.get('code') != '0000':
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f'添加乘机人失败: {pass_info}')

        pass_info_data = pass_info.get('data') or {}
        if isinstance(pass_info_data, dict) and pass_info_data.get('code') not in (None, '0000'):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f'添加乘机人失败: {pass_info}')

        booking_data = {}
        if isinstance(pass_info_data, dict):
            booking_data = pass_info_data.get('data') or {}
            if not booking_data:
                booking_data = pass_info_data
        pnr = booking_data.get('recordLocator') or ''
        pss_token = booking_data.get('token') or ''
        if not pnr or not pss_token:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, '添加乘机人后未返回PNR或PssToken')

        self.__script.find_pnr(pss_token, pnr)
        response_order_data.pnr = pnr
        response_order_data.passengers = passengers
        response_order_data.contact_info = contact_info
        response_order_data.currency_code = bundle.price_info.currency
        response_order_data.total_amount = total_amount
        response_order_data.journeys = [copy.deepcopy(journey)]
        response_order_data.journeys[0].bundles = [copy.deepcopy(bundle)]
        return response_order_data
