# from typing import List
#
# from bs4 import BeautifulSoup
#
#
#
# class VietJetBookingUtils:
#     @staticmethod
#     def generate_passenger_params(passenger_list: List[PassengerInfoModel], contact_info: ContactInfo, pref_language,purchasing: bool):
#         """
#         动态生成 params 字典
#
#         Args:
#             purchasing: 是否需要证件
#             pref_language: 语言代码
#             contact_info (ContactInfo): 联系信息
#             passenger_list (list[PassengerInfoModel]): 乘客信息列表，每个字典包含乘客的详细信息
#
#         Returns:
#             dict: 包含动态生成的参数
#         """
#
#         # 动态生成每个乘客的字段
#         params = {}
#         for idx, passenger in enumerate(passenger_list, start=1):
#             gender = passenger.gender.value if passenger.passenger_type == PassengerTypeEnum.ADT else 'C'
#             params.update({
#                 f"txtPax{idx}_Gender": gender,
#                 f"txtPax{idx}_LName": passenger.last_name(),
#                 f"txtPax{idx}_FName": passenger.first_name(),
#                 f"txtPax{idx}_Addr1": "",
#                 f"txtPax{idx}_City": "",
#                 f"txtPax{idx}_Ctry": "-1",
#                 f"txtPax{idx}_Prov": "-1",
#                 f"txtPax{idx}_EMail": "",
#                 f"txtPax{idx}_DOB_Day": "",
#                 f"txtPax{idx}_DOB_Month": "",
#                 f"txtPax{idx}_DOB_Year": "",
#                 f"txtPax{idx}_Phone2": "",
#                 f"txtPax{idx}_Phone1": "",
#                 f"txtPax{idx}_Passport": "",
#                 f"dlstPax{idx}_PassportExpiry_Day": "",
#                 f"dlstPax{idx}_PassportExpiry_Month": "",
#                 f"txtPax{idx}_Nationality": "",
#                 f"txtPax{idx}_PrefLanguage": pref_language,
#                 f"hidPax{idx}_Search": "-1",
#             })
#             if gender == 'C':
#                 del params[f"hidPax{idx}_Search"]
#             if purchasing:
#                 nation = FlyVietjetConfig.NATION_DICT.get(passenger.issue_place, None)
#                 if nation is None:
#                     raise ServiceError(ServiceStateEnum.INVALID_DATA,
#                                        f"乘客{passenger.name}签发国匹配失败")
#                 docnmbr = passenger.card_number
#                 if not docnmbr:
#                     raise ServiceError(ServiceStateEnum.INVALID_DATA,
#                                        f"乘客{passenger.name}证件号码为空")
#                 params[f"txtPax{idx}_APISDOCNATIONALITY_1"] = nation
#                 params[f"txtPax{idx}_APISDOCNMBR_1"] = docnmbr
#                 params[f"dlstPax{idx}_APISDOCEXPDATE_1_Day"] = passenger.card_expired.day
#                 params[f"dlstPax{idx}_APISDOCEXPDATE_1_Month"] = passenger.card_expired.strftime('%Y-%m')
#
#         params['txtPax1_EMail'] = contact_info.email
#         params['txtPax1_Phone2'] = f'+{contact_info.mobile_country_code}{contact_info.mobile}'
#         return params
#
#     @staticmethod
#     def parse_baggage_details(html_info) -> List[List[BaggageInfoModel]]:
#         """
#
#         Args:
#             html_info:
#
#         Returns:
#
#         """
#         # 解析HTML
#         soup = BeautifulSoup(html_info, 'html.parser')
#         # shopPaxOmega
#         shop_pax_omega_table = soup.find('table', {'id': 'shopPaxOmega'})
#         top_tr = shop_pax_omega_table.find("tr", {"valign": "top"})
#         # 在 top_tr 中查找航班号
#         extracted_soup = BeautifulSoup(str(top_tr), 'html.parser')
#         # 提取航班号
#         flight_segments = extracted_soup.find_all('tr', class_='flight_segment')
#         flights_and_baggages = []
#         for flight_segment in flight_segments:
#             # 提取航班号
#             flight_number = flight_segment.find('span').text.strip().split(" ")[0]
#
#             # 找到当前航班号后的第一个行李列表
#             next_baggage_section = flight_segment.find_next_sibling('tr',
#                                                                     class_='shoppax_item Baggage ContentCategoryID1')
#             flights_and_baggage = []
#             if next_baggage_section:
#                 # 提取行李选项
#                 baggage_options = next_baggage_section.find_all('option')
#                 for option in baggage_options:
#                     if 'Bag' not in option.text.strip() and 'Baggage' not in str(option):
#                         continue
#                     weight = option.text.strip().replace('Bag', '').replace("kgs", '').replace(' ', '').replace(
#                         'kgonly1pc', "").replace('(VZ)', '')
#                     baggage_info = option.attrs['hidpaxvalue'].split('|')
#                     price = baggage_info[13]
#                     bag_tax = baggage_info[15].replace(',', '')
#                     amount_str, currency = price.split(' ', 1)
#                     amount = amount_str.replace(',', '')
#                     amount = float(amount)+float(bag_tax)
#                     flights_and_baggage.append(BaggageInfoModel.model_validate({
#                         'baggageType': BaggageTypeEnum.HAULING_BAGGAGE,
#                         'pieces': 1,
#                         'totalWeight': weight,
#                         'flightNumber': flight_number,
#                         'sellKey': option.attrs['hidpaxvalue'],
#                         'amount': amount,
#                         'code': option.attrs['value'],
#                         'currency': currency
#                     }))
#             flights_and_baggages.append(flights_and_baggage)
#         return flights_and_baggages
#
#     @staticmethod
#     def parse_baggage_data(html_info) -> dict:
#         """
#
#         Args:
#             html_info:
#
#         Returns:
#
#         """
#         soup = BeautifulSoup(html_info, 'html.parser')
#
#         # 定位所有乘客行
#         passenger_tr_list = soup.select('#shopPaxOmega tr[valign="top"]')
#
#         baggage_dict = {}
#
#         for passenger_tr in passenger_tr_list:
#             # 提取乘客姓名
#             name_tag = passenger_tr.select_one('.shopPaxMstr_paxname h1')
#             if name_tag:
#                 name = name_tag.get_text(strip=True).replace(',', "/").replace(' ', "").upper()
#
#                 # 初始化乘客数据
#                 passenger_flights = {}
#
#                 # 定位航班号及其对应行李信息
#                 flights = passenger_tr.select('tr.flight_segment')
#
#                 for flight in flights:
#                     flight_info = flight.select_one('.flight_segment_detail span').get_text(strip=True)
#                     flight_number = flight_info.split(' ')[0]
#                     flight_number = flight_number[:2] + flight_number[2:].zfill(4)
#                     # 获取该航班的行李选项
#                     baggage_section = flight.find_next('tr', class_='shoppax_item Baggage ContentCategoryID1')
#                     baggage_options = baggage_section.select('option') if baggage_section else []
#
#                     flight_baggage = {}
#                     # 定位行李选项列表
#                     option_list = passenger_tr.select('tr.shoppax_item.Baggage.ContentCategoryID1 option')
#                     select_td = passenger_tr.select_one('tr.shoppax_item.Baggage.ContentCategoryID1 select')
#
#                     # 提取 `select` 的 ID 和 Name
#                     if select_td:
#                         select_id = select_td.get('id')
#                         select_name = select_td.get('name')
#                     else:
#                         select_id = None
#                         select_name = None
#
#                     # 初始化乘客行李信息
#                     flight_baggage = {
#                         "select_id": select_id,
#                         "select_name": select_name,
#                     }
#                     for option in baggage_options:
#                         value = option.get('value', '-1')
#                         hidpaxitem = option.get('hidpaxitem', '-1')
#                         hidpaxvalue = option.get('hidpaxvalue', '-1')
#                         text = option.get_text(strip=True).replace(' (VZ)', '')
#                         if 'Oversize' in text:
#                             continue
#                         if text == "不用，谢谢":
#                             text = "Bag 0kgs"
#
#                         # 提取价格
#                         price = 0
#                         if hidpaxvalue != '-1':
#                             hid_list = hidpaxvalue.split('|')
#                             price = float(hid_list[-5])
#
#                         # 构建行李信息
#                         baggage_info = {
#                             "value": value,
#                             "hidpaxitem": hidpaxitem,
#                             "hidpaxvalue": hidpaxvalue,
#                             "price": price,
#                         }
#
#                         # 将 description 作为键
#                         flight_baggage[text] = baggage_info
#
#                     # 将该航班的行李信息存入字典，以航班号为键
#                     passenger_flights[flight_number] = flight_baggage
#
#                 # 存储乘客的所有航班行李信息
#                 baggage_dict[name] = passenger_flights
#         return baggage_dict
#
#     @staticmethod
#     def parse_input_page_data(html, attrs: dict = None):
#         """
#
#         Args:
#             attrs:
#             html:
#
#         Returns:
#
#         """
#         if attrs is None:
#             attrs = {'type': 'hidden'}
#         # 使用 BeautifulSoup 解析 HTML
#         soup = BeautifulSoup(html, 'html.parser')
#
#         # 初始化数据字典
#         data_dict = {}
#
#         # 查找所有隐藏字段的 input 标签
#         hidden_inputs = soup.find_all('input', attrs)
#
#         for input_tag in hidden_inputs:
#             # 提取 id 和 value 属性
#             input_id = input_tag.get('id')
#             input_name = input_tag.get('name')
#             input_value = input_tag.get('value', '')
#
#             # 优先使用 id 作为键，如果 id 不存在则使用 name
#             if input_id:
#                 data_dict[input_id] = input_value
#             elif input_name:
#                 data_dict[input_name] = input_value
#
#         return data_dict
#
#     @staticmethod
#     def pay_type_options(html_info: str) -> dict:
#         """
#         提取网页中支付方式，以及对应的值
#         Args:
#             html_info:
#
#         Returns:
#
#         """
#         #  延迟付款 '5,PL,0,PPPSPR,0,0,0'
#         #  Agency Credi '4,AG,0,PPPSPR,0,0,0'
#         # 解析 HTML
#         soup = BeautifulSoup(html_info, 'html.parser')
#         # 定位表格
#         table = soup.find('table', {'id': 'tblPayTypesMstr'})
#         # 初始化结果字典
#         result = {}
#         trs = table.find_all('tr')
#         for tr in trs:
#             # 遍历每个 <td>
#             for i, td in enumerate(tr.find_all('td')):
#                 td_class = td.get('class', [])
#                 if f'payOptInfo0' in td_class and 'payOptInfoCls' in td_class or f'payOptInfo1' in td_class and 'payOptInfoCls' in td_class:
#                     # 获取 <input> 标签
#                     input_tag = td.find('input', {'type': 'radio'})
#                     if input_tag:
#                         value = input_tag['value']
#                         onclick = input_tag['onclick']
#                         onclick = StringUtil.extract_between(onclick, '("', '")')
#
#                         # 获取选项描述文本
#                         description = td.get_text(strip=True)
#                         # 保存结果
#                         result[description] = {
#                             'value': value,
#                             'onclick': onclick,
#                         }
#         if not result.get('延迟付款') and not result.get('Agency Credit'):
#             raise ServiceError(ServiceStateEnum.INVALID_DATA, "获取代理人支付方式失败")
#         return result
