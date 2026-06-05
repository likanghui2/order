from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_serializer, field_validator

from common.utils.date_util import DateUtil


class FlightSegmentModel(BaseModel):
    segment_key: str = Field(..., alias="segmentKey")
    dep_airport: str = Field(...,alias='depAirport')
    arr_airport: str = Field(...,alias='arrAirport')
    dep_time: datetime = Field(...,alias='depTime')
    arr_time: datetime = Field(...,alias='arrTime')
    flight_number: str = Field(...,alias='flightNumber')
    carrier: str = Field(...,alias='carrier')
    operating_carrier: str = Field(...,alias='operatingCarrier')
    operating_flight_number: str = Field(...,alias='operatingFlightNumber')
    stopoverAirport: Optional[str] = Field(default=None,alias='stopoverAirport')
    stopoverTime: Optional[int] = Field(default=-1,alias='stopoverTime')
    leg_index: int = Field(default=None,alias='legIndex')
    route_index: int = Field(default=None,alias='routeIndex')
    ext: Optional[dict] = Field(default={},alias='ext')

    @field_validator('dep_time', 'arr_time', mode='before')
    @classmethod
    def date_string_parser(cls, v):
        if isinstance(v, str):
            parsed = DateUtil.string_to_date_auto(v)
            if parsed is not None:
                return parsed
        return v

    @field_serializer('dep_time','arr_time', when_used='json')
    def decimal_serializer(self, v:datetime):
        return v.strftime('%Y%m%d%H%M')
