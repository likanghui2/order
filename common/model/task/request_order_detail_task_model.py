from typing import Optional

from pydantic import BaseModel, Field


class RequestOrderDetailTaskModel(BaseModel):
    last_name: str = Field(...,alias="lastName")
    first_name: str = Field(...,alias="firstName")
    pnr: str = Field(...,alias="pnr")
    email: Optional[str] = Field(default=None, alias="email")
    currency_code: str = Field(default="VND", alias="currencyCode")
    ext: Optional[dict] = Field(default=None, alias="ext")
