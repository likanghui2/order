from typing import Optional, List

from common.decorators.retry_decorator import retry_decorator
from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from ..flight_common.flight_info_parser import FlightInfoParser
from ..script.web_script import WebScript

TITLE_MAP = {
    (GenderEnum.M, "ADT"): "MR",
    (GenderEnum.F, "ADT"): "MRS",
    (GenderEnum.M, "CHD"): "MSTR",
    (GenderEnum.F, "CHD"): "MISS",
}


class WebService:
    """越南航空查询/预订服务"""

    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__script = WebScript(proxy_info)

    def init(self):
        """初始化 Incapsula token"""
        self.__script.init_incapsula_token()

    def reset(self):
        """重置代理 IP 并重新初始化"""
        self.__script.reset_proxy_ip()
        self.init()

    @retry_decorator([(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, reset)], retry_max_number=3)
    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               infant_count: int,
               currency_code: str,
               ret_date: Optional[str] = None) -> List[FlightJourneyModel]:
        pax_count = adt_number + chd_number + infant_count

        response = self.__script.search_air_bounds(
            origin=dep_airport,
            destination=arr_airport,
            departure_date=dep_date,
            pax_count=pax_count,
        )

        response_dict = response.to_dict()
        journey_list = FlightInfoParser.journey_info_parser(response_dict)
        return journey_list

    def booking(self, journey: FlightJourneyModel, bundle: FlightBundleModel,
                passengers: List[PassengerInfoModel], contact_info: ContactInfoModel,
                response_order_data: ResponseOrderInfoModel):
        """
        完整预订流程: 创建购物车 -> 填写旅客 -> 填写联系方式 -> 创建订单
        """
        # 1. 创建购物车
        cart_resp = self.__script.create_cart([bundle.fare_key])
        cart_data = cart_resp.to_dict()["data"]
        cart_id = cart_data["id"]
        cart_travelers = cart_data["travelers"]

        # 2. 填写旅客信息
        traveler_infos = []
        for i, pax in enumerate(passengers):
            pax_type = "ADT" if pax.type.value == "ADT" else "CHD"
            title = TITLE_MAP.get((pax.gender, pax_type), "MR")
            traveler_infos.append({
                "traveler_id": cart_travelers[i]["id"],
                "last_name": pax.last_name,
                "first_name": pax.first_name,
                "title": title,
                "pax_type": pax_type,
                "date_of_birth": pax.birthday,
            })
        self.__script.update_travelers(cart_id=cart_id, travelers=traveler_infos)

        # 3. 填写联系方式
        all_traveler_ids = [ct["id"] for ct in cart_travelers]
        self.__script.add_contacts(
            cart_id=cart_id,
            last_name=passengers[0].last_name,
            traveler_ids=all_traveler_ids,
            email=contact_info.email_address.upper(),
            phone_code=f"+{contact_info.phone_code}",
            phone_number=contact_info.phone_number,
        )

        # 4. 创建订单
        order_resp = self.__script.create_order(cart_id)
        order_data = order_resp.to_dict()["data"][0]
        pnr = order_data["id"]

        # 5. 保留订单
        self.__script.hold_order(order_id=pnr, last_name=passengers[0].last_name)

        # 填充响应
        response_order_data.pnr = pnr
        response_order_data.order_number = ""
        response_order_data.passengers = passengers
        response_order_data.contact_info = contact_info
        response_order_data.currency_code = bundle.price_info.currency
        response_order_data.journeys = [journey]
        response_order_data.journeys[0].bundles = [bundle]
        response_order_data.order_state = OrderStateEnum.HOLD
        return response_order_data
