from decimal import Decimal
from itertools import product

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel


class FlightInfoParserV2:
    @classmethod
    def parse(cls, data: dict) -> list[FlightJourneyModel]:
        itineraries = data.get("itineraries")
        if not isinstance(itineraries, list) or not 1 <= len(itineraries) <= 2:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)

        directions = [
            cls._itinerary(itinerary, route_index)
            for route_index, itinerary in enumerate(itineraries, start=1)
        ]
        if any(not journeys for journeys in directions):
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        if len(directions) == 1:
            return directions[0]
        journeys = cls._link_round_trip(directions[0], directions[1])
        if not journeys:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        return journeys

    @classmethod
    def _itinerary(cls, itinerary: dict, route_index: int) -> list[FlightJourneyModel]:
        journeys = []
        for fare in itinerary.get("fares") or []:
            raw_segments = fare.get("flightSegs") or []
            if not raw_segments or any(
                (segment.get("carrier") or {}).get("airCode") != "SL"
                for segment in raw_segments
            ):
                continue
            segments = [
                cls._segment(segment, route_index, leg_index)
                for leg_index, segment in enumerate(raw_segments, start=1)
            ]
            bundles = [
                bundle for bundle in (
                    cls._bundle(fare, brand) for brand in fare.get("brands") or []
                ) if bundle is not None
            ]
            if not bundles:
                continue
            journeys.append(FlightJourneyModel(
                segments=segments,
                bundles=bundles,
                journeyKey=f"{fare['depPort']}|{fare['arrPort']}|{fare['depTime']}",
                depAirport=fare["depPort"],
                arrAirport=fare["arrPort"],
                depTime=fare["depTime"],
                arrTime=fare["arrTime"],
            ))
        if not journeys:
            return []
        return journeys

    @staticmethod
    def _segment(value: dict, route_index: int, leg_index: int) -> FlightSegmentModel:
        carrier = value.get("carrier") or {}
        air_code = carrier.get("airCode") or "SL"
        operating_code = carrier.get("opAirCode") or air_code
        flight_number = f"{air_code}{carrier.get('airFlightNo')}"
        operating_number = f"{operating_code}{carrier.get('opAirFlightNo') or carrier.get('airFlightNo')}"
        return FlightSegmentModel(
            segmentKey=str(value.get("segRef") or ""),
            depAirport=value["depPort"],
            arrAirport=value["arrPort"],
            depTime=value["depDate"],
            arrTime=value["arrDate"],
            flightNumber=flight_number,
            carrier=air_code,
            operatingCarrier=operating_code,
            operatingFlightNumber=operating_number,
            routeIndex=route_index,
            legIndex=leg_index,
            ext={"fareBasis": value.get("fareBasis") or ""},
        )

    @staticmethod
    def _bundle(fare: dict, brand: dict):
        if brand.get("soldOut") is True:
            return None
        prices = brand.get("paxFareCost") or []
        adult = next(
            (
                price.get("fareBreakDown") or {} for price in prices
                if (price.get("fareBreakDown") or {}).get("paxType") == "ADT"
            ),
            None,
        )
        if not adult or not adult.get("quantity"):
            return None
        child_price = next(
            (
                price for price in prices
                if (price.get("fareBreakDown") or {}).get("paxType") == "CHD"
            ),
            None,
        )
        adult_value = next(
            price for price in prices
            if (price.get("fareBreakDown") or {}).get("paxType") == "ADT"
        )
        adult_quantity = Decimal(str(adult["quantity"]))
        adult_fare = Decimal(str(adult.get("baseFare") or 0)) / adult_quantity
        adult_tax = Decimal(str((adult.get("tax") or {}).get("totalTax") or 0)) / adult_quantity
        child = (child_price or {}).get("fareBreakDown") or adult
        child_quantity = Decimal(str(child.get("quantity") or adult["quantity"]))
        child_fare = Decimal(str(child.get("baseFare") or 0)) / child_quantity
        child_tax = Decimal(str((child.get("tax") or {}).get("totalTax") or 0)) / child_quantity
        currency = adult_value.get("currency") or ""
        if child_price and child_price.get("currency") != currency:
            return None
        raw_segments = fare.get("flightSegs") or []
        cabins = "|".join(str(segment.get("bookingClass") or "") for segment in raw_segments)
        fare_basis = "|".join(str(segment.get("fareBasis") or "") for segment in raw_segments)
        return FlightBundleModel(
            priceInfo=FlightBundlePriceModel(
                adultTicketPrice=adult_fare,
                adultTaxPrice=adult_tax,
                childTicketPrice=child_fare,
                childTaxPrice=child_tax,
                currency=currency,
            ),
            ssrInfo=FlightSsrInfoModel(baggage=[]),
            code=fare_basis or str(brand.get("brandId") or ""),
            cabinLevel="C" if str(brand.get("class") or "").upper() == "BUSINESS" else "Y",
            cabin=cabins,
            fareKey=str(brand.get("basketHashCode") or ""),
            productTag=str(brand.get("brandLabel") or ""),
            seat=int(brand.get("seatsRemaining") or 0),
            freightRateType=FreightRateTypeEnum.PT,
            ext={"brandId": str(brand.get("brandId") or "")},
        )

    @classmethod
    def _link_round_trip(
        cls,
        outbound: list[FlightJourneyModel],
        inbound: list[FlightJourneyModel],
    ) -> list[FlightJourneyModel]:
        journeys = []
        for trip, return_trip in product(outbound, inbound):
            if trip.arr_time >= return_trip.dep_time:
                continue
            bundles = [
                cls._combine_bundles(trip_bundle, return_bundle)
                for trip_bundle, return_bundle in product(trip.bundles, return_trip.bundles)
            ]
            bundles = [bundle for bundle in bundles if bundle is not None]
            if not bundles:
                continue
            journeys.append(FlightJourneyModel(
                segments=trip.segments + return_trip.segments,
                bundles=bundles,
                journeyKey=f"{trip.journey_key}^{return_trip.journey_key}",
                depAirport=trip.dep_airport,
                arrAirport=return_trip.arr_airport,
                depTime=trip.dep_time,
                arrTime=return_trip.arr_time,
            ))
        return journeys

    @staticmethod
    def _combine_bundles(
        outbound: FlightBundleModel,
        inbound: FlightBundleModel,
    ) -> FlightBundleModel | None:
        if outbound.price_info.currency != inbound.price_info.currency:
            return None
        product_tag = outbound.product_tag
        if product_tag != inbound.product_tag:
            product_tag = f"{product_tag}^{inbound.product_tag}"
        return FlightBundleModel(
            priceInfo=FlightBundlePriceModel(
                adultTicketPrice=(
                    outbound.price_info.adult_ticket_price
                    + inbound.price_info.adult_ticket_price
                ),
                adultTaxPrice=(
                    outbound.price_info.adult_tax_price
                    + inbound.price_info.adult_tax_price
                ),
                childTicketPrice=(
                    outbound.price_info.child_ticket_price
                    + inbound.price_info.child_ticket_price
                ),
                childTaxPrice=(
                    outbound.price_info.child_tax_price
                    + inbound.price_info.child_tax_price
                ),
                currency=outbound.price_info.currency,
            ),
            ssrInfo=FlightSsrInfoModel(
                baggage=(outbound.ssr_info.baggage or []) + (inbound.ssr_info.baggage or []),
            ),
            code=f"{outbound.code}^{inbound.code}",
            cabinLevel=outbound.cabin_level,
            cabin=f"{outbound.cabin}^{inbound.cabin}",
            fareKey=f"{outbound.fare_key}^{inbound.fare_key}",
            productTag=product_tag,
            seat=min(outbound.seat, inbound.seat),
            freightRateType=outbound.freight_rate_type,
            ext={
                "brandId": (
                    f"{outbound.ext.get('brandId', '')}^{inbound.ext.get('brandId', '')}"
                ),
            },
        )
