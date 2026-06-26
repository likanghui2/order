from datetime import datetime
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
        type_payment: str = "",
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
                "name": (contact_info.first_name or contact_info.last_name or "").strip().upper(),
                "phoneNumber": cls.phone_number(contact_info),
                "extension": "",
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
        phone_country_code = cls.phone_country_code(contact_info)
        passenger_country_code = cls.country_iso2(document.nationality if document else None)
        gender = cls.gender(passenger.gender)
        title = cls.title(passenger.type, passenger.gender)
        profile_key = cls.passenger_profile_key(passenger.type)
        first_name = (passenger.first_name or "").upper()
        last_name = (passenger.last_name or "").upper()
        document_number = document.number if document and document.number else ""
        document_type = document.type.name if document and document.type else ("PASSPORT" if document_number else "")

        passport = None
        if document_number:
            passport = {
                "number": document_number,
                "expiryDate": document.expire_date or "",
                "issuingCountry": None,
                "issuingCity": "",
                "issuingDate": None,
            }

        reservation_profile = {
            "firstName": first_name,
            "lastName": last_name,
            "name": first_name,
            "surName": last_name,
            "memberId": "",
            "middleName": "",
            "birthDate": passenger.birthday or "",
            "birthday": cls.birthday(passenger.birthday),
            "address": {
                "address1": "",
                "location": {
                    "country": nationality,
                },
            },
            "businessContactInformation": cls.contact_channels(contact_info),
            "codeMember": "",
            "country": nationality,
            "countryCode": "",
            "destinationContactInformation": None,
            "documentNumber": document_number,
            "documentType": document_type,
            "email": contact_info.email_address,
            "followAdult": -1,
            "gender": gender,
            "inValids": {
                "address": False,
                "birthday": False,
                "country": False,
                "documentNumber": False,
                "email": False,
                "name": False,
                "phoneCode1": False,
                "phoneCode2": False,
                "phoneNumber1": False,
                "skyclubMember": False,
                "surName": False,
                "tooltipLastName": False,
                "tooltipPhone": False,
            },
            "indexScroll": 0,
            "isReceiveNotify": False,
            "key": profile_key,
            "keyFollow": 0,
            "loyaltyProgram": {"number": None},
            "mapInfo": False,
            "nameIcon": cls.passenger_name_icon(passenger.type),
            "passengers": [],
            "preBoard": False,
            "personalContactInformation": cls.contact_channels(contact_info),
            "phoneCode1": phone_country_code,
            "phoneCode2": passenger_country_code,
            "phoneNumber1": cls.phone_number(contact_info),
            "phoneNumber2": "",
            "status": {"active": True, "inactive": False, "denied": False},
            "reference1": "",
            "reference2": "",
            "skyclubMember": "",
            "title": title,
            "titleTranslate": title,
            "tooltipLastName": last_name,
            "tooltipPhone": last_name,
            "uuid": f"{profile_key}_{index - 1}",
            "notes": "booking by app",
            "passport": passport,
        }

        return {
            "reservationProfile": reservation_profile,
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
            "phoneNumber": "",
            "email": contact_info.email_address,
        }

    @staticmethod
    def phone_number(contact_info: ContactInfoModel) -> str:
        phone = (contact_info.phone_number or "").replace(" ", "")
        if phone.startswith("+"):
            return phone
        if phone.startswith("0"):
            phone = phone[1:]
        phone_code = (contact_info.phone_code or "").replace("+", "")
        return f"+{phone_code}{phone}" if phone_code else phone

    @classmethod
    def country(cls, code: Optional[str]) -> Optional[JsonDict]:
        if not code:
            return None
        code = code.upper()
        country_code = Config.NATION_DICT.get(code, code)
        return {
            "code": country_code,
            "href": f"https://vietjet-api.intelisys.ca/RESTv1/countries/{country_code}",
            "name": cls.country_name(country_code),
        }

    @staticmethod
    def country_name(country_code: Optional[str]) -> Optional[str]:
        if not country_code:
            return None
        for country_info in Config.Country_Code_Dict.values():
            if country_info.get("isoCode1") == country_code:
                return country_info.get("country")
        return None

    @staticmethod
    def country_iso2(code: Optional[str]) -> str:
        if not code:
            return ""
        code = code.upper()
        if len(code) == 2:
            return code.lower()
        for country_info in Config.Country_Code_Dict.values():
            if country_info.get("isoCode1") == code:
                return (country_info.get("isoCode") or "").lower()
        return ""

    @staticmethod
    def phone_country_code(contact_info: ContactInfoModel) -> str:
        phone_code = (contact_info.phone_code or "").replace("+", "")
        country_info = Config.Country_Code_Dict.get(phone_code)
        if not country_info:
            return ""
        return (country_info.get("isoCode") or "").lower()

    @staticmethod
    def birthday(date_value: Optional[str]) -> str:
        if not date_value:
            return ""
        for date_format in ("%Y-%m-%d", "%m-%d-%Y", "%Y%m%d"):
            try:
                return datetime.strptime(date_value[:10], date_format).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return date_value

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
    def passenger_profile_key(passenger_type: PassengerTypeEnum) -> str:
        if passenger_type == PassengerTypeEnum.CHD:
            return "child"
        if passenger_type == PassengerTypeEnum.INF:
            return "infant"
        return "adult"

    @staticmethod
    def passenger_name_icon(passenger_type: PassengerTypeEnum) -> str:
        if passenger_type == PassengerTypeEnum.CHD:
            return "children"
        if passenger_type == PassengerTypeEnum.INF:
            return "infants"
        return "adults"

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
