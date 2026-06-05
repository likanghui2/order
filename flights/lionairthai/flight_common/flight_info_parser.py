import decimal
from typing import List, Any, Optional

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.utils.date_util import DateUtil
from common.utils.string_util import StringUtil


class FlightInfoParser:


    @classmethod
    def journey_info_parser(cls,trip_data_list: List[Any]):

        result_journey_info_list = []

        for info in trip_data_list:
            segment_data_list = []
            # # 过滤中转多航段
            if len(info['SegmentInformation']) != 1:
                continue

            is_stop = False
            stop_number = 0
            for i in info['SegmentInformation']:
                stop_number = i['NoOfStops']
                # if i['NoOfStops'] != 0:
                #     is_stop = True
                #     break

                r = cls.segment_parser(i)
                r.route_index = 1
                segment_data_list.append(r)


            bundle_data_list = []
            for i in ['PromoFlight','EconomyFlight']:
                t = None
                if info[i]:
                    t = cls.bundle_parser(info[i])
                if t is None:
                    continue

                if stop_number != 0:
                    if len(info[i]['FlightFlyInfo']) != stop_number:
                        continue

                    for j in range(len(info[i]['FlightFlyInfo'])):
                        segment_data_list[j].stopoverAirport = info[i]['FlightFlyInfo'][j]['ArrCity']
                        segment_data_list[j].stopoverTime = -1

                bundle_data_list.append(cls.bundle_parser(info[i]))

            if len(bundle_data_list) == 0:
                continue

            result_journey_info_list.append(FlightJourneyModel(
                segments=segment_data_list,
                bundles=bundle_data_list,
                journeyKey='',
                depAirport=segment_data_list[0].dep_airport,
                arrAirport=segment_data_list[0].arr_airport,
                depTime=segment_data_list[0].dep_time,
                arrTime=segment_data_list[0].arr_time,
                ext={
                    'AFIndex':info['AFIndex'],
                    'FlightIndex':info['FlightIndex'],
                }
            ))

        return result_journey_info_list

    @classmethod
    def segment_parser(cls,segment_data: dict) -> FlightSegmentModel:
        dep_time = DateUtil.string_to_date_auto(f"{segment_data['DepDate']} {segment_data['DepTime']}")
        arr_time = DateUtil.string_to_date_auto(f"{segment_data['ArrDate']} {segment_data['ArrTime']}")

        carrier = segment_data['MACode']
        operating_carrier = segment_data['OprAirlineCode']
        flight_number = f'{operating_carrier}{segment_data["FlightNo"]}'

        return FlightSegmentModel(
            depAirport=segment_data['DepCity'],
            arrAirport=segment_data['ArrCity'],
            segmentKey='',
            flightNumber=flight_number,
            carrier=carrier,
            operatingCarrier=operating_carrier,
            depTime=dep_time,
            arrTime=arr_time,
            operatingFlightNumber=flight_number,
        )

    @classmethod
    def bundle_parser(cls,bundle_info:dict) -> Optional[FlightBundleModel]:

        service_adt_fee = None
        service_chd_fee = None
        product_tag = bundle_info['FBClass']

        if product_tag is None:
            product_tag = 'LION PROMO'
        elif product_tag == 'Lion Economy':
            product_tag = 'LION ECONOMY'

        currency_code = bundle_info['CurrencyCode']

        adt_ticket_price = decimal.Decimal(bundle_info['priceInfo']['AdultPrice']['PricePerPax'])
        adt_tax_price =  decimal.Decimal(bundle_info['priceInfo']['AdultPrice']['TaxPerPax'])

        if adt_ticket_price <= 0 or adt_tax_price <= 0:
            return None

        chd_ticket_price = decimal.Decimal(bundle_info['priceInfo']['ChildPrice']['PricePerPax']) if bundle_info['priceInfo']['ChildPrice'] else adt_ticket_price
        chd_tax_price = decimal.Decimal(bundle_info['priceInfo']['ChildPrice']['TaxPerPax']) if bundle_info['priceInfo']['ChildPrice'] else adt_tax_price



        for i in bundle_info['priceInfo']['AdultPrice']['PerPaxTaxBreakDown']:
            if i['BreakDownCode'] == 'YR':
                service_adt_fee = decimal.Decimal(i['Amount'])

        if bundle_info['priceInfo']['ChildPrice']:
            if bundle_info['priceInfo']['ChildPrice']['PerPaxTaxBreakDown']:
                for i in bundle_info['priceInfo']['ChildPrice']['PerPaxTaxBreakDown']:
                    if i['BreakDownCode'] == 'YR':
                        service_chd_fee = decimal.Decimal(i['Amount'])
            else:
                service_chd_fee = service_adt_fee

        if chd_ticket_price <= 0: chd_ticket_price = adt_ticket_price
        if chd_tax_price <= 0: chd_tax_price = adt_tax_price



        if bundle_info['priceInfo']['dispUPAnciPrice']:
            adt_ticket_price += decimal.Decimal(bundle_info['priceInfo']['dispUPAnciPrice'].replace(',', ''))
            chd_ticket_price += decimal.Decimal(bundle_info['priceInfo']['dispUPAnciPrice'].replace(',', ''))

        adt_ticket_price = adt_ticket_price.quantize(decimal.Decimal('0.01'))
        adt_tax_price = adt_tax_price.quantize(decimal.Decimal('0.01'))
        chd_ticket_price = chd_ticket_price.quantize(decimal.Decimal('0.01'))
        chd_tax_price = chd_tax_price.quantize(decimal.Decimal('0.01'))


        baggage_list = [FlightBaggageModel(
            type=SsrTypeEnum.HAND_BAGGAGE,
            number=1,
            weight=7,
            price=decimal.Decimal('0')
        )]

        if product_tag == 'LION ECONOMY':
            t = next((x['FBAncillary']['CommercialName'] for x in bundle_info['priceInfo']['FBSettings'] if x['FBAncillary']['CommercialName'].find('KG') != -1),None)
            if t:
                t = StringUtil.extract_between(t,"UP "," KG")
                if int(t) != 0:
                    baggage_list.append(FlightBaggageModel(
                        type=SsrTypeEnum.HAULING_BAGGAGE,
                        number=1,
                        weight=t,
                        price=decimal.Decimal('0')
                    ))

        if service_adt_fee:
            service_adt_fee = decimal.Decimal(service_adt_fee).quantize(decimal.Decimal('0.01'))

        if service_chd_fee:
            service_chd_fee = decimal.Decimal(service_adt_fee).quantize(decimal.Decimal('0.01'))


        return FlightBundleModel(
            priceInfo=FlightBundlePriceModel(
                adultTicketPrice=adt_ticket_price,
                adultTaxPrice=adt_tax_price,
                childTicketPrice=chd_ticket_price,
                childTaxPrice=chd_tax_price,
                currency=currency_code,
            ),
            ssrInfo=FlightSsrInfoModel(baggage=baggage_list),
            code=bundle_info['FareBasisCode'],
            cabinLevel="Y",
            fareKey=None,
            productTag=product_tag,
            cabin=bundle_info['outBoundFlights'][0]['Segments'][0]['BookingClass'],
            seat= int(bundle_info['outBoundFlights'][0]['Segments'][0]['AvailSeats']) if bundle_info['outBoundFlights'][0]['Segments'][0]['AvailSeats'] else -1,
            freightRateType=FreightRateTypeEnum.PT,
            ext={
                "ClassCode":bundle_info['ClassCode'],
                "ADT":service_adt_fee,
                "CHD":service_chd_fee,
                "text":False if bundle_info['priceInfo']['BaseFareRoundingText'].find('10') == -1 else True
            }
        )

    @classmethod
    def order_parser_passengers(cls,order_dict: dict):
        passengers = []
        for i in order_dict['Passengers']:
            passengers.append(
                PassengerInfoModel(
                    lastName=i['FirstName'],
                    firstName=i['LastName'],
                    type=PassengerTypeEnum.ADT if i['Title'] in ['MR','MS'] else PassengerTypeEnum.CHD,
                    gender=GenderEnum.F if i['Title'] == 'MS' else GenderEnum.M,
                )
            )

        return passengers
