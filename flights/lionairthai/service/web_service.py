import datetime
import decimal
import time
import urllib.parse

import pycountry_convert as pc
from bs4 import BeautifulSoup

from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils.date_util import DateUtil
from common.utils.html_util import HtmlUtil
from common.utils.sham_booking_util import ShamBookingUtil
from common.utils.string_util import StringUtil
from flights.lionairthai.config import Config
from flights.lionairthai.flight_common.flight_info_parser import FlightInfoParser
from flights.lionairthai.script.web_script import WebScript


class WebService:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__script = WebScript(proxy_info_data)

    def initialization(self):
        self.__script.init_sid()


    def search_init(self,
                    dep_airport: str,
                   arr_airport: str,
                   date: str,
                   adt_number: int,
                   chd_number: int):
        self.__script.init_cloudflare()
        self.__script.search_init(
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_date=date,
            adt_number=adt_number,
            chd_number=chd_number
        )
        r = self.__script.default()
        if r == 0:
            return self.__script.get_flight_search()
        t = self.__script.block_search_init()
        html_input_data = HtmlUtil.parse_html_form_data(t)

        input_data = {
            "hdnIsGoogleCaptchaEnabled":"FALSE",
            "btnContinue":"Continue"
        }

        data = []
        for i in Config.BLOCK_SEARCH_DATA:
            key = i
            if i in input_data:
                value = input_data[i]
            else:
                value = html_input_data.get(i) or ""

            data.append(f'{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value)}')

        self.__script.block_search("&".join(data))
        self.__script.default()
        return self.__script.get_flight_search()

    def search(self,
               dep_airport: str,
               arr_airport: str,
               date: str,
               adt_number: int,
               chd_number: int):
        flight_data_dict = self.search_init(
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            date=date,
            adt_number=adt_number,
            chd_number=chd_number
        )
        if not flight_data_dict['d']:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)

        result_journey_info = FlightInfoParser.journey_info_parser(flight_data_dict['d'])

        if len(result_journey_info) == 0:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        return result_journey_info

    def booking_data(self,
                     adt_number: int,
                     chd_number: int,
                     flight_info: FlightJourneyModel,
                     use_bundle: FlightBundleModel):

        booking_html_data = self.__script.booking_html()
        booking_input_dict = HtmlUtil.parse_html_form_data(booking_html_data)

        input_data = {
            '__EVENTTARGET': 'FlightSelected',
            'hfOBAFIndex': str(flight_info.ext['AFIndex']),
            'hfOBIndex': str(flight_info.ext['FlightIndex']),
            'ucMiniSearch$depCity': flight_info.dep_airport,
            'ucMiniSearch$arrCity': flight_info.arr_airport,
            'hfOBClass': 'P',
            'hfOBCategory': 'OB',
            'ucMiniSearch$ddlClass': '0',
            'ucMiniSearch$ddlDirectFlight': '1',
            'ucMiniSearch$ddlAdult': str(adt_number),
            'ucMiniSearch$ddlChild': str(chd_number),
            'ucMiniSearch$ddlInfant': '0',
            'ucMiniSearch$ucMLAirlineModifySrch$ddlAdult1': str(adt_number),
            'ucMiniSearch$ucMLAirlineModifySrch$ddlChild1': str(chd_number),
            'ucMiniSearch$ucMLAirlineModifySrch$ddlInfant1': '0',
            'ucMiniSearch$ucMLAirlineModifySrch$ddlCabinClass': '1',
            'hfInsuranceStatus': '0',
            'ucMiniSearch$rdoJourneyType': '1',
            'hfIBAFIndex': '0',
            'hfIsActualData': '1'

        }
        data = []
        for i in Config.BOOKING_KEY_NAME:
            value = ""
            key = i

            if key == '__EVENTVALIDATION':
                continue
            if i in input_data:
                value = input_data[i]
            elif key.find("dpflightDep") != -1:
                value = booking_input_dict.get('ucMiniSearch$dpd1')
            elif booking_input_dict.get(i):
                value = booking_input_dict.get(i)

            value = value.replace('\n', '\r\n')
            data.append(f'{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value)}')

        package_data = {"OBIndex": str(flight_info.ext['FlightIndex']), "OBClass": 'P',
                        "OBAFIndex": str(flight_info.ext['AFIndex']), "IBIndex": "", "IBClass": "", "IBAFIndex": "",
                        "InsuranceStatus": "0", "IBCategory": "", "OBCategory": "OB", "OBFBClass": "", "IBFBClass": "",
                        "IsInsSelectCall": False}
        self.__script.get_package_summary(package_data)
        data = "&".join(data)
        self.__script.booking(data)

    def passenger_add(self, passengers: list[PassengerInfoModel]):
        passenger_html_data = self.__script.passenger_html()
        passenger_html_input_data = HtmlUtil.parse_html_form_data(passenger_html_data)
        html_bs = BeautifulSoup(passenger_html_data, 'lxml')


        tax_total = decimal.Decimal('0')
        admin_span = html_bs.find(id="ucPackageSummary_lblYRTax")
        tax_total += decimal.Decimal(admin_span.contents[1].replace(",","").strip())
        tax_span = html_bs.find(id="ucPackageSummary_hfOptSummaryTax")
        tax_total += decimal.Decimal(tax_span.attrs['value'].replace(",",""))

        if len(passengers) == 0:
            return tax_total

        input_data = {}
        adt = 1
        chd = 1
        data = []
        for index, value in enumerate(passengers):
            key = f'ucPassenger1$lstPassenger$ctrl{index}'
            passenger_title = 'Main Passenger' if index == 0 else (
                f'Child {chd}' if value.type == PassengerTypeEnum.CHD else f'Passenger {adt}')


            title = Config.PASSENGER_TITLE_MAP[f'{value.type.value}_{value.gender.value}']
            input_data[f'{key}$hdfPassengers'] = index
            input_data[f'{key}$hdfPassengerTitle'] = passenger_title
            input_data[f'{key}$TITLE$ddlTitle'] = title
            input_data[f'{key}$TITLE$hdnv'] = index
            input_data[f'{key}$FIRSTNAME$txtFName'] = value.first_name
            input_data[f'{key}$FIRSTNAME$hdnv'] = index
            input_data[f'{key}$LASTNAME$txtLName'] = value.last_name
            input_data[f'{key}$LASTNAME$hdnv'] = index
            input_data[f'{key}$DATEOFBIRTH$hdnPaxType'] = 'ADULT' if value.type == PassengerTypeEnum.ADT else ''
            input_data[f'{key}$DATEOFBIRTH$hdnPrevAge'] = ''
            input_data[f'{key}$DATEOFBIRTH$hdnIsMainPax'] = "false"
            input_data[f'{key}$DATEOFBIRTH$ddlDay'] = str(int(DateUtil.string_to_target_format(value.birthday, '%d')))
            input_data[f'{key}$DATEOFBIRTH$ddlMonth'] = str(int(DateUtil.string_to_target_format(value.birthday, '%m')))
            input_data[f'{key}$DATEOFBIRTH$ddlYear'] = str(int(DateUtil.string_to_target_format(value.birthday, '%Y')))
            input_data[f'{key}$NATIONALITY$hdnPaxIndex'] = index
            input_data[f'{key}$NATIONALITY$ddlNationality'] = pc.map_country_alpha2_to_country_alpha3().get(
                value.document_info.nationality)
            input_data[f'{key}$PASSPORTNO$txtPassNo'] = value.document_info.number
            input_data[f'{key}$PASSPORTEXPIRYDATE$ddlPassDay'] = str(
                int(DateUtil.string_to_target_format(value.document_info.expire_date, '%d')))
            input_data[f'{key}$PASSPORTEXPIRYDATE$ddlPassMonth'] = str(
                int(DateUtil.string_to_target_format(value.document_info.expire_date, '%m')))
            input_data[f'{key}$PASSPORTEXPIRYDATE$ddlPassYear'] = str(
                int(DateUtil.string_to_target_format(value.document_info.expire_date, '%Y')))
            input_data[f'{key}$PASSPORTISSUECOUNTRY$ddlPassCountry'] = pc.map_country_alpha2_to_country_alpha3().get(
                value.document_info.issuing_country)

        for i in Config.ADD_PASSENGER_DATA:
            key = i
            if key == 'ucPassenger1$ScriptManager1':
                value = 'updateWrapper|btnConfirmPassenger'
                continue
            elif key == '__ASYNCPOST':
                value = "true"
                continue
            elif key == 'hdnIsGoogleCaptchaEnabled':
                value = "FALSE"
                continue
            elif key == 'ucPackageSummary$hfOptSummaryTotalPrice':
                value = ""
            elif key == '__EVENTTARGET':
                value = "PassengersConfirmed"
            else:
                value = passenger_html_input_data.get(key) or ""

            data.append(f'{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value)}')

            if key == 'hfInsuranceStatus':
                for k, v in input_data.items():
                    if type(v) != str:
                        v = str(v)
                    data.append(f'{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}')


        if "ucInsurance$rdoInsurance" in passenger_html_input_data:
            k = "ucInsurance$rdoInsurance"
            v = "rdoInsurance"
            data.append(f'{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}')

            k = "ucInsurance$hdnIsPaxContentNeed"
            v = "0"
            data.append(f'{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}')

            k = "ucInsurance$hdnInsurancePaxList"
            v = ""
            data.append(f'{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}')

        t = self.__script.passenger_add("&".join(data))

        if t.find('OptionalAddOns') == -1:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '添加乘机人失败')

    def optional_add_ons(self):
        optional_add_html_data = self.__script.optional_add_ons_html()
        optional_add_input_data = HtmlUtil.parse_html_form_data(optional_add_html_data)
        data = []
        for i in Config.ADD_ONS_DATA:
            key = i
            value = optional_add_input_data.get(i) or ''
            data.append(f'{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value)}')

        response = self.__script.optional_add_ons("&".join(data))
        if response.headers['location'].find('/SL/FlightBooking.aspx') == -1:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR,'添加辅营失败')


    def booking_create_payment(self,passenger_number:int,contact_info:ContactInfoModel):


        payment_html_data = HtmlUtil.parse_html_form_data(self.__script.booking_payment_html())
        data = []
        for i in Config.SET_PAYMENT_DATA:
            key = i
            if key == '__EVENTTARGET':
                value = 'rdolstPaymentType$16'
            elif key == 'rdolstPaymentType':
                value = '233'
            else :
                value = payment_html_data.get(i) or ''
            data.append(f'{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value)}')

        response_text = self.__script.booking_payment("&".join(data))
        submit_html_data = HtmlUtil.parse_html_form_data(response_text)

        time.sleep(60  * passenger_number)
        # self.__script.get_exchange_currency_response('233')

        city,address,postcode = ShamBookingUtil.build_address()
        contact_info.email_address = StringUtil.generate_random_string(10)+'@'+StringUtil.generate_random_string(10)+".com"
        contact_info.email_address = contact_info.email_address.lower()
        input_data = {
            'ucPersonalDetails1$ddlTitle':'Mr.',
            'ucPersonalDetails1$txtFName':contact_info.first_name,
            'ucPersonalDetails1$txtLName':contact_info.last_name,
            'ucPersonalDetails1$txtAdd1':address,
            'ucPersonalDetails1$txtCity':city,
            'ucPersonalDetails1$ddlCountry':'Thailand',
            'ucPersonalDetails1$txtPostCode':postcode,
            # 'ucPersonalDetails1$ddlCountryCode':contact_info.phone_code,
            'ucPersonalDetails1$ddlCountryCode': '66',
            'ucPersonalDetails1$txtMobileNo':contact_info.phone_number,
            'ucPersonalDetails1$txtEmail':contact_info.email_address,
            'ucPersonalDetails1$txtConformEmail':contact_info.email_address,
            'dangerousgoods':'on',
            'chkRules':'on',
            'chkRules1':'on',
            'hdnAddonAvialble':'0',
            'hdnCAATAnnouncementAvailable':'0'
        }
        data = []
        for i in Config.SUBMIT_PAYMENT_DATA:
            key = i
            if key in input_data:
                value = input_data.get(key)
            elif key == 'rdolstPaymentType':
                value = '233'
            else:
                value = submit_html_data.get(key) or ''
            data.append(f'{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value)}')

        response_text = self.__script.booking_payment("&".join(data))


        redirect_html_data = HtmlUtil.parse_html_form_data(response_text)

        return redirect_html_data

    def search_order_info(self,pnr: str,last_name: str,first_name: str):

        order_info = ResponseOrderInfoModel()
        order_info.pnr = pnr
        order_info.order_state = OrderStateEnum.OPEN_FOR_USE


        response_manage_html,location = self.__script.online_add_on_booking(pnr,last_name,first_name)

        params = HtmlUtil.parse_html_form_data(response_manage_html)
        self.__script.manage_addons(params,location)

        response = self.__script.optional_add_ons_html()
        order_info_json = self.__script.get_meals()
        passengers = FlightInfoParser.order_parser_passengers(order_info_json['d'][0])

        flight_info_soup = BeautifulSoup(response_manage_html,'lxml')
        body_array = flight_info_soup.find_all("tbody")
        passenger_body = body_array[0]
        passenger_tr_array = passenger_body.find_all("tr")

        for index,value in enumerate(passenger_tr_array):
            tb_array = value.find_all("td")
            passengers[index].ticket_number = tb_array[3].text.strip()


        flight_info_body = body_array[1]
        flight_info_tr_array = flight_info_body.find_all("tr")

        if len(flight_info_tr_array) != 1:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR,'不符合航班解析规则')

        for i in flight_info_tr_array:
            tb_array = i.find_all("td")
            flight_number = tb_array[0].text
            flight_number = flight_number[flight_number.find('Thai Lion air ') + len('Thai Lion air '):].strip()
            dep_time = DateUtil.string_to_target_format(tb_array[1].find('span').text, '%Y%m%d%H%M')
            arr_time = DateUtil.string_to_target_format(tb_array[2].find('span').text, '%Y%m%d%H%M')
            order_info.journeys = [
                FlightJourneyModel(
                    depAirport=order_info_json['d'][0]['DepCityCode'],
                    arrAirport=order_info_json['d'][0]['ArrCityCode'],
                    depTime=dep_time,
                    arrTime=arr_time,
                    segments=[
                        FlightSegmentModel(
                            depAirport=order_info_json['d'][0]['DepCityCode'],
                            arrAirport=order_info_json['d'][0]['ArrCityCode'],
                            depTime=dep_time,
                            arrTime=arr_time,
                            segmentKey='',
                            flightNumber=flight_number,
                            carrier=flight_number[:2],
                            operatingCarrier=flight_number[:2],
                            operatingFlightNumber=flight_number,
                        )
                    ],
                    bundles=[],
                    journeyKey=''
                )
            ]

        html_soup = BeautifulSoup(response, 'lxml')

        for index,value in enumerate(passengers):
            t = html_soup.find(id=f'lvPaxBaggages_ucPaxExcessBaggage_{index}_lvPaxExcessOBBaggages_{index}_ucOBBaggageInformation_0_spnAvailBaggage_0')
            t = t.text[t.text.find('Selected Baggage :')+len('Selected Baggage :'):].replace('KG','')
            value.ssr = FlightSsrInfoModel()
            value.ssr.baggage = [
                FlightBaggageModel(
                    type=SsrTypeEnum.HAULING_BAGGAGE,
                    price=decimal.Decimal('0'),
                    number=1,
                    weight=int(float(t)),
                )
            ]
        order_info.passengers = passengers
        return order_info
