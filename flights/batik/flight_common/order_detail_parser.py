import decimal
from typing import List

from bs4 import BeautifulSoup

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from pyquery import PyQuery

from common.utils.date_util import DateUtil
from flights.batik.config import Config


class OrderDetailParser:

    def parse_order_detail(cls, order_data: str):
        """

        Args:

            order_data: WEB官网订单详情

        Returns:
            OrderInfoModel:内部订单详情模型
        """
        temp_order_data = ResponseOrderInfoModel()
        if 'Error in retrieving your booking' in order_data:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, '票号信息错误')
        if 'cancelled already' in order_data:
            temp_order_data.order_state = OrderStateEnum.REFUND
            return temp_order_data

        if 'Since TicketStatus is check-in' in order_data:
            temp_order_data.order_state = OrderStateEnum.CHECKED_IN
            return temp_order_data

        doc = PyQuery(order_data)

        doc('br').replace_with('|')

        pnr_element = doc('input[name="ctl00$bodycontent$txtReservationID"]')
        pnr = pnr_element.val()
        temp_order_data.pnr = pnr
        journey_table = doc('#tblflightdetails')
        headers = [th.text.strip() for th in journey_table('thead th')]
        rows_journey = []
        for tr in journey_table('tbody tr'):
            row_data = []
            for td in tr.findall('td'):
                # 处理 <br> 标签，将文本合并为一行
                text = ''.join([text.strip() for text in td.itertext()])
                row_data.append(text)
            rows_journey.append(dict(zip(headers, row_data)))
        # # 乘机人处理
        passengers_table = doc('#tblpassengers')
        headers = [th.text.strip() for th in passengers_table('thead th')]
        rows_passenger = []
        for tr in passengers_table('tbody tr'):
            row_data = []
            for td in tr.findall('td'):
                # 处理 <br> 标签，将文本合并为一行
                text = ''.join([text.strip() for text in td.itertext()])
                row_data.append(text)
            rows_passenger.append(dict(zip(headers, row_data)))
        passenger_infos = []
        for index, p1 in enumerate(rows_passenger):

            passenger_type = PassengerTypeEnum.ADT if p1['Passenger Type'] == 'Adult' else PassengerTypeEnum.CHD
            passenger_name = p1['Passenger Name']
            p_title = passenger_name.split(' ')[0]
            if p_title in ['MR', 'MS', 'MRS', 'MISS', 'MSTR']:
                if passenger_type == PassengerTypeEnum.ADT:
                    gender = GenderEnum.F if p_title in ['MS', 'MRS'] else GenderEnum.M
                else:
                    gender = GenderEnum.M if p_title == 'MSTR' else GenderEnum.F
            else:
                gender = None

            ticket_no = p1['E-Ticket No']

            passenger_data = PassengerInfoModel.model_validate({
                'type': passenger_type,
                'lastName': passenger_name.split(' ', 1)[-1],
                'firstName': "",
                'gender': gender,
                'ticketNumber': ticket_no,
                "birthday": '2000-09-01'
            })

            passenger_infos.append(passenger_data)
        temp_order_data.passengers = passenger_infos

        temp_order_data.journeys = cls.journey_info_parser(rows_journey)

        temp_order_data.order_state = OrderStateEnum.OPEN_FOR_USE

        return temp_order_data

    @staticmethod
    def journey_info_parser(rows_journey: list, ) -> List[FlightJourneyModel]:
        result_data_list = []
        for index, j1 in enumerate(rows_journey):
            segments = []

            dep_airport_name, dep_time = j1['Departing'].split('|')
            dep_date = DateUtil.string_to_date_auto(dep_time).strftime('%Y%m%d%H%M')
            dep_airport_name = Config.AIRPORT_NAMES[dep_airport_name]
            arr_airport_name, arr_time = j1['Arriving'].split('|')
            arr_date = DateUtil.string_to_date_auto(arr_time).strftime('%Y%m%d%H%M')
            arr_airport_name = Config.AIRPORT_NAMES[arr_airport_name]

            flight_number = j1['Flight'].split('|')[1].strip()
            carrier = flight_number[:2]

            segments.append(FlightSegmentModel.model_validate({
                "segmentKey": '11',
                'depAirport': dep_airport_name,
                'arrAirport': arr_airport_name,
                'depTime': dep_date,
                'arrTime': arr_date,
                'flightNumber': flight_number,
                'carrier': carrier,
                'operatingCarrier': carrier,
                'operatingFlightNumber': flight_number,
                'routeIndex': index,
                'legIndex': index,
            }))

            product_cabin = j1['Class']
            cabin = product_cabin.split('(')[1][0:1]  # Super Saver(XODBSSMY)
            product_tag = product_cabin.split('(')[0]
            bundles = FlightBundleModel(
                priceInfo=FlightBundlePriceModel(
                    adultTicketPrice=decimal.Decimal(-1),
                    adultTaxPrice=decimal.Decimal(-1),
                    childTicketPrice=decimal.Decimal(-1),
                    childTaxPrice=decimal.Decimal(-1),
                    currency='MYR',

                ),
                ssrInfo=FlightSsrInfoModel(),
                code='-1',
                cabinLevel='Y',
                cabin=cabin,
                fareKey='-1',
                productTag=product_tag,
                seat=-1,
                freightRateType=FreightRateTypeEnum.PT,
            )
            result_data_list.append(FlightJourneyModel(
                segments=segments,
                bundles=[bundles],
                journeyKey='-1',
                depAirport=segments[0].dep_airport,
                arrAirport=segments[-1].arr_airport,
                depTime=segments[0].dep_time,
                arrTime=segments[-1].arr_time,
            ))
        return result_data_list

    @staticmethod
    def parse_dep_arr(order_detail: ResponseOrderInfoModel, addon_info):
        soup = BeautifulSoup(addon_info, 'html.parser')
        dep = soup.find('input', {'id': 'ucCleverTap_hdnCTDepCity', 'type': 'hidden'}).attrs['value']
        arr = soup.find('input', {'id': 'ucCleverTap_hdnCTArrCity', 'type': 'hidden'}).attrs['value']
        order_detail.segments[0].dep_airport = dep
        order_detail.segments[0].arr_airport = arr
        return order_detail
