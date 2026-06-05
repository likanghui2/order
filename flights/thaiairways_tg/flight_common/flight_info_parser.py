import re
from decimal import Decimal
from typing import List, Optional

from dateutil import parser

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from flights.thaiairways_tg.config import ThaiairwaysConfig


class FlightInfoParser:
    @classmethod
    def journey_info_parser(cls, flight_list: List[dict]) -> List[FlightJourneyModel]:
        journeys = []
        for route_index, route in enumerate(flight_list, start=1):
            currency_info = route["dictionaries"]["currency"]
            flight_dict = route["dictionaries"]["flight"]
            fare_family_dict = route["dictionaries"].get("fareFamilyWithServices") or {}

            route_journeys = []
            for flight_info in route["data"]["airBoundGroups"]:
                segments = cls.parse_segments(
                    segments=flight_info["boundDetails"]["segments"],
                    flight_dict=flight_dict,
                    route_index=route_index,
                )
                bundles = cls.parse_bundles(
                    bundles=flight_info["airBounds"],
                    currency_info=currency_info,
                    fare_family_dict=fare_family_dict,
                )
                route_journeys.append(FlightJourneyModel.model_validate({
                    "segments": segments,
                    "bundles": bundles,
                    "journeyKey": flight_info["airBounds"][0]["airBoundId"] if flight_info.get("airBounds") else "",
                    "depAirport": segments[0].dep_airport,
                    "arrAirport": segments[-1].arr_airport,
                    "depTime": segments[0].dep_time,
                    "arrTime": segments[-1].arr_time,
                }))
            journeys.append(route_journeys)

        if len(journeys) == 1:
            return journeys[0]

        return cls._link_round_trip(journeys)

    @staticmethod
    def parse_segments(segments: List[dict],
                       flight_dict: dict,
                       route_index: int) -> List[FlightSegmentModel]:
        result = []
        for leg_index, segment_ref in enumerate(segments, start=1):
            segment_info = flight_dict[segment_ref["flightId"]]
            carrier = segment_info["marketingAirlineCode"]
            flight_number = carrier + str(segment_info["marketingFlightNumber"])
            operating_carrier = segment_info.get("operatingAirlineCode") or carrier
            operating_flight_number = operating_carrier + str(segment_info["marketingFlightNumber"])
            result.append(FlightSegmentModel.model_validate({
                "segmentKey": segment_ref["flightId"],
                "depAirport": segment_info["departure"]["locationCode"],
                "arrAirport": segment_info["arrival"]["locationCode"],
                "depTime": parser.parse(segment_info["departure"]["dateTime"]),
                "arrTime": parser.parse(segment_info["arrival"]["dateTime"]),
                "flightNumber": flight_number,
                "carrier": carrier,
                "operatingCarrier": operating_carrier,
                "operatingFlightNumber": operating_flight_number,
                "stopoverAirport": "|".join([stop["locationCode"] for stop in segment_info.get("stops", [])]),
                "stopoverTime": -1,
                "legIndex": leg_index,
                "routeIndex": route_index,
                # "ext": segment_info,
            }))
        return result

    @classmethod
    def parse_bundles(cls,
                      bundles: List[dict],
                      currency_info: dict,
                      fare_family_dict: dict) -> List[FlightBundleModel]:
        result = []
        for bundle in bundles:
            price_info = cls._parse_price_info(bundle, currency_info)
            if price_info is None:
                continue

            product_code = bundle.get("fareFamilyCode") or ""
            services_info = cls._get_services_info(product_code)
            product_tag = services_info.get(f"REFX-FARE-FAMILY.{product_code}".upper(), product_code)
            fare_family = fare_family_dict.get(product_code) or {}
            cabin_level = cls._parse_cabin_level(fare_family.get("commercialFareFamily"))
            cabin = "|".join([item["bookingClass"] for item in bundle.get("availabilityDetails") or []])
            available_count = min(
                [int(item.get("quota") or 0) for item in bundle.get("availabilityDetails") or [{"quota": 0}]]
            )
            fare_basis = "|".join([
                (bundle.get("fareInfos") or [{}])[0].get("fareClass") or ""
            ] * max(1, len(bundle.get("availabilityDetails") or [])))
            baggage_list = cls._parse_baggage_list(product_code, services_info)

            result.append(FlightBundleModel.model_validate({
                "priceInfo": price_info,
                "ssrInfo": FlightSsrInfoModel(baggage=baggage_list),
                "code": product_code,
                "cabinLevel": cabin_level,
                "cabin": cabin,
                "fareKey": bundle.get("airBoundId"),
                "productTag": product_tag,
                "seat": available_count,
                "freightRateType": FreightRateTypeEnum.PT,
                "ext": {
                    # "fareBasis": fare_basis,
                    # "sourceBundle": bundle,
                },
            }))
        return result

    @staticmethod
    def _get_services_info(product_code: str) -> dict:
        product_code = (product_code or "").upper()
        return {
            key.upper(): value
            for key, value in ThaiairwaysConfig.BUNDLE_INFO.items()
            if product_code and product_code in key.upper()
        }

    @classmethod
    def _parse_baggage_list(cls,
                            product_code: str,
                            services_info: dict) -> List[FlightBaggageModel]:
        baggage_list = []
        checked_key = f"REFX-FARE-FAMILY.{product_code}.CHECKEDBAG.SHORT.VALUE".upper()
        carry_key = f"REFX-FARE-FAMILY.{product_code}.CARRYBAG.SHORT.VALUE".upper()

        checked_baggage = cls._build_baggage(
            baggage_type=SsrTypeEnum.HAULING_BAGGAGE,
            baggage_text=services_info.get(checked_key),
            code="CHECKEDBAG",
        )
        if checked_baggage:
            baggage_list.append(checked_baggage)

        carry_baggage = cls._build_baggage(
            baggage_type=SsrTypeEnum.HAND_BAGGAGE,
            baggage_text=services_info.get(carry_key),
            code="CARRYBAG",
        )
        if carry_baggage:
            baggage_list.append(carry_baggage)

        return baggage_list

    @staticmethod
    def _build_baggage(baggage_type: SsrTypeEnum,
                       baggage_text: Optional[str],
                       code: str) -> Optional[FlightBaggageModel]:
        if not baggage_text:
            return None

        normalized = re.sub(r"<[^>]+>", " ", str(baggage_text)).replace("&times;", "x")
        normalized_compact = normalized.replace(" ", "").lower()
        if "notincluded" in normalized_compact:
            return None

        weight_match = re.search(r"(\d+)\s*kg", normalized, re.IGNORECASE)
        if not weight_match:
            return None

        piece_match = re.search(r"(\d+)\s*piece", normalized, re.IGNORECASE)
        return FlightBaggageModel.model_validate({
            "type": baggage_type,
            "code": code,
            "price": Decimal("0"),
            "number": int(piece_match.group(1)) if piece_match else 1,
            "weight": int(weight_match.group(1)),
            "weightUnit": "KG",
        })

    @staticmethod
    def _parse_price_info(bundle: dict, currency_info: dict) -> Optional[FlightBundlePriceModel]:
        adult_fare = Decimal("0")
        adult_tax = Decimal("0")
        child_fare = Decimal("0")
        child_tax = Decimal("0")
        currency = None

        for unit_price in bundle.get("prices", {}).get("unitPrices", []):
            traveler_ids = "".join(unit_price.get("travelerIds") or [])
            price = (unit_price.get("prices") or [{}])[0]
            decimal_places = currency_info.get(price.get("currencyCode"), {}).get("decimalPlaces", 2)
            fare = Decimal(str(price.get("base") or 0)) / (Decimal(10) ** decimal_places)
            tax = Decimal(str(price.get("totalTaxes") or 0)) / (Decimal(10) ** decimal_places)
            if "ADT" in traveler_ids:
                adult_fare = fare
                adult_tax = tax
                currency = price.get("currencyCode")
            elif "CHD" in traveler_ids:
                child_fare = fare
                child_tax = tax

        if not currency:
            return None

        return FlightBundlePriceModel.model_validate({
            "adultTicketPrice": adult_fare,
            "adultTaxPrice": adult_tax,
            "childTicketPrice": child_fare,
            "childTaxPrice": child_tax,
            "currency": currency,
        })

    @staticmethod
    def _parse_cabin_level(commercial_fare_family: Optional[str]) -> str:
        return next(
            (level for level, fare_family in ThaiairwaysConfig.CABIN_TO_FARE.items()
             if fare_family == commercial_fare_family),
            "Y",
        )

    @staticmethod
    def _link_round_trip(journey_groups: List[List[FlightJourneyModel]]) -> List[FlightJourneyModel]:
        result = []
        for outbound in journey_groups[0]:
            for inbound in journey_groups[1]:
                bundles = []
                for outbound_bundle in outbound.bundles:
                    for inbound_bundle in inbound.bundles:
                        bundles.append(FlightBundleModel.model_validate({
                            "priceInfo": {
                                "adultTicketPrice": (
                                    outbound_bundle.price_info.adult_ticket_price
                                    + inbound_bundle.price_info.adult_ticket_price
                                ),
                                "adultTaxPrice": (
                                    outbound_bundle.price_info.adult_tax_price
                                    + inbound_bundle.price_info.adult_tax_price
                                ),
                                "childTicketPrice": (
                                    outbound_bundle.price_info.child_ticket_price
                                    + inbound_bundle.price_info.child_ticket_price
                                ),
                                "childTaxPrice": (
                                    outbound_bundle.price_info.child_tax_price
                                    + inbound_bundle.price_info.child_tax_price
                                ),
                                "currency": outbound_bundle.price_info.currency,
                            },
                            "ssrInfo": FlightSsrInfoModel(
                                baggage=outbound_bundle.ssr_info.baggage + inbound_bundle.ssr_info.baggage
                            ),
                            "code": f"{outbound_bundle.code}^{inbound_bundle.code}",
                            "cabinLevel": outbound_bundle.cabin_level,
                            "cabin": f"{outbound_bundle.cabin}^{inbound_bundle.cabin}",
                            "fareKey": f"{outbound_bundle.fare_key}^{inbound_bundle.fare_key}",
                            "productTag": outbound_bundle.product_tag,
                            "seat": min(outbound_bundle.seat, inbound_bundle.seat),
                            "freightRateType": FreightRateTypeEnum.PT,
                        }))
                result.append(FlightJourneyModel.model_validate({
                    "segments": outbound.segments + inbound.segments,
                    "bundles": bundles,
                    "journeyKey": f"{outbound.journey_key}^{inbound.journey_key}",
                    "depAirport": outbound.dep_airport,
                    "arrAirport": inbound.arr_airport,
                    "depTime": outbound.dep_time,
                    "arrTime": inbound.arr_time,
                }))
        return result
