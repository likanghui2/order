from datetime import datetime
from decimal import Decimal

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from flights.sunphuquocairways_9g.config import Config


class AppFlightParser:
    @classmethod
    def parse(
        cls,
        response_data: dict,
        child_count: int = 0,
        promo_code: str = "",
    ) -> list[FlightJourneyModel]:
        journeys = []
        trips = (response_data.get("data") or {}).get("list_trip") or []
        for route_index, trip in enumerate(trips, start=1):
            segments = cls._parse_segments(trip.get("list_itinerary") or [], route_index)
            if not segments:
                continue
            bundles = cls._parse_bundles(trip.get("booking_class") or [], child_count, promo_code)
            if not bundles:
                continue
            journeys.append(
                FlightJourneyModel(
                    journeyKey=trip.get("trip_id") or "^".join(segment.segment_key for segment in segments),
                    segments=segments,
                    bundles=bundles,
                    depAirport=segments[0].dep_airport,
                    arrAirport=segments[-1].arr_airport,
                    depTime=segments[0].dep_time,
                    arrTime=segments[-1].arr_time,
                    ext={},
                )
            )
        return journeys

    @classmethod
    def _parse_segments(cls, itineraries: list[dict], route_index: int) -> list[FlightSegmentModel]:
        result = []
        for leg_index, itinerary in enumerate(itineraries, start=1):
            departure = itinerary.get("departure_info") or {}
            arrival = itinerary.get("arrival_info") or {}
            segment_key = str(itinerary.get("flight_id") or "")
            if not segment_key or not departure.get("datetime") or not arrival.get("datetime"):
                continue
            flight_number = cls._flight_number(itinerary.get("flight_number"))
            result.append(
                FlightSegmentModel(
                    segmentKey=segment_key,
                    depAirport=departure.get("code"),
                    arrAirport=arrival.get("code"),
                    depTime=datetime.fromisoformat(departure["datetime"]),
                    arrTime=datetime.fromisoformat(arrival["datetime"]),
                    flightNumber=flight_number,
                    carrier="9G",
                    operatingCarrier="9G",
                    operatingFlightNumber=flight_number,
                    routeIndex=route_index,
                    legIndex=leg_index,
                    ext={
                        "aircraft": (itinerary.get("aircraft_info") or {}).get("type"),
                        "aircraftVersion": (itinerary.get("aircraft_info") or {}).get("version"),
                        "depTerminal": departure.get("terminal"),
                        "arrTerminal": arrival.get("terminal"),
                        "durationSeconds": itinerary.get("duration"),
                    },
                )
            )
        return result

    @classmethod
    def _parse_bundles(
        cls,
        booking_classes: list[dict],
        child_count: int,
        promo_code: str,
    ) -> list[FlightBundleModel]:
        result = []
        for booking_class in booking_classes:
            if booking_class.get("booking_status") == "soldOut":
                continue
            fare_family_code = booking_class.get("fare_family_code")
            product_tag = Config.PRODUCT_TAG.get(fare_family_code)
            if not product_tag:
                continue
            segment_fares = booking_class.get("segment_fare") or [{}]
            cabin_name = str(segment_fares[0].get("cabin") or "").lower()
            prices = cls._prices(booking_class.get("pricing") or {})
            adult = prices.get("ADT")
            if adult is None:
                continue
            child = prices.get("CHD") if child_count else None
            child = child or adult
            currency = adult.get("currency") or child.get("currency")
            if not currency:
                continue
            result.append(
                FlightBundleModel(
                    priceInfo=FlightBundlePriceModel(
                        adultTicketPrice=Decimal(str(adult.get("base_fare") or 0)),
                        adultTaxPrice=Decimal(str(adult.get("tax") or 0)),
                        childTicketPrice=Decimal(str(child.get("base_fare") or 0)),
                        childTaxPrice=Decimal(str(child.get("tax") or 0)),
                        currency=currency,
                    ),
                    ssrInfo=FlightSsrInfoModel(baggage=[]),
                    code=fare_family_code,
                    cabinLevel="C" if "business" in cabin_name else "Y",
                    cabin=booking_class.get("booking_class") or "",
                    fareKey=booking_class.get("trip_id"),
                    productTag=product_tag,
                    seat=cls._available_count(booking_class),
                    freightRateType=FreightRateTypeEnum.PT,
                    ext={"fareFamilyCode": fare_family_code, "promoCode": promo_code or ""},
                )
            )
        return result

    @staticmethod
    def _prices(pricing: dict) -> dict[str, dict]:
        return {
            str(item.get("passenger_type") or item.get("pax_type") or item.get("type")): item
            for item in pricing.get("pax_pricing") or []
        }

    @staticmethod
    def _available_count(booking_class: dict) -> int:
        for key in ("available_count", "availableCount", "seat_available", "remaining_seats"):
            if booking_class.get(key) is not None:
                return int(booking_class[key])
        segment_counts = []
        for segment_fare in booking_class.get("segment_fare") or []:
            value = segment_fare.get("seat_availablity")
            if value is None:
                value = segment_fare.get("seat_availability")
            if value is not None:
                segment_counts.append(int(value))
        if segment_counts:
            return min(segment_counts)
        availability = booking_class.get("availability") or {}
        if availability.get("count") is not None:
            return int(availability["count"])
        return 9

    @staticmethod
    def _flight_number(value) -> str:
        number = str(value or "")
        if number.upper().startswith("9G"):
            number = number[2:]
        return f"9G{number.zfill(4)}"
