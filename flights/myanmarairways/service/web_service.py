from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from common.decorators.retry_decorator import retry_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from flights.myanmarairways.flight_common.flight_parser import parse_availability, parse_booking_id
from flights.myanmarairways.script.web_script import WebScript, get_turnstile_token


class WebService:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self._script = WebScript(proxy_info)

    def initialize_session(self):
        self._script.initialize_session()

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, initialize_session), (ServiceStateEnum.CURL_EXCEPTION, initialize_session)])
    def search(self, dep_airport: str, arr_airport: str, dep_date: str, adult_count: int,
               child_count: int, currency: str, cabin_class: str = "ECONOMY"):
        html = self._script.search(dep_airport, arr_airport, dep_date, adult_count, child_count,
                                   currency, cabin_class)
        return parse_availability(html, dep_airport, arr_airport, currency, adult_count + child_count)

    @staticmethod
    def _passenger_date(value: str) -> str:
        normalized = str(value).strip()
        if len(normalized) >= 10 and normalized[4] == "-":
            return datetime.strptime(normalized[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        return datetime.strptime(normalized[:10], "%d/%m/%Y").strftime("%d/%m/%Y")

    def passenger_body(self, passenger_html: str, passenger_infos: list[PassengerInfoModel],
                       contact_info: ContactInfoModel, cid: str, sid: str) -> str:
        soup = BeautifulSoup(passenger_html, "html.parser")
        passenger_ids = [item.get("value", "") for item in soup.select("input[name='passengerId']")]
        if len(passenger_ids) != len(passenger_infos):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "8M passengerId")
        form_data = [("_sid", sid), ("_cid", cid)]
        for index, passenger in enumerate(passenger_infos):
            document = passenger.document_info
            if not passenger.birthday or not document:
                raise ServiceError(ServiceStateEnum.DOCUMENT_INFO_NOT_NULL, passenger.get_passenger_name())
            prefix = f"passengerRequest.passengers[{index}]"
            form_data.extend([
                ("passengerId", passenger_ids[index]),
                (f"{prefix}.title", "MR." if passenger.gender.value == "M" else "MISS."),
                (f"{prefix}.givenName", passenger.first_name),
                (f"{prefix}.surname", passenger.last_name),
                (f"{prefix}.gender", passenger.gender.value),
                (f"{prefix}.country", document.nationality or document.issuing_country),
                (f"{prefix}.birthDate", self._passenger_date(passenger.birthday)),
                (f"{prefix}.documents[0].docType", "PASSPORT"),
                (f"{prefix}.documents[0].docId", document.number),
                (f"{prefix}.documents[0].docExpireDate", self._passenger_date(document.expire_date)),
                (f"{prefix}.documents[0].docIssueCountry", document.issuing_country),
            ])
            for meal in soup.select(f"select[name^='preferredMeals[{index}]']"):
                form_data.append((meal.get("name"), ""))
            form_data.append((f"{prefix}.membershipId", ""))
        contact_prefix = "passengerRequest.contacts[0]"
        phone_code = f"+{str(contact_info.phone_code).lstrip('+')}"
        phone_number = str(contact_info.phone_number).replace(" ", "")
        area_code = phone_number[:3]
        local_number = phone_number[3:]
        full_phone = f"{phone_code} {area_code} {local_number}"
        form_data.extend([
            (f"{contact_prefix}.givenName", contact_info.first_name),
            (f"{contact_prefix}.surname", contact_info.last_name),
            (f"{contact_prefix}.phoneNumber.countryCode", phone_code),
            (f"{contact_prefix}.phoneNumber.areaCode", area_code),
            (f"{contact_prefix}.phoneNumber.number", local_number),
            ("passenger_form__phone", full_phone),
            (f"{contact_prefix}.emailObj.email", contact_info.email_address.lower()),
            (f"{contact_prefix}.address.cityCode", "New York"),
            (f"{contact_prefix}.address.stateProvince", "New York"),
            (f"{contact_prefix}.address.lines[0]", "Main Street"),
            (f"{contact_prefix}.address.countryCode", "US"),
            (f"{contact_prefix}.address.streetNumber", "1"),
            (f"_{contact_prefix}.shareMarketInd", "on"),
            ("passengerRequest.invoiceRequest.invoiceType", "COMPANY"),
            ("passengerRequest.invoiceRequest.companyName", ""),
            ("passengerRequest.invoiceRequest.companyTaxOffice", ""),
            ("passengerRequest.invoiceRequest.companyTaxNumber", ""),
        ])
        return urlencode(form_data)

    def passenger_validation_data(self, passenger: PassengerInfoModel) -> dict:
        document = passenger.document_info
        if not passenger.birthday or not document:
            raise ServiceError(ServiceStateEnum.DOCUMENT_INFO_NOT_NULL, passenger.get_passenger_name())
        return {
            "passengerType": "ADLT",
            "givenName": passenger.first_name,
            "surname": passenger.last_name,
            "birthDate": self._passenger_date(passenger.birthday).replace("/", "."),
            "docId": document.number,
            "docExpireDate": self._passenger_date(document.expire_date).replace("/", "."),
            "membershipId": "",
            "title": "MR." if passenger.gender.value == "M" else "MISS.",
            "gender": passenger.gender.value,
            "country": document.nationality or document.issuing_country,
            "docType": "PASSPORT",
            "docIssueCountry": document.issuing_country,
        }

    def hold(self, journey: FlightJourneyModel, bundle: FlightBundleModel,
             passenger_infos: list[PassengerInfoModel], contact_info: ContactInfoModel) -> str:
        ext = bundle.ext or journey.ext or {}
        fare_reference_id = ext.get("fareReferenceId") or bundle.fare_key
        avail_index = int(ext.get("availIndex", 0))
        cid = ext.get("cid", "")
        sid = ext.get("sid", "")
        self._script.select_flight(fare_reference_id, avail_index, cid)
        self._script.get_turnstile_token()
        self._script.create_booking(cid, sid)
        location = self._script.next(cid, sid)
        html = self._script.passenger(cid, location)
        booking_id = parse_booking_id(html)
        # for passenger in passenger_infos:
        #     self._script.validate_passenger(self.passenger_validation_data(passenger), cid, sid)
        passenger_body = self.passenger_body(html, passenger_infos, contact_info, cid, sid)
        self._script.save_passengers(passenger_body)
        return booking_id
