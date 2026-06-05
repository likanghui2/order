import base64
import decimal
from datetime import datetime
from decimal import Decimal
from typing import List, Any, Optional

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceStateEnum, ServiceError
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel


class FlightInfoParser:

    @classmethod
    def journey_info_parser(cls,trip_data_list: List[Any],currency_code: str,):


        if len(trip_data_list) > 1:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, 'Not supported travel type')

        if not trip_data_list[0]:
            return []

        if not trip_data_list[0].get('flights'):
            return []

        result_data_list = []

        for trip_data in trip_data_list[0]['flights']:
            journey_key = trip_data['journeyKey']

            seat_map_key = trip_data['details']['segments'][0]['seatMapKey']
            seat_map_key = seat_map_key.replace('_','+').replace('-','=')
            seat_map_key = base64.b64decode(seat_map_key).decode('utf-8')


            segments = [cls.segment_parser(x) for x in seat_map_key.split('^')]

            for index, value in enumerate(segments):
                value.leg_index = index + 1
                value.route_index = 1

            basis_amount = decimal.Decimal(trip_data['standard']['cash']['fareAmount'])
            fare_key = trip_data['standard']['cash']['fareAvailabilityKey']

            bundle_array = trip_data_list[0]['bundleFeaturesMapData']['bundles']
            bundles = [cls.bundle_parser(basis_amount,currency_code,x,bundle_array,fare_key,
                                         sum([1 for j in segments if j.stopoverAirport is None])) for x in trip_data['standard']['bundleReferences']]

            if None in bundles:
                continue

            result_data_list.append(FlightJourneyModel(
                segments=segments,
                bundles=bundles,
                journeyKey=journey_key,
                depAirport=segments[0].dep_airport,
                arrAirport=segments[-1].arr_airport,
                depTime=segments[0].dep_time,
                arrTime=segments[-1].arr_time,
            ))

        return result_data_list

    @classmethod
    def segment_parser(cls, segment):

        data = segment.split('~')


        segment_key = segment
        flight_number = f'{data[0]}{data[1].replace(" ","")}'
        dep_airport = data[4]
        arr_airport = data[6]

        dep_time = datetime.strptime(data[5],'%m/%d/%Y %H:%M').strftime('%Y%m%d%H%M')
        arr_time = datetime.strptime(data[7],'%m/%d/%Y %H:%M').strftime('%Y%m%d%H%M')
        carrier = flight_number[0:2]

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
        )

        return ret

    @classmethod
    def bundle_parser(cls,
                      passenger_base_price: decimal.Decimal,
                      currency_code,
                      bundle_info,
                      bundle_map_data_array,
                      fare_key,
                      segment_number: int) -> Optional[FlightBundleModel]:


        fare_data = base64.b64decode(fare_key.replace('_','+').replace('-','=')).decode('utf-8')
        fare_data_array = fare_data.split('^')
        cabin = ','.join([x.split('~')[1] for x in fare_data_array])

        if len(cabin.split('^')) != segment_number:
            return None

        bundle_code = bundle_info['bundleCode']

        bundle_map_data = next((x for x in bundle_map_data_array if x['id'] == bundle_code), None)

        product_tag = bundle_map_data['title']

        total_amount = decimal.Decimal(bundle_info['bundlePrices']['standardActualPricePerPax']) + passenger_base_price
        ticket_price = total_amount * decimal.Decimal('0.7')
        tax_price = total_amount - ticket_price

        price_info = FlightBundlePriceModel(
            adultTicketPrice=ticket_price,
            adultTaxPrice=tax_price,
            childTicketPrice=ticket_price,
            childTaxPrice=tax_price,
            currency=currency_code,
        )

        ssr_info = FlightSsrInfoModel()
        temp_ssr_list = []

        if 'CarryOn' in bundle_map_data['featureIds']:
            temp_ssr_list.append(FlightBaggageModel(
                type=SsrTypeEnum.HAND_BAGGAGE,
                code='',
                price=Decimal(0),
                weight=0,
                number=1,
            ))

        if 'CheckedBag' in bundle_map_data['featureIds']:
            temp_ssr_list.append(FlightBaggageModel(
                type=SsrTypeEnum.HAULING_BAGGAGE,
                code='',
                price=Decimal(0),
                weight=23,
                number=1,
            ))

        ssr_info.baggage = temp_ssr_list

        return FlightBundleModel(
            priceInfo=price_info,
            ssrInfo=ssr_info,
            code=bundle_code,
            cabinLevel='Y',
            cabin=cabin,
            fareKey=fare_key,
            productTag=product_tag,
            seat=-1,
            freightRateType=FreightRateTypeEnum.PT
        )