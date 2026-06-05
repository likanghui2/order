import random
from typing import Optional
from faker import Faker

from common.enums.document_type_enum import DocumentTypeEnum
from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.document_info_model import DocumentInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel


class ShamBookingUtil:


    @classmethod
    def build_sham_passenger_info(cls,adt_number: int,use_pass_port: Optional[bool] = False):
        r = []
        fake = Faker(locale='en_US')
        for i in range(adt_number):
            gender = random.choice([GenderEnum.M, GenderEnum.F])
            last_name = fake.last_name().upper()
            first_name = fake.first_name().upper()

            document_info = None
            if use_pass_port:
                passport = fake.passport_number()
                document_info = DocumentInfoModel(
                    type=DocumentTypeEnum.PASSPORT,
                    nationality="US",
                    issuingCountry="US",
                    number=passport,
                    expireDate=fake.future_date(end_date='+10y').strftime('%Y-%m-%d')
                )
            r.append(
                PassengerInfoModel(
                    type=PassengerTypeEnum.ADT,
                    gender=gender,
                    lastName=last_name,
                    firstName=first_name,
                    birthday=fake.date_of_birth(minimum_age=18, maximum_age=80).strftime('%Y-%m-%d'),
                    ssr=None,
                    documentInfo=document_info
                )
            )

        return r



    @classmethod
    def build_sham_contact_info(cls):
        fake = Faker(locale='en_US')
        return ContactInfoModel(
            lastName=fake.last_name().upper(),
            firstName=fake.first_name().upper(),
            emailAddress=fake.email(),
            phoneNumber="212"+ str(random.randint(1000000,9999999)),
            phoneCode="1"
        )

    @classmethod
    def build_address(cls):
        fake_multi = Faker('en_US')
        return  fake_multi.city(),fake_multi.street_address(),fake_multi.postcode()


if __name__ == '__main__':
    # print(ShamBookingUtil.build_sham_contact_info())
    print(ShamBookingUtil.build_address())