from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from pydantic import BaseModel, Field, field_serializer

from common.enums.ssr_type_enum import SsrTypeEnum


class FlightBaggageModel(BaseModel):
    type: SsrTypeEnum = Field(...,alias='type')
    code: Optional[str] = Field(default=None,alias='code')
    price: Decimal = Field(..., alias='price')
    number: int = Field(...,alias='number')
    weight: int = Field(...,alias='weight')
    weight_unit: Optional[str] = Field(default='KG', alias='weightUnit')
    limit: Optional[int] = Field(default=None,alias='limit',exclude=True)
    key: Optional[str]= Field(default=None,alias='key',exclude=True)


    @field_serializer('price', when_used='json')
    def decimal_serializer(self, v:Decimal):
        return str(v.quantize(Decimal('0.00'),rounding=ROUND_HALF_UP))