from datetime import datetime
from decimal import Decimal

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from flights.sunphuquocairways_9g.config import Config


class WebFlightParser:
    @classmethod
    def parse(
        cls,
        response_data: dict,
        child_count: int = 0,
        promo_code: str = "",
    ) -> list[FlightJourneyModel]:
        dictionaries = response_data.get("dictionaries") or {}
        flights = dictionaries.get("flight") or {}
        currency_info = dictionaries.get("currency") or {}
        result = []
        for route_index, group in enumerate((response_data.get("data") or {}).get("airBoundGroups") or [], start=1):
            flight_ids = [item.get("flightId") for item in (group.get("boundDetails") or {}).get("segments") or []]
            segments = cls._segments(flights, flight_ids, route_index)
            if not segments:
                continue
            bundles = cls._bundles(group.get("airBounds") or [], currency_info, child_count, promo_code)
            if not bundles:
                continue
            result.append(
                FlightJourneyModel(
                    journeyKey=bundles[0].fare_key or "^".join(flight_ids),
                    segments=segments,
                    bundles=bundles,
                    depAirport=segments[0].dep_airport,
                    arrAirport=segments[-1].arr_airport,
                    depTime=segments[0].dep_time,
                    arrTime=segments[-1].arr_time,
                    ext={"channel": "WEB"},
                )
            )
        return result

    @classmethod
    def _segments(cls, flight_data: dict, flight_ids: list, route_index: int) -> list[FlightSegmentModel]:
        result = []
        for leg_index, flight_id in enumerate(flight_ids, start=1):
            item = flight_data.get(flight_id)
            if not item:
                return []
            carrier = str(item.get("marketingAirlineCode") or "9G")
            operating_carrier = str(item.get("operatingAirlineCode") or carrier)
            marketing_number = cls._number(item.get("marketingFlightNumber"))
            operating_number = cls._number(item.get("operatingFlightNumber") or item.get("marketingFlightNumber"))
            departure = item.get("departure") or {}
            arrival = item.get("arrival") or {}
            if not departure.get("dateTime") or not arrival.get("dateTime"):
                return []
            result.append(
                FlightSegmentModel(
                    segmentKey=str(flight_id),
                    depAirport=departure.get("locationCode"),
                    arrAirport=arrival.get("locationCode"),
                    depTime=datetime.fromisoformat(departure["dateTime"]),
                    arrTime=datetime.fromisoformat(arrival["dateTime"]),
                    flightNumber=f"{carrier}{marketing_number}",
                    carrier=carrier,
                    operatingCarrier=operating_carrier,
                    operatingFlightNumber=f"{operating_carrier}{operating_number}",
                    routeIndex=route_index,
                    legIndex=leg_index,
                    ext={
                        "aircraft": item.get("aircraftCode"),
                        "durationSeconds": item.get("duration"),
                        "depTerminal": departure.get("terminal"),
                        "arrTerminal": arrival.get("terminal"),
                    },
                )
            )
        return result

    @classmethod
    def _bundles(
        cls,
        bounds: list[dict],
        currency_info: dict,
        child_count: int,
        promo_code: str,
    ) -> list[FlightBundleModel]:
        result = []
        for bound in bounds:
            if (bound.get("status") or {}).get("value") == "soldOut":
                continue
            family_code = bound.get("fareFamilyCode")
            product_tag = Config.PRODUCT_TAG.get(family_code)
            availability = bound.get("availabilityDetails") or []
            if not product_tag or not availability:
                continue
            prices = cls._price_by_type((bound.get("prices") or {}).get("unitPrices") or [])
            adult = prices.get("ADT")
            if not adult:
                continue
            child = prices.get("CHD") if child_count else None
            child = child or adult
            currency = adult.get("currencyCode") or child.get("currencyCode")
            if not currency:
                continue
            places = int((currency_info.get(currency) or {}).get("decimalPlaces", 0))
            divisor = Decimal(10) ** places
            cabins = [str(item.get("bookingClass") or "") for item in availability]
            quotas = [int(item.get("quota") or 0) for item in availability]
            cabin_level = "C" if any("business" in str(item.get("cabin") or "").lower() for item in availability) else "Y"
            baggage = cls._included_baggage(product_tag)
            result.append(
                FlightBundleModel(
                    priceInfo=FlightBundlePriceModel(
                        adultTicketPrice=Decimal(str(adult.get("base") or 0)) / divisor,
                        adultTaxPrice=Decimal(str(adult.get("totalTaxes") or 0)) / divisor,
                        childTicketPrice=Decimal(str(child.get("base") or 0)) / divisor,
                        childTaxPrice=Decimal(str(child.get("totalTaxes") or 0)) / divisor,
                        currency=currency,
                    ),
                    ssrInfo=FlightSsrInfoModel(baggage=baggage),
                    code=family_code,
                    cabinLevel=cabin_level,
                    cabin="|".join(cabins),
                    fareKey=bound.get("airBoundId"),
                    productTag=product_tag,
                    seat=min(quotas),
                    freightRateType=FreightRateTypeEnum.PT,
                    ext={"promoCode": promo_code or "", "availabilityDetails": availability},
                )
            )
        return result

    @staticmethod
    def _price_by_type(unit_prices: list[dict]) -> dict[str, dict]:
        result = {}
        for unit in unit_prices:
            traveler_text = "".join(str(value) for value in unit.get("travelerIds") or [])
            passenger_type = "CHD" if "CHD" in traveler_text else "ADT" if "ADT" in traveler_text else ""
            prices = unit.get("prices") or []
            if passenger_type and prices:
                result[passenger_type] = prices[0]
        return result

    @staticmethod
    def _included_baggage(product_tag: str) -> list[FlightBaggageModel]:
        business = product_tag in {"BUSINESS PRIME", "BUSINESS ELITE"}
        return [
            FlightBaggageModel(
                type=SsrTypeEnum.HAULING_BAGGAGE,
                price=Decimal(0),
                number=2 if business else 1,
                weight=46 if business else 23,
            ),
            FlightBaggageModel(
                type=SsrTypeEnum.HAND_BAGGAGE,
                price=Decimal(0),
                number=2 if business else 1,
                weight=14 if business else 7,
            ),
        ]

    @staticmethod
    def _number(value) -> str:
        return str(value or "").zfill(4)
