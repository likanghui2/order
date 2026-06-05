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
from flights.cebupacificair_5j.config import CebupacificairConfig


class FlightParser:
    @classmethod
    def parse_flight_data(cls, routes: List[dict], currency: str) -> List[FlightJourneyModel]:
        journey_groups: List[List[FlightJourneyModel]] = []
        for route_index, route in enumerate(routes, start=1):
            route_journeys: List[FlightJourneyModel] = []
            for journey_info in route.get('journeys') or []:
                journey = cls.parse_journey(journey_info, route_index, currency)
                if journey:
                    route_journeys.append(journey)

            if route_journeys:
                journey_groups.append(route_journeys)

        if len(journey_groups) == 1:
            return journey_groups[0]
        if len(journey_groups) == 2:
            return cls.link_round_trip(journey_groups[0], journey_groups[1])
        return []

    @classmethod
    def parse_journey(cls,
                      journey_info: dict,
                      route_index: int,
                      currency: str) -> Optional[FlightJourneyModel]:
        if not journey_info.get('segments') or not journey_info.get('fareAvailabilityKey'):
            return None

        designator = journey_info.get('designator') or {}
        dep_airport = designator.get('origin')
        arr_airport = designator.get('destination')
        dep_time = DateUtil.string_to_date_auto(designator.get('departure'))
        arr_time = DateUtil.string_to_date_auto(designator.get('arrival'))
        if not all([dep_airport, arr_airport, dep_time, arr_time]):
            return None

        segments = cls.parse_segments(journey_info.get('segments') or [], route_index)
        if len(segments) != 1:
            return None
        if not segments:
            return None

        fare_class = journey_info.get('fareClass') or ''
        total_price = Decimal(str(journey_info.get('fareTotal') or 0))
        available_count = int(journey_info.get('availableCount', -1))
        tax_scale = Decimal(str(CebupacificairConfig.TAX_SCALE.get(f'{dep_airport}_{arr_airport}', 0.3)))
        basic_tax_price = total_price * tax_scale
        basic_ticket_price = total_price - basic_tax_price
        flights_num = "$".join(segment.flight_number for segment in segments)

        bundles = cls.parse_bundles(
            bundles=journey_info.get('bundles') or [],
            currency=currency,
            cabin=fare_class,
            available_count=available_count,
            basics_fare_key=journey_info['fareAvailabilityKey'],
            basics_ticket=basic_ticket_price,
            basics_tax=basic_tax_price,
            flights_num=flights_num,
        )
        if not bundles:
            return None

        return FlightJourneyModel(
            journeyKey=journey_info.get('journeyKey') or '',
            segments=segments,
            bundles=bundles,
            depAirport=dep_airport,
            arrAirport=arr_airport,
            depTime=dep_time,
            arrTime=arr_time,
        )

    @staticmethod
    def parse_segments(segments: List[dict], route_index: int) -> List[FlightSegmentModel]:
        result_segments: List[FlightSegmentModel] = []
        for leg_index, segment in enumerate(segments, start=1):
            designator = segment.get('designator') or {}
            identifier = segment.get('identifier') or {}
            dep_airport = designator.get('origin')
            arr_airport = designator.get('destination')
            dep_time = DateUtil.string_to_date_auto(designator.get('departure'))
            arr_time = DateUtil.string_to_date_auto(designator.get('arrival'))
            carrier = identifier.get('carrierCode') or '5J'
            flight_identifier = str(identifier.get('identifier') or '')
            flight_number = (
                flight_identifier
                if flight_identifier.startswith(carrier)
                else f'{carrier}{flight_identifier}'
            )
            if not all([dep_airport, arr_airport, dep_time, arr_time, flight_identifier]):
                continue

            result_segments.append(FlightSegmentModel(
                segmentKey=segment.get('segmentKey') or f'{flight_number}|{dep_airport}{arr_airport}|{dep_time:%Y%m%d%H%M}',
                depAirport=dep_airport,
                arrAirport=arr_airport,
                depTime=dep_time,
                arrTime=arr_time,
                flightNumber=flight_number,
                carrier=carrier,
                operatingCarrier=carrier,
                operatingFlightNumber=flight_number,
                routeIndex=route_index,
                legIndex=leg_index,
                ext={
                    'flightTime': DateUtil.get_time_difference_points(dep_time, arr_time),
                    'international': segment.get('international'),
                },
            ))

        return result_segments

    @classmethod
    def parse_bundles(cls,
                      bundles: List[dict],
                      currency: str,
                      cabin: str,
                      available_count: int,
                      basics_fare_key: str,
                      basics_ticket: Decimal,
                      basics_tax: Decimal,
                      flights_num: str) -> List[FlightBundleModel]:
        result_bundles: List[FlightBundleModel] = [
            FlightBundleModel(
                priceInfo=cls.build_price_info(basics_ticket, basics_tax, currency),
                ssrInfo=FlightSsrInfoModel(baggage=[
                    FlightBaggageModel(
                        type=SsrTypeEnum.HAND_BAGGAGE,
                        price=Decimal('0'),
                        number=1,
                        weight=7,
                    )
                ]),
                code='GO_BASIC',
                cabinLevel='Y',
                cabin=cabin,
                fareKey=basics_fare_key,
                productTag='GO Basic',
                seat=available_count,
                freightRateType=FreightRateTypeEnum.PT,
                ext={
                    'bundleCode': '',
                    'flightsNum': flights_num,
                },
            )
        ]

        for bundle in bundles:
            service_charges = bundle.get('serviceCharges') or []
            if len(service_charges) == 0 or len(service_charges) > 2:
                continue

            code = service_charges[0].get('code')
            code_data = CebupacificairConfig.PRODUCT_RULE.get(code)
            if code_data is None:
                continue

            baggage_list = [
                FlightBaggageModel(
                    type=item['type'],
                    price=Decimal('0'),
                    number=1,
                    weight=item['weight'],
                )
                for item in code_data['baggage_data']
            ]

            bundle_ticket = basics_ticket + Decimal(str(service_charges[0].get('amount') or 0))
            bundle_tax = basics_tax + Decimal(str(service_charges[1].get('amount') if len(service_charges) == 2 else 0))
            result_bundles.append(FlightBundleModel(
                priceInfo=cls.build_price_info(bundle_ticket, bundle_tax, currency),
                ssrInfo=FlightSsrInfoModel(baggage=baggage_list),
                code=bundle.get('bundleCode') or code,
                cabinLevel='Y',
                cabin=cabin,
                fareKey=basics_fare_key,
                productTag=code_data['tag'],
                seat=available_count,
                freightRateType=FreightRateTypeEnum.PT,
                ext={
                    'bundleCode': bundle.get('bundleCode') or '',
                    'serviceChargeCode': code,
                    'flightsNum': flights_num,
                    'seatIncluded': code in ['EASYPC', 'FLEXPC'],
                },
            ))

        return result_bundles

    @staticmethod
    def build_price_info(ticket: Decimal, tax: Decimal, currency: str) -> FlightBundlePriceModel:
        return FlightBundlePriceModel(
            adultTicketPrice=ticket,
            adultTaxPrice=tax,
            childTicketPrice=ticket,
            childTaxPrice=tax,
            currency=currency,
        )

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
                    baggage=trip_bundle.ssr_info.baggage + return_bundle.ssr_info.baggage
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
