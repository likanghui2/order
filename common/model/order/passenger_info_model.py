from typing import List, Any, Optional

from pydantic import BaseModel, Field, field_validator

from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.order.document_info_model import DocumentInfoModel
from common.model.order.passenger_price_detail_model import PassengerPriceDetailModel


class PassengerInfoModel(BaseModel):
    key: Optional[str] = Field(default=None, alias='key', exclude=True)
    type: PassengerTypeEnum = Field(..., alias='type', description='乘客类型')
    last_name: str = Field(..., alias='lastName', description='姓')
    first_name: str = Field(..., alias='firstName', description='名')
    gender: GenderEnum = Field(..., alias='gender', description='性别')
    birthday: Optional[str] = Field(default=None, alias='birthday', description='生日')
    document_info: Optional[DocumentInfoModel] = Field(default=None, alias='documentInfo', description='证件信息')
    ssr: Optional[FlightSsrInfoModel] = Field(default=FlightSsrInfoModel(baggage=[]), alias='ssr',
                                              description='辅营信息')
    price_detail: PassengerPriceDetailModel = Field(default=None, alias='priceDetail')
    buy_baggage: List[FlightBaggageModel] = Field(default=[], exclude=True)
    bag_combination: List[int] = Field(default=[], exclude=True)
    ext: dict = Field(default={}, exclude=True)
    ticket_number: str = Field(default=None, alias='ticketNumber')

    def get_passenger_name(self):
        return self.last_name + '/' + self.first_name

    @field_validator("ssr")
    @classmethod
    def default_ssr(cls, v):
        if v is None:
            return FlightSsrInfoModel(baggage=[])
        return v
