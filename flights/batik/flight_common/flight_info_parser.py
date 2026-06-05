import re
from datetime import datetime
from decimal import Decimal
from typing import List, Dict

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from flights.batik.config import Config


class FlightInfoParser:

    @classmethod
    def journey_info_parser(cls, flight_data: dict)->List[FlightJourneyModel]:
        routes = flight_data.get('itineraries')
        if not routes:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        result_data_list = []
        for index, itinerarie in enumerate(routes,start=1):
            for fare in itinerarie['fares']:
                segments = cls.segment_parser(fare['flightSegs'], index=index)
                if len(segments) != 1 or fare['stops'] != 0:
                    continue
                bundles = cls.bundle_parser(fare['brands'])

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
        for segment in segs_data:
            segment_key = segment['segRef']
            carrier = segment['carrier']['airCode']
            flight_number = carrier + str(segment['flightNo'])
            dep_airport = segment['depPort']
            arr_airport = segment['arrPort']

            dep_time = datetime.strptime(segment['depDate'], '%Y-%m-%dT%H:%M:%S')
            arr_time = datetime.strptime(segment['arrDate'], '%Y-%m-%dT%H:%M:%S')

            segment_list.append(FlightSegmentModel(
                segmentKey=segment_key,
                depAirport=dep_airport,
                arrAirport=arr_airport,
                depTime=dep_time,
                arrTime=arr_time,
                carrier=carrier,
                flightNumber=flight_number,
                operatingCarrier=carrier,
                operatingFlightNumber=flight_number,
                routeIndex=index,
                legIndex=index,
            ))

        return segment_list

    @staticmethod
    def __extract_brand_data(marketing: str) -> List[Dict]:
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
                pieces, weight = 1, int(m.group(1))
            else:
                pieces = int(m.group(1)) if has_piece and len(m.groups()) > 1 else 1
                weight = int(m.group(2)) if has_piece and len(m.groups()) > 1 else int(m.group(1))
            data.append({'type': btype.value, 'pieces': pieces, 'weight': weight})
        return data

    @classmethod
    def bundle_parser(cls, data: List[dict]) -> List[FlightBundleModel]:
        bundle_list = []
        for bundle_data in data:
            seats = bundle_data.get('seatsRemaining', 0)
            if seats <= 0:
                continue
            if  bundle_data['brandLabel'] == 'BUSINESS FLEXI':
                pax = bundle_data['paxFareCost'][0]
                bd = pax['fareBreakDown']
                qty = bd.get('quantity', 1) or 1
                base_fare = bd['totalWithoutDiscount'] / qty
                tax_total = bd['tax']['totalTax'] / qty
                base_fare = base_fare-tax_total
                currency_code = pax['currency']
                price_info = FlightBundlePriceModel(
                    adultTicketPrice=base_fare,
                    adultTaxPrice=tax_total,
                    childTicketPrice=base_fare,
                    childTaxPrice=tax_total,
                    currency=currency_code,

                )
            else:
                # 基本票价/税金
                pax = bundle_data['paxFareCost'][0]
                bd = pax['fareBreakDown']
                qty = bd.get('quantity', 1) or 1
                base_fare = bd['baseFare'] / qty
                tax_total = bd['tax']['totalTax'] / qty
                currency_code = pax['currency']
                price_info = FlightBundlePriceModel(
                    adultTicketPrice=base_fare,
                    adultTaxPrice=tax_total,
                    childTicketPrice=base_fare,
                    childTaxPrice=tax_total,
                    currency=currency_code,

                )
            code = bundle_data['brandId']
            ssr_info = FlightSsrInfoModel()
            temp_ssr_list = []
            baggage_datas = cls.__extract_brand_data(bundle_data['marketingText'])
            for baggage_data in baggage_datas:
                temp_ssr_list.append(FlightBaggageModel(
                    type=SsrTypeEnum(baggage_data['type']),
                    price=Decimal(0),
                    weight=baggage_data['weight'],
                    number=1
                ))
            ssr_info.baggage = temp_ssr_list
            bundle_list.append(FlightBundleModel(
                priceInfo=price_info,
                ssrInfo=ssr_info,
                code=code,
                cabinLevel='Y' if bundle_data.get('class') == 'Economy' else 'C',
                cabin=bundle_data['fareBasis'][0],
                fareKey=str(bundle_data['basketHashCode']),
                productTag=bundle_data['brandLabel'],
                seat=seats,
                freightRateType=FreightRateTypeEnum.PT,
            ))
        return bundle_list
