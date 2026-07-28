from datetime import datetime, timedelta
from decimal import Decimal

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from flights.malaysiaairlines_mh.config import MalaysiaAirlinesConfig


class WebFlightParser:
    @classmethod
    def parse(
        cls,
        responses: list[dict],
        child_count: int = 0,
        promo_code: str = "",
    ) -> list[FlightJourneyModel]:
        routes = [
            cls._parse_route(response, route_index, child_count, promo_code)
            for route_index, response in enumerate(responses, start=1)
        ]
        if not routes:
            return []
        if len(routes) == 1:
            return routes[0]
        return cls._link_routes(routes)

    @classmethod
    def _parse_route(
        cls,
        response_data: dict,
        route_index: int,
        child_count: int,
        promo_code: str,
    ) -> list[FlightJourneyModel]:
        dictionaries = response_data.get("dictionaries") or {}
        flights = dictionaries.get("flight") or {}
        currency_info = dictionaries.get("currency") or {}
        result = []
        groups = (response_data.get("data") or {}).get("airBoundGroups") or []
        for group in groups:
            segment_refs = (group.get("boundDetails") or {}).get("segments") or []
            flight_ids = [item.get("flightId") for item in segment_refs if item.get("flightId")]
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
                    ext={"channel": "WEB", "routeIndex": route_index},
                )
            )
        return result

    @classmethod
    def _segments(
        cls,
        flight_data: dict,
        flight_ids: list[str],
        route_index: int,
    ) -> list[FlightSegmentModel]:
        result = []
        for leg_index, flight_id in enumerate(flight_ids, start=1):
            item = flight_data.get(flight_id)
            if not item:
                return []
            departure = item.get("departure") or {}
            arrival = item.get("arrival") or {}
            if not departure.get("dateTime") or not arrival.get("dateTime"):
                return []
            carrier = str(item.get("marketingAirlineCode") or "MH")
            operating_carrier = str(item.get("operatingAirlineCode") or carrier)
            marketing_number = cls._number(item.get("marketingFlightNumber"))
            operating_number = cls._number(
                item.get("operatingFlightNumber") or item.get("marketingFlightNumber")
            )
            result.append(
                FlightSegmentModel(
                    segmentKey=str(flight_id),
                    depAirport=departure.get("locationCode"),
                    arrAirport=arrival.get("locationCode"),
                    depTime=cls._date(departure["dateTime"]),
                    arrTime=cls._date(arrival["dateTime"]),
                    flightNumber=f"{carrier}{marketing_number}",
                    carrier=carrier,
                    operatingCarrier=operating_carrier,
                    operatingFlightNumber=f"{operating_carrier}{operating_number}",
                    routeIndex=route_index,
                    legIndex=leg_index,
                    stopoverAirport="|".join(
                        str(stop.get("locationCode") or "")
                        for stop in item.get("stops") or []
                        if stop.get("locationCode")
                    ) or None,
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
            availability = bound.get("availabilityDetails") or []
            if not availability:
                continue
            family_code = str(bound.get("fareFamilyCode") or "")
            family = MalaysiaAirlinesConfig.bundle_info(family_code)
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
            promo = any((price.get("discount") or {}).get("discountCode") for price in prices.values())
            result.append(
                FlightBundleModel(
                    priceInfo=FlightBundlePriceModel(
                        adultTicketPrice=Decimal(str(adult.get("base") or 0)) / divisor,
                        adultTaxPrice=Decimal(str(adult.get("totalTaxes") or 0)) / divisor,
                        childTicketPrice=Decimal(str(child.get("base") or 0)) / divisor,
                        childTaxPrice=Decimal(str(child.get("totalTaxes") or 0)) / divisor,
                        currency=currency,
                    ),
                    ssrInfo=FlightSsrInfoModel(
                        baggage=cls._included_baggage(family)
                    ),
                    code=family_code,
                    cabinLevel="C" if "Business" in family["tag"] or "First" in family["tag"] else "Y",
                    cabin="|".join(cabins),
                    fareKey=bound.get("airBoundId"),
                    productTag=family["tag"],
                    seat=min(quotas),
                    freightRateType=FreightRateTypeEnum.PT,
                    ext={
                        "privateCode": promo_code if promo else "",
                        "availabilityDetails": availability,
                    },
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
    def _included_baggage(family: dict) -> list[FlightBaggageModel]:
        return [
            FlightBaggageModel(
                type=SsrTypeEnum.HAULING_BAGGAGE,
                price=Decimal(0),
                number=1,
                weight=int(family["checkin_weight"]),
            ),
            FlightBaggageModel(
                type=SsrTypeEnum.HAND_BAGGAGE,
                price=Decimal(0),
                number=int(family["cabin_pieces"]),
                weight=int(family["cabin_weight"]),
            ),
        ]

    @staticmethod
    def _link_routes(routes: list[list[FlightJourneyModel]]) -> list[FlightJourneyModel]:
        result = []
        for outbound in routes[0]:
            for inbound in routes[1]:
                if inbound.dep_time - outbound.arr_time < timedelta(hours=2):
                    continue
                segments = outbound.segments + inbound.segments
                bundles = []
                for outbound_bundle in outbound.bundles:
                    inbound_bundle = next(
                        (
                            bundle
                            for bundle in inbound.bundles
                            if bundle.product_tag == outbound_bundle.product_tag
                        ),
                        None,
                    )
                    if inbound_bundle is None:
                        continue
                    bundles.append(
                        FlightBundleModel(
                            priceInfo=FlightBundlePriceModel(
                                adultTicketPrice=(
                                    outbound_bundle.price_info.adult_ticket_price
                                    + inbound_bundle.price_info.adult_ticket_price
                                ),
                                adultTaxPrice=(
                                    outbound_bundle.price_info.adult_tax_price
                                    + inbound_bundle.price_info.adult_tax_price
                                ),
                                childTicketPrice=(
                                    outbound_bundle.price_info.child_ticket_price
                                    + inbound_bundle.price_info.child_ticket_price
                                ),
                                childTaxPrice=(
                                    outbound_bundle.price_info.child_tax_price
                                    + inbound_bundle.price_info.child_tax_price
                                ),
                                currency=outbound_bundle.price_info.currency,
                            ),
                            ssrInfo=FlightSsrInfoModel(
                                baggage=(
                                    outbound_bundle.ssr_info.baggage
                                    + inbound_bundle.ssr_info.baggage
                                )
                            ),
                            code=outbound_bundle.code,
                            cabinLevel=outbound_bundle.cabin_level,
                            cabin=(
                                f"{outbound_bundle.cabin}^{inbound_bundle.cabin}"
                            ),
                            fareKey=(
                                f"{outbound_bundle.fare_key}^{inbound_bundle.fare_key}"
                                if outbound_bundle.fare_key and inbound_bundle.fare_key
                                else None
                            ),
                            productTag=outbound_bundle.product_tag,
                            seat=min(outbound_bundle.seat, inbound_bundle.seat),
                            freightRateType=outbound_bundle.freight_rate_type,
                            ext={
                                "privateCode": (
                                    (outbound_bundle.ext or {}).get("privateCode")
                                    or (inbound_bundle.ext or {}).get("privateCode")
                                    or ""
                                ),
                            },
                        )
                    )
                if not bundles:
                    continue
                result.append(
                    FlightJourneyModel(
                        journeyKey=f"{outbound.journey_key}^{inbound.journey_key}",
                        segments=segments,
                        bundles=bundles,
                        depAirport=outbound.dep_airport,
                        arrAirport=inbound.arr_airport,
                        depTime=outbound.dep_time,
                        arrTime=inbound.arr_time,
                        ext={"channel": "WEB"},
                    )
                )
        return result

    @staticmethod
    def _number(value) -> str:
        return str(value or "").zfill(4)

    @staticmethod
    def _date(value: str) -> datetime:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
