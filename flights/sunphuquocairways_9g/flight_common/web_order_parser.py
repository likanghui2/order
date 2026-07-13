import json
import re
from decimal import Decimal

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from flights.sunphuquocairways_9g.config import Config


class WebOrderParser:
    @classmethod
    def parse(cls, itinerary: dict, baggage: dict | None = None) -> ResponseOrderInfoModel:
        data = itinerary.get("data") or {}
        dictionaries = itinerary.get("dictionaries") or {}
        pnr = str(data.get("id") or "") or None
        documents = data.get("travelDocuments") or []
        passengers = cls._passengers(
            data.get("travelers") or [],
            documents,
            data.get("services") or [],
            (baggage or {}).get("data") or {},
        )
        journeys = cls._journeys(data.get("air") or {}, dictionaries)
        currency = cls._currency(data, dictionaries)
        total_amount = cls._total_amount(data, dictionaries, currency)
        values = {
            "orderState": cls._order_state(itinerary, pnr, documents),
            "passengers": passengers,
            "journeys": journeys,
            "totalAmount": total_amount,
        }
        if pnr:
            values.update({"orderNumber": pnr, "pnr": pnr})
        contact = cls._contact(data.get("contacts") or [])
        if contact:
            values["contactInfo"] = contact
        if currency:
            values["currencyCode"] = currency
        return ResponseOrderInfoModel(**values)

    @classmethod
    def _order_state(cls, itinerary: dict, pnr: str | None, documents: list[dict]) -> OrderStateEnum:
        data = itinerary.get("data") or {}
        status_text = " ".join(
            str(data.get(key) or "")
            for key in ("status", "orderStatus", "bookingStatus", "state")
        ).upper()
        warning_text = json.dumps(itinerary.get("warnings") or []).upper()
        if any(value in status_text for value in ("CANCEL", "VOID", "DELETED")):
            return OrderStateEnum.CANCEL
        if "NO OFFER FOUND IN ORDER" in warning_text:
            return OrderStateEnum.CANCEL
        if any(
            str(document.get("documentType") or "").lower() == "eticket"
            and str(document.get("status") or "").upper() in {"ISSUED", "OPEN", "OPEN_FOR_USE"}
            for document in documents
        ):
            return OrderStateEnum.OPEN_FOR_USE
        if pnr and data.get("travelers"):
            return OrderStateEnum.HOLD
        return OrderStateEnum.UNKNOWN

    @classmethod
    def _passengers(
        cls,
        travelers: list[dict],
        documents: list[dict],
        services: list[dict],
        baggage_policies: dict,
    ) -> list[PassengerInfoModel]:
        ticket_by_traveler = {}
        for document in documents:
            if str(document.get("documentType") or "").lower() != "eticket":
                continue
            if str(document.get("status") or "").upper() not in {"ISSUED", "OPEN", "OPEN_FOR_USE"}:
                continue
            for traveler_id in document.get("travelerIds") or []:
                ticket_by_traveler[str(traveler_id)] = str(document.get("id") or "") or None

        result = []
        for traveler in travelers:
            names = traveler.get("names") or [{}]
            name = names[0]
            title = str(name.get("title") or "").upper()
            passenger_type = PassengerTypeEnum.get_object(str(traveler.get("passengerTypeCode") or "ADT"))
            passenger_type = passenger_type or PassengerTypeEnum.ADT
            traveler_id = str(traveler.get("id") or "")
            values = {
                "key": traveler_id or None,
                "type": passenger_type,
                "lastName": str(name.get("lastName") or ""),
                "firstName": str(name.get("firstName") or ""),
                "gender": GenderEnum.F if title in {"MRS", "MISS", "MS"} else GenderEnum.M,
                "birthday": traveler.get("dateOfBirth"),
                "ssr": FlightSsrInfoModel(
                    baggage=[
                        *cls._traveler_baggage(traveler_id, services),
                        *cls._policy_baggage(traveler_id, baggage_policies),
                    ]
                ),
                "ext": {"travelerId": traveler_id},
            }
            ticket_number = ticket_by_traveler.get(traveler_id)
            if ticket_number:
                values["ticketNumber"] = ticket_number
            result.append(PassengerInfoModel(**values))
        return result

    @staticmethod
    def _traveler_baggage(traveler_id: str, services: list[dict]) -> list[FlightBaggageModel]:
        result = []
        for service in services:
            ids = [str(value) for value in service.get("travelerIds") or []]
            single_id = str(service.get("travelerId") or "")
            if traveler_id not in ids and traveler_id != single_id:
                continue
            description = " ".join(
                str(item.get("content") or "") for item in service.get("descriptions") or []
            )
            match = re.search(r"(\d+(?:\.\d+)?)\s*KG", description, re.IGNORECASE)
            if not match:
                continue
            result.append(
                FlightBaggageModel(
                    type=SsrTypeEnum.HAULING_BAGGAGE,
                    code=str(service.get("id") or "") or None,
                    price=Decimal(0),
                    number=int(service.get("quantity") or 1),
                    weight=int(Decimal(match.group(1))),
                )
            )
        return result

    @staticmethod
    def _policy_baggage(traveler_id: str, policies: dict) -> list[FlightBaggageModel]:
        result = []
        policy_types = (
            ("freeCheckedBaggageAllowance", SsrTypeEnum.HAULING_BAGGAGE),
            ("freeCarryOnAllowance", SsrTypeEnum.HAND_BAGGAGE),
        )
        for key, baggage_type in policy_types:
            for item in policies.get(key) or []:
                if traveler_id not in [str(value) for value in item.get("travelerIds") or []]:
                    continue
                details = item.get("details") or {}
                descriptions = details.get("baggageCharacteristics") or []
                description = " ".join(str(value.get("description") or "") for value in descriptions)
                match = re.search(r"(\d+(?:\.\d+)?)\s*KG", description, re.IGNORECASE)
                if not match:
                    continue
                result.append(
                    FlightBaggageModel(
                        type=baggage_type,
                        price=Decimal(0),
                        number=int(details.get("quantity") or 1),
                        weight=int(Decimal(match.group(1))),
                    )
                )
        return result

    @classmethod
    def _journeys(cls, air: dict, dictionaries: dict) -> list[FlightJourneyModel]:
        flight_dictionary = dictionaries.get("flight") or {}
        result = []
        for route_index, bound in enumerate(air.get("bounds") or [], start=1):
            bound_flights = bound.get("flights") or []
            segments = []
            for leg_index, reference in enumerate(bound_flights, start=1):
                if str(reference.get("statusCode") or "").upper() == "UN":
                    continue
                flight_id = str(reference.get("id") or "")
                flight = flight_dictionary.get(flight_id) or {}
                departure = flight.get("departure") or {}
                arrival = flight.get("arrival") or {}
                if not departure.get("dateTime") or not arrival.get("dateTime"):
                    continue
                carrier = str(flight.get("marketingAirlineCode") or "9G")
                operating_carrier = str(flight.get("operatingAirlineCode") or carrier)
                segments.append(
                    FlightSegmentModel(
                        segmentKey=flight_id,
                        depAirport=departure.get("locationCode"),
                        arrAirport=arrival.get("locationCode"),
                        depTime=departure["dateTime"],
                        arrTime=arrival["dateTime"],
                        flightNumber=f"{carrier}{cls._number(flight.get('marketingFlightNumber'))}",
                        carrier=carrier,
                        operatingCarrier=operating_carrier,
                        operatingFlightNumber=(
                            f"{operating_carrier}{cls._number(flight.get('operatingFlightNumber') or flight.get('operatingAirlineFlightNumber') or flight.get('marketingFlightNumber'))}"
                        ),
                        routeIndex=route_index,
                        legIndex=leg_index,
                        ext={
                            "depTerminal": departure.get("terminal"),
                            "arrTerminal": arrival.get("terminal"),
                        },
                    )
                )
            if not segments:
                continue
            bundle = cls._bundle(bound_flights, dictionaries)
            result.append(
                FlightJourneyModel(
                    journeyKey="^".join(segment.segment_key for segment in segments),
                    segments=segments,
                    bundles=[bundle],
                    depAirport=segments[0].dep_airport,
                    arrAirport=segments[-1].arr_airport,
                    depTime=segments[0].dep_time,
                    arrTime=segments[-1].arr_time,
                    ext={"channel": "WEB", "orderDetail": True},
                )
            )
        return result

    @classmethod
    def _bundle(cls, bound_flights: list[dict], dictionaries: dict) -> FlightBundleModel:
        first = bound_flights[0] if bound_flights else {}
        family_code = str(first.get("fareFamilyCode") or "")
        currency = next(iter((dictionaries.get("currency") or {}).keys()), "")
        cabin = "|".join(str(item.get("bookingClass") or "") for item in bound_flights)
        cabin_level = "C" if any(
            "business" in str(item.get("cabin") or "").lower() for item in bound_flights
        ) else "Y"
        return FlightBundleModel(
            priceInfo=FlightBundlePriceModel(
                adultTicketPrice=Decimal(0),
                adultTaxPrice=Decimal(0),
                childTicketPrice=Decimal(0),
                childTaxPrice=Decimal(0),
                currency=currency,
            ),
            ssrInfo=FlightSsrInfoModel(baggage=[]),
            code=family_code,
            cabinLevel=cabin_level,
            cabin=cabin,
            fareKey="",
            productTag=Config.PRODUCT_TAG.get(family_code, family_code),
            seat=0,
            freightRateType=FreightRateTypeEnum.PT,
        )

    @staticmethod
    def _contact(contacts: list[dict]) -> ContactInfoModel | None:
        email = next((item for item in contacts if item.get("contactType") == "Email"), {})
        phone = next((item for item in contacts if item.get("contactType") == "Phone"), {})
        if not email and not phone:
            return None
        return ContactInfoModel(
            lastName="",
            firstName="",
            emailAddress=str(email.get("address") or ""),
            phoneCode=str(phone.get("countryPhoneExtension") or ""),
            phoneNumber=str(phone.get("number") or ""),
        )

    @staticmethod
    def _currency(data: dict, dictionaries: dict) -> str:
        records = data.get("paymentRecords") or []
        transactions = (records[0].get("paymentTransactions") or []) if records else []
        amount = (transactions[0].get("amount") or {}) if transactions else {}
        return str(amount.get("currencyCode") or next(iter((dictionaries.get("currency") or {}).keys()), ""))

    @staticmethod
    def _total_amount(data: dict, dictionaries: dict, currency: str) -> Decimal:
        records = data.get("paymentRecords") or []
        transactions = (records[0].get("paymentTransactions") or []) if records else []
        amount = (transactions[0].get("amount") or {}) if transactions else {}
        value = amount.get("value") or 0
        decimal_places = int(((dictionaries.get("currency") or {}).get(currency) or {}).get("decimalPlaces", 0))
        return Decimal(str(value)) / (Decimal(10) ** decimal_places)

    @staticmethod
    def _number(value) -> str:
        return str(value or "").zfill(4)
