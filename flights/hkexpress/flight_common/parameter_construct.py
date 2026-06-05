import decimal
import json
from typing import Optional, List

from common.enums.passenger_type_enum import PassengerTypeEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.response_info_model import ResponseInfoModel
from flights.hkexpress.config import Config


class ParameterConstruct:

    @classmethod
    def search_construct(cls,
                         dep_airport: str,
                         arr_airport: str,
                         dep_date: str,
                         adt_number: int,
                         chd_number: int,
                         currency_code: str,
                         promotion_code: Optional[str] = None,
                         ret_date: Optional[str] = None):
        flights_data = {
            "origin": dep_airport,
            "destination": arr_airport,
            "begin_date": dep_date,
        }

        if ret_date:
            flights_data["end_date"] = ret_date

        submit_data = {
            "application_code": "IBE",
            "flights": [flights_data],
            "currency_code": currency_code,
            "promotion_code": "" if not promotion_code else promotion_code,
            "passengers": {
                "adult_count": adt_number,
                "infant_count": 0,
                "children_count": chd_number
            }
        }

        return submit_data

    @staticmethod
    def ssr_booking_construct(key_list: dict[str, List], currency_code: str) -> dict:
        journeys = []

        for key, value in key_list.items():
            segments = [
                {
                    'segment_key': x[0],
                    'leg_key': x[1]
                }
                for x in value
            ]
            journeys.append({
                "journey_key": key,
                "segments": segments
            })

        submit_data = {
            "currency_code": currency_code,
            "application_code": "IBE",
            "journeys": journeys
        }

        return submit_data

    @staticmethod
    def passenger_construct(passengers: List[PassengerInfoModel]):

        result_passengers = []
        for passenger in passengers:
            passenger_info = {
                "title": Config.TITLE_MAP[f'{passenger.type.value}_{passenger.gender.value}'],
                "first_name": passenger.first_name,
                "last_name": passenger.last_name,
                "date_of_birth": passenger.birthday,
                "passenger_type": passenger.type.value,
                "passenger_key": passenger.key,
                "seats": [],
                "gender": Config.GENDER_MAP[passenger.gender],
                "passport": ""
            }

            if passenger.document_info is not None:
                passenger_info["travel_doc"] = {
                    "doc_type": Config.DOCUMENT_TYPE_MAP[passenger.document_info.type],
                    "doc_nationality": passenger.document_info.nationality,
                    "doc_number": passenger.document_info.number,
                    "expire_date": passenger.document_info.expire_date,
                    "issuing_country": passenger.document_info.issuing_country,
                }
            result_passengers.append(passenger_info)

        return result_passengers

    @staticmethod
    def journey_construct(journeys: List[FlightJourneyModel],
                          bundle_info: FlightBundleModel,
                          passengers: List[PassengerInfoModel]):

        journey_infos = []

        item_amount = decimal.Decimal(0)
        surcharge_amount = decimal.Decimal(0)
        tax_amount = decimal.Decimal(0)

        adt_number = 0
        chd_number = 0


        for  p in passengers:
            if p.type == PassengerTypeEnum.ADT:
                adt_number += 1
            else:
                chd_number += 1

            item_amount += decimal.Decimal(journeys[0].ext['passenger_base_price_data'][p.type.value]['ticket_price']) if isinstance(journeys[0].ext['passenger_base_price_data'][p.type.value]['ticket_price'], str) else journeys[0].ext['passenger_base_price_data'][p.type.value]['ticket_price']
            surcharge_amount += decimal.Decimal(journeys[0].ext['passenger_base_price_data'][p.type.value]['other_price']) if isinstance(journeys[0].ext['passenger_base_price_data'][p.type.value]['other_price'], str) else journeys[0].ext['passenger_base_price_data'][p.type.value]['other_price']
            tax_amount += decimal.Decimal(journeys[0].ext['passenger_base_price_data'][p.type.value]['tax_price']) if isinstance(journeys[0].ext['passenger_base_price_data'][p.type.value]['tax_price'], str) else journeys[0].ext['passenger_base_price_data'][p.type.value]['tax_price']


        for i in journeys:
            journey_infos.append(
                {
                    "origin_country": i.ext['origin']['market'],
                    "destination_country": i.ext['destination']['market'],
                    "origin_port": i.dep_airport,
                    "destination_port": i.arr_airport,
                    "fare_type": bundle_info.ext['type'],
                    "flight_numbers": [x.flight_number for x in i.segments],
                    "departure_date_time": i.ext['journeyData']['departure_date_time'],
                    "arrival_date_time": i.ext['journeyData']['arrival_date_time'],
                    "journey_key": i.journey_key,
                    "fare_availability_key": bundle_info.fare_key,
                    "item_amount": "0" if item_amount == 0 else  str(item_amount.quantize(decimal.Decimal('0.000000000'))),
                    "surcharge": "0" if surcharge_amount == 0 else  str(surcharge_amount.quantize(decimal.Decimal('0.000000000'))),
                    "tax": "0" if tax_amount == 0 else str(tax_amount.quantize(decimal.Decimal('0.000000000'))),
                    "is_first_journey": True,
                    "bundle": {
                        "bundle_code": bundle_info.code,
                        "adult_price": bundle_info.ext['adult_amount'] * adt_number,
                        "child_price": 0 if bundle_info.ext.get('child_amount', None) is None else bundle_info.ext[
                            'child_amount'] * chd_number,
                    }
                }
            )

        return journey_infos

    @staticmethod
    def contact_construct(contact_info: ContactInfoModel):

        return {
            "title": "MR",
            "passenger_type": "ADT",
            "phone_number": {
                "country_code": contact_info.phone_code,
                "number": contact_info.phone_number,
            },
            "first_name": contact_info.first_name,
            "last_name": contact_info.last_name,
            "email_address": contact_info.email_address,
            "date_of_birth": "2003-06-15T16:00:00.000Z",
            "language": "en-HK"
        }

    @staticmethod
    def ssr_construct(passengers: List[PassengerInfoModel]):

        result_list = []
        for passenger in passengers:
            for i in passenger.buy_baggage:
                result_list.append({
                    "ssr_code": i.code,
                    "ssr_key": i.key,
                    "item_amount": float(i.price),
                    "surcharge": 0,
                    "tax": 0,
                    "quantity": 1,
                    "_journeyIndex": 0,
                    "_passengerKey": passenger.key
                })
        return result_list

    @staticmethod
    def order_construct(total_amount:decimal.Decimal,
                        origin_market: str,
                        origin_port: str,
                        currency_code: str,
                        journeys: List[dict],
                        passengers: List[dict],
                        contact_info: dict,
                        ssr:List[dict],
                        cancel_quote_id: str):
        data = {
            "sales_channel": "ONLINE",
            "sales_market": origin_market,
            "customer_country": "HK",
            "sales_port": origin_port,
            "selected_currency_code": currency_code,
            "cash_amount": float(total_amount.quantize(decimal.Decimal('0.00'))),
            "mile_amount": 0,
            "infant_total_amount": "0.000000000",
            "promotion_code": "",
            "trip_type": "OW",
            "mcp": None,
            "is_subscribed_to_email": False,
            "journeys": journeys,
            "passengers": passengers,
            "ssrs": ssr,
            "contact_person": contact_info,
            "insurance": None,
            "carbon_offset": None,
            "total": {
                "amount": 10,
                "currency": "HKD",
                "label": "Grand total (including taxes)"
            },
            "language": "en-HK",
            "cancel_chooose_quote_id": cancel_quote_id
        }


        return data
