from datetime import datetime
from decimal import Decimal
from typing import List

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel


class VZWebFlightParser:
    @classmethod
    def journey_info_parser(cls, flight_data: dict) -> List[FlightJourneyModel]:
        result = []
        search_data = (flight_data or {}).get("data") or {}
        api_uuid = search_data.get("api_uuid")
        departure_list = search_data.get("departure_list") or {}
        for journey_index, journey_data in enumerate(departure_list.values(), start=1):
            segments = cls.segment_parser(journey_data.get("flights") or [], journey_index)
            if len(segments) != 1:
                continue
            journey_raw = dict(journey_data)
            if api_uuid:
                journey_raw["_api_uuid"] = api_uuid
            bundles = cls.bundle_parser(journey_raw.get("fare_types") or {}, journey_raw)
            if not bundles:
                continue
            result.append(FlightJourneyModel(
                journeyKey=journey_raw.get("id") or "",
                segments=segments,
                bundles=bundles,
                depAirport=segments[0].dep_airport,
                arrAirport=segments[-1].arr_airport,
                depTime=segments[0].dep_time,
                arrTime=segments[-1].arr_time,
                ext={"raw": journey_raw},
            ))
        return result

    @classmethod
    def segment_parser(cls, flights: list[dict], journey_index: int) -> List[FlightSegmentModel]:
        segments = []
        for leg_index, flight in enumerate(flights, start=1):
            carrier = flight.get("airline_code") or ""
            flight_number = f"{carrier}{flight.get('flight_number') or ''}"
            dep_time = cls._parse_datetime(flight.get("departure_date_html"))
            arr_time = cls._parse_datetime(flight.get("arrival_date_html"))
            segments.append(FlightSegmentModel(
                segmentKey=flight_number,
                depAirport=flight.get("departure_code"),
                arrAirport=flight.get("arrival_code"),
                depTime=dep_time,
                arrTime=arr_time,
                flightNumber=flight_number,
                carrier=carrier,
                operatingCarrier=carrier,
                operatingFlightNumber=flight_number,
                routeIndex=journey_index,
                legIndex=leg_index,
                ext={
                    "raw": flight,
                    "flight_time": journey_data_duration(flight.get("trip_hour")),
                },
            ))
        return segments

    @classmethod
    def bundle_parser(cls, fare_types: dict, journey_data: dict) -> List[FlightBundleModel]:
        bundles = []
        for product_tag, fare in fare_types.items():
            seat = int(fare.get("availability") or 0)
            if seat <= 0:
                continue
            price_info = cls.price_parser(fare)
            fare_name = cls._fare_class_name(fare)
            bundles.append(FlightBundleModel(
                priceInfo=price_info,
                ssrInfo=FlightSsrInfoModel(),
                code=fare.get("code") or product_tag,
                cabinLevel="Y",
                cabin=fare_name.split("_")[0][0] if fare_name else None,
                fareKey=fare.get("bookingKey"),
                productTag=fare.get("name") or product_tag,
                seat=seat,
                freightRateType=FreightRateTypeEnum.PT,
                ext={
                    "raw": fare,
                    "journey_raw": journey_data,
                },
            ))
        return bundles

    @classmethod
    def price_parser(cls, fare: dict) -> FlightBundlePriceModel:
        price_detail = fare.get("price_detail") or {}
        currency = fare.get("currency_code") or cls._currency_from_price_detail(price_detail)

        adult_fare, adult_tax = cls._passenger_price(price_detail, "adult")
        child_fare, child_tax = cls._passenger_price(price_detail, "child")

        if child_fare == 0 and child_tax == 0:
            child_fare = adult_fare
            child_tax = adult_tax

        return FlightBundlePriceModel(
            adultTicketPrice=adult_fare,
            adultTaxPrice=adult_tax,
            childTicketPrice=child_fare,
            childTaxPrice=child_tax,
            currency=currency,
        )

    @classmethod
    def _passenger_price(cls, price_detail: dict, passenger_type: str):
        fare_info = ((price_detail.get("fare") or {}).get(passenger_type) or {})
        count = Decimal(str(fare_info.get("count") or 1))
        fare_amount = cls._money(fare_info.get("amount")) / count
        tax_amount = Decimal("0")
        for tax_fee in (price_detail.get("tax_fee") or {}).values():
            if int(tax_fee.get("count") or 0) <= 0:
                continue
            tax_amount += cls._money(tax_fee.get("amount")) / Decimal(str(tax_fee.get("count") or 1))
        return fare_amount, tax_amount

    @staticmethod
    def _currency_from_price_detail(price_detail: dict):
        fare = (price_detail.get("fare") or {}).get("adult") or {}
        return fare.get("currency") or "THB"

    @staticmethod
    def _fare_class_name(fare: dict):
        fare_detail = ((fare.get("price_detail") or {}).get("fare") or {})
        adult_fare = fare_detail.get("adult") or {}
        child_fare = fare_detail.get("child") or {}
        return adult_fare.get("name") or child_fare.get("name") or fare.get("code")

    @staticmethod
    def _money(value):
        if value in (None, ""):
            return Decimal("0")
        return Decimal(str(value))

    @staticmethod
    def _parse_datetime(value: str):
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def journey_data_duration(value: str):
    if not value:
        return 0
    hours = 0
    minutes = 0
    for part in value.split():
        if part.endswith("h"):
            hours = int(part[:-1])
        elif part.endswith("m"):
            minutes = int(part[:-1])
    return hours * 60 + minutes
