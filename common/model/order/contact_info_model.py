from pydantic import BaseModel, Field


class ContactInfoModel(BaseModel):
    last_name: str = Field(...,alias='lastName',description='姓')
    first_name: str = Field(...,alias='firstName',description='名')
    email_address: str = Field(...,alias='emailAddress',description='邮箱')
    phone_code: str = Field(...,alias='phoneCode',description='电话国家代码')
    phone_number: str = Field(...,alias='phoneNumber',description='联系人号码')