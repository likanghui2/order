import decimal
from typing import Optional, List

from common.enums.order_state_enum import OrderStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils.log_util import LogUtil
from common.utils.machine_cache_util import MachineCache
from flights.batik.flight_common.api_flight_info_parser import FlightParser
from flights.batik.script.api_script import ApiScript

LOG = LogUtil("batikSearch")

CACHE = MachineCache()


class ApiService:

    def __init__(self):
        self.__script = ApiScript()
        self.__token = None

    def initialize_token(self):
        self.token_cache = CACHE.get_data()
        if self.token_cache:
            self.__token = self.token_cache['value']
            self.__script.set_toke(self.__token)
        else:
            response = self.__script.init_token()
            self.__token = response['data']['token']

    def set_cache(self):
        if self.token_cache is None:
            CACHE.set_data(self.__token, 86000)
        else:
            CACHE.set_data(self.token_cache['value'], None, self.token_cache['timeOut'])

    def availability(self,
                     dep_airport: str,
                     arr_airport: str,
                     dep_date: str,
                     adt_number: int,
                     chd_number: int,
                     infant_count: int,
                     ret_date: Optional[str] = None) -> List[FlightJourneyModel]:

        data = {
            "flightRequests": [
                {
                    "originLocation": dep_airport if i == 0 else arr_airport,
                    "destinationLocation": arr_airport if i == 0 else dep_airport,
                    "departureDateTime": dep_date if i == 0 else ret_date,
                } for i in range(1 if ret_date is None else 2)
            ],
            "adultCount": adt_number,
            "childCount": chd_number,
            "infantCount": infant_count
        }
        response = self.__script.search(data)
        search_response = FlightParser.parse_flight_data(response)
        return search_response

    def booking(self, use_bundle: FlightBundleModel, passenger_info: List[PassengerInfoModel],
                contact_info: ContactInfoModel, flight_number: str, response_order_data: ResponseOrderInfoModel):
        select_price = self.select_price(use_bundle.fare_key.split('^'))
        self.add_passenger(passenger_info, contact_info)

        # self.get_baggage(flight_number)
        # self.add_baggage(passenger_info)
        pnr_info = self.get_pnr()
        pnr = pnr_info["data"]["bookingReloc"]
        response_order_data.order_number = ""
        response_order_data.pnr = pnr
        response_order_data.passengers = passenger_info
        response_order_data.currency_code = pnr_info["data"]["fare"]["totalFare"]["code"]
        response_order_data.journeys[0].bundles = [use_bundle]
        response_order_data.contact_info = contact_info
        response_order_data.total_amount = decimal.Decimal(str(pnr_info["data"]["fare"]["totalFare"]["amount"]))
        response_order_data.order_state = OrderStateEnum.HOLD

    def select_price(self, key):
        trip_type = 'Oneway'
        if len(key) > 1:
            trip_type = 'Return'
        data = {
            "shoppingBasketHashCodes": key,
            "tripType": trip_type
        }
        response = self.__script.select_price(data)
        return response

    def add_passenger(self, passenger_info: List[PassengerInfoModel], contact_info: ContactInfoModel):
        passengers = []
        one_title = None
        for index, value in enumerate(passenger_info):
            value.key = str(index + 1)
            if value.type.value == 'ADT':
                passenger_type = "ADT"
                if value.gender.value == 'M':
                    title = "Mr"
                    gender = "MALE"
                else:
                    title = "Mrs"
                    gender = "FEMALE"
            else:
                passenger_type = "CHD"
                if value.gender.value == 'M':
                    title = "Mstr"
                    gender = "MALE"
                else:
                    title = "Miss"
                    gender = "FEMALE"
            if index == 0:
                one_title = title
            number = f"{passenger_type}{index + 1}"
            pass_data = {
                "title": title,
                "firstName": value.first_name,
                "surName": value.last_name,
                "gender": gender,
                "number": number,
                "type": passenger_type,
                "doB": value.birthday,
                "specialRequest": ""
            }
            if value.document_info is not None and value.document_info.number:
                pass_data["document"] = {
                    "type": "Passport",
                    "number": value.document_info.number,
                    "expiry": value.document_info.expire_date,
                    "issuingCountry": value.document_info.issuing_country,
                    "nationality": value.document_info.nationality
                }
            passengers.append(pass_data)
        data = {
            "passenger": passengers,
            "isInsuranceSelected": False,
            "contact": {
                "title": one_title,
                "firstName": contact_info.first_name,
                "surName": contact_info.last_name,
                "phone": [
                    {
                        "originCode": f"+{contact_info.phone_code}",
                        "number": contact_info.phone_number,
                        "type": "MOBILE"
                    }
                ],
                "agentMail": contact_info.email_address,
                "passengerMail": contact_info.email_address
            }
        }
        response = self.__script.add_passenger(data)
        return response

    def get_baggage(self):
        response = self.__script.get_baggage()
        # todo 暂不处理行李
        # flight_number_list = flight_number_.split('|')
        # baggage_list = []
        # for index, value in enumerate(response['data']['baggage']):
        #     flight_number = flight_number_list[index]
        #     bagggaes = []
        #     if not value.get('ancillary'):
        #         continue
        #     for i in value['ancillary']:
        #         price = i['amount']['amount']
        #         currency = i['amount']['code']
        #         total_weight = i['weight']
        #         code = i['subCode']
        #         pieces = i['quantity']
        #         bagggaes.append(BaggageInfoModel.model_validate({
        #             'baggageType': BaggageTypeEnum.HAULING_BAGGAGE,
        #             'pieces': pieces,
        #             'totalWeight': total_weight,
        #             'flightNumber': flight_number,
        #             'amount': price,
        #             'code': code,
        #             'currency': currency,
        #         }))
        #     baggage_list.append(bagggaes)
        # return baggage_list

    def add_baggage(self):
        data_list = [
            {
                "subCode": "B10",
                "groupCode": "BG",
                "segment": {
                    "origin": "BOM",
                    "destination": "KUL",
                    "departure": "2026-02-28T23:20:00",
                    "type": "ITINERARY_PART"
                },
                "passenger": [
                    {
                        "index": 1,
                        "quantity": 1
                    }
                ]
            }
        ]
        response = self.__script.add_baggage(data_list)
        return response

    #
    def get_pnr(self):
        ticket_type = "Hold"
        data = {
            "ticketType": ticket_type,
            "remarks": "GetPaymentOptions"
        }
        self.__script.get_pay_type(data)
        data = {
            "ticketType": ticket_type,
            "remarks": "createpnr"
        }
        pnr_response = self.__script.create_pnr(data)
        return pnr_response

    #
    def pay(self, pnr):
        data = {
            "Reloc": pnr,
            "ticketType": "Prepaid",
            "remarks": "IssueTicket"
        }
        pay_response = self.__script.pay(data)
        return pay_response

    #
    def get_order_detail(self, pnr):
        order_detail_response = self.__script.order_detail(pnr)
        return order_detail_response

    def after_add_ancillary(self, pnr):
        self.__script.after_get_baggage(pnr=pnr)
        data = {
            "addOn": [
                {
                    "groupCode": "BG",
                    "subCode": "0CZ",
                    "segment": {
                        "origin": "BOM",
                        "flightNumber": 216,
                        "destination": "KUL",
                        "departure": "2026-02-28T23:20:00",
                        "type": "ITINERARY_PART",
                        "segmentNumber": 1
                    },
                    "passenger": [
                        {
                            "index": 0,
                            "quantity": 1,
                            "nameNumber": "01.01"
                        }
                    ]
                },
                {
                    "groupCode": "SA",
                    "subCode": "4A",
                    "segment": {
                        "origin": "BOM",
                        "destination": "KUL",
                        "departure": "2026-02-28T00:00:00",
                        "type": "SEGMENT",
                        'flightNumber': 216,
                        "segmentNumber": 1
                    },
                    "passenger": [
                        {
                            "index": 0,
                            "quantity": 1,
                            "nameNumber": "01.01"
                        }
                    ]
                }
            ],
            "bookingReloc": pnr,
            "ticketType": "Prepaid"
        }
        self.__script.after_add_baggage(data=data, pnr=pnr)

    def pnr_cancel(self, pnr):
        self.__script.cancel(pnr)

    #
    def pnr_refund(self, pnr):
        data = {
            "reloc": pnr,
            "personNameNumbers": ["01.01"]
        }
        response = self.__script.refund(data)
        return response

    def special_refund(self, pnr, email_address):
        data = {
            "bookingReloc": pnr,
            "emailAddress": email_address,
            "waiverCode": "DELAYED (DLY)",
            # "FileUploadId": "20241010181642558",
            "refundRequestPassengers": [
                {
                    "nameNumber": "02.01"
                },
                # {
                #     "nameNumber": "02.01"
                # }
            ]
        }
        response = self.__script.special_refund(data)

    def exchange(self, pnr):
        data = {
            "flightRequests": [
                {
                    "originLocation": "BOM",
                    "destinationLocation": "KUL",
                    "departureDateTime": "2026-02-28",
                }
            ],
            "adultCount": 1,
            "childCount": 0,
            "infantCount": 0
        }
        response = self.__script.search_exchange(data)
        data = {
            "bookingReloc": pnr,
            "newSegment": [
                {
                    "airlineCode": "OD",
                    "flightNumber": str(
                        response["data"]["brandedResults"]["itineraryPartBrands"][0][0]["itineraryPart"]["segments"][0][
                            "flight"]["flightNumber"]),
                    "class":
                        response["data"]["brandedResults"]["itineraryPartBrands"][0][0]["itineraryPart"]["segments"][0][
                            "bookingClass"],
                    "departureDate":
                        response["data"]["brandedResults"]["itineraryPartBrands"][0][0]["itineraryPart"]["segments"][0][
                            "departure"],
                    "departurePort":
                        response["data"]["brandedResults"]["itineraryPartBrands"][0][0]["itineraryPart"]["segments"][0][
                            "origin"]["locationCode"],
                    "arrivalPort":
                        response["data"]["brandedResults"]["itineraryPartBrands"][0][0]["itineraryPart"]["segments"][0][
                            "destination"]["locationCode"],
                    "marketingCarrier": "OD",
                    "segmentNumber": "1",
                    "numberInParty": 1,
                    "fareBasisCode":
                        response["data"]["brandedResults"]["itineraryPartBrands"][0][0]["itineraryPart"]["segments"][0][
                            "fareBasis"],
                    "brand": "VL"
                }
            ],
            "personNameNumbers": [
                "02.01"
            ],
            "cancelSegment": [
                1
            ]
        }
        self.__script.detail_exchange(data)
        data = {
            "bookingReloc": pnr,
            "ticketType": "Prepaid"
        }
        self.__script.confirm_exchange(data)

    def logout(self):
        self.__script.logout()
    @staticmethod
    def get_ticket_number(pnr_info, passenger_info: list[PassengerInfoModel]):
        # 提取源列表
        pnr_passengers = pnr_info["data"]["pnrResponse"]["itinerary"][0]["flight"]["passenger"]
        ticket_list = pnr_info["data"]["pnrResponse"]["travelerTicketDetail"]

        for pax in passenger_info:
            # 1. 查找对应的 Name Number
            # 使用 next() 查找第一个满足条件的元素，找不到返回 None
            matched_pnr_pax = next(
                (p for p in pnr_passengers
                 if p["lastName"].upper() == pax.last_name.upper()
                 and p["firstName"].upper() == pax.first_name.upper()),
                None
            )

            if matched_pnr_pax:
                pax.key = matched_pnr_pax['nameNumber']

                # 2. 只有找到了 Key，才去查找 Ticket
                matched_ticket = next(
                    (t for t in ticket_list if t["nameNumber"] == pax.key),
                    None
                )

                if matched_ticket:
                    pax.ticket_number = matched_ticket["ticket"]

        return passenger_info
