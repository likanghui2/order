"""
Module: flight_parse
Author: Likanghui
Date: 2024-10-07

Description:
    官网数据处理
"""
import decimal
import re
from collections import defaultdict
from datetime import datetime
from typing import List

from lxml import etree

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.utils.date_util import DateUtil
from common.utils.flight_util import FlightUtil


class FlightParser:

    @classmethod
    def parse_flight_data(cls, routes_html: str) -> List[FlightJourneyModel]:
        """

        Args:
            routes_html:航司官网航段数据html

        Returns:

        """

        routes_list = etree.HTML(routes_html).xpath('''//div[@class="flight-table"]''')
        if not routes_list:
            routes_list = etree.HTML(routes_html).xpath('''//div[@class="flight-matrix-container"]''')
        journeys = []
        for index, route in enumerate(routes_list, start=1):
            grouped = defaultdict(list)
            for tr in route.xpath('''.//table[@class="flight-matrix"]//tr[@class="flight-matrix-row"]'''):
                id_attr = tr.get('id', '')
                match = re.search(r'flightRow(?:In|Out)bound(\d+)_\d+', id_attr)
                if match:
                    key = int(match.group(1))
                    grouped[key].append(tr)

            segment_infos = list(grouped.values())

            for segment_info in segment_infos:
                segments = cls.parse_segments(
                    segment_infos=segment_info,
                    segment_type=index
                )
                bundles = cls.parse_bundles(bundles=segment_info[0])
                journeys.append(FlightJourneyModel(
                    journeyKey="",
                    segments=segments,
                    bundles=bundles,
                    depAirport=segments[0].dep_airport,
                    arrAirport=segments[-1].arr_airport,
                    depTime=segments[0].dep_time,
                    arrTime=segments[-1].arr_time,
                ))
        return journeys

    @staticmethod
    def parse_segments(segment_infos: list, segment_type: int) -> List[FlightSegmentModel]:
        """
            解析航段信息
        Args:
            segment_infos:
            segment_type:

        Returns:

        """

        result_segments: List[FlightSegmentModel] = []

        for segment_info in segment_infos:
            dep_airport = ''.join(
                segment_info.xpath('''.//span[@class="departurePort"]//span[@class="port-code"]//text()''')).strip()
            arr_airport = ''.join(
                segment_info.xpath('''.//span[@class="arrivalPort"]//span[@class="port-code"]//text()''')).strip()

            dep_time = datetime.strptime(
                ''.join(segment_info.xpath('''.//span[@class="departureDate"]//text()''')).strip().split(",")[
                    -1].strip() + ' ' + ''.join(
                    segment_info.xpath('''.//span[@class="departureTime"]//text()''')).strip(), '%d %b %Y %H:%M')
            arr_time = datetime.strptime(
                ''.join(segment_info.xpath('''.//span[@class="arrivalDate"]//text()''')).strip().split(",")[
                    -1].strip() + ' ' + ''.join(
                    segment_info.xpath('''.//span[@class="arrivalTime"]//text()''')).strip(), '%d %b %Y %H:%M')
            carrier = ''.join(segment_info.xpath('''.//span[@class="flight-carrier-info"]/text()''')).strip()[:2]
            flight_number = ''.join(segment_info.xpath('''.//span[@class="flight-carrier-info"]/text()''')).strip()

            operating_carrier = ''.join(segment_info.xpath('''.//span[@class="flight-carrier-info"]/text()''')).strip()[
                                :2]
            code_share = True if carrier != operating_carrier else False
            flight_time = DateUtil.get_time_difference_points(dep_time, arr_time)
            operating_flight_number = flight_number if code_share else flight_number

            # 暂未找到机型
            segment_info = FlightSegmentModel(
                segmentKey='111',
                depAirport=dep_airport,
                arrAirport=arr_airport,
                depTime=dep_time,
                arrTime=arr_time,
                carrier=carrier,
                flightNumber=flight_number,
                operatingCarrier=carrier,
                operatingFlightNumber=flight_number,
                routeIndex=segment_type,
                legIndex=segment_type,
            )
            result_segments.append(segment_info)
        return result_segments

    @staticmethod
    def parse_bundles(bundles) -> List[FlightBundleModel]:
        """
            解析价格信息
        Args:
            bundles:

        Returns:
            result_bundles：航段详情(包含增值服务)

        """
        result_bundles = []
        for index, bundle in enumerate(bundles.xpath('''.//td[@rowspan]''')):

            if index in [0, 1]:
                cabin_level = 'Y'
            elif index in [2]:
                cabin_level = 'C'
            else:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"仓等判断失败")

            if ''.join(bundle.xpath('''./text()''')) == "Sold Out" or ''.join(bundle.xpath('''./text()''')) == "N/A":
                continue

            bundle_name_dict = {0: "Promo", 1: "Economy", 2: "Business"}
            product_tag = bundle_name_dict[index]

            currency = ''.join(bundle.xpath('''.//span[@class="currency"]//text()''')).strip()

            bundle_key = ''.join(bundle.xpath('''.//input//@value'''))

            fare = decimal.Decimal(
                re.findall(r'Base Fare:\s*[A-Z]{3}\s*([\d,]+)', ''.join(bundle.xpath(".//@title")))[0].replace(",",
                                                                                                               "").strip())
            tax = decimal.Decimal(
                re.findall(r'Taxes & Fees:\s*[A-Z]{3}\s*([\d,]+)', ''.join(bundle.xpath(".//@title")))[0].replace(
                    ",", "").strip())

            price_info = FlightBundlePriceModel(
                adultTicketPrice=fare,
                adultTaxPrice=tax,
                childTicketPrice=fare,
                childTaxPrice=tax,
                currency=currency,

            )

            bundle_info = FlightBundleModel(
                priceInfo=price_info,
                ssrInfo=FlightSsrInfoModel(),
                code=product_tag,
                cabinLevel=cabin_level,
                cabin='Y',
                fareKey=str(bundle_key),
                productTag=product_tag,
                seat=-1,
                freightRateType=FreightRateTypeEnum.PT,
            )
            result_bundles.append(bundle_info)
        return result_bundles
