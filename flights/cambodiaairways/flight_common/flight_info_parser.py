from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from flights.cambodiaairways.config import Config


class FlightInfoParser:
    @classmethod
    def journey_info_parser(cls,
                            flight_data: dict,
                            dep_date: Optional[str] = None,
                            ret_date: Optional[str] = None,
                            group_id: Optional[str] = None) -> List[FlightJourneyModel]:
        result_data_list: List[FlightJourneyModel] = []
        data = flight_data.get('data') or {}

        for route_index, price_arr_key in enumerate(('priceArrOne7', 'priceArrTwo7'), start=1):
            price_arr = data.get(price_arr_key) or []
            target_date = ret_date if route_index == 2 and ret_date else dep_date
            for date_item in price_arr:
                if target_date and date_item.get('departureDate') != target_date:
                    continue

                air_routes = date_item.get('airRoutes') or {}
                for route_key, route_data in air_routes.items():
                    flight = route_data.get('flight') or {}
                    segments = cls.segment_parser(flight, route_index=route_index)
                    if not segments:
                        continue

                    bundles = cls.bundle_parser(
                        route_key=route_key,
                        route_data=route_data,
                        date_item=date_item,
                        group_id=group_id,
                    )
                    if not bundles:
                        continue

                    journey_key = cls.build_journey_key(segments[0], group_id)
                    result_data_list.append(FlightJourneyModel(
                        journeyKey=journey_key,
                        segments=segments,
                        bundles=bundles,
                        depAirport=segments[0].dep_airport,
                        arrAirport=segments[-1].arr_airport,
                        depTime=segments[0].dep_time,
                        arrTime=segments[-1].arr_time,
                        ext={
                            'groupId': group_id,
                            'routeKey': route_key,
                            'departureDate': date_item.get('departureDate'),
                            'localCurrency': date_item.get('localCurrency'),
                            'exchangeRate': date_item.get('exchangeRate'),
                        },
                    ))
        return result_data_list

    @classmethod
    def segment_parser(cls, flight: dict, route_index: int) -> List[FlightSegmentModel]:
        if not flight:
            return []

        carrier = flight.get('carrier') or flight.get('operatingCarrier') or 'KR'
        flight_number = str(flight.get('flightNumber') or '')
        if carrier and flight_number and not flight_number.startswith(carrier):
            flight_number = f'{carrier}{flight_number}'

        dep_airport = flight.get('departureAirport')
        arr_airport = flight.get('arrivalAirport')
        dep_time = cls.parse_datetime(flight.get('departureDate') or {}, flight.get('departureTime') or {})
        arr_time = cls.parse_datetime(flight.get('arrivalDate') or {}, flight.get('arrivalTime') or {})
        segment_key = f'{flight_number}|{dep_airport}{arr_airport}|{dep_time.strftime("%Y%m%d%H%M")}'

        return [
            FlightSegmentModel(
                segmentKey=segment_key,
                depAirport=dep_airport,
                arrAirport=arr_airport,
                depTime=dep_time,
                arrTime=arr_time,
                carrier=carrier,
                flightNumber=flight_number,
                operatingCarrier=flight.get('operatingCarrier') or carrier,
                operatingFlightNumber=(
                    flight.get('operatingFlightNumber')
                    if str(flight.get('operatingFlightNumber') or '').startswith(carrier)
                    else f'{carrier}{flight.get("operatingFlightNumber") or flight_number.replace(carrier, "")}'
                ),
                routeIndex=route_index,
                legIndex=1,
                ext={
                    'aircraftType': cls.get_aircraft_type(flight),
                    'durationHour': flight.get('durationHour'),
                    'distance': flight.get('distance'),
                    'rawAvl': flight.get('avl'),
                },
            )
        ]

    @classmethod
    def bundle_parser(cls,
                      route_key: str,
                      route_data: dict,
                      date_item: dict,
                      group_id: Optional[str]) -> List[FlightBundleModel]:
        flight = route_data.get('flight') or {}
        cabin_and_price = route_data.get('cabinAndPrice') or {}
        cabin_status = route_data.get('avl') or {}
        result_bundle_list: List[FlightBundleModel] = []

        for cabin in route_data.get('cabins') or cabin_and_price.keys():
            price_data = cabin_and_price.get(cabin) or {}
            adult_price = price_data.get('adultPrice') or {}
            if not adult_price:
                continue

            child_price = price_data.get('childPrice') or adult_price
            cabin_level = adult_price.get('cabinGrade') or Config.DEFAULT_CABIN_GRADE
            currency = adult_price.get('currency') or child_price.get('currency') or 'USD'
            fare_key = f'{route_key}|{cabin}'
            seat = cls.parse_available_seat(cabin_status.get(cabin), flight.get('avl'), cabin)

            result_bundle_list.append(FlightBundleModel(
                priceInfo=FlightBundlePriceModel(
                    adultTicketPrice=cls.to_decimal(adult_price.get('totalBase')),
                    adultTaxPrice=cls.parse_tax(adult_price),
                    childTicketPrice=cls.to_decimal(child_price.get('totalBase')),
                    childTaxPrice=cls.parse_tax(child_price),
                    currency=currency,
                ),
                ssrInfo=FlightSsrInfoModel(),
                code=cabin,
                cabinLevel=cabin_level,
                cabin=cabin,
                fareKey=fare_key,
                productTag=cls.build_product_tag(cabin_level, cabin),
                seat=seat,
                freightRateType=FreightRateTypeEnum.PT,
                ext={
                    'groupId': group_id,
                    'routeKey': route_key,
                    'cabin': cabin,
                    'localCurrency': date_item.get('localCurrency'),
                    'localCurrencyAmount': date_item.get('localCurrencyAmount'),
                    'exchangeRate': date_item.get('exchangeRate'),
                    'adultTotal': adult_price.get('total'),
                    'childTotal': child_price.get('total'),
                    'infPrice': price_data.get('infPrice'),
                },
            ))

        return result_bundle_list

    @staticmethod
    def parse_datetime(date_data: Dict, time_data: Dict) -> datetime:
        return datetime(
            int(date_data.get('year')),
            int(date_data.get('month')),
            int(date_data.get('day')),
            int(time_data.get('hour', 0)),
            int(time_data.get('minutes', 0)),
        )

    @staticmethod
    def to_decimal(value) -> Decimal:
        if value is None:
            return Decimal('0')
        return Decimal(str(value))

    @classmethod
    def parse_tax(cls, price_data: dict) -> Decimal:
        if price_data.get('total') is not None and price_data.get('totalBase') is not None:
            return cls.to_decimal(price_data.get('total')) - cls.to_decimal(price_data.get('totalBase'))
        return cls.to_decimal(price_data.get('totalTaxIata')) + cls.to_decimal(price_data.get('totalTaxYQYR'))

    @staticmethod
    def parse_available_seat(cabin_avl: Optional[str], raw_avl: Optional[str], cabin: str) -> int:
        if cabin_avl is not None and cabin_avl != '':
            if str(cabin_avl).isdigit():
                return int(cabin_avl)
            if cabin_avl == 'A':
                return Config.DEFAULT_AVAILABLE_SEAT
            return 0

        if raw_avl:
            for item in raw_avl.split(','):
                cabin_count = item.strip().split(':')
                if len(cabin_count) == 2 and cabin_count[0] == cabin and cabin_count[1].isdigit():
                    return int(cabin_count[1])
        return 0

    @staticmethod
    def get_aircraft_type(flight: dict) -> Optional[str]:
        aircraft_types = flight.get('aircraftTypes') or []
        if not aircraft_types:
            return None
        return aircraft_types[0].get('aircraftTypeCode')

    @staticmethod
    def build_product_tag(cabin_level: str, cabin: str) -> str:
        cabin_name = 'Business' if cabin_level == 'C' else 'Economy'
        return f'{cabin_name} {cabin}'

    @staticmethod
    def build_journey_key(segment: FlightSegmentModel, group_id: Optional[str]) -> str:
        base_key = f'{segment.flight_number}|{segment.dep_airport}{segment.arr_airport}|{segment.dep_time:%Y%m%d%H%M}'
        return f'{group_id}|{base_key}' if group_id else base_key
