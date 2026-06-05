from typing import Optional

from pydantic import BaseModel, Field


class BookingConfig(BaseModel):
    currency_code: str = Field(...,alias="currencyCode")
    book_rate: Optional[int] = Field(default=None,alias="bookRate")
