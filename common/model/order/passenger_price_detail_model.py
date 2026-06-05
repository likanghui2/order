from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel, Field, field_serializer

from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel


class PassengerPriceDetailModel(BaseModel):
    ticket_price: Decimal = Field(None,alias='ticketPrice')
    tax_price: Decimal = Field(...,alias='taxPrice')

    @field_serializer('ticket_price','tax_price', when_used='json')
    def decimal_serializer(self, v:Decimal):
        return str(v.quantize(Decimal('0.00'),rounding=ROUND_HALF_UP))