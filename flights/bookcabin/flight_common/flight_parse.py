from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.utils.date_util import DateUtil


class FlightParse:
    @classmethod
    def parse_search_response(cls,
                              response: dict,
                              child_count: int = 0) -> List[FlightJourneyModel]:
        data = response.get("data") or {}
        cart_id = data.get("cartId") or ""
        search_id = data.get("searchId") or ""
        if not cart_id or not search_id:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cartId/searchId")

        journeys: Dict[Tuple[str, ...], FlightJourneyModel] = {}
        for fare in cls.__collect_fares(data):
            segments = cls.__parse_segments(fare.get("flightGroups") or [])
            if not segments:
                continue
            bundle = cls.__parse_bundle(
                fare=fare,
                segments=segments,
                child_count=child_count,
                cart_id=cart_id,
                search_id=search_id,
            )
            if bundle is None:
                continue

            journey_key_tuple = tuple(segment.segment_key for segment in segments)
            journey = journeys.get(journey_key_tuple)
            if journey is None:
                journey = FlightJourneyModel(
                    journeyKey="^".join(journey_key_tuple),
                    segments=segments,
                    bundles=[],
                    depAirport=segments[0].dep_airport,
                    arrAirport=segments[-1].arr_airport,
                    depTime=segments[0].dep_time,
                    arrTime=segments[-1].arr_time,
                    ext={
                        "cartId": cart_id,
                        "searchId": search_id,
                    },
                )
                journeys[journey_key_tuple] = journey
            journey.bundles.append(bundle)

        result = list(journeys.values())
        if not result:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        return result

    @classmethod
    def parse_order_result(cls, response: dict) -> dict:
        data = response.get("data") or {}
        order = data.get("order") or {}
        order_items = order.get("orderItems") or []
        first_item = order_items[0] if order_items else {}
        flight_detail = first_item.get("flightDetail") or {}
        depart_detail = flight_detail.get("depart") or {}
        price_summary = first_item.get("priceSummary") or {}

        pnr = (
            order.get("bookingPNR")
            or flight_detail.get("bookingPNR")
            or depart_detail.get("providerPNR")
            or ""
        )
        if not pnr:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "BCMweb押位未返回PNR")

        total_amount = cls.__to_decimal(price_summary.get("totalAmount"))
        if total_amount is None:
            total_amount = Decimal("0")

        return {
            "pnr": pnr,
            "orderNo": str(order.get("orderId") or ""),
            "orderHashId": order.get("orderHashId") or "",
            "currency": first_item.get("currencyCode") or "",
            "totalAmount": total_amount,
            "rawOrder": order,
        }

    @classmethod
    def __collect_fares(cls, data: dict) -> List[dict]:
        result: List[dict] = []
        seen = set()

        def add_fare(fare_data: dict, route_key: str = "depart"):
            fare_id = fare_data.get("id")
            if not fare_id or fare_id in seen:
                return
            item = dict(fare_data)
            item["_routeKey"] = route_key
            result.append(item)
            seen.add(fare_id)

        fares = data.get("fares") or {}
        for route_key in ("depart", "return"):
            route_fares = fares.get(route_key) or []
            if isinstance(route_fares, list):
                for fare in route_fares:
                    add_fare(fare, route_key)

        ribboned_fares = data.get("ribbonedFares") or {}
        for ribbon in ribboned_fares.values():
            for fare in (ribbon or {}).get("fare") or []:
                add_fare(fare, "depart")

        return result

    @classmethod
    def __parse_segments(cls, flight_groups: List[dict]) -> List[FlightSegmentModel]:
        segments: List[FlightSegmentModel] = []
        for route_index, flight_group in enumerate(flight_groups, start=1):
            group_route_index = cls.__route_index(flight_group, route_index)
            flights = sorted(
                flight_group.get("flights") or [],
                key=lambda item: item.get("flightLegNumber") if item.get("flightLegNumber") is not None else 0,
            )
            for leg_index, flight in enumerate(flights, start=1):
                dep_airport = flight.get("departureAirport")
                arr_airport = flight.get("arrivalAirport")
                dep_time = cls.__parse_datetime(flight.get("departureDateTime"))
                arr_time = cls.__parse_datetime(flight.get("arrivalDateTime"))
                marketing_airline = flight.get("marketingAirline") or {}
                operating_airline = flight.get("operatingAirline") or {}
                carrier = (marketing_airline.get("code") or "").upper()
                operating_carrier = (operating_airline.get("code") or carrier).upper()
                flight_no = str(flight.get("flightNumber") or "")
                if not all([dep_airport, arr_airport, dep_time, arr_time, carrier, flight_no]):
                    continue

                full_flight_no = f"{carrier}{flight_no}"
                operating_flight_no = f"{operating_carrier}{flight_no}"
                segment_key = (
                    flight.get("flightUniqueId")
                    or f"{full_flight_no}|{dep_airport}{arr_airport}|{dep_time:%Y%m%d%H%M}"
                )
                segments.append(FlightSegmentModel(
                    segmentKey=segment_key,
                    depAirport=dep_airport,
                    arrAirport=arr_airport,
                    depTime=dep_time,
                    arrTime=arr_time,
                    carrier=carrier,
                    flightNumber=full_flight_no,
                    operatingCarrier=operating_carrier,
                    operatingFlightNumber=operating_flight_no,
                    routeIndex=group_route_index,
                    legIndex=leg_index,
                    ext={
                        "depTerminal": flight.get("departureTerminal") or "",
                        "arrTerminal": flight.get("arrivalTerminal") or "",
                        "aircraft": flight.get("aircraftType") or "",
                        "duration": flight.get("flightDurationInMinutes"),
                        "marketingCarrierName": marketing_airline.get("name") or "",
                        "operatingCarrierName": operating_airline.get("name") or "",
                        "flightBookingKey": flight.get("flightBookingKey") or "",
                    },
                ))
        return segments

    @classmethod
    def __parse_bundle(cls,
                       fare: dict,
                       segments: List[FlightSegmentModel],
                       child_count: int,
                       cart_id: str,
                       search_id: str) -> Optional[FlightBundleModel]:
        adult_price = cls.__passenger_price(fare, "ADULT") or cls.__passenger_price(fare, "ALL")
        if adult_price is None:
            return None
        child_price = cls.__passenger_price(fare, "CHILD") or cls.__passenger_price(fare, "CHD")
        if child_count > 0 and child_price is None:
            child_price = adult_price
        if child_price is None:
            child_price = adult_price

        fare_id = fare.get("id") or ""
        booking_key = ((fare.get("bookingInfo") or {}).get("bookingKey") or "").strip()
        product_tag = fare.get("displayName") or fare.get("name") or booking_key or "ECONOMY"
        cabin_level = cls.__cabin_level(fare)
        seat_count = cls.__seat_count(fare)
        selected_fare_id = {
            "depart": fare_id if fare.get("_routeKey") != "return" else "",
            "return": fare_id if fare.get("_routeKey") == "return" else "",
        }

        return FlightBundleModel(
            priceInfo=FlightBundlePriceModel(
                adultTicketPrice=adult_price["fare"],
                adultTaxPrice=adult_price["tax"],
                childTicketPrice=child_price["fare"],
                childTaxPrice=child_price["tax"],
                currency=adult_price["currency"],
            ),
            ssrInfo=cls.__parse_ssr_info(fare),
            code=booking_key or fare.get("cabin") or product_tag,
            cabinLevel=cabin_level,
            cabin=booking_key or fare.get("cabin") or cabin_level,
            fareKey=fare_id,
            productTag=product_tag,
            seat=seat_count,
            freightRateType=FreightRateTypeEnum.PT,
            ext={
                "cartId": cart_id,
                "searchId": search_id,
                "fareId": fare_id,
                "selectedFareId": selected_fare_id,
                "provider": fare.get("provider") or "",
                "name": fare.get("name") or "",
                "displayName": fare.get("displayName") or "",
                "fareBasisCode": fare.get("fareBasisCode") or "",
                "bookingKey": booking_key,
                "carrier": fare.get("carrier") or "",
                "carrierName": fare.get("carrierName") or "",
                "rawCabin": fare.get("cabin") or "",
                "flightsNum": ",".join(segment.flight_number for segment in segments),
            },
        )

    @staticmethod
    def __route_index(flight_group: dict, default_index: int) -> int:
        group_no = flight_group.get("flightGroupNumber")
        if isinstance(group_no, int):
            return group_no + 1
        return default_index

    @staticmethod
    def __passenger_price(fare: dict, pax_type: str) -> Optional[dict]:
        target = pax_type.upper()
        breakdown = next(
            (
                item for item in fare.get("breakdowns") or []
                if (item.get("paxType") or "").upper() == target
            ),
            None,
        )
        if not breakdown:
            return None

        fare_amount = FlightParse.__to_decimal(
            breakdown.get("discountedBaseFare")
            if breakdown.get("discountedBaseFare") is not None
            else breakdown.get("baseFare")
        )
        tax_amount = FlightParse.__to_decimal(breakdown.get("totalTax"))
        currency = breakdown.get("currencyCode") or ""
        if fare_amount is None or tax_amount is None or not currency:
            return None
        return {
            "fare": fare_amount,
            "tax": tax_amount,
            "currency": currency,
        }

    @classmethod
    def __parse_ssr_info(cls, fare: dict) -> FlightSsrInfoModel:
        baggage_items: List[FlightBaggageModel] = []
        for flight_group in fare.get("flightGroups") or []:
            for flight in flight_group.get("flights") or []:
                baggage_items.extend(cls.__baggage_models(
                    flight.get("carryOnBaggageOptions") or [],
                    SsrTypeEnum.HAND_BAGGAGE,
                    "HAND",
                ))
                baggage_items.extend(cls.__baggage_models(
                    flight.get("checkedBaggageOptions") or [],
                    SsrTypeEnum.HAULING_BAGGAGE,
                    "BAG",
                ))
        return FlightSsrInfoModel(baggage=baggage_items)

    @staticmethod
    def __baggage_models(options: List[dict], baggage_type: SsrTypeEnum, code_prefix: str) -> List[FlightBaggageModel]:
        result: List[FlightBaggageModel] = []
        for index, option in enumerate(options, start=1):
            quantity = option.get("quantity") or 0
            try:
                weight = int(quantity)
            except (TypeError, ValueError):
                weight = 0
            result.append(FlightBaggageModel(
                type=baggage_type,
                code=f"{code_prefix}{index}",
                price=Decimal("0"),
                number=1 if weight > 0 else 0,
                weight=weight,
                weightUnit=(option.get("unit") or "KG").upper(),
            ))
        return result

    @staticmethod
    def __seat_count(fare: dict) -> int:
        seats: List[int] = []
        for flight_group in fare.get("flightGroups") or []:
            for flight in flight_group.get("flights") or []:
                try:
                    seat = int(flight.get("seatsAvailable"))
                except (TypeError, ValueError):
                    continue
                if seat > 0:
                    seats.append(seat)
        return min(seats) if seats else -1

    @staticmethod
    def __cabin_level(fare: dict) -> str:
        cabin = (fare.get("cabin") or "").upper()
        name = ((fare.get("displayName") or fare.get("name") or "")).upper()
        if cabin in {"B", "C", "J"} or "BUSINESS" in name:
            return "C"
        if cabin in {"F"} or "FIRST" in name:
            return "F"
        return "Y"

    @staticmethod
    def __parse_datetime(date_text: str):
        if not date_text:
            return None
        return DateUtil.string_to_date_auto(date_text)

    @staticmethod
    def __to_decimal(value) -> Optional[Decimal]:
        if value is None:
            return None
        return Decimal(str(value))
