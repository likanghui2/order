from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, Field, field_serializer


class FlightBundlePriceModel(BaseModel):

    adult_ticket_price: Decimal = Field(..., alias='adultTicketPrice')
    adult_tax_price: Decimal = Field(..., alias='adultTaxPrice')
    child_ticket_price: Decimal = Field(..., alias='childTicketPrice')
    child_tax_price: Decimal = Field(..., alias='childTaxPrice')
    currency: str = Field(...,alias='currency')

    @field_serializer('adult_ticket_price', 'adult_tax_price','child_ticket_price','child_tax_price', when_used='json')
    def decimal_serializer(self, v:Decimal):
        return str(v.quantize(Decimal('0.00'),rounding=ROUND_HALF_UP))