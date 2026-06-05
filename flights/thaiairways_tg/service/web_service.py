from decimal import Decimal
from typing import List, Optional
from urllib.parse import quote

from common.decorators.retry_decorator import retry_decorator
from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.order.payment_info_model import PaymentInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils.date_util import DateUtil
from flights.thaiairways_tg.config import ThaiairwaysConfig
from flights.thaiairways_tg.flight_common.flight_info_parser import FlightInfoParser
from flights.thaiairways_tg.flight_common.paco_payment import PacoPayment
from flights.thaiairways_tg.script.web_script import WebScript

TITLE_MAP = {
    (GenderEnum.M, PassengerTypeEnum.ADT): "MR",
    (GenderEnum.F, PassengerTypeEnum.ADT): "MS",
    (GenderEnum.M, PassengerTypeEnum.CHD): "MSTR",
    (GenderEnum.F, PassengerTypeEnum.CHD): "MISS",
}


class WebService:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__script = WebScript(proxy_info)

    def initialize_session(self):
        self.__script.initialize_session()
        self.get_reese84()
        self.__script.initialization()

    @retry_decorator([
        (ServiceStateEnum.API_RESPONSE_EXCEPTION, None),
        (ServiceStateEnum.API_RESPONSE_FAILED, None),
    ], retry_max_number=5)
    def get_reese84(self):
        self.__script.get_reese84()

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               currency_code: str,
               cabin_level: str = "Y",
               ret_date: Optional[str] = None,
               promo_code: str = "",
               commercial_fare_families: Optional[List[str]] = None) -> List[FlightJourneyModel]:
        airport_data = [(dep_airport, arr_airport, dep_date)]
        if ret_date:
            airport_data.append((arr_airport, dep_airport, ret_date))
        return self.availability(
            airport_data=airport_data,
            currency_code=currency_code,
            adult_count=adt_number,
            child_count=chd_number,
            cabin_level=cabin_level,
            promo_code=promo_code,
            commercial_fare_families=commercial_fare_families,
        )

    def availability(self,
                     airport_data: list[tuple[str, str, str]],
                     currency_code: str,
                     adult_count: int,
                     child_count: int,
                     cabin_level: str = "Y",
                     promo_code: str = "",
                     commercial_fare_families: Optional[List[str]] = None) -> List[FlightJourneyModel]:
        travelers = [
            {"passengerTypeCode": passenger_type}
            for passenger_type, count in (("ADT", adult_count), ("CHD", child_count))
            for _ in range(count)
        ]
        commercial_fare_families = commercial_fare_families or [
            ThaiairwaysConfig.CABIN_TO_FARE.get(cabin_level, ThaiairwaysConfig.CABIN_TO_FARE["Y"])
        ]
        flight_list = []
        for route_index, _ in enumerate(airport_data):
            selected_bound_id = None
            if route_index == 1:
                selected_bound_id = flight_list[0]["data"]["airBoundGroups"][0]["airBounds"][0]["airBoundId"]
            itineraries = [
                {
                    "destinationLocationCode": item[1],
                    "originLocationCode": item[0],
                    "departureDateTime": f"{item[2]}T00:00:00.000",
                    "isRequestedBound": route_index == index,
                }
                for index, item in enumerate(airport_data)
            ]
            data = {
                "commercialFareFamilies": commercial_fare_families,
                "itineraries": itineraries,
                "travelers": travelers,
                "searchPreferences": {"showMilesPrice": False},
            }
            if selected_bound_id:
                data["selectedBoundId"] = selected_bound_id
            flight_list.append(self.__script.search_flight(data))
        return FlightInfoParser.journey_info_parser(flight_list)

    def availability_www(self,
                         airport_data: list[tuple[str, str, str]],
                         currency_code: str,
                         adult_count: int,
                         child_count: int,
                         cabin_level: str = "Y",
                         promo_code: str = "",
                         commercial_fare_families: Optional[List[str]] = None) -> List[FlightJourneyModel]:
        self.__script.auth_www(airport_data)
        travelers = [
            {"passengerTypeCode": passenger_type}
            for passenger_type, count in (("ADT", adult_count), ("CHD", child_count))
            for _ in range(count)
        ]
        commercial_fare_families = commercial_fare_families or [
            ThaiairwaysConfig.CABIN_TO_FARE.get(cabin_level, ThaiairwaysConfig.CABIN_TO_FARE["Y"])
        ]
        commercial_fare_families = list(dict.fromkeys(commercial_fare_families + ["DPECONOMY", "DPBUSINESS"]))
        flight_list = []
        for route_index, _ in enumerate(airport_data):
            selected_bound_id = None
            if route_index == 1:
                selected_bound_id = flight_list[0]["data"]["airBoundGroups"][0]["airBounds"][0]["airBoundId"]
            itineraries = [
                {
                    "id": index + 1,
                    "destinationLocationCode": item[1],
                    "originLocationCode": item[0],
                    "departureDateTime": f"{item[2]}T00:00:00.000",
                    "flexibility": 3,
                    "isRequestedBound": route_index == index,
                }
                for index, item in enumerate(airport_data)
            ]
            data = {
                "commercialFareFamilies": commercial_fare_families,
                "noOfAdt": str(adult_count),
                "noOfChd": child_count,
                "noOfInf": 0,
                "noOfYth": 0,
                "itineraries": itineraries,
                "travelers": travelers,
                "searchPreferences": {"showMilesPrice": False},
            }
            if selected_bound_id:
                data["selectedBoundId"] = selected_bound_id
            if promo_code:
                data["promotionCode"] = promo_code
            flight_list.append(self.__script.www_search_flight(data))

        return FlightInfoParser.journey_info_parser(flight_list)

    def booking(self,
                journey: FlightJourneyModel,
                bundle: FlightBundleModel,
                passengers: List[PassengerInfoModel],
                contact_info: ContactInfoModel,
                response_order_data: ResponseOrderInfoModel) -> ResponseOrderInfoModel:
        if not bundle.fare_key:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "fareKey")

        select_flight_response = self.__script.sell_flight(bundle.fare_key.split("^"))
        cart_id = select_flight_response["data"]["id"]
        self.add_passenger(passengers, contact_info, cart_id)
        order_response, pnr = self.orders(cart_id=cart_id, passengers=passengers)
        total_price, currency = self.parse_order_summary(order_response)

        journey.bundles = [bundle]
        response_order_data.pnr = pnr
        response_order_data.order_number = pnr
        response_order_data.passengers = passengers
        response_order_data.contact_info = contact_info
        response_order_data.currency_code = currency or bundle.price_info.currency
        response_order_data.total_amount = total_price
        response_order_data.journeys = [journey]
        response_order_data.order_state = OrderStateEnum.HOLD
        return response_order_data

    def add_passenger(self,
                      passengers: List[PassengerInfoModel],
                      contact_info: ContactInfoModel,
                      cart_id: str) -> None:
        for index, passenger in enumerate(passengers, start=1):
            traveler_id = f"SKH-{index}-EXT"
            passenger.key = traveler_id
            self.__script.add_passenger(
                url=(
                    f"https://api-des.thaiairways.com/v2/shopping/carts/{cart_id}/travelers/"
                    f"{traveler_id}?lastName={quote(passenger.last_name)}&includeWaitlist=false"
                ),
                data={
                    "id": traveler_id,
                    "passengerTypeCode": passenger.type.value,
                    "names": [
                        {
                            "firstName": passenger.first_name,
                            "lastName": passenger.last_name,
                            "middleName": "",
                            "title": TITLE_MAP.get((passenger.gender, passenger.type), "MR"),
                        }
                    ],
                    "dateOfBirth": DateUtil.string_to_target_format(passenger.birthday, "%Y-%m-%d"),
                    "gender": "male" if passenger.gender == GenderEnum.M else "female",
                    "nationalityCountryCodes": [],
                },
            )

        self.__script.add_contacts(
            cart_id=cart_id,
            last_name=passengers[0].last_name,
            data=[
                {
                    "id": "",
                    "travelerIds": [],
                    "category": "personal",
                    "contactType": "Email",
                    "purpose": "standard",
                    "address": contact_info.email_address,
                    "lang": "zh",
                },
                {
                    "id": "",
                    "travelerIds": [],
                    "category": "other",
                    "contactType": "Phone",
                    "purpose": "standard",
                    "deviceType": "mobile",
                    "countryPhoneExtension": f"+{contact_info.phone_code}",
                    "number": contact_info.phone_number,
                    "lang": "zh",
                },
                {
                    "id": "",
                    "contactType": "Phone",
                    "category": "other",
                    "purpose": "emergency",
                    "deviceType": "mobile",
                    "countryPhoneExtension": f"+{contact_info.phone_code}",
                    "number": contact_info.phone_number,
                    "travelerIds": [],
                    "lang": "zh",
                    "countryCode": "CN",
                    "addresseeName": contact_info.last_name + contact_info.first_name,
                },
            ],
        )

    @retry_decorator([
        (ServiceStateEnum.API_RESPONSE_EXCEPTION, None),
        (ServiceStateEnum.API_RESPONSE_FAILED, None),
    ], retry_max_number=3)
    def h_getcaptcha(self):
        token = self.__script.h_getcaptcha()
        self.__script.verify(token)

    @retry_decorator([
        (ServiceStateEnum.HCAP_RISK_CHECK_FAILED, h_getcaptcha),
    ], retry_max_number=3)
    def orders(self, cart_id: str, passengers: List[PassengerInfoModel]) -> tuple[dict, str]:
        response = self.__script.orders(cart_id=cart_id)
        order_data = response["data"][0]
        pnr = order_data["id"]
        if not pnr:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "pnr")

        traveler_map = {
            (traveler["names"][0]["lastName"].upper(), traveler["names"][0]["firstName"].upper()): traveler["id"]
            for traveler in order_data.get("travelers", [])
        }
        for passenger in passengers:
            passenger.key = traveler_map.get(
                (passenger.last_name.upper(), passenger.first_name.upper()),
                passenger.key,
            )
        return response, pnr

    def add_passenger_www(self,
                          passengers: List[PassengerInfoModel],
                          contact_info: ContactInfoModel,
                          cart_id: str) -> None:
        for index, passenger in enumerate(passengers, start=1):
            traveler_id = f"SKH-{index}-EXT"
            passenger.key = traveler_id
            self.__script.www_add_passenger({
                "passengerTypeCode": passenger.type.value,
                "id": traveler_id,
                "tid": f"PAX{index}",
                "names": [
                    {
                        "firstName": passenger.first_name,
                        "lastName": passenger.last_name,
                        "title": TITLE_MAP.get((passenger.gender, passenger.type), "MR"),
                    }
                ],
                "cartId": cart_id,
            })

        self.__script.www_retrieve_cart(cart_id)
        self.__script.www_add_contacts({
            "cartid": cart_id,
            "contactRequest": [
                {
                    "category": "personal",
                    "contactType": "Email",
                    "purpose": "standard",
                    "lang": "en",
                    "address": contact_info.email_address,
                },
                {
                    "category": "other",
                    "contactType": "Phone",
                    "purpose": "standard",
                    "deviceType": "mobile",
                    "lang": "en",
                    "countryPhoneExtension": f"+{contact_info.phone_code}",
                    "number": contact_info.phone_number,
                },
            ],
        })
        self.__script.www_retrieve_cart(cart_id)
        self.__script.www_duplicate_traveler(cart_id)

    def orders_www(self, cart_id: str, passengers: List[PassengerInfoModel]) -> tuple[dict, str]:
        travelers = [
            {
                "id": passenger.key or f"SKH-{index}-EXT",
                "isSingleName": False,
            }
            for index, passenger in enumerate(passengers, start=1)
        ]
        response = self.__script.www_orders(cart_id=cart_id, travelers=travelers)
        pnr = response["data"][0]["id"]
        if not pnr:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "pnr")
        return response, pnr

    def prepare_payment_www(self, order_id: str, last_name: str) -> dict:
        self.__script.www_order_baggage_policies(order_id=order_id, last_name=last_name)
        self.__script.www_order_retrieve(order_id=order_id, last_name=last_name)
        self.__script.www_ancillaries_catalogue(order_id=order_id, last_name=last_name)
        payment_data = self.__script.www_payment_init(order_id=order_id, last_name=last_name)
        if not payment_data.get("redirectionUrl"):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "redirectionUrl")
        return payment_data

    def payment_www(self,
                    payment_info: PaymentInfoModel,
                    contact_info: ContactInfoModel,
                    payment_data: dict,
                    response_order_data: ResponseOrderInfoModel) -> ResponseOrderInfoModel:
        payment_id = PacoPayment.payment_id(payment_data.get("redirectionUrl"))
        payment_page = self.__script.paco_payment_page_ui(payment_id)
        payment_page_data = payment_page.get("data") or {}
        paco_payment_info = payment_page_data.get("paymentInfo") or {}
        company_info = payment_page_data.get("companyInfo") or {}
        transaction_amount = paco_payment_info.get("transactionAmount") or {}
        response_order_data.total_amount, response_order_data.currency_code = PacoPayment.amount(transaction_amount)

        server_public_key = self.__script.paco_server_public_key()
        office_guid = paco_payment_info.get("officeGuid")
        if not office_guid:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "officeGuid")
        check_card_response = self.__script.paco_check_card(
            office_guid=office_guid,
            data=PacoPayment.encrypt_payload(PacoPayment.build_check_card_request(
                payment_id=payment_id,
                card_number=payment_info.card_number,
                currency_code=response_order_data.currency_code,
            ), server_public_key),
        )
        if not check_card_response.get("isValid"):
            raise ServiceError(ServiceStateEnum.PAYMENT_EXCEPTION, "PACO卡号校验失败")

        validate_card_holder = self.__script.paco_card_holder_validate(
            data=PacoPayment.encrypt_payload(payment_info.card_holder_name, server_public_key),
        )
        if not validate_card_holder:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cardHolderName")

        api_key = company_info.get("idToken")
        if not api_key:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "companyInfo.idToken")

        payment_type = PacoPayment.card_payment_type(payment_info.card_type, check_card_response.get("cardScheme"))
        request_data = PacoPayment.build_card_request(
            payment_page_data=payment_page_data,
            payment_info=payment_info,
            contact_info=contact_info,
            payment_type=payment_type,
        )
        payment_response = self.__script.paco_payment_non_ui(
            data=PacoPayment.encrypt_payload(request_data, server_public_key),
            api_key=api_key,
            api_version=str(paco_payment_info.get("apiVersion") or "1.0"),
        )
        redirect_url = self._payment_redirect_url(payment_response)
        if redirect_url:
            raise ServiceError(ServiceStateEnum.PAYMENT_EXCEPTION, f"PACO支付需要跳转确认[{redirect_url}]")

        status_response = self.__script.paco_payment_status(payment_id)
        process_url = self._payment_process_url(status_response)
        if process_url:
            self.__script.www_payment_process(process_url)

        ticketing_status = self.__script.www_ticketing_payment_status(
            order_number=paco_payment_info.get("orderNo") or payment_data.get("orderNumber"),
            referer=process_url or "https://www.thaiairways.com/booking/payment/process/",
        )
        if self._ticketing_payment_success(ticketing_status):
            response_order_data.order_state = OrderStateEnum.OPEN_FOR_USE
            return response_order_data

        status_message = self._payment_failed_message(status_response, ticketing_status)
        raise ServiceError(ServiceStateEnum.PAYMENT_EXCEPTION, status_message)

    @staticmethod
    def parse_order_summary(order_response: dict) -> tuple[Decimal, str]:
        order_data = order_response["data"][0]
        total_price_data = order_data["air"]["prices"]["totalPrices"][0]["total"]
        currency = total_price_data["currencyCode"]
        decimal_places = order_response.get("dictionaries", {}).get("currency", {}).get(
            currency, {}
        ).get("decimalPlaces", 2)
        total_price = Decimal(total_price_data["value"]) / (Decimal(10) ** decimal_places)
        return total_price, currency

    @staticmethod
    def _payment_redirect_url(payment_response: dict) -> Optional[str]:
        for path in (
            ("data", "webPaymentResult", "webPaymentUrl"),
            ("data", "webPaymentUrl"),
            ("data", "redirectUrl"),
            ("redirectUrl",),
        ):
            value = payment_response
            for key in path:
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _payment_process_url(status_response: dict) -> Optional[str]:
        payment_info = ((status_response.get("data") or {}).get("paymentInfo") or {})
        notification_urls = payment_info.get("notificationUrls") or {}
        payment_status = ((payment_info.get("paymentStatusInfo") or {}).get("paymentStatus") or "").upper()
        if payment_status in ["A", "S"]:
            return notification_urls.get("confirmationUrl")
        if payment_status == "C":
            return notification_urls.get("cancellationUrl")
        return notification_urls.get("failedUrl") or notification_urls.get("confirmationUrl")

    @staticmethod
    def _ticketing_payment_success(ticketing_status: dict) -> bool:
        return (
            ticketing_status.get("pgwStatus") in ["A", "S"]
            or ticketing_status.get("dapiPaymentFinalStatus") in ["PAYMENT_COMPLETED", "PROCESS_ON_HOLD"]
            or ticketing_status.get("status") in ["PAYMENT_COMPLETED", "PROCESS_ON_HOLD"]
        )

    @staticmethod
    def _payment_failed_message(status_response: dict, ticketing_status: dict) -> str:
        response_code = PacoPayment.response_code(status_response)
        response_description = PacoPayment.response_description(status_response)
        ticketing_final_status = ticketing_status.get("dapiPaymentFinalStatus") or ticketing_status.get("status")
        ticketing_status_code = ticketing_status.get("pgwStatus")
        return (
            f"PACO支付失败[{response_code or '-'}]，"
            f"卡组织响应[{response_description or '-'}]，"
            f"泰航状态[{ticketing_final_status or ticketing_status_code or '-'}]"
        )
