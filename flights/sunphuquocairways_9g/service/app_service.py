import random
import string
import time
from datetime import date, datetime
from typing import Optional

from common.decorators.retry_decorator import retry_decorator
from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from flights.sunphuquocairways_9g.config import Config
from flights.sunphuquocairways_9g.flight_common.app_flight_parser import AppFlightParser
from flights.sunphuquocairways_9g.script.app_script import AppScript


class AppService:
    PAX_ID_CHARS = string.digits + string.ascii_lowercase

    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None, script=None):
        self._script = script or AppScript(proxy_info)

    def initialize_session(self) -> None:
        self._script.initialize_session()

    @retry_decorator(
        [(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, initialize_session)],
        retry_max_number=3,
    )
    def search(
        self,
        dep_airport: str,
        arr_airport: str,
        dep_date: str,
        adt_number: int,
        chd_number: int,
        currency_code: str,
        ret_date: Optional[str] = None,
        promo_code: str = "",
    ) -> list[FlightJourneyModel]:
        airport_data = [(dep_airport, arr_airport, dep_date)]
        if ret_date:
            airport_data.append((arr_airport, dep_airport, ret_date))
        response = self._script.search(
            airport_data=airport_data,
            adult_count=adt_number,
            child_count=chd_number,
            infant_count=0,
            promo_code=promo_code,
            **Config.currency_context(currency_code),
        )
        journeys = AppFlightParser.parse(response, child_count=chd_number, promo_code=promo_code)
        if not journeys:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        return journeys

    def create_and_hold(
        self,
        bundle: FlightBundleModel,
        passengers: list[PassengerInfoModel],
        contact_info: ContactInfoModel,
        currency_code: str,
    ) -> tuple[str, str]:
        try:
            if not bundle.fare_key:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "fare_key")
            context = Config.currency_context(currency_code)
            pax_ids = [self._pax_id() for _ in passengers]
            response = self._script.create_order(
                trip_ids=bundle.fare_key.split("^"),
                passenger_list=self._build_passengers(passengers, pax_ids),
                contact_list=self._build_contacts(contact_info, context["x_lang"]),
                **context,
            )
            booking_id = (response.get("data") or {}).get("booking_id")
            if not booking_id:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "booking_id")
            hold_response = self._script.hold_booking(booking_id=booking_id, **context)
            pnr = (hold_response.get("data") or {}).get("pnr_number")
            if not pnr:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "pnr_number")
            return booking_id, pnr
        finally:
            self._script.trace_id = None

    @classmethod
    def _build_passengers(cls, passengers: list[PassengerInfoModel], pax_ids: list[str]) -> list[dict]:
        adult_id = next(
            (pax_ids[index] for index, passenger in enumerate(passengers) if passenger.type == PassengerTypeEnum.ADT),
            None,
        )
        result = []
        for index, passenger in enumerate(passengers):
            birthday = passenger.birthday
            if isinstance(birthday, (date, datetime)):
                birthday = birthday.strftime("%Y-%m-%d")
            item = {
                "first_name": passenger.first_name,
                "last_name": passenger.last_name,
                "date_of_birth": birthday,
                "pax_id": pax_ids[index],
                "type": passenger.type.value,
                "title": cls._title(passenger),
            }
            if passenger.type == PassengerTypeEnum.INF:
                if not adult_id:
                    raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "婴儿关联成人")
                item["parent_id"] = adult_id
            result.append(item)
        return result

    @staticmethod
    def _build_contacts(contact_info: ContactInfoModel, language: str) -> list[dict]:
        return [
            {"tid": "1_1", "email": contact_info.email_address, "language": language},
            {
                "tid": "1_2",
                "dial_code": contact_info.phone_code.replace("+", ""),
                "number": contact_info.phone_number,
                "language": language,
            },
        ]

    @staticmethod
    def _title(passenger: PassengerInfoModel) -> str:
        if passenger.type == PassengerTypeEnum.ADT:
            return "Mrs" if passenger.gender == GenderEnum.F else "Mr"
        return "Ms" if passenger.gender == GenderEnum.F else "Mstr"

    @classmethod
    def _pax_id(cls) -> str:
        timestamp = cls._base36(int(time.time() * 1000))
        return timestamp + "".join(random.choices(cls.PAX_ID_CHARS, k=6))

    @staticmethod
    def _base36(value: int) -> str:
        if value == 0:
            return "0"
        result = []
        while value:
            value, remainder = divmod(value, 36)
            result.append(AppService.PAX_ID_CHARS[remainder])
        return "".join(reversed(result))
