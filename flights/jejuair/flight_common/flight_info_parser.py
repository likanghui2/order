import copy
import json
import re
from datetime import datetime
from decimal import Decimal
from html import unescape
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from ..config import Config


class FlightInfoParser:
    @classmethod
    def journey_info_parser(cls, flight_data: str,
                            route_ancillary_groups: Optional[List[List[Dict[str, Any]]]] = None) -> List[FlightJourneyModel]:
        if not flight_data:
            return []

        soup = BeautifulSoup(flight_data, 'html.parser')
        currency_code = cls.extract_currency_code(flight_data)

        result_data_list: List[FlightJourneyModel] = []
        journey_data_list = []
        for route_group_index, ticket_pare in enumerate(soup.select('div.ticket-pare')):
            list_items = ticket_pare.select('ul.fare-list li.list-item')
            if not list_items:
                continue

            for list_item in list_items:
                moving_time = list_item.select_one('.moving-time[data-segments]')
                if not moving_time:
                    continue

                journey_data = {
                    'segments': moving_time.get('data-segments'),
                    'price_nodes': [],
                    'fareTabs': [],
                    'routeGroupIndex': route_group_index,
                }
                for tab_btn in list_item.select('.tab-btn'):
                    price_node = tab_btn.select_one('.price[data-fares]')
                    if not price_node:
                        continue

                    fare_tab = {
                        'classes': set(tab_btn.get('class', [])),
                        'priceNode': dict(price_node.attrs),
                        'grade': cls.__clean_text(
                            (tab_btn.select_one('.grade') or {}).get_text()
                            if tab_btn.select_one('.grade') else ''
                        ),
                        'remainingSeatText': cls.__clean_text(
                            (tab_btn.select_one('.remaining-seat') or {}).get_text()
                            if tab_btn.select_one('.remaining-seat') else ''
                        ),
                        'bundleDetails': [],
                    }
                    for grade_info in tab_btn.select('.bundleListInfo .grade-info-detail'):
                        bundle_code_node = grade_info.select_one('.bundleCD')
                        bundle_price_node = grade_info.select_one('.bundlePrice')
                        bundle_desc_node = grade_info.select_one('.bundleDescription')
                        fare_tab['bundleDetails'].append({
                            'bundleCode': cls.__clean_text(
                                bundle_code_node.get('value') if bundle_code_node and bundle_code_node.get('value')
                                else bundle_code_node.get_text() if bundle_code_node else ''
                            ),
                            'bundlePrice': cls.__clean_text(
                                bundle_price_node.get('value') if bundle_price_node and bundle_price_node.get('value')
                                else bundle_price_node.get_text() if bundle_price_node else ''
                            ),
                            'bundleDescription': cls.__clean_text(
                                bundle_desc_node.get('value') if bundle_desc_node and bundle_desc_node.get('value')
                                else bundle_desc_node.get_text() if bundle_desc_node else ''
                            ),
                        })
                    journey_data['price_nodes'].append(dict(price_node.attrs))
                    journey_data['fareTabs'].append(fare_tab)
                if journey_data['price_nodes']:
                    journey_data_list.append(journey_data)

        for index, journey_data in enumerate(journey_data_list, start=1):
            segments_data = cls.parse_json_attr(journey_data.get('segments'))
            if isinstance(segments_data, dict):
                segments_data = [segments_data]
            if not segments_data:
                continue

            segments = cls.segment_parser(segments_data, index=index)
            if not segments or len(segments) != 1:
                continue

            route_group_index = journey_data.get('routeGroupIndex', 0)
            bundles = cls.bundle_parser(
                price_nodes=journey_data.get('price_nodes', []),
                default_currency=currency_code,
                ancillary_data=(
                    route_ancillary_groups[route_group_index]
                    if route_ancillary_groups and route_group_index < len(route_ancillary_groups)
                    else None
                ),
                fare_tabs=journey_data.get('fareTabs', []),
            )
            if not bundles:
                continue

            journey_key = ''
            candidate_nodes = []
            for fare_tab in journey_data.get('fareTabs', []):
                price_node = fare_tab.get('priceNode')
                if price_node:
                    candidate_nodes.append(price_node)
            candidate_nodes.extend(journey_data.get('price_nodes', []))
            for price_node in candidate_nodes:
                journey_key = price_node.get('data-journeykey') or ''
                if journey_key:
                    break
                fares_data = cls.parse_json_attr(price_node.get('data-fares'))
                if isinstance(fares_data, dict):
                    fares_data = [fares_data]
                for fare_data in fares_data or []:
                    journey_key = fare_data.get('journeyKey') or ''
                    if journey_key:
                        break
                if journey_key:
                    break
            first_identifier = (segments_data[0].get('identifier') or {}) if segments_data else {}
            selected_flights_no = {
                'carrierCode': first_identifier.get('carrierCode') or segments[0].carrier,
                'identifier': (
                    first_identifier.get('identifier')
                    or (
                        segments[0].flight_number[len(segments[0].carrier):]
                        if segments[0].carrier and segments[0].flight_number.startswith(segments[0].carrier)
                        else segments[0].flight_number
                    )
                )
            }
            for bundle in bundles:
                bundle.ext = {
                    **(bundle.ext or {}),
                    'journeyKey': (bundle.ext or {}).get('journeyKey') or journey_key,
                    'fareAvailabilityKey': (bundle.ext or {}).get('fareAvailabilityKey') or bundle.fare_key or '',
                    'selectedFlightsNo': copy.deepcopy(selected_flights_no),
                }
            result_data_list.append(FlightJourneyModel(
                journeyKey=journey_key,
                segments=segments,
                bundles=bundles,
                depAirport=segments[0].dep_airport,
                arrAirport=segments[-1].arr_airport,
                depTime=segments[0].dep_time,
                arrTime=segments[-1].arr_time,
                # ext={
                #     'priceOptionCount': len(journey_data.get('price_nodes', [])),
                #     'routeGroupIndex': route_group_index,
                # }
            ))
        return result_data_list

    @staticmethod
    def parse_json_attr(raw_value: Optional[str]) -> Any:
        if not raw_value:
            return None

        raw_value = unescape(raw_value).strip()
        if raw_value.startswith("'") and raw_value.endswith("'"):
            raw_value = raw_value[1:-1]
        return json.loads(raw_value)

    @staticmethod
    def extract_currency_code(flight_data: str) -> Optional[str]:
        patterns = [
            r'id=["\']currencyCode["\'][^>]*value=["\']([^"\']+)["\']',
            r'name=["\']currencyCode["\'][^>]*value=["\']([^"\']+)["\']',
            r'currencyCode["\']?\s*:\s*["\']([A-Z]{3})["\']',
            r'currencyCode\s*=\s*["\']([A-Z]{3})["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, flight_data)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def parse_datetime(date_time: str) -> datetime:
        if not date_time:
            raise ValueError('segment datetime is empty')

        date_time = date_time.strip().replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(date_time)
        except ValueError:
            pass

        if '.' in date_time:
            trimmed_value = date_time.split('.', 1)[0]
            try:
                return datetime.fromisoformat(trimmed_value)
            except ValueError:
                pass

        for date_format in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y%m%d%H%M'):
            try:
                return datetime.strptime(date_time, date_format)
            except ValueError:
                continue

        raise ValueError(f'invalid datetime: {date_time}')

    @classmethod
    def segment_parser(cls, segs_data: List[dict], index: int) -> List[FlightSegmentModel]:
        segment_list = []
        for leg_index, segment in enumerate(segs_data, start=1):
            identifier = segment.get('identifier') or {}
            designator = segment.get('designator') or {}

            flight_number = identifier.get('identifier') or segment.get('flightNumber') or ''
            carrier = identifier.get('carrierCode') or segment.get('carrierCode') or flight_number[:2]
            operating_carrier = identifier.get('operatingCarrierCode') or carrier

            if carrier and flight_number and not flight_number.startswith(carrier):
                flight_number = f'{carrier}{flight_number}'

            dep_airport = designator.get('origin') or segment.get('departureStation')
            arr_airport = designator.get('destination') or segment.get('arrivalStation')
            dep_time = cls.parse_datetime(designator.get('departure'))
            arr_time = cls.parse_datetime(designator.get('arrival'))
            segment_key = (
                    segment.get('segmentKey')
                    or identifier.get('identifier')
                    or f'{dep_airport}{arr_airport}{dep_time.strftime("%Y%m%d%H%M")}'
            )

            segment_list.append(FlightSegmentModel(
                segmentKey=segment_key,
                depAirport=dep_airport,
                arrAirport=arr_airport,
                depTime=dep_time,
                arrTime=arr_time,
                carrier=carrier,
                flightNumber=flight_number,
                operatingCarrier=operating_carrier,
                operatingFlightNumber=flight_number,
                routeIndex=1,
                legIndex=leg_index,
                # ext={'rawSegment': segment},
            ))

        return segment_list

    @classmethod
    def calculate_price_info(cls, fares_data: List[dict], default_currency: Optional[str]) -> FlightBundlePriceModel:
        price_map = {
            'ADT': {'ticket': Decimal('0'), 'tax': Decimal('0')},
            'CHD': {'ticket': Decimal('0'), 'tax': Decimal('0')},
        }
        currency_code = default_currency
        has_child_price = False

        for fare_data in fares_data:
            currency_code = currency_code or fare_data.get('currencyCode') or fare_data.get('currency')
            for passenger_fare in fare_data.get('passengerFares') or []:
                passenger_type = passenger_fare.get('passengerType')
                if passenger_type not in price_map:
                    continue

                if passenger_type == 'CHD':
                    has_child_price = True

                service_charges = passenger_fare.get('serviceCharges') or []
                for service_charge in service_charges:
                    amount = Decimal(str(service_charge.get('amount') or 0))
                    charge_type = service_charge.get('type') or service_charge.get('chargeType')
                    charge_code = service_charge.get('code') or service_charge.get('chargeCode') or ''
                    currency_code = (
                            currency_code
                            or service_charge.get('currencyCode')
                            or service_charge.get('currency')
                    )

                    if charge_type == 'FarePrice':
                        price_map[passenger_type]['ticket'] += amount
                    elif charge_type == 'FareSurcharge':
                        if charge_code == 'HZ':
                            price_map[passenger_type]['tax'] += amount
                        else:
                            price_map[passenger_type]['ticket'] += amount
                    elif charge_type == 'TravelFee':
                        price_map[passenger_type]['tax'] += amount
                    elif charge_type in {'Discount', 'PromotionDiscount'}:
                        price_map[passenger_type]['ticket'] -= amount
                    else:
                        price_map[passenger_type]['tax'] += amount

        if not currency_code:
            currency_code = ''

        child_ticket_price = (
            price_map['CHD']['ticket']
            if has_child_price
            else price_map['ADT']['ticket']
        )
        child_tax_price = (
            price_map['CHD']['tax']
            if has_child_price
            else price_map['ADT']['tax']
        )

        return FlightBundlePriceModel(
            adultTicketPrice=price_map['ADT']['ticket'],
            adultTaxPrice=price_map['ADT']['tax'],
            childTicketPrice=child_ticket_price,
            childTaxPrice=child_tax_price,
            currency=currency_code,
        )

    @classmethod
    def infer_bundle_seat(cls, fares_data: List[dict], remaining_seat_text: Optional[str] = None) -> int:
        candidates = []
        possible_keys = (
            'availableCount',
            'availableSeats',
            'seatCount',
            'remaining',
            'remainingSeatCount',
        )

        for fare_data in fares_data:
            for source in (fare_data, fare_data.get('availability') or {}):
                if not isinstance(source, dict):
                    continue
                for key in possible_keys:
                    value = source.get(key)
                    if value in (None, '') or isinstance(value, bool):
                        continue
                    try:
                        candidates.append(int(str(value)))
                    except (TypeError, ValueError):
                        continue

        if remaining_seat_text:
            seat_match = re.search(r'(\d+)', remaining_seat_text)
            if seat_match:
                candidates.append(int(seat_match.group(1)))

        if not candidates:
            return -1
        return min(candidates)

    @classmethod
    def __normalize_fare_name(cls, text: Optional[str]) -> str:
        return re.sub(r'\s+', '', (text or '').upper())

    @classmethod
    def __clean_text(cls, text: Optional[str]) -> str:
        return re.sub(r'\s+', ' ', (text or '')).strip()

    @classmethod
    def __append_baggage(cls, baggage_list: List[FlightBaggageModel],
                         baggage_type: SsrTypeEnum, weight: int):
        if weight <= 0:
            return
        for baggage in baggage_list:
            if baggage.type == baggage_type:
                baggage.weight = max(baggage.weight, weight)
                return
        baggage_list.append(FlightBaggageModel(
            type=baggage_type,
            price=Decimal(0),
            weight=weight,
            number=1,
        ))

    @classmethod
    def __get_bundle_meta_dict(cls, ancillary_data: Optional[List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        bundle_meta_dict = {}
        if not ancillary_data:
            return bundle_meta_dict

        for ancillary in ancillary_data:
            fare_name = cls.__normalize_fare_name(ancillary.get('FARE_NM'))
            if not fare_name:
                continue

            if fare_name not in bundle_meta_dict:
                bundle_meta_dict[fare_name] = {
                    'name': None,
                    'recommended': None,
                    'discount': None,
                    'labels': [],
                    'benefits': [],
                    'baggage_data': [],
                }

            bundle_meta = bundle_meta_dict[fare_name]
            option_type = ancillary.get('OPTION_TYPE')
            option_name = cls.__clean_text(
                ancillary.get('OPTION_NM')
                or ancillary.get('ANC_NM')
                or ancillary.get('LABEL_NM')
            )
            if not option_name:
                continue

            if option_type == 'H' and not bundle_meta['name']:
                bundle_meta['name'] = option_name
            elif option_type == 'R' and not bundle_meta['recommended']:
                bundle_meta['recommended'] = option_name
            elif option_type == 'S' and not bundle_meta['discount']:
                bundle_meta['discount'] = option_name
            elif option_type == 'I':
                bundle_meta['labels'].append(option_name)
            elif option_type == 'B':
                bundle_meta['benefits'].append(option_name)
                weight_match = re.search(r'(\d+)\s*KG', option_name, re.IGNORECASE)
                if not weight_match:
                    continue
                weight = int(weight_match.group(1))
                lower_option_name = option_name.lower()
                if any(keyword in lower_option_name for keyword in Config.HAND_BAGGAGE_KEYWORDS):
                    baggage_type = SsrTypeEnum.HAND_BAGGAGE
                elif any(keyword in lower_option_name for keyword in Config.CHECKED_BAGGAGE_KEYWORDS):
                    baggage_type = SsrTypeEnum.HAULING_BAGGAGE
                else:
                    continue

                baggage_data = next(
                    (
                        item for item in bundle_meta['baggage_data']
                        if item['type'] == baggage_type
                    ),
                    None,
                )
                if baggage_data:
                    baggage_data['weight'] = max(baggage_data['weight'], weight)
                else:
                    bundle_meta['baggage_data'].append({
                        'type': baggage_type,
                        'weight': weight,
                    })

        return bundle_meta_dict

    @classmethod
    def build_baggage_info(cls, product_class: str,
                           bundle_meta_dict: Dict[str, Dict[str, Any]],
                           fare_name: Optional[str] = None,
                           description_text: Optional[str] = None) -> List[FlightBaggageModel]:
        baggage_list: List[FlightBaggageModel] = []
        temp_baggage_data = []
        if fare_name:
            temp_baggage_data = (
                    bundle_meta_dict.get(cls.__normalize_fare_name(fare_name), {}).get('baggage_data') or []
            )
        if not temp_baggage_data:
            temp_baggage_data = (
                    bundle_meta_dict.get(
                        cls.__normalize_fare_name(Config.PRODUCT_CLASS_MAPPING.get(product_class, product_class)),
                        {}
                    ).get('baggage_data') or []
            )

        for baggage_data in temp_baggage_data:
            baggage_list.append(FlightBaggageModel(
                type=baggage_data['type'],
                price=Decimal(0),
                weight=baggage_data['weight'],
                number=1,
            ))

        if description_text:
            cleaned_text = cls.__clean_text(description_text)
            base_checked_weight = Config.BASE_CHECKED_BAGGAGE_MAPPING.get(product_class, 0)
            for weight_match in re.finditer(r'([+＋]?)(\d+)\s*KG', cleaned_text, re.IGNORECASE):
                start_index = max(0, weight_match.start() - 16)
                end_index = min(len(cleaned_text), weight_match.end() + 16)
                context_text = cleaned_text[start_index:end_index].lower()

                baggage_type = None
                base_weight = 0
                if any(keyword.lower() in context_text for keyword in Config.CHECKED_BAGGAGE_KEYWORDS):
                    baggage_type = SsrTypeEnum.HAULING_BAGGAGE
                    base_weight = base_checked_weight
                elif any(keyword.lower() in context_text for keyword in Config.HAND_BAGGAGE_KEYWORDS):
                    baggage_type = SsrTypeEnum.HAND_BAGGAGE
                    base_weight = Config.BASE_HAND_BAGGAGE_WEIGHT

                if baggage_type is None:
                    continue

                weight = int(weight_match.group(2))
                if weight_match.group(1) in ('+', '＋'):
                    weight += base_weight
                cls.__append_baggage(baggage_list, baggage_type, weight)

        return baggage_list

    @classmethod
    def bundle_parser(cls, price_nodes: List[Dict[str, str]], default_currency: Optional[str],
                      ancillary_data: Optional[List[Dict[str, Any]]] = None,
                      fare_tabs: Optional[List[Dict[str, Any]]] = None) -> List[FlightBundleModel]:
        result_bundles: List[FlightBundleModel] = []
        seen_bundle_keys = set()
        bundle_meta_dict = cls.__get_bundle_meta_dict(ancillary_data)

        price_options = []
        if fare_tabs:
            tabs_with_details = [fare_tab for fare_tab in fare_tabs if
                                 fare_tab.get('priceNode') and fare_tab.get('bundleDetails')]
            active_tabs = [
                fare_tab for fare_tab in fare_tabs
                if fare_tab.get('priceNode') and 'active' in (fare_tab.get('classes') or set())
            ]
            selected_tabs = tabs_with_details or active_tabs or fare_tabs
            for fare_tab in selected_tabs:
                if not fare_tab.get('priceNode'):
                    continue
                if fare_tab.get('priceNode'):
                    price_options.append({
                        'priceNode': fare_tab.get('priceNode'),
                        'grade': cls.__clean_text(fare_tab.get('grade')),
                        'remainingSeatText': cls.__clean_text(fare_tab.get('remainingSeatText')),
                        'bundleDetails': fare_tab.get('bundleDetails') or [],
                    })
        if not price_options:
            price_options = [
                {'priceNode': price_node, 'grade': '', 'remainingSeatText': '', 'bundleDetails': []}
                for price_node in price_nodes
            ]

        for price_option in price_options:
            price_node = price_option.get('priceNode') or {}
            fares_data = cls.parse_json_attr(price_node.get('data-fares'))
            if isinstance(fares_data, dict):
                fares_data = [fares_data]
            if not fares_data:
                continue

            first_fare = fares_data[0]
            fare_key = price_node.get('data-fareavailabilitykey') or first_fare.get('fareAvailabilityKey') or ''
            product_class = first_fare.get('productClass') or ''
            bundle_code = first_fare.get('fareBasisCode') or product_class or fare_key

            bundle_identity = (fare_key, bundle_code, product_class)
            if bundle_identity in seen_bundle_keys:
                continue
            seen_bundle_keys.add(bundle_identity)

            price_info = cls.calculate_price_info(fares_data, default_currency=default_currency)
            seat = cls.infer_bundle_seat(
                fares_data,
                remaining_seat_text=price_option.get('remainingSeatText'),
            )
            if seat == 0:
                continue

            cabin = '|'.join(filter(None, [fare.get('classOfService') or '' for fare in fares_data])) or None
            cabin_level = 'C' if product_class == 'N' else 'Y'
            product_tag = Config.PRODUCT_CLASS_MAPPING.get(product_class, product_class or bundle_code)
            ssr_info = FlightSsrInfoModel()
            ssr_info.baggage = cls.build_baggage_info(
                product_class=product_class,
                bundle_meta_dict=bundle_meta_dict,
                fare_name=product_tag,
            )

            bundle_details = []
            seen_bundle_codes = set()
            temp_bundle_details = []
            for fare_data in fares_data:
                bundle_infos = fare_data.get('bundleInfos') or []
                if isinstance(bundle_infos, dict):
                    bundle_infos = [bundle_infos]
                for bundle_info in bundle_infos:
                    temp_bundle_details.append({
                        'bundleCode': cls.__clean_text(
                            bundle_info.get('bundleCode')
                            or bundle_info.get('bundleCd')
                            or bundle_info.get('code')
                        ),
                        'bundleName': cls.__clean_text(
                            bundle_info.get('bundleName')
                            or bundle_info.get('name')
                        ),
                        'bundlePrice': str(
                            bundle_info.get('bundlePrice')
                            or bundle_info.get('bundleAmount')
                            or bundle_info.get('amount')
                            or bundle_info.get('price')
                            or bundle_info.get('standardActualPricePerPax')
                            or ''
                        ),
                        'bundleDescription': bundle_info.get('bundleDescription') or bundle_info.get(
                            'description') or '',
                    })
            temp_bundle_details.extend(price_option.get('bundleDetails') or [])
            for bundle_detail in temp_bundle_details:
                addon_bundle_code = cls.__clean_text(bundle_detail.get('bundleCode'))
                if not addon_bundle_code or addon_bundle_code in seen_bundle_codes:
                    continue
                seen_bundle_codes.add(addon_bundle_code)
                bundle_details.append({
                    'bundleCode': addon_bundle_code,
                    'bundleName': cls.__clean_text(bundle_detail.get('bundleName')),
                    'bundlePrice': cls.__clean_text(bundle_detail.get('bundlePrice')),
                    'bundleDescription': (bundle_detail.get('bundleDescription') or '').strip(),
                })

            booking_pax_fares = copy.deepcopy(fares_data)
            for temp_fare_data in booking_pax_fares:
                temp_fare_data.setdefault('bundleInfos', {})

            selected_bundle_data = []
            for benefit_name in bundle_meta_dict.get(
                    cls.__normalize_fare_name(product_tag), {}
            ).get('benefits') or []:
                selected_bundle_data.append({'desc': benefit_name})
            for bundle_detail in bundle_details:
                addon_bundle_code = bundle_detail.get('bundleCode')
                if not addon_bundle_code:
                    continue
                addon_bundle_meta = bundle_meta_dict.get(cls.__normalize_fare_name(addon_bundle_code), {})
                if not addon_bundle_meta.get('name'):
                    continue
                for benefit_name in addon_bundle_meta.get('benefits') or []:
                    selected_bundle_data.append({'desc': benefit_name})

            booking_context = {
                'journeyKey': price_node.get('data-journeykey') or '',
                'fareAvailabilityKey': fare_key,
                'selectedPaxFares': booking_pax_fares,
                'selectedBundleData': selected_bundle_data,
            }

            result_bundles.append(FlightBundleModel(
                priceInfo=price_info,
                ssrInfo=ssr_info,
                code=bundle_code,
                cabinLevel=cabin_level,
                cabin=cabin,
                fareKey=fare_key,
                productTag=product_tag,
                seat=seat,
                freightRateType=FreightRateTypeEnum.PT,
                ext=copy.deepcopy(booking_context),
            ))

            for bundle_detail in bundle_details:
                addon_bundle_code = bundle_detail.get('bundleCode')
                if not addon_bundle_code:
                    continue
                bundle_meta = bundle_meta_dict.get(cls.__normalize_fare_name(addon_bundle_code), {})
                if not bundle_meta.get('name'):
                    continue

                addon_identity = (fare_key, addon_bundle_code, 'addon')
                if addon_identity in seen_bundle_keys:
                    continue
                seen_bundle_keys.add(addon_identity)

                bundle_price_text = re.sub(
                    r'[^0-9.-]',
                    '',
                    (bundle_detail.get('bundlePrice') or '').replace(',', ''),
                )
                bundle_amount = Decimal(bundle_price_text) if bundle_price_text else Decimal('0')
                if bundle_amount <= 0:
                    continue

                bundle_name = (
                        bundle_detail.get('bundleName')
                        or bundle_meta.get('name')
                        or addon_bundle_code
                )
                addon_ssr_info = FlightSsrInfoModel()
                addon_ssr_info.baggage = cls.build_baggage_info(
                    product_class=product_class,
                    bundle_meta_dict=bundle_meta_dict,
                    fare_name=addon_bundle_code,
                    description_text=bundle_detail.get('bundleDescription'),
                )

                result_bundles.append(FlightBundleModel(
                    priceInfo=FlightBundlePriceModel(
                        adultTicketPrice=price_info.adult_ticket_price + bundle_amount,
                        adultTaxPrice=price_info.adult_tax_price,
                        childTicketPrice=price_info.child_ticket_price + bundle_amount,
                        childTaxPrice=price_info.child_tax_price,
                        currency=price_info.currency,
                    ),
                    ssrInfo=addon_ssr_info,
                    code=addon_bundle_code,
                    cabinLevel=cabin_level,
                    cabin=cabin,
                    fareKey=fare_key,
                    productTag=bundle_name,
                    seat=seat,
                    freightRateType=FreightRateTypeEnum.PT,
                    ext=copy.deepcopy(booking_context),
                ))

        return result_bundles
