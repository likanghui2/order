import base64
import copy
import json
from datetime import datetime
from decimal import Decimal
from typing import List, Any

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.document_info_model import DocumentInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.order.passenger_price_detail_model import PassengerPriceDetailModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils.dict_util import DictUtil
from flights.hkexpress.config import Config


class FlightInfoParser:

    @classmethod
    def journey_info_parser(cls, trip_data_list: List[Any], parser_type: int):

        if len(trip_data_list) > 1:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'Not supported travel type')

        if not trip_data_list[0]:
            return []

        if not (trip_data_list[0].get('journey') or trip_data_list[0].get('journeys')):
            return []

        result_data_list = []
        for trip_data in trip_data_list[0].get('journey') or trip_data_list[0].get('journeys'):
            journey_key = trip_data['journey_key']
            segments = [cls.segment_parser(x) for x in trip_data.get('segment') or trip_data['segments']]
            passenger_base_price_data = {}

            for i in ['adult_fare_details', 'child_fare_details']:
                if not trip_data['fare'][i]:
                    break

                other_price = Decimal(0)
                ticket_price = Decimal(0)
                tax_price = Decimal(0)

                for j in trip_data['fare'][i]['service_charge']:
                    if j['type'] == 'TAX':
                        tax_price += Decimal(j['amount'])
                    elif j['type'] == 'FARE':
                        if j.get('amount') is None and parser_type == 0:
                            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'amount is None')

                        ticket_price += 0 if j.get('amount') is None else Decimal(j['amount'])
                    else:
                        other_price += Decimal(j['amount'])

                if i.find('adult') != -1:
                    passenger_type = PassengerTypeEnum.ADT
                else:
                    passenger_type = PassengerTypeEnum.CHD

                passenger_base_price_data[passenger_type.value] = {
                    'ticket_price': ticket_price,
                    'tax_price': tax_price,
                    'other_price': other_price,
                }

            if passenger_base_price_data == {}:
                return []

            bundle_data = trip_data['fare'].get('bundle_offers') or [trip_data['fare'].get('bundle')]

            if not bundle_data:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'Bundle is None')

            currency_code = bundle_data[0]['currency_code'] if 'currency_code' in bundle_data[0] else trip_data_list[0][
                'currency_code']
            if not currency_code:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'Currency code is None')

            fare_availability_key = trip_data['fare']['fare_availability_key']
            if fare_availability_key is None and parser_type == 0:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'fareKey is None')

            bundles = [
                cls.bundle_parser(fare_availability_key, x, passenger_base_price_data, currency_code, parser_type) for x
                in bundle_data]

            for index, value in enumerate(segments):
                value.route_index = 1

            origin = trip_data_list[0].get('origin') or trip_data_list[0]['journeys'][0]['origin']['airport_code']
            if origin is None:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'origin is None')

            destination = trip_data_list[0].get('destination') or trip_data_list[0]['journeys'][0]['destination'][
                'airport_code']
            if destination is None:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'destination is None')

            result_data_list.append(FlightJourneyModel(
                segments=segments,
                bundles=bundles,
                journeyKey=journey_key,
                depAirport=segments[0].dep_airport,
                arrAirport=segments[-1].arr_airport,
                depTime=segments[0].dep_time,
                arrTime=segments[-1].arr_time,
                ext={
                    'journeyData': trip_data,
                    'origin': origin,
                    'destination': destination,
                    'passenger_base_price_data': passenger_base_price_data
                    # 'ticketPrice': passenger_base_price_data[PassengerTypeEnum.ADT]['ticket_price'],
                    # 'otherPrice': passenger_base_price_data[PassengerTypeEnum.ADT]['other_price'],
                    # 'taxAmount': passenger_base_price_data[PassengerTypeEnum.ADT]['tax_price'],
                }
            ))

        return result_data_list

    @classmethod
    def segment_parser(cls, data: dict) -> FlightSegmentModel:
        segment_key = data['segment_key']
        flight_number = data['flight_number']
        dep_airport = data['origin']
        arr_airport = data['destination']

        dep_time = datetime.strptime(data['departure_date_time'],
                                     '%Y-%m-%dT%H:%M:%S' if data['departure_date_time'].find(
                                         '+') == -1 else '%Y-%m-%dT%H:%M:%S%z').strftime('%Y%m%d%H%M')
        arr_time = datetime.strptime(data['arrival_date_time'], '%Y-%m-%dT%H:%M:%S' if data['arrival_date_time'].find(
            '+') == -1 else '%Y-%m-%dT%H:%M:%S%z').strftime('%Y%m%d%H%M')
        carrier = flight_number[0:2]
        ext = {
            "legs": data['legs']
        }

        ret = FlightSegmentModel(
            segmentKey=segment_key,
            depAirport=dep_airport,
            arrAirport=arr_airport,
            depTime=dep_time,
            arrTime=arr_time,
            carrier=carrier,
            flightNumber=flight_number,
            operatingCarrier=carrier,
            operatingFlightNumber=flight_number,
            ext=ext,
        )

        return ret

    @classmethod
    def bundle_parser(cls,
                      price_key: str,
                      data: dict,
                      passenger_base_price: dict,
                      currency_code,
                      parser_type: int) -> FlightBundleModel:
        code = data['bundle_code']

        if price_key:
            price_key_decode = base64.b64decode(price_key.replace('_', '+').replace('-', '=')).decode('utf-8')
            cabin = '^'.join([x.split('~')[1] for x in price_key_decode.split('^')])
        else:
            cabin = None

        if data["type"] == 'U_LITE':
            product_tag = Config.BUNDLE_TYPE_U_LITE
        elif data["type"] == 'LITE':
            product_tag = Config.BUNDLE_TYPE_LITE
        elif data["type"] == 'ESSE':
            product_tag = Config.BUNDLE_TYPE_ESSE
        elif data["type"] == 'MAX':
            product_tag = Config.BUNDLE_TYPE_MAX
        else:
            raise ValueError(f"Unsupported bundle type: {data['type']}")

        adult_ticket_price = None
        adult_tax_price = None
        child_ticket_price = None
        child_tax_price = None

        adult_ticket_price_data = data.get('adult_amount') if data.get('adult_price') is None else data.get(
            'adult_price')
        child_ticket_price_data = data.get('child_amount') if data.get('child_price') is None else data.get(
            'child_price')

        for key, value in {'adult': adult_ticket_price_data, 'child': child_ticket_price_data}.items():
            if value is None and parser_type == 0 and key == 'adult':
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, f'{key}Amount is None')

        if child_ticket_price_data is None:
            child_ticket_price_data = 0

        for i in passenger_base_price:
            ticket_price = passenger_base_price[i]['ticket_price']
            tax_price = passenger_base_price[i]['tax_price'] + passenger_base_price[i]['other_price']
            if i == PassengerTypeEnum.ADT.value:
                adult_ticket_price = ticket_price + Decimal(adult_ticket_price_data)
                adult_tax_price = tax_price
            elif i == PassengerTypeEnum.CHD.value:
                child_ticket_price = ticket_price + Decimal(child_ticket_price_data)
                child_tax_price = tax_price
            else:
                raise ValueError('invalid passenger type')

        price_info = FlightBundlePriceModel(
            adultTicketPrice=adult_ticket_price,
            adultTaxPrice=adult_tax_price,
            childTicketPrice=child_ticket_price or adult_ticket_price,
            childTaxPrice=child_tax_price or adult_tax_price,
            currency=currency_code,

        )

        ssr_info = FlightSsrInfoModel()

        temp_ssr_list = []

        bundle_ssr_data = data.get('bundles') if data.get('bundle_ssr') is None else data.get('bundle_ssr')
        # if bundle_ssr_data is None:
        #     raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'bundleSsr is None')

        if bundle_ssr_data:
            for j in bundle_ssr_data:
                ssr_code = j['ssr_code']
                if ssr_code.find('PC') == -1:
                    continue

                temp_ssr_list.append(FlightBaggageModel(
                    type=SsrTypeEnum.HAULING_BAGGAGE,
                    code=ssr_code,
                    price=Decimal(0),
                    weight=int(ssr_code[2:]),
                    number=1,
                ))

        # temp_ssr_list.append(FlightBaggageModel(
        #     type=SsrTypeEnum.CARRY_BAGGAGE,
        #     code='',
        #     price=Decimal(0),
        #     weight=7,
        #     number=1,
        # ))

        if code in ["GO1","GO3"]:
            temp_ssr_list.append(FlightBaggageModel(
                type=SsrTypeEnum.HAND_BAGGAGE,
                code='',
                price=Decimal(0),
                weight=7,
                number=1,
            ))

        ssr_info.baggage += temp_ssr_list

        return FlightBundleModel(
            priceInfo=price_info,
            ssrInfo=ssr_info,
            code=code,
            cabinLevel='Y',
            cabin=cabin,
            fareKey=price_key,
            productTag=product_tag,
            seat=-1,
            freightRateType=FreightRateTypeEnum.PT,
            ext={
                'adult_amount': adult_ticket_price_data,
                'child_amount': child_ticket_price_data,
                'type': data["type"]
            }
        )

    @classmethod
    def passenger_parser(cls, passenger_list):
        result_passengers = []

        for passenger in passenger_list:

            passenger_key = passenger.get('passenger_key')
            passenger_type = passenger.get('passenger_type')
            if passenger_type is None or Config.PASSENGER_TYPE_MAP.get(passenger_type) is None:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'invalid passenger type')

            last_name = passenger.get('last_name')
            first_name = passenger.get('first_name')
            if last_name is None or first_name is None:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'invalid passenger name')

            date_of_birth = passenger.get('date_of_birth')
            if date_of_birth is None:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'invalid passenger dateBirth')

            gender = passenger.get('title')
            if gender is None or Config.GENDER_MAP.get(gender) is None:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'invalid gender')

            gender = Config.GENDER_MAP.get(gender)
            document_data = passenger.get('travel_document')

            document_info = None
            if document_data is not None:
                document_type_text = document_data.get('type')
                document_type = DictUtil.reverse_lookup(Config.DOCUMENT_TYPE_MAP, document_type_text)
                issuing_country = document_data.get('issuing_country')
                nationality = document_data.get('nationality')
                number = document_data.get('number')
                expiry_date = document_data.get('expiry_date')
                document_info = DocumentInfoModel(
                    number=number,
                    expireDate=expiry_date,
                    type=document_type,
                    issuingCountry=issuing_country,
                    nationality=nationality,
                )

            r = PassengerInfoModel(
                key=passenger_key,
                type=Config.PASSENGER_TYPE_MAP.get(passenger_type),
                lastName=last_name,
                firstName=first_name,
                gender=gender,
                birthday=date_of_birth,
                ssr=FlightSsrInfoModel(),
                documentInfo=document_info
            )

            result_passengers.append(r)

        return result_passengers

    @classmethod
    def contact_parser(cls, contact_data):

        last_name = contact_data.get('last_name')
        first_name = contact_data.get('first_name')
        if last_name is None or first_name is None:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'invalid c data')

        email = contact_data.get('email_address')
        if email is None:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'invalid contactEmail data')

        phone = contact_data.get('phone_number')
        if phone is None:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'invalid contactPhone data')

        return ContactInfoModel(
            lastName=last_name,
            firstName=first_name,
            emailAddress=email,
            phoneNumber=phone[2:],
            phoneCode=phone[:2],
        )

    @classmethod
    def parse_order(cls, order_data, response_order_data=None):

        temp_order_data = ResponseOrderInfoModel()
        t_order_data = order_data[0]
        order_status = t_order_data['payment_detail']['status']
        temp_order_data.order_state = Config.PAYMENT_STATUS_MAP.get(order_status)
        if temp_order_data.order_state is None:
            temp_order_data.order_state = OrderStateEnum.UNKNOWN
        temp_order_data.journeys = cls.journey_info_parser(order_data, 1)
        temp_order_data.passengers = cls.passenger_parser(t_order_data['passengers'])
        for i in temp_order_data.passengers:
            i.ssr.baggage = copy.deepcopy(temp_order_data.journeys[0].bundles[0].ssr_info.baggage)
        if t_order_data.get('contact'):
            temp_order_data.contact_info = cls.contact_parser(t_order_data['contact'])
        if t_order_data.get('total_amount'):
            temp_order_data.total_amount = Decimal(t_order_data['total_amount'])
        temp_order_data.pnr = t_order_data['sales_reference']
        temp_order_data.currency_code = t_order_data['currency_code']

        if t_order_data.get('journeys'):
            for i in t_order_data['journeys'][0]['ssrs']:
                if i['type'] != "baggage": continue

                for j in i['product']:
                    passenger_key = j['passenger_key']
                    ssr_code = j['ssr_code']
                    amount = j['item_amount']
                    number = j['count']

                    if ssr_code[:2] != 'PC':
                        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'invalid ssr code')

                    t = next((x for x in temp_order_data.passengers if x.key == passenger_key), None)
                    if t is None:
                        continue

                    t.ssr.baggage.append(FlightBaggageModel(
                        type=SsrTypeEnum.HAULING_BAGGAGE,
                        price=amount,
                        number=number,
                        weight=int(ssr_code[2:]),
                    ))


        for passenger in temp_order_data.passengers:
            ticket_price = Decimal(0)
            tax_price = Decimal(0)
            if passenger.type == PassengerTypeEnum.ADT:
                ticket_price += Decimal(temp_order_data.journeys[0].bundles[0].price_info.adult_ticket_price)
                tax_price += Decimal(temp_order_data.journeys[0].bundles[0].price_info.adult_tax_price)
            elif passenger.type == PassengerTypeEnum.CHD:
                ticket_price += Decimal(temp_order_data.journeys[0].bundles[0].price_info.chd_ticket_price)
                tax_price += Decimal(temp_order_data.journeys[0].bundles[0].price_info.chd_tax_price)

            passenger.price_detail = PassengerPriceDetailModel(
                ticketPrice=ticket_price,
                taxPrice=tax_price,
            )

        return temp_order_data
