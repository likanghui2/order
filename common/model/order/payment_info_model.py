from pydantic import BaseModel, Field


class PaymentInfoModel(BaseModel):
    type: str = Field(..., alias='type')
    card_number: str = Field(..., alias='cardNumber')
    card_expiry_date: str = Field(..., alias='cardExpiryDate')
    card_holder_name: str = Field(..., alias='cardHolderName')
    card_type: str = Field(..., alias='cardType')
    card_cvv: str = Field(..., alias='cardCVV')

