import copy
import datetime
from typing import List

from bs4 import BeautifulSoup

from common.decorators.retry_decorator import retry_decorator
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.utils.flight_util import FlightUtil
from common.utils.sham_booking_util import ShamBookingUtil
from flights.batik.lionair.flight_common.cart_parse import CartParser
from flights.batik.lionair.flight_common.flight_info_parser import FlightParser
from flights.batik.lionair.script.web_script import WebScript


class WebService:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__script = WebScript(proxy_info_data)

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int):
        self.__script.search(dep_airport=dep_airport, arr_airport=arr_airport, dep_date=dep_date,
                             adult_count=adt_number,
                             child_count=chd_number, )
        flight_html_str = self.__script.get_booking_html()

        if flight_html_str == "":
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "查询页面响应空数据")

        journey_info_model = FlightParser.parse_flight_data(routes_html=flight_html_str)

        if not journey_info_model:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        return journey_info_model, flight_html_str

    def passenger_booking(self, cart_html_str: str, passenger_infos: List[PassengerInfoModel]):
        """

        Args:
            cart_html_str: 订单html源码
            passenger_infos: 乘机人信息

        Returns:

        """
        new_passenger_infos = copy.deepcopy(passenger_infos)
        cart_post_data, passenger_map = CartParser.cart_passengers_parse(cart_html_str=cart_html_str,
                                                                         passenger_infos=new_passenger_infos)
        add_on_html_str = self.__script.passenger_booking(cart_html_str=cart_html_str, cart_post_data=cart_post_data)

        return add_on_html_str, passenger_map

    def add_baggage(self, passenger_infos: List[PassengerInfoModel], passenger_map: dict, add_on_html_str: str):
        """

        Args:
            passenger_infos: 乘机人信息
            passenger_map: 乘机人id字典
            add_on_html_str: 添加行李html源码

        Returns:

        """
        # baggage_str_key = FlightParser.parse_baggage_add(passenger_infos=passenger_infos, passenger_map=passenger_map)
        baggage_str_key = ''
        add_baggage_html = self.__script.add_baggage(add_on_html_str=add_on_html_str, baggage_str_key=baggage_str_key)

        return add_baggage_html

    @retry_decorator([(ServiceStateEnum.ROBOT_CHECK, None)])
    def booking(self, use_bundle: FlightBundleModel,
                dep_airport: str,
                arr_airport: str,
                dep_date: datetime,
                passenger_infos: List[PassengerInfoModel],
                flight_html_str: str):
        img_token = self.__script.get_image_code()
        cart_html_str = self.__script.cart_booking(flight_id=use_bundle.fare_key,
                                                   dep_airport=dep_airport,
                                                   arr_airport=arr_airport,
                                                   dep_date=dep_date,
                                                   adult_count=sum([1 for x in passenger_infos if
                                                                    x.type == PassengerTypeEnum.ADT]),
                                                   child_count=sum([1 for x in passenger_infos if
                                                                    x.type == PassengerTypeEnum.CHD]),
                                                   flight_html_str=flight_html_str,
                                                   img_token=img_token)
        add_on_html_str, passenger_map = self.passenger_booking(cart_html_str, passenger_infos)
        # # # 先不处理行李
        # source_baggage_data = self.get_baggage(add_on_html_str=add_on_html_str,
        #                                                   journey_segments=journey_segments)
        add_baggage_html = self.add_baggage(passenger_infos=passenger_infos, passenger_map=passenger_map,
                                            add_on_html_str=add_on_html_str)
        return add_baggage_html

    def auth_pay(self,contact_info: ContactInfoModel, add_baggage_html: str):
        data = {
            "ctl00$mainContent$payDet": "rbPay_ATM",
            "ctl00$mainContent$CreditCardDisplay1$CreditCardType": "VI",
            "ctl00$mainContent$CreditCardDisplay1$txtCardHolderName": "",
            "ctl00$mainContent$CreditCardDisplay1$CreditCardNumber": "",
            "ctl00$mainContent$CreditCardDisplay1$CreditCardExpiryMonth": "MM",
            "ctl00$mainContent$CreditCardDisplay1$CreditCardExpiryYear": "YY",
            "ctl00$mainContent$CreditCardDisplay1$CVVNumber": "",
            "ctl00$mainContent$txtPaymentReference": "",
            "ctl00$mainContent$DebitCardNumber": "",
            "ctl00$mainContent$txtOVOPhone": "",
            "ctl00$mainContent$ContactTitle": "Mr",
            "ctl00$mainContent$ContactFirstName": contact_info.first_name,
            "ctl00$mainContent$ContactLastName": contact_info.last_name,
            "ctl00$mainContent$ddlCountryCode3": f"+{contact_info.phone_code}",
            "ctl00$mainContent$txtPhoneNumber3": contact_info.phone_number,
            "ctl00$mainContent$ddlCountryCode1": f"+{contact_info.phone_code}",
            "ctl00$mainContent$txtAreaCode1": "",
            "ctl00$mainContent$txtPhoneNumber1": "",
            "ctl00$mainContent$ddlOriNumber": "H",
            "ctl00$mainContent$txtEmailAddress1": contact_info.email_address,
            "ctl00$mainContent$txtEmailAddress2": contact_info.email_address,
            "ctl00$mainContent$chkSpecialOffers": "on",
            "ctl00$mainContent$AcceptFareConditions": "on",
            "ctl00$mainContent$btnContinue": "Continue",
            "response": "",
            "ctl00$mainContent$hidTokenId": ""
        }
        pay_info = self.__script.atm_payment(pay_data=data, add_baggage_html=add_baggage_html)
        soup = BeautifulSoup(pay_info, "html.parser")
        # 根据唯一的 ID 查找元素
        pnr_element = soup.find(id="ctl00_mainContent_lblRefNumber")

        if pnr_element:
            # .strip() 用于去除 PNR 前后的换行符和空格
            return pnr_element.get_text(strip=True)
        return '111111'


if __name__ == '__main__':
    service = WebService(GlobalVariable.PROXY_INFO_DATA)

    journey_list, flight_html_str = service.search(
        dep_airport='KUL',
        arr_airport='CAN',
        dep_date="20260227",
        adt_number=7,
        chd_number=0,
    )
    journey_list = FlightUtil.number_filter(journey_list, 'OD612')
    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, 'OD612')
    use_bundle = journey_list[0].bundles[0]
    passengers: List[PassengerInfoModel] = ShamBookingUtil.build_sham_passenger_info(1, False)

    service.booking(
        use_bundle=use_bundle,
        passengers=passengers,
        dep_airport=journey_list[0].dep_airport,
        arr_airport=journey_list[0].arr_airport,
        dep_date=journey_list[0].dep_time, flight_html_str=flight_html_str
    )
