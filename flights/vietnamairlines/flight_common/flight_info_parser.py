from datetime import datetime
from decimal import Decimal
from typing import List, Dict

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel

# Amadeus DES 舱位映射: API cabin 值 -> 标准舱位代码
CABIN_MAP = {
    "eco": "Y",
    "ecoPremium": "W",
    "business": "C",
    "first": "F",
}

# fareFamilyCode 前缀 -> productTag 映射（后缀为数字，不同航线不同）
PRODUCT_TAG_PREFIX_MAP = {
    "EP": "Economy Super Lite",
    "EL": "Economy Lite",
    "EC": "Economy Classic",
    "EF": "Economy Flex",
    "DC": "Premium Economy Classic",
    "DF": "Premium Economy Flex",
    "BC": "Business Classic",
    "BF": "Business Flex",
}


def _get_product_tag(fare_family_code: str):
    """通过前缀匹配 fareFamilyCode（如 EL7、EL5、EL1 都匹配 EL -> Economy Lite）"""
    prefix = fare_family_code[:2] if len(fare_family_code) >= 2 else ""
    return PRODUCT_TAG_PREFIX_MAP.get(prefix)


class FlightInfoParser:
    """
    越南航空 Amadeus DES API 响应解析器

    响应结构:
      data.airBoundGroups[]                      -> 航程组(按航线分组)
        .boundDetails.segments[].flightId        -> 航段ID，关联 dictionaries.flight
        .airBounds[]                             -> 票价选项
          .fareFamilyCode                        -> 票价家族代码，关联 dictionaries.fareFamilyWithServices
          .availabilityDetails[].quota            -> 剩余座位
          .prices.totalPrices[0]                  -> 票价(base + totalTaxes)
          .services[].serviceCode                 -> 服务代码，关联 dictionaries.service
      dictionaries.flight                         -> 航班详情字典(航司/航班号/起降时间)
      dictionaries.fareFamilyWithServices          -> 票价家族定义(舱位等级)
      dictionaries.service                         -> 服务定义(免费托运行李)
    """

    @classmethod
    def journey_info_parser(cls, data: dict) -> List[FlightJourneyModel]:
        """解析 /v2/search/air-bounds 响应，返回航程列表"""
        root = data.get("data", {})
        # dictionaries 与 data 同级，不在 data 内部
        dictionaries = data.get("dictionaries", {})
        flight_dict = dictionaries.get("flight", {})
        fare_family_dict = dictionaries.get("fareFamilyWithServices", {})
        service_dict = dictionaries.get("service", {})

        result = []
        for group_index, group in enumerate(root.get("airBoundGroups", []), start=1):
            bound_details = group.get("boundDetails", {})
            segment_flight_ids = [s["flightId"] for s in bound_details.get("segments", [])]

            # 过滤非直飞航班
            if len(segment_flight_ids) != 1:
                continue

            # routeIndex: 航线索引，单程固定为1，往返时去程=1/回程=2
            route_index = bound_details.get("ranking", 1)
            segments = cls.__parse_segments(segment_flight_ids, flight_dict, route_index)
            if not segments:
                continue

            bundles = cls.__parse_bundles(group.get("airBounds", []), fare_family_dict, service_dict)

            result.append(FlightJourneyModel(
                journeyKey="|".join(segment_flight_ids),
                segments=segments,
                bundles=bundles,
                depAirport=segments[0].dep_airport,
                arrAirport=segments[-1].arr_airport,
                depTime=segments[0].dep_time,
                arrTime=segments[-1].arr_time,
            ))
        return result

    @classmethod
    def __parse_segments(cls, flight_ids: list, flight_dict: dict, route_index: int) -> List[FlightSegmentModel]:
        """通过 flightId 从 dictionaries.flight 字典查找航段详情"""
        segment_list = []
        for flight_id in flight_ids:
            flight = flight_dict.get(flight_id)
            if not flight:
                continue

            carrier = flight["marketingAirlineCode"]
            operating_carrier = flight.get("operatingAirlineCode", carrier)
            # 过滤代码共享航班
            if carrier != operating_carrier:
                return []

            flight_number = carrier + flight["marketingFlightNumber"]
            operating_flight_number = operating_carrier + flight.get("operatingAirlineFlightNumber", flight["marketingFlightNumber"])

            dep = flight["departure"]
            arr = flight["arrival"]
            dep_time = datetime.fromisoformat(dep["dateTime"])
            arr_time = datetime.fromisoformat(arr["dateTime"])

            segment_list.append(FlightSegmentModel(
                segmentKey=flight_id,
                depAirport=dep["locationCode"],
                arrAirport=arr["locationCode"],
                depTime=dep_time,
                arrTime=arr_time,
                carrier=carrier,
                flightNumber=flight_number,
                operatingCarrier=operating_carrier,
                operatingFlightNumber=operating_flight_number,
                routeIndex=route_index,
                legIndex=route_index,
            ))
        return segment_list

    @classmethod
    def __parse_bundles(cls, air_bounds: list, fare_family_dict: dict,
                        service_dict: dict) -> List[FlightBundleModel]:
        """解析票价选项: 每个 airBound 对应一个票价家族(EL7/EC7/BF7等)"""
        bundle_list = []
        for bound in air_bounds:
            availability = bound.get("availabilityDetails", [])
            quota = min((a.get("quota", 0) for a in availability), default=0)
            if quota <= 0:
                continue

            fare_family_code = bound.get("fareFamilyCode", "")
            # 过滤未定义的票价家族（前缀匹配）
            product_tag = _get_product_tag(fare_family_code)
            if not product_tag:
                continue

            fare_family = fare_family_dict.get(fare_family_code, {})
            cabin_raw = fare_family.get("cabin", "eco")
            cabin_level = CABIN_MAP.get(cabin_raw, "Y")

            # unitPrices 为单人价格，totalPrices 为所有乘客总价
            unit_price = bound.get("prices", {}).get("unitPrices", [{}])[0].get("prices", [{}])[0]
            currency = unit_price.get("currencyCode", "")
            base = Decimal(str(unit_price.get("base", 0))) / 100
            total_taxes = Decimal(str(unit_price.get("totalTaxes", 0))) / 100

            price_info = FlightBundlePriceModel(
                adultTicketPrice=base,
                adultTaxPrice=total_taxes,
                childTicketPrice=base,
                childTaxPrice=total_taxes,
                currency=currency,
            )

            baggage_list = cls.__parse_baggage(bound.get("services", []), service_dict)
            # 手提行李: 经济舱 1x10kg，商务舱 1x18kg（API 不返回，按官网规则补充）
            hand_weight = 18 if cabin_level == "C" else 10
            baggage_list.append(FlightBaggageModel(
                type=SsrTypeEnum.HAND_BAGGAGE, price=Decimal(0), weight=hand_weight, number=1
            ))
            ssr_info = FlightSsrInfoModel(baggage=baggage_list)

            bundle_list.append(FlightBundleModel(
                priceInfo=price_info,
                ssrInfo=ssr_info,
                code=fare_family_code,
                cabinLevel=cabin_level,
                cabin=availability[0].get("bookingClass", "") if availability else "",
                fareKey=bound.get("airBoundId", ""),
                productTag=product_tag,
                seat=quota,
                freightRateType=FreightRateTypeEnum.PT,
            ))
        return bundle_list

    @classmethod
    def __parse_baggage(cls, services: list, service_dict: dict) -> List[FlightBaggageModel]:
        """从 dictionaries.service 解析免费托运行李(经济舱 23kg x1, 商务舱 32kg x2)"""
        baggage_list = []
        for svc in services:
            code = svc.get("serviceCode", "")
            definition = service_dict.get(code, {})
            if definition.get("serviceType") != "freeCheckedBaggage":
                continue
            for desc in definition.get("baggagePolicyDescriptions", []):
                quantity = desc.get("quantity", 1)
                weight = 0
                for char in desc.get("baggageCharacteristics", []):
                    for policy in char.get("policyDetails", []):
                        if policy.get("type") == "weight" and policy.get("unit") == "kilogram":
                            weight = int(policy["value"])
                            break
                if weight > 0:
                    baggage_list.append(FlightBaggageModel(
                        type=SsrTypeEnum.HAULING_BAGGAGE,
                        price=Decimal(0),
                        weight=weight,
                        number=quantity,
                    ))
        return baggage_list
