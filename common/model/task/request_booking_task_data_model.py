from typing import List, Optional

from pydantic import BaseModel, Field

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.model.booking.ticket_config_model import TicketConfigModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.order.payment_info_model import PaymentInfoModel

from common.enums.passenger_type_enum import PassengerTypeEnum

class RequestBookingTaskDataModel(BaseModel):
    dep_airport: str = Field(...,alias="depAirport")
    arr_airport: str = Field(...,alias="arrAirport")
    dep_time: str = Field(...,alias="depTime")
    arr_time: str = Field(...,alias="arrTime")
    flight_number: Optional[str] = Field(...,alias="flightNumber")
    product_tag: str = Field(...,alias="productTag")
    promo_code: Optional[str] = Field(default="",alias="promoCode")
    ticket_config: TicketConfigModel = Field(...,alias="ticketConfig")
    freight_rate_type: FreightRateTypeEnum = Field(...,alias='freightRateType')
    passengers: List[PassengerInfoModel] = Field(..., alias='passengers',description='乘客列表')
    contact_info: ContactInfoModel = Field(..., alias='contactInfo',description='联系人列表')
    payment_info: PaymentInfoModel = Field(..., alias='paymentInfo',description='支付信息')
    pnr: Optional[str] = Field(default="",alias="pnr")


    def get_passenger_number(self):
        """
            获取乘客数量
        :return:
        """
        adt_number = sum([1 for x in self.passengers if x.type == PassengerTypeEnum.ADT])
        chd_number = sum([1 for x in self.passengers if x.type == PassengerTypeEnum.CHD])

        return adt_number,chd_number



