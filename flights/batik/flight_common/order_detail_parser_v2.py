import decimal
from datetime import datetime
from decimal import Decimal
from typing import List

from bs4 import BeautifulSoup

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
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


class OrderDetailParserV2:
    @classmethod
    def parse_order_detail(cls, order_data: dict):
        """

        Args:

            order_data: WEB官网订单详情

        Returns:
            OrderInfoModel:内部订单详情模型
        """
        temp_order_data = ResponseOrderInfoModel()
        if order_data['isSuccess'] is False:
            if order_data['errMessage'] == 'This booking was flown already.':
                order_state = OrderStateEnum.USED
            else:
                order_state = OrderStateEnum.ABNORMAL
        else:
            order_state = OrderStateEnum.OPEN_FOR_USE
        temp_order_data.order_state = order_state
        if order_state == OrderStateEnum.OPEN_FOR_USE:
            create_time = order_data['ticketIssueDt']
        else:
            return temp_order_data
        pnr = order_data['confirmationRes']['pnr']
        currency = order_data['confirmationRes']['paymentDetails']['currency']
        temp_order_data.pnr = pnr
        temp_order_data.currency_code = currency

        passenger_infos = cls.parse_passenger_info(order_data['confirmationRes']['passengerInfos'],
                                                   order_data['confirmationRes']['fares'])

        journeys = []
        for index, bound in enumerate(order_data['confirmationRes']['fares']):
            segments = cls.parse_order_segments(
                segments_data=bound['flight'],
            )
            bundles = cls.parse_bundles(fare_infos=bound)
            journeys.append(FlightJourneyModel(
                segments=segments,
                bundles=bundles,
                journeyKey='-1',
                depAirport=segments[0].dep_airport,
                arrAirport=segments[-1].arr_airport,
                depTime=segments[0].dep_time,
                arrTime=segments[-1].arr_time,
            ))
        temp_order_data.passengers = passenger_infos

        temp_order_data.journeys = journeys
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

    @classmethod
    def parse_passenger_info(cls,
                             passengers_data: List[dict],
                             flights_dict: dict) -> List[PassengerInfoModel]:
        passengers_list = []
        for i in passengers_data:
            if i['title'] == 'MR' or i['title'] == 'MSTR':
                gender = GenderEnum.M
            else:
                gender = GenderEnum.F
            passenger_type = i['paxType']

            passenger_data = PassengerInfoModel.model_validate({
                "type": PassengerTypeEnum.ADT if passenger_type == 'ADT' else PassengerTypeEnum.ADT,
                "lastName": i['surname'],
                "firstName": i['givenName'],
                "gender": gender,
                'ticketNumber': i['ticketNumber'],

            })
            ssr_info = FlightSsrInfoModel()

            temp_ssr_list = []

            for index, value in enumerate(flights_dict):
                for j in value['fareAncillaries']:
                    if f"{i['surname']}{i['givenName']}".upper().replace(' ', '') + i['title'] == j['name'].replace(' ',
                                                                                                                    ''):
                        if j.get('baggages'):
                            for x in j['baggages']:
                                total_weight = x['code'].replace('B', '')
                                temp_ssr_list.append(FlightBaggageModel(
                                    type=SsrTypeEnum.HAULING_BAGGAGE,
                                    code=total_weight,
                                    price=Decimal(0),
                                    weight=total_weight,
                                    number=1,
                                ))
            ssr_info.baggage = temp_ssr_list
            passenger_data.ssr = ssr_info
            passengers_list.append(passenger_data)

        return passengers_list

    @classmethod
    def parse_order_segments(cls, segments_data: List[dict]) -> List[FlightSegmentModel]:
        """
        解析订单详情
        Args:
            segments_data:

        Returns:

        """

        result_segment_infos = []
        for index, i in enumerate(segments_data):
            dep_airport = i['flightSeg']['depPort']
            arr_airport = i['flightSeg']['arrPort']
            dep_time = datetime.fromisoformat(i['flightSeg']['depDate'])
            arr_time = datetime.fromisoformat(i['flightSeg']['arrDate'])
            carrier = i['flightSeg']['carrier']['airCode']
            flight_number = i['flightSeg']['carrier']['airCode'] + str(i['flightSeg']['carrier']['airFlightNo'])
            operating_carrier = i['flightSeg']['carrier']['opAirCode']
            operating_flight_number = i['flightSeg']['carrier']['opAirCode'] + str(
                i['flightSeg']['carrier']['opAirFlightNo'])
            result_segment_infos.append(FlightSegmentModel.model_validate({
                "segmentKey": '11',
                'depAirport': dep_airport,
                'arrAirport': arr_airport,
                'depTime': dep_time,
                'arrTime': arr_time,
                'flightNumber': flight_number,
                'carrier': carrier,
                'operatingCarrier': operating_carrier,
                'operatingFlightNumber': operating_flight_number,
                'routeIndex': index,
                'legIndex': index,
            }))
        return result_segment_infos

    @classmethod
    def parse_bundles(
            cls,
            fare_infos: dict,) -> List[FlightBundleModel]:
        """
        解析航段数据，生成包含票价、舱位、行李信息的 FlightBundleModel 列表。

        Args:
            fare_infos: 运价信息列表
        Returns:
            List[FlightBundleModel]
        """
        # 解析票价，每种乘客类型保留一条
        booking_class = []
        fare_basis = None
        product_tags = fare_infos['brandLabel']
        for i in fare_infos['flight']:
            booking_class.append(i['flightSeg']['bookingClass'])
            fare_basis = i['flightSeg']['fareBasis']
        ssr_info = FlightSsrInfoModel()

        temp_ssr_list = []

        for i in fare_infos['flight']:
            if i['flightAncillaries'][0]['freeBaggage']:
                if i['flightAncillaries'][0]['freeBaggage']['quantity'] == 0:
                    continue
                temp_ssr_list.append(FlightBaggageModel(
                    type=SsrTypeEnum.HAULING_BAGGAGE,
                    code=i['flightAncillaries'][0]['freeBaggage']['name'],
                    price=Decimal(0),
                    weight=i['flightAncillaries'][0]['freeBaggage']['name'],
                    number= i['flightAncillaries'][0]['freeBaggage']['quantity'],
                            ))
        ssr_info.baggage = temp_ssr_list
        return [FlightBundleModel(
            priceInfo=FlightBundlePriceModel(
                adultTicketPrice=decimal.Decimal(-1),
                adultTaxPrice=decimal.Decimal(-1),
                childTicketPrice=decimal.Decimal(-1),
                childTaxPrice=decimal.Decimal(-1),
                currency='MYR',
            ),
            ssrInfo=ssr_info,
            code='-1',
            cabinLevel='Y',
            cabin=fare_basis[0] if fare_basis else 'Y',
            fareKey='-1',
            productTag=product_tags,
            seat=-1,
            freightRateType=FreightRateTypeEnum.PT,
        )]