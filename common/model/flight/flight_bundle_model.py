from typing import Optional

from pydantic import BaseModel, Field

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel


class FlightBundleModel(BaseModel):
    price_info: FlightBundlePriceModel = Field(..., alias='priceInfo')
    ssr_info: FlightSsrInfoModel  = Field(..., alias='ssrInfo')
    code: str = Field(..., alias='code')
    cabin_level: str = Field(..., alias='cabinLevel')
    cabin: Optional[str] = Field(default=None, alias='cabin')
    fare_key: Optional[str] = Field(None, alias='fareKey')
    product_tag: str = Field(..., alias='productTag')
    seat: int = Field(..., alias='seat')
    freight_rate_type: FreightRateTypeEnum = Field(..., alias='freightRateType')
    allow_reschedule: Optional[bool] = Field(default=None, alias='allowReschedule',description='允许改期')
    allow_refund: Optional[bool] = Field(default=None, alias='allowRefund',description='允许退票')
    refund_description: Optional[str] = Field(default=None, alias='refundDescription',description='退票描述')
    reschedule_description: Optional[str] = Field(default=None, alias='rescheduleDescription',description='改期描述')
    ext:Optional[dict] = Field(default={},alias='ext')