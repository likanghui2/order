import decimal
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List

from pydantic import BaseModel, Field, field_serializer

from common.enums.order_state_enum import OrderStateEnum
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.order.passenger_price_detail_model import PassengerPriceDetailModel


class ResponseOrderInfoModel(BaseModel):
    order_number: str = Field(default=None,alias="orderNumber")
    order_state: OrderStateEnum = Field(default=None,alias='orderState')
    pnr: str = Field(default=None,alias='pnr')
    passengers:List[PassengerInfoModel] = Field(default=None,alias='passengers')
    journeys: List[FlightJourneyModel] = Field(default=None,alias='journeys')
    contact_info: ContactInfoModel= Field(default=None,alias="contactInfo")
    total_amount: Decimal = Field(default=decimal.Decimal('0'),alias="totalAmount")
    currency_code: str = Field(default=None,alias='currencyCode')

    @field_serializer('total_amount', when_used='json')
    def decimal_serializer(self, v:Decimal):
        return str(v.quantize(Decimal('0.00'),rounding=ROUND_HALF_UP))