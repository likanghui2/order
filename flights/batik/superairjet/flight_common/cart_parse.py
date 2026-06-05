from typing import List
from lxml import etree
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.order.passenger_info_model import PassengerInfoModel


class CartParser:
    @staticmethod
    def cart_passengers_parse(cart_html_str: str, passenger_infos: List[PassengerInfoModel]):
        data = {

            "ctl00$ctl00$additionalContent$additionalContent$FlightInfo": "",
            "ctl00$ctl00$additionalContent$additionalContent$AXTotal": "",
            "ctl00$ctl00$additionalContent$additionalContent$DCTotal": "",
            "ctl00$ctl00$additionalContent$additionalContent$OtherTotal": "",
            "ctl00$ctl00$additionalContent$additionalContent$nameMismatch": ""
        }

        # [i.replace("\n", "").replace("\r", "").strip() for i in
        # etree.HTML(cart_html_str).xpath('''//h3[@class='headstyle1 redclr']//text()''') if i.strip()]

        ddl_airline = ''.join(
            etree.HTML(cart_html_str).xpath(
                '''//*[@id="ctl00_ctl00_mainContent_bookingMainContent_NameBlock1_ddlAirline"]//option//@value''')).strip()
        print(ddl_airline)
        user_list = [i.replace("\n", "").replace("\r", "").strip().split(".") for i in
                     etree.HTML(cart_html_str).xpath('''//h3[@class="headstyle1 brownclr"]/text()''') if i.strip()]

        if len(user_list) != len(passenger_infos):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR,
                               f'乘机人数异常 官网人数：{len(user_list)},实际人数：{len(passenger_infos)}')
        passenger_map = {}
        for user in user_list:
            user_type = user[1].strip()
            user_index = user[0].strip()

            if user_type == "Adult":
                passenger_type = "ADT"
            else:
                passenger_type = "CHD"

            passenger_info = passenger_infos.pop(
                next(i for i, x in enumerate(passenger_infos) if x.type.value == passenger_type))

            if user_type == "Adult":
                title = "Mr" if passenger_info.gender.value == "M" else "Ms"
            else:
                title = "Mstr" if passenger_info.gender.value == "M" else "Miss"

            passenger_map[passenger_info.last_name + "/" + passenger_info.first_name] = user_index

            if "txtPassportNumber" in cart_html_str:
                user_info_data = {
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlTitle": title,
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtFirstName": passenger_info.first_name,
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtLastName": passenger_info.last_name,
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlDOBDay": str(
                        passenger_info.birthday.split("-")[-1]).zfill(2),
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlDOBMonth": str(
                        int(passenger_info.birthday.split("-")[-2])),
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlDOBYear": str(passenger_info.birthday.split("-")[-3]),
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlPaxCountry": str(
                        passenger_info.document_info.nationality),
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtFFNo": "",
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtCountryCode": "",
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtPhoneNumber": "",
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlSpecRequest": "NA",
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlGender": passenger_info.gender.value,
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlAirline": ddl_airline,
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlSeatRequest": "NA",
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlMealRequest": "No Preference",
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtPassportNumber": passenger_info.document_info.number,
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlPassportExpDay": str(
                        passenger_info.document_info.expire_date.split("-")[-1]).zfill(2),
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlPassportExpMon": str(
                        int(passenger_info.document_info.expire_date.split("-")[-2])),
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlPassportExpYear": str(
                        passenger_info.document_info.expire_date.split("-")[0]),
                    f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlDocCountry": passenger_info.document_info.nationality,
                }
                if passenger_type == "CHD":
                    user_info_data.pop(f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtFFNo")
                    user_info_data.pop(f"ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlSpecRequest")
            else:
                if passenger_type == "ADT":
                    user_info_data = {
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlTitle': title,
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtFirstName': passenger_info.first_name,
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtLastName': passenger_info.last_name,
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtFFNo': '',
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlSpecRequest': 'NA',
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlAirline': ddl_airline,
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlSeatRequest': 'NA',
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlMealRequest': 'No Preference',
                    }
                else:
                    user_info_data = {

                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlTitle': title,
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtFirstName': passenger_info.first_name,
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$txtLastName': passenger_info.last_name,
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlDOBDay': str(
                            passenger_info.birthday.split("-")[-1]).zfill(2),
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlDOBMonth': str(
                            int(passenger_info.birthday.split("-")[-2])),
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlDOBYear': str(
                            passenger_info.birthday.split('-')[0]),
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlAirline': ddl_airline,
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlSeatRequest': 'NA',
                        f'ctl00$ctl00$mainContent$bookingMainContent$NameBlock{user_index}$ddlMealRequest': 'No Preference',
                    }

            data.update(user_info_data)

        return data, passenger_map
