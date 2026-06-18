from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from lxml import etree

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.utils.date_util import DateUtil
from common.utils.string_util import StringUtil
from flights.vietjet.config import Config


class FlightParser:

    @classmethod
    def journey_info_parser(cls,
                            flight_data: dict,
                            baggage_data: Optional[dict] = None,
                            target_dates: Optional[List[str]] = None) -> List[FlightJourneyModel]:
        result_data_list = []
        route_index_by_date = {date: index for index, date in enumerate(target_dates or [], start=1)}

        for fare, index in cls._iter_travel_options(flight_data, route_index_by_date):
            segments = cls.segment_parser(fare['flights'], index=index)
            if len(segments) != 1:
                continue
            bundles = cls.bundle_parser(fare['fareOptions'], baggage_info=baggage_data or {}, segments=segments)
            if not bundles:
                continue
            result_data_list.append(FlightJourneyModel(
                journeyKey="",
                segments=segments,
                bundles=bundles,
                depAirport=segments[0].dep_airport,
                arrAirport=segments[-1].arr_airport,
                depTime=segments[0].dep_time,
                arrTime=segments[-1].arr_time,
                ext=cls.journey_ext(fare),
            ))

        return result_data_list

    @staticmethod
    def journey_ext(fare: dict) -> dict:
        city_pair = fare.get("cityPair") or {}
        route_type = city_pair.get("routeType") or {}
        ext = {}
        if city_pair:
            ext["cityPair"] = city_pair
        if route_type:
            ext["routeType"] = route_type
            ext["routeTypeIdentifier"] = route_type.get("identifier")
        return ext

    @classmethod
    def _iter_travel_options(cls, flight_data: dict, route_index_by_date: dict):
        if "travelOption" in flight_data:
            for index, (_, itineraries) in enumerate(flight_data["travelOption"].items(), start=1):
                for fare in itineraries:
                    yield fare, index
            return

        for fare in flight_data.get("travelOptionData") or []:
            departure_date = fare.get("departureDate")
            if route_index_by_date and departure_date not in route_index_by_date:
                continue
            yield fare, route_index_by_date.get(departure_date, 1)

    @classmethod
    def segment_parser(cls, segs_data: List[dict], index: int) -> List[FlightSegmentModel]:
        segment_list = []
        for segment in segs_data:
            segment_key = segment['key']
            carrier = segment['airlineCode']['code']
            flight_number = carrier + str(segment['flightNumber'])
            dep_airport = segment['departure']['airport']['code']
            arr_airport = segment['arrival']['airport']['code']

            dep_time = DateUtil.string_to_date_auto(segment['departure']['localScheduledTime'])
            arr_time = DateUtil.string_to_date_auto(segment['arrival']['localScheduledTime'])
            if dep_time is None:
                dep_time = datetime.strptime(segment['departure']['localScheduledTime'], '%Y-%m-%d %H:%M:%S')
            if arr_time is None:
                arr_time = datetime.strptime(segment['arrival']['localScheduledTime'], '%Y-%m-%d %H:%M:%S')

            segment_list.append(FlightSegmentModel(
                segmentKey=segment_key,
                depAirport=dep_airport,
                arrAirport=arr_airport,
                depTime=dep_time,
                arrTime=arr_time,
                carrier=carrier,
                flightNumber=flight_number,
                operatingCarrier=carrier,
                operatingFlightNumber=flight_number,
                routeIndex=index,
                legIndex=index,
                ext={
                    'flight_time': DateUtil.get_time_difference_points(dep_time, arr_time)
                }
            ))

        return segment_list

    @classmethod
    def __extract_brand_data(cls, baggages: dict, product_tag: str, segments: List[FlightSegmentModel],) -> \
            List[FlightBaggageModel]:
        baggage_list = []
        for i in baggages['ticket']:
            if product_tag == 'SkyBoss' and i['ticketName'] == 'Skyboss':
                if not baggages['special_baggage_data']['journeyConfigs'] or baggages['special_baggage_data']['journeyConfigs']== [None]:
                    baggage_text = None
                else:
                    baggage_text = baggages['special_baggage_data']['journeyConfigs'][0]['metadata'][
                        'fareDescription'].get(
                        'Skyboss')
                pass
            else:
                if not baggages['special_baggage_data']['journeyConfigs'] or baggages['special_baggage_data']['journeyConfigs']== [None]:
                    baggage_text = None
                else:
                    baggage_text = baggages['special_baggage_data']['journeyConfigs'][0]['metadata'][
                        'fareDescription'].get(product_tag)
                if i['ticketName'] != product_tag:
                    continue

            html_text = i['description']
            flight_number = '$'.join([i.flight_number for i in segments])
            flight_info = {'dep': segments[0].dep_airport, 'arr': segments[-1].arr_airport,
                           'flight_number': flight_number}
            cities = Config.CITIES
            if product_tag == 'Eco':
                baggage_list.append(FlightBaggageModel(
                    type=SsrTypeEnum.HAND_BAGGAGE,
                    price=Decimal(0),
                    weight=7,
                    number=1
                ))
            else:
                baggage_result_list = cls.parse_baggage_info(html_text, flight_info, cities, baggage_text)
                for baggage_result in baggage_result_list:
                    if baggage_result['baggage_type'] == '手提':
                        baggage_type = SsrTypeEnum.HAND_BAGGAGE
                    else:
                        baggage_type = SsrTypeEnum.HAULING_BAGGAGE
                    baggage_list.append(FlightBaggageModel(
                        type=baggage_type,
                        price=Decimal(0),
                        weight=baggage_result['total_weight'],
                        number=1
                    ))
        return baggage_list

    @classmethod
    def parse_baggage_info(cls, html, flight_info, cities, baggage_text):
        baggage_list = []

        # 解析HTML
        tree = etree.HTML(html)
        items = tree.xpath('//div[@class="class_content"]//p')
        international = True if flight_info['dep'] in cities or flight_info['arr'] in cities else False
        for item in items:
            text = ''.join(item.xpath('.//span//text()')).strip()

            if '手提行李' in text:
                if '适用' in text:
                    total_wight_text = StringUtil.extract_between(text, '适用', '公斤手提行李').replace(' ', '').split(
                        '公斤或')
                    if international:
                        weight = total_wight_text[1]
                    else:
                        weight = total_wight_text[0]
                else:
                    weight = text.split('公斤')[0].strip()

                baggage_list.append({
                    'baggage_type': '手提',
                    'total_weight': weight,
                })

            elif '托运行李' in text and '公斤' in text:
                total_wight_text = StringUtil.extract_between(text, '免费', '公斤的托运行李').replace(' ', '').split(
                    '公斤或')
                if international:
                    if flight_info['dep'] in ['PER', 'ADL'] or flight_info['arr'] in ['PER', 'ADL']:
                        weight = 0
                        for p in etree.HTML(baggage_text).xpath('//div[@class="class_content"]//p'):
                            p_text = ''.join(p.xpath('.//span//text()')).strip()
                            if '托運行李' in p_text:
                                weight = p_text.split('公斤')[0]
                        # weight = total_wight_text[0]
                    else:
                        weight = total_wight_text[1]
                else:
                    weight = total_wight_text[0]

                baggage_list.append({
                    'baggage_type': '托运',
                    'total_weight': weight,
                })

        return baggage_list

    @classmethod
    def bundle_parser(cls,
                      data: List[dict],
                      baggage_info: Optional[dict] = None,
                      segments: Optional[List[FlightSegmentModel]] = None) -> List[FlightBundleModel]:
        bundle_list = []
        for bundle in data:
            if not bundle.get('bookingKey'):
                continue
            seats = bundle.get('availability', 0)
            if seats <= 0:
                continue

            adt_fare = 0
            adt_tax = 0
            chd_fare = 0
            chd_tax = 0
            for i in bundle['fareCharges']:
                money = i['currencyAmounts'][0]['totalAmount']
                if i['chargeType']['code'] == 'FA':
                    if i['passengerApplicability']['adult']:
                        adt_fare = money
                    if i['passengerApplicability']['child']:
                        chd_fare = money
                charge_description = i.get('description') or (i.get('chargeType') or {}).get('description')
                if i['chargeType']['code'] != 'FA' and charge_description != 'Seat Assignment':
                    if i['passengerApplicability']['adult']:
                        adt_tax += money
                    if i['passengerApplicability']['child']:
                        chd_tax += money
            currency = bundle['fareCharges'][0]['currencyAmounts'][0]['currency']['code']

            price_info = FlightBundlePriceModel(
                adultTicketPrice=adt_fare,
                adultTaxPrice=adt_tax,
                childTicketPrice=chd_fare,
                childTaxPrice=chd_tax,
                currency=currency,

            )
            booking_code = bundle.get("fareClass") or bundle.get("bookingCode") or {}
            code = booking_code.get("code", "")
            ssr_info = FlightSsrInfoModel()
            temp_ssr_list = []
            fare_type = bundle.get("fareType") or {}
            product_tag = fare_type.get("identifier") or fare_type.get("description") or code
            ssr_info.baggage = temp_ssr_list
            bundle_list.append(FlightBundleModel(
                priceInfo=price_info,
                ssrInfo=ssr_info,
                code=product_tag,
                cabinLevel="Y",
                cabin=code[:1],
                fareKey=bundle['bookingKey'],
                productTag=product_tag,
                seat=seats,
                freightRateType=FreightRateTypeEnum.PT,
            ))
        return bundle_list


AppFlightParser = FlightParser
