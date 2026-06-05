# -*- coding: utf-8 -*-
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Tuple, Any, Union

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from flights.batik.config import Config


class FlightParser:
    @classmethod
    def parse_flight_data(cls, data: dict) -> List[FlightJourneyModel]:
        result_data_list = []
        fare_families = data["data"]["fareFamilies"]
        for index, itinerarie in enumerate(data['data']['brandedResults']['itineraryPartBrands'], start=1):
            for fare in itinerarie:
                segments = cls.segment_parser(fare['itineraryPart']['segments'], index=index)
                if len(segments) != 1 or fare['itineraryPart']['stops'] != 0:
                    continue
                familie_data = cls._get_famliles_data(fare_families, str(fare['itineraryPart']['programIDs'][0]))
                print(familie_data)
                bundles = cls.bundle_parser(fare['brandOffers'], familie_data)

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
    def _get_famliles_data(cls, fare_families: List, program_id: str) -> dict:
        product_tag_dict = {}
        for fare_familie in fare_families:
            brand_id = fare_familie['brandId']
            tag = None
            for brand_label in fare_familie['brandLabel']:
                if brand_label['programId'] == program_id and brand_label['languageId'] == 'en_US':
                    tag = brand_label['marketingText']
            data_list = []
            # ---- 处理 marketingTexts, 解析 baggage 数据 ----
            for mt in fare_familie.get('marketingTexts', []):
                if str(mt['programId']) == program_id and mt['languageId'] == 'en_US':
                    data_list.append(
                        cls._extract_brand_data(mt['marketingText'])
                    )
            product_tag_dict[brand_id] = {
                'tag': tag,
                'data_list': data_list
            }
        return product_tag_dict

    @classmethod
    def segment_parser(cls, segs_data: List[dict], index: int) -> List[FlightSegmentModel]:
        segment_list = []
        for segment in segs_data:
            segment_key = '1'
            carrier = segment['flight']['airlineCode']
            flight_number = carrier + str(segment['flight']['flightNumber'])
            operating_carrier = segment['flight']['operatingAirlineCode']
            operating_flight_number = operating_carrier + str(segment['flight']['operatingFlightNumber'])
            dep_airport = segment['origin']['locationCode']
            arr_airport = segment['destination']['locationCode']

            dep_time = datetime.strptime(segment['departure'], '%Y-%m-%dT%H:%M:%S')
            arr_time = datetime.strptime(segment['arrival'], '%Y-%m-%dT%H:%M:%S')

            segment_list.append(FlightSegmentModel(
                segmentKey=segment_key,
                depAirport=dep_airport,
                arrAirport=arr_airport,
                depTime=dep_time,
                arrTime=arr_time,
                carrier=carrier,
                flightNumber=flight_number,
                operatingCarrier=operating_carrier,
                operatingFlightNumber=operating_flight_number,
                routeIndex=index,
                legIndex=index,
            ))

        return segment_list

    @classmethod
    def bundle_parser(cls, data: List[dict], familie_data) -> List[FlightBundleModel]:
        bundle_list: List[FlightBundleModel] = []
        for bundle_data in data:
            seats = bundle_data['seatsRemaining']['count']
            if seats <= 0:
                continue
            # 基本票价/税金
            fare = bundle_data['priceByPassengerTypes'][0]['fare']['amount'] / bundle_data['priceByPassengerTypes'][0]['passengerQuantity']
            tax = bundle_data['priceByPassengerTypes'][0]['taxes']['amount'] / bundle_data['priceByPassengerTypes'][0]['passengerQuantity']
            currency = bundle_data['priceByPassengerTypes'][0]['total']['code']
            price_info = FlightBundlePriceModel(
                adultTicketPrice=fare,
                adultTaxPrice=tax,
                childTicketPrice=fare,
                childTaxPrice=tax,
                currency=currency,

            )
            code = bundle_data['brandId']
            ssr_info = FlightSsrInfoModel()
            temp_ssr_list = []
            baggage_datas = familie_data[code]
            for baggage_data in baggage_datas['data_list']:
                for baggage in baggage_data:
                    temp_ssr_list.append(FlightBaggageModel(
                        type=SsrTypeEnum(baggage['type']),
                        price=Decimal(0),
                        weight=baggage['weight'],
                        number=1
                    ))
            ssr_info.baggage = temp_ssr_list
            bundle_list.append(FlightBundleModel(
                priceInfo=price_info,
                ssrInfo=ssr_info,
                code=code,
                cabinLevel='Y' if bundle_data.get('cabinClass') == 'Economy' else 'C',
                cabin=bundle_data['fareBasisCode'][0],
                fareKey=str(bundle_data['shoppingBasketHashCode']),
                productTag=familie_data[code]['tag'],
                seat=seats,
                freightRateType=FreightRateTypeEnum.PT,
            ))
        return bundle_list

    @staticmethod
    def _extract_brand_data(marketing: str) -> List[Dict]:
        """
        从 marketingText 中提取行李信息列表
        Args:
            marketing:

        Returns:

        """
        patterns = [
            *((p, SsrTypeEnum.HAULING_BAGGAGE, False) for p in Config.PATTERNS_CHECK),
            *((p, SsrTypeEnum.HAND_BAGGAGE, True) for p in Config.PATTERNS_HAND),
        ]
        data = []
        for patt, btype, has_piece in patterns:
            m = re.search(patt, marketing, re.IGNORECASE)
            if not m:
                continue
            if btype is SsrTypeEnum.HAULING_BAGGAGE:
                pieces, weight = -1, int(m.group(1))
            else:
                pieces = int(m.group(1)) if has_piece and len(m.groups()) > 1 else -1
                weight = int(m.group(2)) if has_piece and len(m.groups()) > 1 else int(m.group(1))
            data.append({'type': btype.value, 'pieces': pieces, 'weight': weight})
        return data


if __name__ == '__main__':
    null = None
    false = False
    true = True
    data = {
        "data": {
            "fareFamilies": [
                {
                    "brandId": "SS",
                    "brandLabel": [
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "SUPER SAVER"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "SUPER SAVER"
                        },
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "SUPER SAVER"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "SUPER SAVER"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "SUPER SAVER"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "SUPER SAVER"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "SUPER SAVER"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "SUPER SAVER"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "SUPER SAVER"
                        }
                    ],
                    "marketingTexts": [
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//无托运行李//</p></font><font><p>1件手提行李 7公斤//</p></font><font><p>付费选座//</p></font><font><p>改期 - 需支付服务费和价差//</p></font><font><p>无法灵活调整搭乘更早的航班//</p></font><font><p>不可退票</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//无托运行李//</p></font><font><p>1件手提行李 7公斤//</p></font><font><p>付费选座//</p></font><font><p>改期 - 需支付服务费和价差//</p></font><font><p>无法灵活调整搭乘更早的航班//</p></font><font><p>不可退票</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//NO FREE CHECKED BAGGAGE ALLOWANCE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SEAT SELECTION WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO FLEXIBILITY TO BOARD EARLIER FLIGHT//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND NOT ALLOWED</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//무료 위탁 수하물 허용량 없음//</p></font><font><p>기내 수하물 7kg 1개//</p></font><font><p>유료 좌석 지정//</p></font><font><p>수수료 지불후 재예약 가능 - 요금차액 적용//</p></font><font><p>이전 항공편 탑승 불가//</p></font><font><p>환불 불가</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//NO FREE CHECKED BAGGAGE ALLOWANCE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SEAT SELECTION WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO FLEXIBILITY TO BOARD EARLIER FLIGHT//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND NOT ALLOWED</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//NO FREE CHECKED BAGGAGE ALLOWANCE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SEAT SELECTION WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO FLEXIBILITY TO BOARD EARLIER FLIGHT//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND NOT ALLOWED</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//NO FREE CHECKED BAGGAGE ALLOWANCE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SEAT SELECTION WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO FLEXIBILITY TO BOARD EARLIER FLIGHT//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND NOT ALLOWED</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//NO FREE CHECKED BAGGAGE ALLOWANCE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SEAT SELECTION WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO FLEXIBILITY TO BOARD EARLIER FLIGHT//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND NOT ALLOWED</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//NO FREE CHECKED BAGGAGE ALLOWANCE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SEAT SELECTION WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO FLEXIBILITY TO BOARD EARLIER FLIGHT//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND NOT ALLOWED</FONT></P>"
                        }
                    ]
                },
                {
                    "brandId": "VL",
                    "brandLabel": [
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "VALUE"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "VALUE"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "VALUE"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "VALUE"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "VALUE"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "VALUE"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "VALUE"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "VALUE"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "VALUE"
                        }
                    ],
                    "marketingTexts": [
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 15KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY STANDARD SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1ST REBOOKING FREE OF CHARGE-FARE DIFFERENCE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//含托运行李 10公斤//</p></font><font><p>1件手提行李 7公斤//</p></font><font><p>免费选座标准座位//</p></font><font><p>1次免更改手续费-需支付票价差额//</p></font><font><p>灵活享受旅行当天候补更早航班-视座位供应情况而定//</p></font><font><p>可退票 -需付费</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//含托运行李 10公斤//</p></font><font><p>1件手提行李 7公斤//</p></font><font><p>免费选座标准座位//</p></font><font><p>1次免更改手续费-需支付票价差额//</p></font><font><p>灵活享受旅行当天候补更早航班-视座位供应情况而定//</p></font><font><p>可退票 -需付费</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//위탁 수하물 허용량 10kg//</p></font><font><p>수하물 1개 7kg//</p></font><font><p>무료로 일반 좌석 선택 가능//</p></font><font><p>첫 번째 재예약은 무료로 가능 - 요금 차액 적용//</p></font><font><p>좌석 상황에 따라 여행 당일 더 이른 항공편에 탑승 가능//</p></font><font><p>수수료 지불 후 환불 가능</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 15KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY STANDARD SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1ST REBOOKING FREE OF CHARGE-FARE DIFFERENCE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 15KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY STANDARD SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1ST REBOOKING FREE OF CHARGE-FARE DIFFERENCE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 15KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY STANDARD SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1ST REBOOKING FREE OF CHARGE-FARE DIFFERENCE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 15KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY STANDARD SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1ST REBOOKING FREE OF CHARGE-FARE DIFFERENCE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 15KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY STANDARD SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1ST REBOOKING FREE OF CHARGE-FARE DIFFERENCE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        }
                    ]
                },
                {
                    "brandId": "FL",
                    "brandLabel": [
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "FLEXI"
                        }
                    ],
                    "marketingTexts": [
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 25KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//위탁 수하물 허용량 20kg//</p></font><font><p>기내 수하물 7kg 1개//</p></font><font><p>무료 스낵/기내식 및 음료//</p></font><font><p>무료로 일반 좌석 선택 가능//</p></font><font><p>무료로 무제한 재예약 가능 - 요금 차액 적용//</p></font><font><p>좌석 상황에 따라 여행 당일 더 이른 항공편에 탑승 가능//</p></font><font><p>수수료 지불 후 환불 가능</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//含托运行李 20公斤//</p></font><font><p>1件手提行李 7公斤//</p></font><font><p>免费小食//</p></font><font><p>免费选位//</p></font><font><p>无限次免费改期-须支付票价差额//</p></font><font><p>灵活享受旅行当天候补更早航班-视座位供应情况而定//</p></font><font><p>可退票 -需付费</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//含托运行李 20公斤//</p></font><font><p>1件手提行李 7公斤//</p></font><font><p>免费小食//</p></font><font><p>免费选位//</p></font><font><p>无限次免费改期-须支付票价差额//</p></font><font><p>灵活享受旅行当天候补更早航班-视座位供应情况而定//</p></font><font><p>可退票 -需付费</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 25KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 25KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 25KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 25KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 25KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">1 PIECE CABIN BAGGAGE OF 7KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        }
                    ]
                },
                {
                    "brandId": "BP",
                    "brandLabel": [
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "BUSINESS PROMO"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "BUSINESS PROMO"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "BUSINESS PROMO"
                        },
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "BUSINESS PROMO"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "BUSINESS PROMO"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "BUSINESS PROMO"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "BUSINESS PROMO"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "BUSINESS PROMO"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "BUSINESS PROMO"
                        }
                    ],
                    "marketingTexts": [
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//위탁 수하물 허용량 30kg//</p></font><font><p>기내 수하물 최대 2개, 총 10kg//</p></font><font><p>무료 스낵/기내식 및 음료//</p></font><font><p>무료로 일반 좌석 선택 가능//</p></font><font><p>수수료 지불후 재예약 가능 - 요금차액 적용//</p></font><font><p>우선 탑승//</p></font><font><p>우선 체크인//</p></font><font><p>수하물 우선 위탁//</p></font><font><p>좌석 상황에 따라 여행 당일 더 이른 항공편에 탑승 가능//</p></font><font><p>수수료 지불 후 환불 가능//</p></font><font><p>라운지 이용 불가</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//含托运行李 30公斤//</p></font><font><p>2件手提行李共 10公斤//</p></font><font><p>免费小食 / 餐点和饮料//</p></font><font><p>免费选位//</p></font><font><p>改期 - 需支付服务费和价差//</p></font><font><p>优先登机//</p></font><font><p>优先值机//</p></font><font><p>优先处理行李//</p></font><font><p>灵活享受旅行当天候补更早航班-视座位供应情况而定//</p></font><font><p>可退票 -需付费//</p></font><font><p>无休息室使用权</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//含托运行李 30公斤//</p></font><font><p>2件手提行李共 10公斤//</p></font><font><p>免费小食 / 餐点和饮料//</p></font><font><p>免费选位//</p></font><font><p>改期 - 需支付服务费和价差//</p></font><font><p>优先登机//</p></font><font><p>优先值机//</p></font><font><p>优先处理行李//</p></font><font><p>灵活享受旅行当天候补更早航班-视座位供应情况而定//</p></font><font><p>可退票 -需付费//</p></font><font><p>无休息室使用权</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 30KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 30KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 30KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 30KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 30KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 30KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REBOOKING WITH A FEE-FARE DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">NO LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        }
                    ]
                },
                {
                    "brandId": "BF",
                    "brandLabel": [
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "BUSINESS FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "BUSINESS FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "BUSINESS FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "BUSINESS FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "BUSINESS FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "BUSINESS FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "BUSINESS FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "BUSINESS FLEXI"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "BUSINESS FLEXI"
                        }
                    ],
                    "marketingTexts": [
                        {
                            "programId": "246938",
                            "languageId": "ko_KR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//위탁 수하물 허용량 40kg//</p></font><font><p>기내 수하물 최대 2개, 총 10kg//</p></font><font><p>무료 스낵/기내식 및 음료//</p></font><font><p>무료로 일반 좌석 선택 가능//</p></font><font><p>무료로 무제한 재예약 가능 - 요금 차액 적용//</p></font><font><p>우선 탑승//</p></font><font><p>우선 체크인//</p></font><font><p>수하물 우선 위탁//</p></font><font><p>좌석 상황에 따라 여행 당일 더 이른 항공편에 탑승 가능//</p></font><font><p>수수료 지불 후 환불 가능//</p></font><font><p>라운지 이용</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "en_US",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 40KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_TW",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//含托运行李 40公斤//</p></font><font><p>2件手提行李共 10公斤//</p></font><font><p>免费小食/餐点和饮料//</p></font><font><p>免费选位//</p></font><font><p>无限次免费改期-须支付票价差额//</p></font><font><p>优先登机//</p></font><font><p>优先值机//</p></font><font><p>优先处理行李//</p></font><font><p>灵活享受旅行当天候补更早航班-视座位供应情况而定//</p></font><font><p>可退票-需付费//</p></font><font><p>拥有休息室使用权</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "zh_CN",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\"><font><p>//含托运行李 40公斤//</p></font><font><p>2件手提行李共 10公斤//</p></font><font><p>免费小食/餐点和饮料//</p></font><font><p>免费选位//</p></font><font><p>无限次免费改期-须支付票价差额//</p></font><font><p>优先登机//</p></font><font><p>优先值机//</p></font><font><p>优先处理行李//</p></font><font><p>灵活享受旅行当天候补更早航班-视座位供应情况而定//</p></font><font><p>可退票-需付费//</p></font><font><p>拥有休息室使用权</p></font></FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "fr_FR",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 40KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "de_DE",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 40KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ja_JP",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 40KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "ru_RU",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 40KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        },
                        {
                            "programId": "246938",
                            "languageId": "vi_VI",
                            "marketingText": "<P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">//CHECKED BAGGAGE ALLOWANCE 40KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">MAX 2 PIECES CABIN BAGGAGE TOTAL 10 KG//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SNACKS/MEALS AND BEVERAGES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">COMPLIMENTARY SEAT SELECTION//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">UNLIMITED REBOOKING FREE OF CHARGE-FARE</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">DIFFERENCE APPLIES//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BOARDING//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY CHECKIN//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">PRIORITY BAGGAGE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">FLEXIBILITY TO BOARD EARLIER ON DAY OF TRAVEL-</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">SUBJECT TO AVAILABILITY//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">REFUND ALLOWED WITH A FEE//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">LOUNGE ACCESS//</FONT></P><P ALIGN=\"LEFT\"><FONT FACE=\"VERDANA\" SIZE=\"11\" COLOR=\"#333333\" LETTERSPACING=\"0\" KERNING=\"0\">EARN POINTS</FONT></P>"
                        }
                    ]
                }
            ],
            "brandedResults": {
                "itineraryPartBrands": [
                    [
                        {
                            "itineraryPart": {
                                "segments": [
                                    {
                                        "duration": 180,
                                        "cabinClass": "Economy",
                                        "equipment": "738",
                                        "flight": {
                                            "flightNumber": 1900,
                                            "operatingFlightNumber": 1900,
                                            "airlineCode": "OD",
                                            "operatingAirlineCode": "OD",
                                            "stopAirports": [],
                                            "departureTerminal": null,
                                            "arrivalTerminal": null
                                        },
                                        "origin": {
                                            "locationCode": "KUL",
                                            "locationName": "Kuala Lumpur (KLIA)",
                                            "countryCode": "MY"
                                        },
                                        "destination": {
                                            "locationCode": "TWU",
                                            "locationName": "Tawau",
                                            "countryCode": "MY"
                                        },
                                        "departure": "2026-03-15T06:50:00",
                                        "arrival": "2026-03-15T09:50:00",
                                        "segmentStatusCode": null,
                                        "bookingClass": "M",
                                        "layoverDuration": 0,
                                        "fareBasis": "MODBSSMY",
                                        "meals": null,
                                        "segmentNumber": 0,
                                        "segmentType": 0
                                    }
                                ],
                                "stops": 0,
                                "totalDuration": 180,
                                "connectionInformations": null,
                                "bookingClass": "M",
                                "programIDs": [
                                    246938
                                ]
                            },
                            "brandOffers": [
                                {
                                    "shoppingBasketHashCode": 1938300033,
                                    "brandId": "SS",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 9,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 1258,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 238,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1020,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 629,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 119,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 510,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 1887,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 357,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 1530,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 123,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 15,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 156,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M",
                                    "fareBasisCode": "MODBSSMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": -1765786562,
                                    "brandId": "VL",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 9,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 1518,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 258,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1260,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 759,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 129,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 630,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 2277,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 387,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 1890,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 153,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 15,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 156,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M",
                                    "fareBasisCode": "MODBVLMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": 1989986867,
                                    "brandId": "FL",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 9,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 1648,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 268,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1380,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 824,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 134,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 690,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 2472,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 402,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 2070,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 168,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 15,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 156,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M",
                                    "fareBasisCode": "MODBFXMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": 718150954,
                                    "brandId": "BP",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 4,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Business",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 2964,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 364,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 2600,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 1482,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 182,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1300,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 4446,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 546,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 3900,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 15,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 156,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "D",
                                    "fareBasisCode": "DODBBPMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": -131683387,
                                    "brandId": "BF",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 4,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Business",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 5082,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 522,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 4560,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 2541,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 261,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 2280,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 7623,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 783,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 6840,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 549,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 15,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 156,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "D",
                                    "fareBasisCode": "DODBBFMY",
                                    "status": null,
                                    "departureDates": null
                                }
                            ]
                        },
                        {
                            "itineraryPart": {
                                "segments": [
                                    {
                                        "duration": 150,
                                        "cabinClass": "Economy",
                                        "equipment": "738",
                                        "flight": {
                                            "flightNumber": 1002,
                                            "operatingFlightNumber": 1002,
                                            "airlineCode": "OD",
                                            "operatingAirlineCode": "OD",
                                            "stopAirports": [],
                                            "departureTerminal": "1",
                                            "arrivalTerminal": "1"
                                        },
                                        "origin": {
                                            "locationCode": "KUL",
                                            "locationName": "Kuala Lumpur (KLIA)",
                                            "countryCode": "MY"
                                        },
                                        "destination": {
                                            "locationCode": "BKI",
                                            "locationName": "Kota Kinabalu",
                                            "countryCode": "MY"
                                        },
                                        "departure": "2026-03-15T07:30:00",
                                        "arrival": "2026-03-15T10:00:00",
                                        "segmentStatusCode": null,
                                        "bookingClass": "M",
                                        "layoverDuration": 0,
                                        "fareBasis": "MRDBSSMY",
                                        "meals": null,
                                        "segmentNumber": 0,
                                        "segmentType": 0
                                    },
                                    {
                                        "duration": 55,
                                        "cabinClass": "Economy",
                                        "equipment": "738",
                                        "flight": {
                                            "flightNumber": 1700,
                                            "operatingFlightNumber": 1700,
                                            "airlineCode": "OD",
                                            "operatingAirlineCode": "OD",
                                            "stopAirports": [],
                                            "departureTerminal": null,
                                            "arrivalTerminal": null
                                        },
                                        "origin": {
                                            "locationCode": "BKI",
                                            "locationName": "Kota Kinabalu",
                                            "countryCode": "MY"
                                        },
                                        "destination": {
                                            "locationCode": "TWU",
                                            "locationName": "Tawau",
                                            "countryCode": "MY"
                                        },
                                        "departure": "2026-03-15T11:35:00",
                                        "arrival": "2026-03-15T12:30:00",
                                        "segmentStatusCode": null,
                                        "bookingClass": "M",
                                        "layoverDuration": 0,
                                        "fareBasis": "MRDBSSMY",
                                        "meals": null,
                                        "segmentNumber": 0,
                                        "segmentType": 0
                                    }
                                ],
                                "stops": 1,
                                "totalDuration": 300,
                                "connectionInformations": null,
                                "bookingClass": "M",
                                "programIDs": [
                                    246938
                                ]
                            },
                            "brandOffers": [
                                {
                                    "shoppingBasketHashCode": 130381353,
                                    "brandId": "SS",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 6,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 1872,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 412,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1460,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 936,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 206,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 730,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 2808,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 618,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 2190,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 177,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M,M",
                                    "fareBasisCode": "MRDBSSMY,MRDBSSMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": -1757158318,
                                    "brandId": "VL",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 6,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 2436,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 456,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1980,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 1218,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 228,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 990,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 3654,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 684,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 2970,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 243,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M,M",
                                    "fareBasisCode": "MRDBVLMY,MRDBVLMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": -992507895,
                                    "brandId": "FL",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 6,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 3428,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 528,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 2900,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 1714,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 264,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1450,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 5142,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 792,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 4350,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 351,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M,M",
                                    "fareBasisCode": "MRDBFXMY,MRDBFXMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": 831737330,
                                    "brandId": "BP",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 4,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Business",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 4054,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 574,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 3480,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 2027,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 287,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1740,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 6081,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 861,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 5220,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 420,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "D,I",
                                    "fareBasisCode": "DRDBBPMY,IRDBBPMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": 1010871497,
                                    "brandId": "BF",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 4,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Business",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 7792,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 852,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 6940,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 3896,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 426,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 3470,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 11688,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 1278,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 10410,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 837,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "D,I",
                                    "fareBasisCode": "DRDBBFMY,IRDBBFMY",
                                    "status": null,
                                    "departureDates": null
                                }
                            ]
                        },
                        {
                            "itineraryPart": {
                                "segments": [
                                    {
                                        "duration": 150,
                                        "cabinClass": "Economy",
                                        "equipment": "738",
                                        "flight": {
                                            "flightNumber": 1002,
                                            "operatingFlightNumber": 1002,
                                            "airlineCode": "OD",
                                            "operatingAirlineCode": "OD",
                                            "stopAirports": [],
                                            "departureTerminal": "1",
                                            "arrivalTerminal": "1"
                                        },
                                        "origin": {
                                            "locationCode": "KUL",
                                            "locationName": "Kuala Lumpur (KLIA)",
                                            "countryCode": "MY"
                                        },
                                        "destination": {
                                            "locationCode": "BKI",
                                            "locationName": "Kota Kinabalu",
                                            "countryCode": "MY"
                                        },
                                        "departure": "2026-03-15T07:30:00",
                                        "arrival": "2026-03-15T10:00:00",
                                        "segmentStatusCode": null,
                                        "bookingClass": "M",
                                        "layoverDuration": 0,
                                        "fareBasis": "MRDBSSMY",
                                        "meals": null,
                                        "segmentNumber": 0,
                                        "segmentType": 0
                                    },
                                    {
                                        "duration": 55,
                                        "cabinClass": "Economy",
                                        "equipment": "738",
                                        "flight": {
                                            "flightNumber": 1704,
                                            "operatingFlightNumber": 1704,
                                            "airlineCode": "OD",
                                            "operatingAirlineCode": "OD",
                                            "stopAirports": [],
                                            "departureTerminal": null,
                                            "arrivalTerminal": null
                                        },
                                        "origin": {
                                            "locationCode": "BKI",
                                            "locationName": "Kota Kinabalu",
                                            "countryCode": "MY"
                                        },
                                        "destination": {
                                            "locationCode": "TWU",
                                            "locationName": "Tawau",
                                            "countryCode": "MY"
                                        },
                                        "departure": "2026-03-15T15:30:00",
                                        "arrival": "2026-03-15T16:25:00",
                                        "segmentStatusCode": null,
                                        "bookingClass": "M",
                                        "layoverDuration": 0,
                                        "fareBasis": "MRDBSSMY",
                                        "meals": null,
                                        "segmentNumber": 0,
                                        "segmentType": 0
                                    }
                                ],
                                "stops": 1,
                                "totalDuration": 535,
                                "connectionInformations": null,
                                "bookingClass": "M",
                                "programIDs": [
                                    246938
                                ]
                            },
                            "brandOffers": [
                                {
                                    "shoppingBasketHashCode": -1566205727,
                                    "brandId": "SS",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 6,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 1872,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 412,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1460,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 936,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 206,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 730,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 2808,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 618,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 2190,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 177,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M,M",
                                    "fareBasisCode": "MRDBSSMY,MRDBSSMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": 841221898,
                                    "brandId": "VL",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 6,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 2436,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 456,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1980,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 1218,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 228,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 990,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 3654,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 684,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 2970,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 243,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M,M",
                                    "fareBasisCode": "MRDBVLMY,MRDBVLMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": 1605872321,
                                    "brandId": "FL",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 6,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 3428,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 528,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 2900,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 1714,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 264,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1450,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 5142,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 792,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 4350,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 351,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M,M",
                                    "fareBasisCode": "MRDBFXMY,MRDBFXMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": -864849750,
                                    "brandId": "BP",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 4,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Business",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 4054,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 574,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 3480,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 2027,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 287,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1740,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 6081,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 861,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 5220,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 420,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "D,I",
                                    "fareBasisCode": "DRDBBPMY,IRDBBPMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": -685715583,
                                    "brandId": "BF",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 4,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Business",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 7792,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 852,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 6940,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 3896,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 426,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 3470,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 11688,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 1278,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 10410,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 837,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "D,I",
                                    "fareBasisCode": "DRDBBFMY,IRDBBFMY",
                                    "status": null,
                                    "departureDates": null
                                }
                            ]
                        },
                        {
                            "itineraryPart": {
                                "segments": [
                                    {
                                        "duration": 150,
                                        "cabinClass": "Economy",
                                        "equipment": "738",
                                        "flight": {
                                            "flightNumber": 1004,
                                            "operatingFlightNumber": 1004,
                                            "airlineCode": "OD",
                                            "operatingAirlineCode": "OD",
                                            "stopAirports": [],
                                            "departureTerminal": "1",
                                            "arrivalTerminal": "1"
                                        },
                                        "origin": {
                                            "locationCode": "KUL",
                                            "locationName": "Kuala Lumpur (KLIA)",
                                            "countryCode": "MY"
                                        },
                                        "destination": {
                                            "locationCode": "BKI",
                                            "locationName": "Kota Kinabalu",
                                            "countryCode": "MY"
                                        },
                                        "departure": "2026-03-15T12:00:00",
                                        "arrival": "2026-03-15T14:30:00",
                                        "segmentStatusCode": null,
                                        "bookingClass": "M",
                                        "layoverDuration": 0,
                                        "fareBasis": "MRDBSSMY",
                                        "meals": null,
                                        "segmentNumber": 0,
                                        "segmentType": 0
                                    },
                                    {
                                        "duration": 55,
                                        "cabinClass": "Economy",
                                        "equipment": "738",
                                        "flight": {
                                            "flightNumber": 1704,
                                            "operatingFlightNumber": 1704,
                                            "airlineCode": "OD",
                                            "operatingAirlineCode": "OD",
                                            "stopAirports": [],
                                            "departureTerminal": null,
                                            "arrivalTerminal": null
                                        },
                                        "origin": {
                                            "locationCode": "BKI",
                                            "locationName": "Kota Kinabalu",
                                            "countryCode": "MY"
                                        },
                                        "destination": {
                                            "locationCode": "TWU",
                                            "locationName": "Tawau",
                                            "countryCode": "MY"
                                        },
                                        "departure": "2026-03-15T15:30:00",
                                        "arrival": "2026-03-15T16:25:00",
                                        "segmentStatusCode": null,
                                        "bookingClass": "M",
                                        "layoverDuration": 0,
                                        "fareBasis": "MRDBSSMY",
                                        "meals": null,
                                        "segmentNumber": 0,
                                        "segmentType": 0
                                    }
                                ],
                                "stops": 1,
                                "totalDuration": 265,
                                "connectionInformations": null,
                                "bookingClass": "M",
                                "programIDs": [
                                    246938
                                ]
                            },
                            "brandOffers": [
                                {
                                    "shoppingBasketHashCode": 1067554461,
                                    "brandId": "SS",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 9,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 1872,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 412,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1460,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 936,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 206,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 730,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 2808,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 618,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 2190,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 177,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M,M",
                                    "fareBasisCode": "MRDBSSMY,MRDBSSMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": -819985210,
                                    "brandId": "VL",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 9,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 2436,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 456,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1980,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 1218,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 228,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 990,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 3654,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 684,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 2970,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 243,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M,M",
                                    "fareBasisCode": "MRDBVLMY,MRDBVLMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": -55334787,
                                    "brandId": "FL",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 9,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Economy",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 3428,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 528,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 2900,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 1714,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 264,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1450,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 5142,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 792,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 4350,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 351,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "M,M",
                                    "fareBasisCode": "MRDBFXMY,MRDBFXMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": 1768910438,
                                    "brandId": "BP",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 4,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Business",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 4054,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 574,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 3480,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 2027,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 287,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 1740,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 6081,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 861,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 5220,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 420,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "D,I",
                                    "fareBasisCode": "DRDBBPMY,IRDBBPMY",
                                    "status": null,
                                    "departureDates": null
                                },
                                {
                                    "shoppingBasketHashCode": 1948044605,
                                    "brandId": "BF",
                                    "soldout": false,
                                    "seatsRemaining": {
                                        "count": 4,
                                        "lowAvailability": false
                                    },
                                    "cabinClass": "Business",
                                    "priceByPassengerTypes": [
                                        {
                                            "passengerType": "ADT",
                                            "passengerQuantity": 2,
                                            "total": {
                                                "amount": 7792,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 852,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 6940,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        },
                                        {
                                            "passengerType": "CHD",
                                            "passengerQuantity": 1,
                                            "total": {
                                                "amount": 3896,
                                                "code": "CNY"
                                            },
                                            "totalWithoutDiscount": null,
                                            "taxes": {
                                                "amount": 426,
                                                "code": "CNY"
                                            },
                                            "fare": {
                                                "amount": 3470,
                                                "code": "CNY"
                                            },
                                            "taxesBreakdown": null
                                        }
                                    ],
                                    "total": {
                                        "amount": 11688,
                                        "code": "CNY"
                                    },
                                    "totalWithoutDiscount": null,
                                    "taxes": {
                                        "amount": 1278,
                                        "code": "CNY"
                                    },
                                    "fare": {
                                        "amount": 10410,
                                        "code": "CNY"
                                    },
                                    "itineraryPart": null,
                                    "taxesBreakdowns": [
                                        {
                                            "taxCode": "D8",
                                            "taxName": "Service Tax (D8)",
                                            "price": {
                                                "amount": 837,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "D83",
                                            "taxName": "",
                                            "price": {
                                                "amount": 30,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "H8",
                                            "taxName": "Regulatory Charge Domestic And International (H8)",
                                            "price": {
                                                "amount": 6,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY",
                                            "taxName": "Passenger Service And Security Charge (MY)",
                                            "price": {
                                                "amount": 57,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "MY3",
                                            "taxName": "",
                                            "price": {
                                                "amount": 36,
                                                "code": "CNY"
                                            }
                                        },
                                        {
                                            "taxCode": "YQF",
                                            "taxName": "Fuel Surcharge (YQF)",
                                            "price": {
                                                "amount": 312,
                                                "code": "CNY"
                                            }
                                        }
                                    ],
                                    "bookingClasses": "D,I",
                                    "fareBasisCode": "DRDBBFMY,IRDBBFMY",
                                    "status": null,
                                    "departureDates": null
                                }
                            ]
                        }
                    ]
                ]
            },
            "unbundledAlternateDateOffers": [
                [
                    {
                        "shoppingBasketHashCode": null,
                        "brandId": "SS",
                        "soldout": false,
                        "seatsRemaining": {
                            "count": 9,
                            "lowAvailability": false
                        },
                        "cabinClass": "Economy",
                        "priceByPassengerTypes": [
                            {
                                "passengerType": "ADT",
                                "passengerQuantity": 2,
                                "total": {
                                    "amount": 1086,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 226,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 860,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            },
                            {
                                "passengerType": "CHD",
                                "passengerQuantity": 1,
                                "total": {
                                    "amount": 543,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 113,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 430,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            }
                        ],
                        "total": {
                            "amount": 1629,
                            "code": "CNY"
                        },
                        "totalWithoutDiscount": null,
                        "taxes": {
                            "amount": 339,
                            "code": "CNY"
                        },
                        "fare": {
                            "amount": 1290,
                            "code": "CNY"
                        },
                        "itineraryPart": null,
                        "taxesBreakdowns": [
                            {
                                "taxCode": "D8",
                                "taxName": "Service Tax (D8)",
                                "price": {
                                    "amount": 105,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "D83",
                                "taxName": "",
                                "price": {
                                    "amount": 15,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "H8",
                                "taxName": "Regulatory Charge Domestic And International (H8)",
                                "price": {
                                    "amount": 6,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "MY",
                                "taxName": "Passenger Service And Security Charge (MY)",
                                "price": {
                                    "amount": 57,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "YQF",
                                "taxName": "Fuel Surcharge (YQF)",
                                "price": {
                                    "amount": 156,
                                    "code": "CNY"
                                }
                            }
                        ],
                        "bookingClasses": "N",
                        "fareBasisCode": "NODBSSMY",
                        "status": "AVAILABLE",
                        "departureDates": [
                            "2026-03-12T00:00:00"
                        ]
                    },
                    {
                        "shoppingBasketHashCode": null,
                        "brandId": "SS",
                        "soldout": false,
                        "seatsRemaining": {
                            "count": 7,
                            "lowAvailability": false
                        },
                        "cabinClass": "Economy",
                        "priceByPassengerTypes": [
                            {
                                "passengerType": "ADT",
                                "passengerQuantity": 2,
                                "total": {
                                    "amount": 1258,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 238,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 1020,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            },
                            {
                                "passengerType": "CHD",
                                "passengerQuantity": 1,
                                "total": {
                                    "amount": 629,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 119,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 510,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            }
                        ],
                        "total": {
                            "amount": 1887,
                            "code": "CNY"
                        },
                        "totalWithoutDiscount": null,
                        "taxes": {
                            "amount": 357,
                            "code": "CNY"
                        },
                        "fare": {
                            "amount": 1530,
                            "code": "CNY"
                        },
                        "itineraryPart": null,
                        "taxesBreakdowns": [
                            {
                                "taxCode": "D8",
                                "taxName": "Service Tax (D8)",
                                "price": {
                                    "amount": 123,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "D83",
                                "taxName": "",
                                "price": {
                                    "amount": 15,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "H8",
                                "taxName": "Regulatory Charge Domestic And International (H8)",
                                "price": {
                                    "amount": 6,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "MY",
                                "taxName": "Passenger Service And Security Charge (MY)",
                                "price": {
                                    "amount": 57,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "YQF",
                                "taxName": "Fuel Surcharge (YQF)",
                                "price": {
                                    "amount": 156,
                                    "code": "CNY"
                                }
                            }
                        ],
                        "bookingClasses": "M",
                        "fareBasisCode": "MODBSSMY",
                        "status": "AVAILABLE",
                        "departureDates": [
                            "2026-03-13T00:00:00"
                        ]
                    },
                    {
                        "shoppingBasketHashCode": null,
                        "brandId": "SS",
                        "soldout": false,
                        "seatsRemaining": {
                            "count": 8,
                            "lowAvailability": false
                        },
                        "cabinClass": "Economy",
                        "priceByPassengerTypes": [
                            {
                                "passengerType": "ADT",
                                "passengerQuantity": 2,
                                "total": {
                                    "amount": 1258,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 238,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 1020,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            },
                            {
                                "passengerType": "CHD",
                                "passengerQuantity": 1,
                                "total": {
                                    "amount": 629,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 119,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 510,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            }
                        ],
                        "total": {
                            "amount": 1887,
                            "code": "CNY"
                        },
                        "totalWithoutDiscount": null,
                        "taxes": {
                            "amount": 357,
                            "code": "CNY"
                        },
                        "fare": {
                            "amount": 1530,
                            "code": "CNY"
                        },
                        "itineraryPart": null,
                        "taxesBreakdowns": [
                            {
                                "taxCode": "D8",
                                "taxName": "Service Tax (D8)",
                                "price": {
                                    "amount": 123,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "D83",
                                "taxName": "",
                                "price": {
                                    "amount": 15,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "H8",
                                "taxName": "Regulatory Charge Domestic And International (H8)",
                                "price": {
                                    "amount": 6,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "MY",
                                "taxName": "Passenger Service And Security Charge (MY)",
                                "price": {
                                    "amount": 57,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "YQF",
                                "taxName": "Fuel Surcharge (YQF)",
                                "price": {
                                    "amount": 156,
                                    "code": "CNY"
                                }
                            }
                        ],
                        "bookingClasses": "M",
                        "fareBasisCode": "MODBSSMY",
                        "status": "AVAILABLE",
                        "departureDates": [
                            "2026-03-14T00:00:00"
                        ]
                    },
                    {
                        "shoppingBasketHashCode": null,
                        "brandId": "SS",
                        "soldout": false,
                        "seatsRemaining": {
                            "count": 9,
                            "lowAvailability": false
                        },
                        "cabinClass": "Economy",
                        "priceByPassengerTypes": [
                            {
                                "passengerType": "ADT",
                                "passengerQuantity": 2,
                                "total": {
                                    "amount": 1258,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 238,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 1020,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            },
                            {
                                "passengerType": "CHD",
                                "passengerQuantity": 1,
                                "total": {
                                    "amount": 629,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 119,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 510,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            }
                        ],
                        "total": {
                            "amount": 1887,
                            "code": "CNY"
                        },
                        "totalWithoutDiscount": null,
                        "taxes": {
                            "amount": 357,
                            "code": "CNY"
                        },
                        "fare": {
                            "amount": 1530,
                            "code": "CNY"
                        },
                        "itineraryPart": null,
                        "taxesBreakdowns": [
                            {
                                "taxCode": "D8",
                                "taxName": "Service Tax (D8)",
                                "price": {
                                    "amount": 123,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "D83",
                                "taxName": "",
                                "price": {
                                    "amount": 15,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "H8",
                                "taxName": "Regulatory Charge Domestic And International (H8)",
                                "price": {
                                    "amount": 6,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "MY",
                                "taxName": "Passenger Service And Security Charge (MY)",
                                "price": {

                                    "amount": 57,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "YQF",
                                "taxName": "Fuel Surcharge (YQF)",
                                "price": {
                                    "amount": 156,
                                    "code": "CNY"
                                }
                            }
                        ],
                        "bookingClasses": "M",
                        "fareBasisCode": "MODBSSMY",
                        "status": "AVAILABLE",
                        "departureDates": [
                            "2026-03-15T00:00:00"
                        ]
                    },
                    {
                        "shoppingBasketHashCode": null,
                        "brandId": "SS",
                        "soldout": false,
                        "seatsRemaining": {
                            "count": 9,
                            "lowAvailability": false
                        },
                        "cabinClass": "Economy",
                        "priceByPassengerTypes": [
                            {
                                "passengerType": "ADT",
                                "passengerQuantity": 2,
                                "total": {
                                    "amount": 1258,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 238,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 1020,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            },
                            {
                                "passengerType": "CHD",
                                "passengerQuantity": 1,
                                "total": {
                                    "amount": 629,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 119,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 510,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            }
                        ],
                        "total": {
                            "amount": 1887,
                            "code": "CNY"
                        },
                        "totalWithoutDiscount": null,
                        "taxes": {
                            "amount": 357,
                            "code": "CNY"
                        },
                        "fare": {
                            "amount": 1530,
                            "code": "CNY"
                        },
                        "itineraryPart": null,
                        "taxesBreakdowns": [
                            {
                                "taxCode": "D8",
                                "taxName": "Service Tax (D8)",
                                "price": {
                                    "amount": 123,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "D83",
                                "taxName": "",
                                "price": {
                                    "amount": 15,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "H8",
                                "taxName": "Regulatory Charge Domestic And International (H8)",
                                "price": {
                                    "amount": 6,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "MY",
                                "taxName": "Passenger Service And Security Charge (MY)",
                                "price": {
                                    "amount": 57,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "YQF",
                                "taxName": "Fuel Surcharge (YQF)",
                                "price": {
                                    "amount": 156,
                                    "code": "CNY"
                                }
                            }
                        ],
                        "bookingClasses": "M",
                        "fareBasisCode": "MODBSSMY",
                        "status": "AVAILABLE",
                        "departureDates": [
                            "2026-03-16T00:00:00"
                        ]
                    },
                    {
                        "shoppingBasketHashCode": null,
                        "brandId": "FL",
                        "soldout": false,
                        "seatsRemaining": {
                            "count": 9,
                            "lowAvailability": false
                        },
                        "cabinClass": "Economy",
                        "priceByPassengerTypes": [
                            {
                                "passengerType": "ADT",
                                "passengerQuantity": 2,
                                "total": {
                                    "amount": 2014,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 294,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 1720,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            },
                            {
                                "passengerType": "CHD",
                                "passengerQuantity": 1,
                                "total": {
                                    "amount": 1007,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 147,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 860,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            }
                        ],
                        "total": {
                            "amount": 3021,
                            "code": "CNY"
                        },
                        "totalWithoutDiscount": null,
                        "taxes": {
                            "amount": 441,
                            "code": "CNY"
                        },
                        "fare": {
                            "amount": 2580,
                            "code": "CNY"
                        },
                        "itineraryPart": null,
                        "taxesBreakdowns": [
                            {
                                "taxCode": "D8",
                                "taxName": "Service Tax (D8)",
                                "price": {
                                    "amount": 207,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "D83",
                                "taxName": "",
                                "price": {
                                    "amount": 15,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "H8",
                                "taxName": "Regulatory Charge Domestic And International (H8)",
                                "price": {
                                    "amount": 6,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "MY",
                                "taxName": "Passenger Service And Security Charge (MY)",
                                "price": {
                                    "amount": 57,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "YQF",
                                "taxName": "Fuel Surcharge (YQF)",
                                "price": {
                                    "amount": 156,
                                    "code": "CNY"
                                }
                            }
                        ],
                        "bookingClasses": "Y",
                        "fareBasisCode": "YODBFXFL",
                        "status": "AVAILABLE",
                        "departureDates": [
                            "2026-03-17T00:00:00"
                        ]
                    },
                    {
                        "shoppingBasketHashCode": null,
                        "brandId": "FL",
                        "soldout": false,
                        "seatsRemaining": {
                            "count": 9,
                            "lowAvailability": false
                        },
                        "cabinClass": "Economy",
                        "priceByPassengerTypes": [
                            {
                                "passengerType": "ADT",
                                "passengerQuantity": 2,
                                "total": {
                                    "amount": 2014,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 294,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 1720,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            },
                            {
                                "passengerType": "CHD",
                                "passengerQuantity": 1,
                                "total": {
                                    "amount": 1007,
                                    "code": "CNY"
                                },
                                "totalWithoutDiscount": null,
                                "taxes": {
                                    "amount": 147,
                                    "code": "CNY"
                                },
                                "fare": {
                                    "amount": 860,
                                    "code": "CNY"
                                },
                                "taxesBreakdown": null
                            }
                        ],
                        "total": {
                            "amount": 3021,
                            "code": "CNY"
                        },
                        "totalWithoutDiscount": null,
                        "taxes": {
                            "amount": 441,
                            "code": "CNY"
                        },
                        "fare": {
                            "amount": 2580,
                            "code": "CNY"
                        },
                        "itineraryPart": null,
                        "taxesBreakdowns": [
                            {
                                "taxCode": "D8",
                                "taxName": "Service Tax (D8)",
                                "price": {
                                    "amount": 207,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "D83",
                                "taxName": "",
                                "price": {
                                    "amount": 15,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "H8",
                                "taxName": "Regulatory Charge Domestic And International (H8)",
                                "price": {
                                    "amount": 6,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "MY",
                                "taxName": "Passenger Service And Security Charge (MY)",
                                "price": {
                                    "amount": 57,
                                    "code": "CNY"
                                }
                            },
                            {
                                "taxCode": "YQF",
                                "taxName": "Fuel Surcharge (YQF)",
                                "price": {
                                    "amount": 156,
                                    "code": "CNY"
                                }
                            }
                        ],
                        "bookingClasses": "Y",
                        "fareBasisCode": "YODBFXFL",
                        "status": "AVAILABLE",
                        "departureDates": [
                            "2026-03-18T00:00:00"
                        ]
                    }
                ]
            ],
            "resultMapping": null
        },
        "success": true,
        "message": null
    }
    search_response = FlightParser.parse_flight_data(data)
