from typing import List, Optional, Tuple

from common.decorators.retry_decorator import retry_decorator
from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.utils.date_util import DateUtil
from flights.garuda.flight_common.flight_info_parser import FlightInfoParser
from flights.garuda.script.web_script import WebScript


class WebService:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__script = WebScript(proxy_info_data)
        self.office_id = None

    def initialize_session(self):
        self.__script.initialize_http_util()

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               ret_date: Optional[str],
               adt_number: int,
               chd_number: int,
               currency_code: str,
               promo_code: str = ""):
        airport_data = [
            (dep_airport, arr_airport, dep_date),
        ]
        if ret_date:
            airport_data.append((arr_airport, dep_airport, ret_date))

        return self.start_search(
            airport_data=airport_data,
            adult_count=adt_number,
            child_count=chd_number,
            currency=currency_code,
            promo_code=promo_code,
        )

    def start_search(self,
                     airport_data: List[Tuple[str, str, str]],
                     adult_count: int,
                     child_count: int,
                     currency: str,
                     promo_code: str = ""):
        location = 'id' if currency == "IDR" else ""
        flights = []
        for index, (origin, destination, flight_date) in enumerate(airport_data, start=1):
            flight_params = self.__build_search_params(
                dep_airport=origin,
                arr_airport=destination,
                dep_date=DateUtil.string_to_target_format(flight_date, "%Y-%m-%d"),
                adt_number=adult_count,
                chd_number=child_count,
                promo_code=promo_code,
            )
            if promo_code:
                self.__script.check_promocode(
                    dep_date=flight_params['parameter']['data']['depart'],
                    promo_code=promo_code,
                )
            flights.append(self.__script.search(flight_params, location, route_index=index))

        journey_list = FlightInfoParser.journey_info_parser(flight_data=flights)
        if not journey_list:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        self.office_id = flights[0]['result'].get('officeId')
        return journey_list

    def cart_booking(self, bundle: FlightBundleModel) -> dict:
        aid = bundle.fare_key
        if not aid:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'fareKey')
        booking_params = {
            'parameter': {
                'data': {
                    'aid': aid,
                    'officeId': self.office_id,
                },
            },
        }
        return self.__script.booking_request(booking_params)

    @retry_decorator([
        (ServiceStateEnum.ROBOT_CHECK, initialize_session),
    ], retry_max_number=3)
    def booking_booking(self,
                        cart_data: dict,
                        passengers: List[PassengerInfoModel],
                        contact_info: ContactInfoModel,
                        promo_code: str = "") -> dict:
        token = self.__script.get_cf_code()
        pax_info = self.__build_pax_info(passengers)
        traveler_ids = [item['id'] for item in pax_info]
        data = {
            "cid": cart_data["result"]["cartId"],
            "pricingData": cart_data['result']['pricingData'],
            "officeId": self.office_id,
            "promoCode": promo_code,
            "paxInfo": pax_info,
            "contactInfo": [
                {
                    "id": "1",
                    "tid": "01",
                    "travelerIds": traveler_ids,
                    "category": "personal",
                    "address": contact_info.email_address,
                    "purpose": "standard",
                    "contactType": "Email",
                },
                {
                    "id": "2",
                    "tid": "02",
                    "travelerIds": traveler_ids,
                    "category": "personal",
                    "address": contact_info.email_address,
                    "purpose": "notification",
                    "contactType": "Email",
                },
                {
                    "id": "3",
                    "tid": "03",
                    "travelerIds": traveler_ids,
                    "category": "personal",
                    "number": contact_info.phone_code + contact_info.phone_number,
                    "purpose": "standard",
                    "deviceType": "mobile",
                    "contactType": "Phone",
                },
            ],
            "garudaInfo": {
                "deviceId": "IBE",
                "deviceType": "IBE",
                "appVersion": "1.0",
                "appBuild": 1,
                "milesId": "",
            },
            "token": token,
        }
        return self.__script.add_passenger(data)

    @staticmethod
    def get_pnr(booking_data: dict) -> str:
        booking_list = booking_data.get("result", {}).get("booking", {}).get("data") or []
        pnr = booking_list[0].get("id") if booking_list else None
        if not pnr:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'pnr')
        return pnr

    @staticmethod
    def __build_pax_info(passengers: List[PassengerInfoModel]) -> List[dict]:
        gender_mapping = {
            GenderEnum.M: 'Male',
            GenderEnum.F: 'Female',
        }
        adt_title_mapping = {
            'Male': 'Mr',
            'Female': 'Ms',
        }
        chd_title_mapping = {
            'Male': 'Mstr',
            'Female': 'Miss',
        }
        result = []
        for index, passenger in enumerate(passengers):
            gender = gender_mapping[passenger.gender]
            passenger_type = 'ADT' if passenger.type == PassengerTypeEnum.ADT else 'CHD'
            title = adt_title_mapping[gender] if passenger.type == PassengerTypeEnum.ADT else chd_title_mapping[gender]
            result.append({
                "passengerTypeCode": passenger_type,
                "id": f"SKH-{index + 1}-EXT",
                "tid": f"PAX{index + 1}",
                "gender": gender,
                "names": [
                    {
                        "firstName": passenger.first_name,
                        "lastName": passenger.last_name,
                        "title": title,
                        "nameType": "universal",
                    },
                ],
                "dateOfBirth": DateUtil.string_to_target_format(passenger.birthday, "%Y-%m-%d"),
            })
        return result

    @staticmethod
    def __build_search_params(dep_airport: str,
                              arr_airport: str,
                              dep_date: str,
                              adt_number: int,
                              chd_number: int,
                              promo_code: str = "") -> dict:
        return {
            'parameter': {
                'data': {
                    'origin': dep_airport,
                    'destination': arr_airport,
                    'class': 'ECONOMY',
                    'depart': dep_date,
                    'pax': f'{adt_number}ADT,{chd_number}CHD' if chd_number > 0 else f'{adt_number}ADT',
                    'promoCode': promo_code,
                    'showSoldOut': False,
                    'isWeb': True,
                    'upSell': True,
                },
            },
        }
