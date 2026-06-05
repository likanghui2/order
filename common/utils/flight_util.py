import decimal
import itertools
from collections import defaultdict
from decimal import Decimal
from typing import List

from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.order.passenger_info_model import PassengerInfoModel


class FlightUtil:

    @staticmethod
    def number_filter(journeys:List[FlightJourneyModel], flight_number:str) -> List[FlightJourneyModel]:

        result = []
        for journey in journeys:
            _flight_number = ",".join([x.flight_number for x in journey.segments])
            print(_flight_number)

            if _flight_number == flight_number:
                result.append(journey)
        return result

    @staticmethod
    def time_verify(journey:FlightJourneyModel,target_time:List):
        if journey.dep_time.strftime("%Y%m%d%H%M") != target_time[0]:
            raise ServiceError(ServiceStateEnum.FLIGHT_TIME_INCONSISTENT,'出发',target_time[0],journey.dep_time)
        if journey.arr_time.strftime("%Y%m%d%H%M") != target_time[1]:
            raise ServiceError(ServiceStateEnum.FLIGHT_TIME_INCONSISTENT,'到达',target_time[0],journey.arr_time)
        return True

    @staticmethod
    def bundle_verify(journey:FlightJourneyModel,target_bundle_code: str):
        t = next((x for x in journey.bundles if x.code == target_bundle_code),None)
        if t is None:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
        return t

    @staticmethod
    def product_tag_verify(journey:FlightJourneyModel,target_product_tag: str):
        t = next((x for x in journey.bundles if x.product_tag == target_product_tag),None)
        if t is None:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
        return t

    @staticmethod
    def sort_segment(segments:List[FlightSegmentModel]) -> bool:
        sorted_data = sorted(segments, key=lambda x:x.route_index)

        r = defaultdict(list)
        for i in segments:
            if i.route_index is None:
                return False

            r[i.route_index].append(i)

        for k,v in r.items():
            for leg_index,segment in enumerate(v,start=1):
                segment.leg_index = leg_index

        return True

    @staticmethod
    def flight_data_check(journeys:List[FlightJourneyModel]):
        """
            航班数据检查
        :param journeys:
        :return:
        """

        for i in range(len(journeys)-1,-1,-1):
            if not FlightUtil.sort_segment(journeys[i].segments):
                del journeys[i]


    @staticmethod
    def find_min_luggage_cost(items, target_weight, max_types, allow_repeat=False):
        """
        计算满足目标重量的最低价格行李组合
        :param items: 行李额度列表，每个元素为元组(weight, price)
        :param target_weight: 目标重量（必须达到或超过）
        :param max_types: 最大可购买的种类数（如最多选2种行李）
        :param allow_repeat: 是否允许同种额度重复购买（True/False）
        :return: (min_cost, selected_items) 最低总价和组合列表
        """

        # 生成组合
        if allow_repeat:
            bag_combination = list(itertools.product([x[0] for x in items], repeat=max_types))
        else:
            bag_combination = list(itertools.combinations([x[0] for x in items], max_types))

        if max_types > 1:
            bag_combination += list(itertools.combinations([x[0] for x in items], 1))

        bag_price_data = dict(items)
        price_data = []
        for weight_data in bag_combination:
            total_weight = sum([x for x in weight_data])
            total_price = sum([bag_price_data[x] for x in weight_data])
            if total_weight < target_weight:
                continue
            price_data.append((total_price,weight_data))

        result_combination = min(price_data, key=lambda x:x[0])
        return result_combination


    @staticmethod
    def ticket_price_check(bundle: FlightBundleModel,passengers:List[PassengerInfoModel],price_threshold:decimal.Decimal):
        """
            出票价格检查
        :param bundle: 使用的套餐
        :param passengers:  乘机人信息，已添加辅营后
        :param price_threshold:  OTA价格阈值
        :return:
        """
        order_price = decimal.Decimal(0)
        for passenger in passengers:

            if passenger.type == PassengerTypeEnum.ADT:
                ticket_price = bundle.price_info.adult_ticket_price + bundle.price_info.adult_tax_price
            else:
                ticket_price = bundle.price_info.child_ticket_price + bundle.price_info.child_tax_price

            order_price = order_price + ticket_price

            for j in passenger.ssr.baggage:
                if j.price > 0: order_price = order_price + j.price

        if order_price > price_threshold:
            raise ServiceError(ServiceStateEnum.ORDER_PRICE_CHECK_FAILED,order_price,price_threshold,bundle.price_info.currency)
