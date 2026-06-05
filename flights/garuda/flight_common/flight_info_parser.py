from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.utils.date_util import DateUtil
from flights.garuda.config import Config


class FlightInfoParser:

    @classmethod
    def journey_info_parser(cls, flight_data: List[dict]) -> List[FlightJourneyModel]:
        journey_groups: List[List[FlightJourneyModel]] = []
        for itinerarie in flight_data:
            route_journeys = []
            route_index = itinerarie.get('routeIndex', 1)
            flights_dict_list = itinerarie['result'].get('flightData') or []
            price_dict = itinerarie['result'].get('pricingData') or {}
            for fare in flights_dict_list:
                segments = cls.segment_parser(fare, index=route_index)
                if not segments:
                    continue
                bundle_id = fare['sid']
                if bundle_id not in price_dict:
                    continue
                bundles = cls.bundle_parser(
                    bundles_list=price_dict[bundle_id],
                    bundle_id=bundle_id)
                if not bundles:
                    continue

                route_journeys.append(FlightJourneyModel(
                    journeyKey=bundle_id,
                    segments=segments,
                    bundles=bundles,
                    depAirport=segments[0].dep_airport,
                    arrAirport=segments[-1].arr_airport,
                    depTime=segments[0].dep_time,
                    arrTime=segments[-1].arr_time,
                ))
            if route_journeys:
                journey_groups.append(route_journeys)

        if len(journey_groups) == 1:
            return journey_groups[0]
        if len(journey_groups) == 2:
            return cls.link_round_trip(journey_groups[0], journey_groups[1])
        return []

    @staticmethod
    def parse_datetime(dateTime: str) -> str:
        """
        处理时间

        Args:
            dateTime: 解析航段列表dep，arr时间

        Returns:
            f'{year}{month}{day}{hour}{minute}' 格式化时间

        """
        date_str = dateTime.split('.')[0]
        date_part, time_part = date_str.split('T')
        year, month, day = date_part.split('-')
        hour, minute = time_part.split(':')[:2]
        return f'{year}{month}{day}{hour}{minute}'

    @classmethod
    def segment_parser(cls, segs_data: dict, index: int) -> List[FlightSegmentModel]:
        segment_list = []
        segs_data = segs_data['detail']

        for segment in segs_data:
            segment_key = segment['extra']['id']
            carrier = segment['marketingAirlineCode']
            flight_number = carrier + str(segment['marketingFlightNumber'])
            operating_carrier = segment.get('operatingAirlineCode') or carrier
            code_share = carrier != operating_carrier
            operating_flight_number = cls.parse_operating_flight_number(
                segment=segment,
                flight_number=flight_number,
                operating_carrier=operating_carrier,
                code_share=code_share,
            )
            if operating_flight_number is None:
                return []
            dep_airport = segment['departure']['locationCode']
            arr_airport = segment['arrival']['locationCode']

            dep_time = cls.parse_datetime(segment['departure']['dateTime'])
            arr_time = cls.parse_datetime(segment['arrival']['dateTime'])

            segment_list.append(FlightSegmentModel(
                segmentKey=segment_key,
                depAirport=dep_airport,
                arrAirport=arr_airport,
                depTime=datetime.strptime(dep_time, "%Y%m%d%H%M"),
                arrTime=datetime.strptime(arr_time, "%Y%m%d%H%M"),
                carrier=carrier,
                flightNumber=flight_number,
                operatingCarrier=operating_carrier,
                operatingFlightNumber=operating_flight_number,
                routeIndex=index,
                legIndex=index,
                stopoverAirport=segment.get('stops'),
                ext={
                    'aircraft': segment.get('aircraftCode'),
                    'depTerminal': segment.get('departure', {}).get('terminal'),
                    'arrTerminal': segment.get('arrival', {}).get('terminal'),
                    'codeShare': code_share,
                    'duration': segment.get('duration'),
                    'connectionTime': segment.get('extra', {}).get('connectionTime'),
                },
            ))

        return segment_list

    @staticmethod
    def parse_operating_flight_number(segment: dict,
                                      flight_number: str,
                                      operating_carrier: str,
                                      code_share: bool) -> Optional[str]:
        if segment.get('operatingFlightNumber') is not None:
            return operating_carrier + str(segment['operatingFlightNumber'])
        if Config.OPERATING_FLIGHT_NUMBER_MAP.get(flight_number) is not None:
            return Config.OPERATING_FLIGHT_NUMBER_MAP.get(flight_number)
        if code_share:
            return None
        return operating_carrier + str(segment['marketingFlightNumber'])

    @staticmethod
    def extract_numbers(str_list):
        """
        清洗字符串

        Args:
            str_list: 未清洗的 baggage allowance

        Returns:

        """

        numbers = []
        for item in str_list:
            sub_items = item.split()
            for sub_item in sub_items:
                if sub_item.isdigit():
                    numbers.append(int(sub_item))
        numbers.sort(reverse=True)
        return numbers

    @classmethod
    def parse_baggage(cls, product_code: str,) -> \
            List[FlightBaggageModel]:
        """
           解析行李信息，并返回BaggageInfoModel对象列表。

           Args:
               product_code: 产品代码。

           Returns:
               包含解析后的BaggageInfoModel对象的列表。
           """
        result_baggage: List[FlightBaggageModel] = []
        baggage_collection = Config.BAGGAGE_COLLECTION
        result = None
        for item in baggage_collection:
            if item[0] == product_code:
                result = item
                break
        if result is not None:
            result_weight = result[2].replace('kg', '').strip().split(',')

            if len(result_weight) == 2:
                total_weight_list = cls.extract_numbers(result_weight)
                baggage_types = [
                    [SsrTypeEnum.HAULING_BAGGAGE, total_weight_list[0]],
                    [SsrTypeEnum.HAND_BAGGAGE, total_weight_list[1]]
                ]
            else:
                weight_single = int(result_weight[0])
                baggage_types = [[SsrTypeEnum.HAULING_BAGGAGE, weight_single]]

            for i in baggage_types:
                baggage_info = FlightBaggageModel(
                    type=i[0],
                    price=Decimal(0),
                    weight=i[1],
                    number=1
                )
                result_baggage.append(baggage_info)
        return result_baggage

    @classmethod
    def bundle_parser(cls, bundles_list: List, bundle_id: str) -> List[FlightBundleModel]:
        result_bundles: List[FlightBundleModel] = []
        for bundle_data in bundles_list:
            sub_count = len(bundle_id.split('^'))
            cabin = ''
            currency = bundle_data['totalPrices'][0]['taxes'][0]['currencyCode']

            available_count_list = []
            for i in range(sub_count):
                booking_class = bundle_data['subclassInfo'][i].get('bookingClass', '')
                quota = bundle_data['subclassInfo'][i].get('quota', 0)
                if cabin:
                    cabin += '|' + booking_class
                else:
                    cabin = booking_class

                available_count_list.append(quota)
            if not available_count_list:
                continue
            available_count = min(available_count_list)
            if available_count <= 0:
                continue

            adt_fare, adt_tax, chd_fare, chd_tax = Decimal(0), Decimal(0), Decimal(0), Decimal(0)
            interface_price = bundle_data['interfaceTotal'].replace(",", "")
            flag = None
            for traveler in bundle_data['unitPrices']:
                if traveler['travelerIds'][0].split('-')[0] == 'ADT':
                    adt_total = traveler['prices'][0]['total']
                    adt_fare = Decimal(str(traveler['prices'][0]['base']))
                    adt_tax = Decimal(str(traveler['prices'][0]['totalTaxes']))
                    if str(adt_total) != interface_price:
                        flag = 100
                        adt_fare = adt_fare / flag
                        adt_tax = adt_tax / flag

                if traveler['travelerIds'][0].split('-')[0] == 'CHD':
                    chd_fare = Decimal(str(traveler['prices'][0]['base']))
                    chd_tax = Decimal(str(traveler['prices'][0]['totalTaxes']))
                    if flag is not None:
                        chd_fare = chd_fare / flag
                        chd_tax = chd_tax / flag
            price_info = FlightBundlePriceModel(
                adultTicketPrice=adt_fare,
                adultTaxPrice=adt_tax,
                childTicketPrice=chd_fare if chd_fare != 0 else adt_fare,
                childTaxPrice=chd_tax if chd_tax != 0 else adt_tax,
                currency=currency,

            )

            class_cabin = bundle_data['classCabin'].lower()
            cabin_level = 'C' if "business" == class_cabin else 'Y' if "eco" == class_cabin else 'F'
            product_tag = bundle_data['fareFamilyDescription']
            ssr_info = FlightSsrInfoModel(
            )
            temp_ssr_list = cls.parse_baggage(bundle_data['fareFamilyCode'])
            ssr_info.baggage = temp_ssr_list
            result_bundles.append(FlightBundleModel(
                priceInfo=price_info,
                ssrInfo=ssr_info,
                code=bundle_id,
                cabinLevel=cabin_level,
                cabin=cabin,
                fareKey=bundle_data['aid'],
                productTag=product_tag,
                seat=available_count,
                freightRateType=FreightRateTypeEnum.PT,
                ext={
                    'productCode': bundle_data['fareFamilyCode'],
                },
            ))
        return result_bundles

    @classmethod
    def link_round_trip(cls,
                        trip_journeys: List[FlightJourneyModel],
                        return_journeys: List[FlightJourneyModel]) -> List[FlightJourneyModel]:
        result_journeys: List[FlightJourneyModel] = []
        for trip_journey in trip_journeys:
            for return_journey in return_journeys:
                if DateUtil.get_time_difference_points(trip_journey.arr_time, return_journey.dep_time) < 240:
                    continue

                merged_bundles = cls.link_bundles(trip_journey.bundles, return_journey.bundles)
                if not merged_bundles:
                    continue

                result_journeys.append(FlightJourneyModel(
                    journeyKey='^'.join([trip_journey.journey_key, return_journey.journey_key]),
                    segments=trip_journey.segments + return_journey.segments,
                    bundles=merged_bundles,
                    depAirport=trip_journey.dep_airport,
                    arrAirport=return_journey.arr_airport,
                    depTime=trip_journey.dep_time,
                    arrTime=return_journey.arr_time,
                ))

        return result_journeys

    @classmethod
    def link_bundles(cls,
                     trip_bundles: List[FlightBundleModel],
                     return_bundles: List[FlightBundleModel]) -> List[FlightBundleModel]:
        result_bundles: List[FlightBundleModel] = []
        for trip_bundle in trip_bundles:
            return_bundle = next(
                (item for item in return_bundles if item.product_tag == trip_bundle.product_tag),
                None,
            )
            if return_bundle is None:
                continue

            trip_price = trip_bundle.price_info
            return_price = return_bundle.price_info
            result_bundles.append(FlightBundleModel(
                priceInfo=FlightBundlePriceModel(
                    adultTicketPrice=trip_price.adult_ticket_price + return_price.adult_ticket_price,
                    adultTaxPrice=trip_price.adult_tax_price + return_price.adult_tax_price,
                    childTicketPrice=trip_price.child_ticket_price + return_price.child_ticket_price,
                    childTaxPrice=trip_price.child_tax_price + return_price.child_tax_price,
                    currency=trip_price.currency,
                ),
                ssrInfo=FlightSsrInfoModel(
                    baggage=trip_bundle.ssr_info.baggage + return_bundle.ssr_info.baggage,
                ),
                code='^'.join([trip_bundle.code, return_bundle.code]),
                cabinLevel=trip_bundle.cabin_level,
                cabin='^'.join([trip_bundle.cabin or '', return_bundle.cabin or '']),
                fareKey='^'.join([trip_bundle.fare_key or '', return_bundle.fare_key or '']),
                productTag=trip_bundle.product_tag,
                seat=min(trip_bundle.seat, return_bundle.seat),
                freightRateType=trip_bundle.freight_rate_type,
                ext={
                    'trip': trip_bundle.ext or {},
                    'return': return_bundle.ext or {},
                },
            ))

        return result_bundles
