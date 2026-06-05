from typing import Optional

from pydantic import BaseModel, Field

from common.model.booking.booking_config_model import BookingConfig
from common.model.booking.ticket_config_model import TicketConfigModel


class RequestShamBookingTaskDataModel(BaseModel):
    dep_airport: str = Field(...,alias="depAirport")
    arr_airport: str = Field(...,alias="arrAirport")
    dep_date: str = Field(...,alias="depDate")
    flight_number: str = Field(...,alias="flightNumber")
    cabin: Optional[str] = Field(None,alias="cabin")
    priceInterval: Optional[str] = Field(None,alias="priceInterval")
    booking_config: BookingConfig = Field(...,alias="bookingConfig")
    ext: Optional[dict] = Field(None,alias="ext")
