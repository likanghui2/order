from typing import List, Optional

from pydantic import BaseModel, Field

from common.enums.freight_rate_type_enum import FreightRateTypeEnum


class RequestSearchTaskDataModel(BaseModel):
    dep_airport: str = Field(..., alias='depAirport')
    arr_airport: str = Field(..., alias='arrAirport')
    dep_date: str = Field(..., alias='depDate')
    adult_number: int = Field(...,alias='adultNumber')
    child_number: int = Field(...,alias='childNumber')
    currency_code: str = Field(..., alias='currencyCode')
    freight_rate_type: FreightRateTypeEnum = Field(...,alias='freightRateType')
    ret_date: Optional[str] = Field(default=None, alias='retDate')
    flight_number: Optional[str] = Field(default=None, alias='flightNumber')
    cabin_level: Optional[str] = Field(default='Y', alias='cabinLevel')
    private_code: Optional[List[str]] = Field(default_factory=list, alias='privateCode')
