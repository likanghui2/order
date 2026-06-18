from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from flights.vietjet.config import Config


JsonDict = Dict[str, Any]


class AppBookingFlow:
    RESERVATION_STATUS = {
        "confirmed": True,
        "waitlist": False,
        "standby": False,
        "cancelled": False,
        "open": False,
        "finalized": False,
        "external": False,
    }

    PAYMENT_TYPE = {
        "international_debit_card": 0,
        "skyclub": 1,
        "qr_code": 2,
        "domestic_debit_card": 3,
        "pay_later": 4,
        "vjint": 5,
    }

    PAYMENT_IDENTIFIER = {
        "pay_later": "PL6",
        "pl15": "PL15",
        "pl30": "PL30",
        "vnpay": "VJVNPAY",
        "qr_code": "VJVNQR",
        "skyclub": "VJPAY",
        "visa": "VI",
        "vjint": "VJINT",
        "alipay": "VJPALI",
        "momo": "VJPMOMO",
        "zalo": "VJPZALO",
        "hdss": "VJHDSS",
    }

    @classmethod
    def build_payment_methods_params(
        cls,
        journey: FlightJourneyModel,
        departure_bundle: FlightBundleModel,
        return_bundle: Optional[FlightBundleModel] = None,
        status: int = 0,
    ) -> JsonDict:
        booking_keys = cls.booking_keys(departure_bundle, return_bundle)
        first_segment = journey.segments[0]
        return {
            "bookingKeyDeparture": booking_keys[0],
            "bookingKeyArrival": booking_keys[1] if len(booking_keys) > 1 else "",
            "flightCode": first_segment.carrier,
            "cityPair": f"{journey.dep_airport}-{journey.arr_airport}",
            "status": status,
        }

    @classmethod
    def build_reserve_payload(
        cls,
        journey: FlightJourneyModel,
        departure_bundle: FlightBundleModel,
        passengers: List[PassengerInfoModel],
        contact_info: ContactInfoModel,
        payment_method: Optional[JsonDict] = None,
        payment_method_criteria: Optional[JsonDict] = None,
        total_amount: Any = 0,
        currency_code: Optional[str] = None,
        payment_currency: Optional[JsonDict] = None,
        processing_currency_amounts: Optional[List[JsonDict]] = None,
        return_bundle: Optional[FlightBundleModel] = None,
        seat_selections: Optional[Iterable[Any]] = None,
        ancillary_purchases: Optional[Iterable[Any]] = None,
        insurance_policies: Optional[List[JsonDict]] = None,
        type_payment: str = "pay_later",
        extra: Optional[JsonDict] = None,
        route_type: Optional[Any] = None,
    ) -> JsonDict:
        booking_keys = cls.booking_keys(departure_bundle, return_bundle)
        app_passengers = cls.passengers(passengers, contact_info)
        seat_selection_list = cls.flatten_items(seat_selections)
        ancillary_purchase_list = cls.ancillary_purchases(ancillary_purchases)
        payment_transactions = [
            cls.payment_transaction(
                payment_method=payment_method or cls.default_payment_method(type_payment),
                payment_method_criteria=payment_method_criteria or {},
                total_amount=total_amount,
                currency_code=currency_code or departure_bundle.price_info.currency,
                payment_currency=payment_currency,
                processing_currency_amounts=processing_currency_amounts,
            )
        ]

        payload = {"Flag": False}
        payment_type = cls.payment_type_code(type_payment)
        if payment_type is not None:
            payload["PaymentType"] = payment_type
        if extra:
            payload.update(extra)
        payload["Data"] = {
            "ameliaData": {
                "typePayment": type_payment,
                "bookingInformation": cls.booking_information(contact_info),
                "passengers": app_passengers,
                "journeys": cls.journeys(
                    booking_keys,
                    len(app_passengers),
                    city_pair=cls.city_pair(journey, route_type),
                ),
                "SeatSelections": seat_selection_list,
                "AncillaryPurchases": ancillary_purchase_list,
                "paymentTransactions": payment_transactions,
                "insurancePolicies": insurance_policies,
            }
        }
        return cls.json_ready(payload)

    @classmethod
    def booking_keys(
        cls,
        departure_bundle: FlightBundleModel,
        return_bundle: Optional[FlightBundleModel] = None,
    ) -> List[str]:
        if return_bundle and return_bundle.fare_key:
            return [departure_bundle.fare_key, return_bundle.fare_key]
        return [key for key in (departure_bundle.fare_key or "").split("^") if key]

    @classmethod
    def booking_information(cls, contact_info: ContactInfoModel) -> JsonDict:
        return {
            "contactInformation": {
                "name": f"{contact_info.last_name} {contact_info.first_name}".strip().upper(),
                "phoneNumber": cls.phone_number(contact_info),
                "extension": contact_info.phone_code or "",
                "email": contact_info.email_address,
            },
            "hold": None,
        }

    @classmethod
    def passengers(
        cls,
        passengers: List[PassengerInfoModel],
        contact_info: ContactInfoModel,
    ) -> List[JsonDict]:
        normal_passengers: List[JsonDict] = []
        infants: List[JsonDict] = []

        for passenger in passengers:
            if passenger.type == PassengerTypeEnum.INF:
                infants.append(cls.passenger(passenger, contact_info, len(normal_passengers) + len(infants) + 1))
                continue
            normal_passengers.append(cls.passenger(passenger, contact_info, len(normal_passengers) + 1))

        for index, infant in enumerate(infants):
            adult_index = min(index, max(len(normal_passengers) - 1, 0))
            if normal_passengers:
                normal_passengers[adult_index].setdefault("infants", []).append(infant)

        return normal_passengers

    @classmethod
    def passenger(
        cls,
        passenger: PassengerInfoModel,
        contact_info: ContactInfoModel,
        index: int,
    ) -> JsonDict:
        document = passenger.document_info
        nationality = cls.country(document.nationality if document else None)
        issuing_country = cls.country(document.issuing_country if document else None)
        gender = cls.gender(passenger.gender)

        passport = None
        if document and document.number:
            passport = {
                "number": document.number,
                "expiryDate": document.expire_date or "",
                "issuingCountry": issuing_country,
                "issuingCity": "",
                "issuingDate": None,
            }

        reservation_profile = {
            "firstName": (passenger.first_name or "").upper(),
            "lastName": (passenger.last_name or "").upper(),
            "memberId": "",
            "middleName": "",
            "birthDate": passenger.birthday or "",
            "postalCode": None,
            "address": {
                "address1": "",
                "location": {
                    "country": nationality,
                    "province": None,
                },
            },
            "nationCountry": nationality,
            "personalContactInformation": cls.contact_channels(contact_info),
            "businessContactInformation": cls.contact_channels(contact_info),
            "destinationContactInformation": None,
            "loyaltyProgram": {"number": None},
            "preBoard": False,
            "status": {"active": True, "inactive": False, "denied": False},
            "reference1": "",
            "reference2": "",
            "gender": gender,
            "title": cls.title(passenger.type, passenger.gender),
            "notes": "booking by app",
            "passport": passport,
        }

        return {
            "reservationProfile": reservation_profile,
            "advancePassengerInformation": cls.advance_passenger_information(reservation_profile, passport),
            "passengerTypeCode": {"code": cls.passenger_type_code(passenger.type)},
            "index": index,
            "reservationStatus": dict(cls.RESERVATION_STATUS),
            "fareApplicability": {
                "adult": passenger.type == PassengerTypeEnum.ADT,
                "child": passenger.type == PassengerTypeEnum.CHD,
            },
        }

    @staticmethod
    def advance_passenger_information(reservation_profile: JsonDict,
                                      passport: Optional[JsonDict]) -> Optional[JsonDict]:
        if not passport or not passport.get("number"):
            return None
        passenger_document = {
            "firstName": reservation_profile.get("firstName"),
            "lastName": reservation_profile.get("lastName"),
            "middleName": reservation_profile.get("middleName"),
            "birthDate": reservation_profile.get("birthDate"),
            "number": passport.get("number"),
            "expiryDate": passport.get("expiryDate"),
            "issuingCountry": passport.get("issuingCountry"),
            "issuingCity": "",
            "issuingDate": None,
        }
        return {
            "firstName": reservation_profile.get("firstName"),
            "lastName": reservation_profile.get("lastName"),
            "middleName": reservation_profile.get("middleName"),
            "birthDate": reservation_profile.get("birthDate"),
            "documents": [
                {
                    "documentType": {
                        "code": "P",
                        "name": "Passport",
                    },
                    "documentInformation": passenger_document,
                }
            ],
        }

    @classmethod
    def journeys(cls,
                 booking_keys: List[str],
                 passenger_count: int,
                 city_pair: Optional[JsonDict] = None) -> List[JsonDict]:
        result = []
        for index, booking_key in enumerate(booking_keys, start=1):
            journey = {
                "index": index,
                "passengerJourneyDetails": [
                    {
                        "passenger": {"index": passenger_index},
                        "bookingKey": booking_key,
                        "reservationStatus": dict(cls.RESERVATION_STATUS),
                    }
                    for passenger_index in range(1, passenger_count + 1)
                ],
            }
            if city_pair and index == 1:
                journey["cityPair"] = city_pair
            result.append(journey)
        return result

    @staticmethod
    def city_pair(journey: FlightJourneyModel, route_type: Optional[Any] = None) -> Optional[JsonDict]:
        if not route_type:
            return None
        if isinstance(route_type, str):
            route_type = {"identifier": route_type}
        if not isinstance(route_type, dict):
            return None
        return {
            "identifier": f"{journey.dep_airport}-{journey.arr_airport}",
            "routeType": route_type,
        }

    @classmethod
    def payment_transaction(
        cls,
        payment_method: JsonDict,
        payment_method_criteria: JsonDict,
        total_amount: Any,
        currency_code: str,
        payment_currency: Optional[JsonDict],
        processing_currency_amounts: Optional[List[JsonDict]],
        exchange_rate: Any = 1,
    ) -> JsonDict:
        currency = dict(payment_currency) if payment_currency else {"code": currency_code}
        if currency.get("baseCurrency") is None:
            currency["baseCurrency"] = False
        return {
            "paymentMethod": cls.pick_payment_method(payment_method),
            "paymentMethodCriteria": payment_method_criteria,
            "currencyAmounts": [
                {
                    "totalAmount": cls.number(total_amount),
                    "currency": currency,
                    "exchangeRate": cls.number(exchange_rate),
                }
            ],
            "processingCurrencyAmounts": processing_currency_amounts,
            "allPassengers": True,
            "notes": "App booking payment",
        }

    @staticmethod
    def pick_payment_method(payment_method: JsonDict) -> JsonDict:
        return {
            key: payment_method[key]
            for key in ("key", "identifier", "description")
            if payment_method.get(key) is not None
        }

    @classmethod
    def default_payment_method(cls, type_payment: str) -> JsonDict:
        return {
            "identifier": cls.PAYMENT_IDENTIFIER.get(type_payment, type_payment),
        }

    @classmethod
    def payment_type_code(cls, type_payment: str) -> Optional[int]:
        return cls.PAYMENT_TYPE.get(type_payment)

    @classmethod
    def ancillary_purchases(cls, values: Optional[Iterable[Any]]) -> List[JsonDict]:
        purchases = []
        for item in cls.flatten_items(values):
            ancillary_item = item.get("ancillaryItem") if isinstance(item, dict) else None
            if isinstance(ancillary_item, dict):
                item = {
                    **item,
                    "ancillaryItem": {
                        "key": ancillary_item.get("key"),
                        "ancillaryCategory": ancillary_item.get("ancillaryCategory"),
                    },
                }
            purchases.append(item)
        return purchases

    @staticmethod
    def flatten_items(values: Optional[Iterable[Any]]) -> List[Any]:
        if not values:
            return []
        if isinstance(values, dict):
            values = values.values()
        result = []
        for value in values:
            if isinstance(value, (list, tuple)):
                result.extend(value)
            elif isinstance(value, dict):
                result.extend(value.values())
            else:
                result.append(value)
        return result

    @staticmethod
    def contact_channels(contact_info: ContactInfoModel) -> JsonDict:
        phone = AppBookingFlow.phone_number(contact_info)
        return {
            "mobileNumber": phone,
            "phoneNumber": phone,
            "email": contact_info.email_address,
        }

    @staticmethod
    def phone_number(contact_info: ContactInfoModel) -> str:
        phone = contact_info.phone_number or ""
        if phone.startswith("0"):
            phone = phone[1:]
        return phone

    @staticmethod
    def country(code: Optional[str]) -> Optional[JsonDict]:
        if not code:
            return None
        return {
            "code": Config.NATION_DICT.get(code, code),
        }

    @staticmethod
    def gender(gender: GenderEnum) -> str:
        return "male" if gender == GenderEnum.M else "female"

    @staticmethod
    def title(passenger_type: PassengerTypeEnum, gender: GenderEnum) -> str:
        if passenger_type == PassengerTypeEnum.INF:
            return "Infant"
        if passenger_type == PassengerTypeEnum.CHD:
            return "Master" if gender == GenderEnum.M else "Miss"
        return "Mr" if gender == GenderEnum.M else "Ms"

    @staticmethod
    def passenger_type_code(passenger_type: PassengerTypeEnum) -> str:
        if passenger_type == PassengerTypeEnum.CHD:
            return "CHD"
        if passenger_type == PassengerTypeEnum.INF:
            return "INF"
        return "ADT"

    @staticmethod
    def number(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        return value

    @classmethod
    def json_ready(cls, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, list):
            return [cls.json_ready(item) for item in value]
        if isinstance(value, tuple):
            return [cls.json_ready(item) for item in value]
        if isinstance(value, dict):
            return {key: cls.json_ready(item) for key, item in value.items()}
        return value
