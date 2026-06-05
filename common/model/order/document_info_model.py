from typing import Optional

from pydantic import Field, BaseModel, field_validator

from common.enums.document_type_enum import DocumentTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum


class DocumentInfoModel(BaseModel):
    type: Optional[DocumentTypeEnum] = Field(default=None, alias='type', description='证件类型')
    nationality: Optional[str] = Field(alias='nationality',description='国籍')
    issuing_country: Optional[str] = Field(alias='issuingCountry',description='发行国')
    number: Optional[str] = Field(alias='number',description='证件号')
    expire_date: Optional[str] = Field(alias='expireDate',description='有效期')
