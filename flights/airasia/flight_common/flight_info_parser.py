import decimal

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.utils.date_util import DateUtil


class FlightInfoParser:


    @classmethod
    def journey_info_parser(cls, flight_data: dict):

        result_array = []
        flight_array = flight_data['recommendedFlights'][0]['flightsList'] +flight_data['trips'][0]['flightsList']
        for i in flight_array:
            segments = [cls.segment_parser(x) for x in i['flightDetails']['segments']]

            if len(segments) == 0:
                continue

            for index, value in enumerate(segments):
                value.route_index = 1

            adt_total_price = decimal.Decimal(str(i['fare']['adults']))
            chd_total_price = adt_total_price if i['fare']['children'] <= 0 else decimal.Decimal(str(i['fare']['children']))

            adt_tax_price = adt_total_price - decimal.Decimal(str(i['baseFare']['adults']))
            chd_tax_price = adt_tax_price if i['baseFare']['children'] <= 0 else chd_total_price - decimal.Decimal(str(i['baseFare']['children']))

            adt_ticket_price = adt_total_price - adt_tax_price
            chd_ticket_price = chd_total_price - chd_tax_price



            bundles = [
                FlightBundleModel(
                    priceInfo=FlightBundlePriceModel(
                        adultTicketPrice=adt_ticket_price,
                        adultTaxPrice=adt_tax_price,
                        childTicketPrice=chd_ticket_price,
                        childTaxPrice=chd_tax_price,
                        currency=i['currencyCode']
                    ),
                    ssrInfo=FlightSsrInfoModel(
                        baggage=[
                            FlightBaggageModel(
                                type=SsrTypeEnum.HAND_BAGGAGE,
                                price=decimal.Decimal('0'),
                                number=1,
                                weight=7
                            )
                        ]
                    ),
                    code='',
                    cabinLevel='Y',
                    productTag='Economy',
                    fareKey='',
                    seat=i['seatAvailability']['seats'],
                    freightRateType=FreightRateTypeEnum.PT,
                    cabin=i['flightDetails']['segments'][0]['fareType']
                )
            ]

            result_array.append(
                FlightJourneyModel(
                    segments=segments,
                    bundles=bundles,
                    journeyKey='',
                    depAirport=i['flightDetails']['designator']['departureStation'],
                    arrAirport=i['flightDetails']['designator']['arrivalStation'],
                    depTime=segments[0].dep_time,
                    arrTime=segments[0].arr_time,
                )
            )

        return result_array


    @classmethod
    def segment_parser(cls,segment_data: dict) -> FlightSegmentModel:

        dep_airport = segment_data['designator']["departureStation"]
        arr_airport = segment_data['designator']["arrivalStation"]
        carrier_code = segment_data["carrierCode"]
        flight_number = segment_data["marketingFlightNo"]

        dep_time = DateUtil.string_to_date_auto(segment_data['designator']['departureTime'])
        arr_time = DateUtil.string_to_date_auto(segment_data['designator']['arrivalTime'])

        return FlightSegmentModel(
            segmentKey='',
            depAirport=dep_airport,
            arrAirport=arr_airport,
            depTime=dep_time,
            arrTime=arr_time,
            flightNumber=f'{carrier_code}{flight_number}',
            carrier=carrier_code,
            operatingCarrier=carrier_code,
            operatingFlightNumber=f'{carrier_code}{flight_number}'
        )