import decimal
from datetime import datetime
from decimal import Decimal
from typing import List

from lxml import etree

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.utils.date_util import DateUtil
from common.utils.string_util import StringUtil
from flights.vietjet.config import Config


class FlightParser:

    @classmethod
    def journey_info_parser(cls, flight_data: dict)-> List[FlightJourneyModel]:
        result_data_list = []
        for index, route in enumerate([flight_data['data']['list_Travel_Options_Departure'],
                                       flight_data['data']['list_Travel_Options_Arrival']]):
            if route is None:
                continue
            for fare in route:
                segments = cls.segment_parser(fare['segmentOptions'], index=index)
                if len(segments) != 1:
                    continue
                bundles = cls.bundle_parser(fare['fareOption'], segments=segments)
                if not bundles:
                    continue
                result_data_list.append(FlightJourneyModel(
                    journeyKey="",
                    segments=segments,
                    bundles=bundles,
                    depAirport=segments[0].dep_airport,
                    arrAirport=segments[-1].arr_airport,
                    depTime=segments[0].dep_time,
                    arrTime=segments[-1].arr_time,
                ))

        return result_data_list

    @classmethod
    def segment_parser(cls, segs_data: List[dict], index: int) -> List[FlightSegmentModel]:
        segment_list = []
        for segment_index, segment in enumerate(segs_data):
            segment = segment['flight']
            dep_time = DateUtil.string_to_date_auto(segment['ETDLocal'])
            arr_time = DateUtil.string_to_date_auto(segment['ETALocal'])

            flight_number = segment['Number']
            carrier = segment['AirlineCode']

            dep_airport = segment['departureAirport']['Code']
            arr_airport = segment['arrivalAirport']['Code']
            segment_list.append(FlightSegmentModel(
                segmentKey='',
                depAirport=dep_airport,
                arrAirport=arr_airport,
                depTime=dep_time,
                arrTime=arr_time,
                carrier=carrier,
                flightNumber=flight_number,
                operatingCarrier=carrier,
                operatingFlightNumber=flight_number,
                routeIndex=index,
                legIndex=segment_index,
            ))

        return segment_list

    @classmethod
    def __extract_brand_data(cls, baggages: dict, product_tag: str, segments: List[FlightSegmentModel],) -> \
            List[FlightBaggageModel]:
        baggage_list = []
        for i in baggages['ticket']:
            if product_tag == 'SkyBoss' and i['ticketName'] == 'Skyboss':
                if not baggages['special_baggage_data']['journeyConfigs'] or baggages['special_baggage_data']['journeyConfigs']== [None]:
                    baggage_text = None
                else:
                    baggage_text = baggages['special_baggage_data']['journeyConfigs'][0]['metadata'][
                        'fareDescription'].get(
                        'Skyboss')
                pass
            else:
                if not baggages['special_baggage_data']['journeyConfigs'] or baggages['special_baggage_data']['journeyConfigs']== [None]:
                    baggage_text = None
                else:
                    baggage_text = baggages['special_baggage_data']['journeyConfigs'][0]['metadata'][
                        'fareDescription'].get(product_tag)
                if i['ticketName'] != product_tag:
                    continue

            html_text = i['description']
            flight_number = '$'.join([i.flight_number for i in segments])
            flight_info = {'dep': segments[0].dep_airport, 'arr': segments[-1].arr_airport,
                           'flight_number': flight_number}
            cities = Config.CITIES
            if product_tag == 'Eco':
                baggage_list.append(FlightBaggageModel(
                    type=SsrTypeEnum.HAND_BAGGAGE,
                    price=Decimal(0),
                    weight=7,
                    number=1
                ))
            else:
                baggage_result_list = cls.parse_baggage_info(html_text, flight_info, cities, baggage_text)
                for baggage_result in baggage_result_list:
                    if baggage_result['baggage_type'] == '手提':
                        baggage_type = SsrTypeEnum.HAND_BAGGAGE
                    else:
                        baggage_type = SsrTypeEnum.HAULING_BAGGAGE
                    baggage_list.append(FlightBaggageModel(
                        type=baggage_type,
                        price=Decimal(0),
                        weight=baggage_result['total_weight'],
                        number=1
                    ))
        return baggage_list

    @classmethod
    def parse_baggage_info(cls, html, flight_info, cities, baggage_text):
        baggage_list = []

        # 解析HTML
        tree = etree.HTML(html)
        items = tree.xpath('//div[@class="class_content"]//p')
        international = True if flight_info['dep'] in cities or flight_info['arr'] in cities else False
        for item in items:
            text = ''.join(item.xpath('.//span//text()')).strip()

            if '手提行李' in text:
                if '适用' in text:
                    total_wight_text = StringUtil.extract_between(text, '适用', '公斤手提行李').replace(' ', '').split(
                        '公斤或')
                    if international:
                        weight = total_wight_text[1]
                    else:
                        weight = total_wight_text[0]
                else:
                    weight = text.split('公斤')[0].strip()

                baggage_list.append({
                    'baggage_type': '手提',
                    'total_weight': weight,
                })

            elif '托运行李' in text and '公斤' in text:
                total_wight_text = StringUtil.extract_between(text, '免费', '公斤的托运行李').replace(' ', '').split(
                    '公斤或')
                if international:
                    if flight_info['dep'] in ['PER', 'ADL'] or flight_info['arr'] in ['PER', 'ADL']:
                        weight = 0
                        for p in etree.HTML(baggage_text).xpath('//div[@class="class_content"]//p'):
                            p_text = ''.join(p.xpath('.//span//text()')).strip()
                            if '托運行李' in p_text:
                                weight = p_text.split('公斤')[0]
                        # weight = total_wight_text[0]
                    else:
                        weight = total_wight_text[1]
                else:
                    weight = total_wight_text[0]

                baggage_list.append({
                    'baggage_type': '托运',
                    'total_weight': weight,
                })

        return baggage_list

    @classmethod
    def bundle_parser(cls, fares_info, segments: list[FlightSegmentModel]) -> List[FlightBundleModel]:
        bundle_list = []
        if fares_info is None:
            return bundle_list
        for bundle in fares_info:
            fare, currency = bundle['FareCost'], bundle['currency']['code']
            fare = decimal.Decimal(fare)
            # 计算税费
            tax =decimal.Decimal (0)
            price_info = FlightBundlePriceModel(
                adultTicketPrice=fare,
                adultTaxPrice=tax,
                childTicketPrice=fare,
                childTaxPrice=tax,
                currency=currency,

            )
            # 确定套餐键
            key = bundle['BookingKey']

            product_dict = {"SkybossBusiness".upper(): "Business",
                            "Skyboss".upper(): "SkyBoss",
                            "Deluxe".upper(): "Deluxe",
                            "Eco".upper(): "Eco"}

            # 确认套餐类型是否合法
            product_tag = product_dict[bundle['Description'].upper()]
            cabin = bundle['FareCategory']
            # 确定舱位等级
            cabinlevel = 'Y'
            if product_tag == 'Business':
                cabinlevel = 'F'
            elif product_tag == 'SkyBoss':
                cabinlevel = 'C'
            ssr_info = cls.baggage_parse(
                segments=segments,
                product_tag=product_tag
            )
            cabin = bundle['FareCategory']

            bundle_list.append(FlightBundleModel(
                priceInfo=price_info,
                ssrInfo=ssr_info,
                code=product_tag,
                cabinLevel=cabinlevel,
                cabin=cabin,
                fareKey=key,
                productTag=product_tag,
                seat=bundle['SeatsAvailable'],
                freightRateType=FreightRateTypeEnum.PT,
            ))
        return bundle_list
    @classmethod
    def baggage_parse(cls, product_tag: str,
                      segments: List[FlightSegmentModel]) -> FlightSsrInfoModel:
        """
        解析行李信息

        Args:
            product_tag: 套餐名
            segments: 航段
            has_child: 是否有儿童乘客

        Returns:
            List[BaggageInfoModel]: 行李信息列表
        """
        dep = segments[0].dep_airport
        arr = segments[-1].arr_airport

        bundle_rules = {
            "Eco": {
                "default": [
                    (SsrTypeEnum.HAND_BAGGAGE, 7)
                ],
            },
            "Deluxe": {
                "group2": [
                    (SsrTypeEnum.HAULING_BAGGAGE, 40),
                    (SsrTypeEnum.HAND_BAGGAGE, 10),
                ],
                "default": [
                    (SsrTypeEnum.HAULING_BAGGAGE, 20),
                    (SsrTypeEnum.HAND_BAGGAGE, 7),
                ]
            },
            "SkyBoss": {
                "group2": [
                    (SsrTypeEnum.HAULING_BAGGAGE, 50),
                    (SsrTypeEnum.HAND_BAGGAGE, 12),
                ],
                "per_group": [
                    (SsrTypeEnum.HAULING_BAGGAGE, 40),
                    (SsrTypeEnum.HAND_BAGGAGE, 12),
                ],
                "default": [
                    (SsrTypeEnum.HAULING_BAGGAGE, 30),
                    (SsrTypeEnum.HAND_BAGGAGE, 10),
                ]
            },
            "Business": {
                "group2": [
                    (SsrTypeEnum.HAULING_BAGGAGE, 60),
                    (SsrTypeEnum.HAND_BAGGAGE, 18),
                ],
                "default": [
                    (SsrTypeEnum.HAULING_BAGGAGE, 40),
                    (SsrTypeEnum.HAND_BAGGAGE, 18),
                ]
            }
        }

        GROUP2_FROM_1 = {"SYD", "MEL", "BNE", "ALA", "NQZ"}
        GROUP2_TO_1 = {"SGN", "HAN", "DAD", "PQC", "CXR"}

        GROUP2_FROM_2 = {"SGN", "HAN", "DAD", "PQC", "CXR"}
        GROUP2_TO_2 = {"SYD", "MEL", "BNE"}

        PER_FROM = {"PER"}
        PER_TO = {"SGN", "HAN"}
        SGN_HAN = {"SGN", "HAN"}

        def is_group2_route(dep, arr):
            return (
                    (dep in GROUP2_FROM_1 and arr in GROUP2_TO_1)
                    or
                    (dep in GROUP2_FROM_2 and arr in GROUP2_TO_2)
            )

        # 拼接航班号
        flights_num = "$".join(segment.flight_number for segment in segments)

        if product_tag == "Deluxe":
            if is_group2_route(dep, arr):
                ruler_key = "group2"
            else:
                ruler_key = "default"

        elif product_tag == "SkyBoss":
            if is_group2_route(dep, arr):
                ruler_key = "group2"
            elif (dep in PER_FROM and arr in PER_TO) or (dep in SGN_HAN and arr == "PER"):
                ruler_key = "per_group"
            else:
                ruler_key = "default"

        elif product_tag == "Business":
            if is_group2_route(dep, arr):
                ruler_key = "group2"
            else:
                ruler_key = "default"

        elif product_tag == "Eco":
            ruler_key = "default"

        else:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "行李规格匹配异常")

        # 构造行李类型列表
        baggage_types = bundle_rules.get(product_tag).get(ruler_key)
        # 确定乘客类型

        # 构造行李信息列表
        baggage_list = [{
                'baggageType': baggage_type[0],  # 行李类型
                'pieces': 1,  # 件数
                'flightNumber': flights_num,  # 航班号
                'totalWeight': baggage_type[1],  # 总重量
                'weightUnit': 'kg'  # 重量单位
            }
            for baggage_type in baggage_types
        ]
        ssr_info = FlightSsrInfoModel()
        temp_ssr_list = []
        for baggage_data in baggage_list:
            temp_ssr_list.append(FlightBaggageModel(
                type=baggage_data['baggageType'],
                price=Decimal(0),
                weight=baggage_data['totalWeight'],
                number=1
            ))
        ssr_info.baggage = temp_ssr_list
        return ssr_info

    @staticmethod
    def verify_price_parse(verify_price_resp, adult_count: int, child_count: int, currency: str):
        adt_fare, adt_tax, chd_fare, chd_tax = 0, 0, 0, 0

        for price_info in [verify_price_resp['data']['departure'], verify_price_resp['data']['arrival']]:
            if price_info is None:
                continue
            for key_name, price_row in price_info.items():
                if key_name == "fares":
                    for r in price_row['charges']:
                        if r['code'] == 'FA':
                            adt_fare += r['totalbaseamount'] / r['count']
                            chd_fare += r['totalbaseamount'] / r['count']
                        elif r['groupname'] == 'VAT':
                            adt_tax += r['totalbaseamount'] / (adult_count + child_count)
                            chd_tax += r['totalbaseamount'] / (adult_count + child_count)
                        else:
                            adt_tax += r['totalbaseamount'] / r['count']
                            chd_tax += r['totalbaseamount'] / r['count']

                else:
                    for r in price_row['charges']:
                        if r['groupname'] == 'VAT':
                            adt_tax += r['totalbaseamount'] / (adult_count + child_count)
                            chd_tax += r['totalbaseamount'] / (adult_count + child_count)
                        elif not any(x in r['groupname'].lower() for x in ["chd", "chid", "child"]):
                            if r['count'] == adult_count + child_count:
                                adt_tax += r['totalbaseamount'] / r['count']
                                chd_tax += r['totalbaseamount'] / r['count']
                            elif r['count'] == adult_count:
                                adt_tax += r['totalbaseamount'] / r['count']
                            elif r['groupname'] == 'VAT':
                                adt_tax += r['totalbaseamount'] / (adult_count + child_count)
                                chd_tax += r['totalbaseamount'] / (adult_count + child_count)
                            elif r['groupname'] == 'User Development Fee':
                                adt_tax += r['totalbaseamount'] / (adult_count + child_count)
                                chd_tax += r['totalbaseamount'] / (adult_count + child_count)
                            else:
                                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "税费格式化失败")
                        elif any(x in r['groupname'].lower() for x in ["chd", "chid", "child"]):
                            chd_tax += r['totalbaseamount'] / r['count']
                        else:
                            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "税费格式化失败")

        return FlightBundlePriceModel(
            adultTicketPrice=adt_fare,
            adultTaxPrice=adt_tax,
            childTicketPrice=adt_fare if child_count == 0 else chd_fare,
            childTaxPrice=adt_tax if child_count == 0 else chd_tax,
            currency=currency,

        )