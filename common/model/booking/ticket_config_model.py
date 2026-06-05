
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_serializer


class TicketConfigModel(BaseModel):
    orderTotalPrice: Optional[Decimal] = Field(default=None, alias="orderTotalPrice")
    isForceIssue: Optional[bool] = Field(default=False, alias="isForceIssue")
    priceThreshold: Optional[Decimal] = Field(default=None, alias="priceThreshold")
    currency_code: str = Field(...,alias="currencyCode")
    fake_order: Optional[bool] = Field(default=False, alias="fakeOrder")
    agent_user_name: Optional[str] = Field(default="", alias="agentUserName")
    agent_password: Optional[str] = Field(default="", alias="agentPassword")