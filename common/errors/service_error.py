"""
Module: _service_state_enum
Author: Ciwei
Date: 2024-10-05

Description: 
    This module provides functionalities for ...
"""

from common.errors._base_state_enum import BaseStateEnum
from common.errors._my_base_error import MyBaseError


class ServiceStateEnum(BaseStateEnum):
    BUSINESS_ERROR = "业务错误[{}]"
    NO_FLIGHT_DATA = "无航班数据"
    FLIGHT_NUMBER_NOT_NULL = "航班号不能为空"
    DOCUMENT_INFO_NOT_NULL = "乘客[{}],证件信息不能为空"
    NO_AVAILABLE_FLIGHT_NUMBER = "无可用航班号[{}]"
    NO_AVAILABLE_CABIN = "无可用舱位[{}]，当前舱[{}]"
    NO_AVAILABLE_BUNDLE = "无可用套餐信息"
    FLIGHT_TIME_INCONSISTENT = "航班{}时间不一致,OTA传入[{}],实际时间[{}]"
    API_RESPONSE_FAILED = '第三方API响应失败'
    API_RESPONSE_EXCEPTION = '第三方API响应异常'
    RESPONSE_STATE_ERROR = '响应状态错误[{}]'
    EXCEPTION_UPPER_LIMIT = "触发异常检查上限[{}]"
    ORDER_STATE_CHECK_LIMIT = "触发订单状态检查上限，请人工检查授权状态，出票状态"
    PAYMENT_EXCEPTION = "支付异常，请检查卡片是否已扣款，异常信息[{}]"
    GET_PNR_INFO_EXCEPTION = "获取PNR信息异常，请检查卡片是否已扣款，异常信息[{}]"
    ORDER_PRICE_CHECK_FAILED = "订单价格检查失败，官网价格[{0}/{2}]，OTA价格阈值[{1}/{2}]"
    HTTP_EXCEPTION = 'HTTP异常'
    CURL_EXCEPTION = 'CURL异常'
    CURL_EXCEPTION_16 = 'HTTP异常16'
    HTTP_TIMEOUT = 'HTTP请求超时[{}]'
    HTTP_RESPONSE_STATE_NOT_SATISFY = 'HTTP响应状态未满足[{}]'
    PAYMENT_FAILED = '支付失败，请检查卡片日志信息'
    DATA_VALIDATION_FAILED = '数据验证失败[{}]'
    AKM_RISK_CHECK_FAILED = 'AKM风控未通过'
    AKM_RISK_TWO_CHECK_FAILED = 'AKM风控二验未通过'
    HCAP_RISK_CHECK_FAILED = 'Hcap风控未通过'
    BOOKING_SEAT_FAILURE = '预订座位失败'
    ROBOT_CHECK = '机器人验证'
    CLOUD_FLARE_CHECK_FAILURE = 'CloudFlae验证未通过'
    AWS_CHECK_FAILURE = 'AWS验证未通过'


class ServiceError(MyBaseError):

    def __init__(self, service_state: ServiceStateEnum, *args):
        message = service_state.value.format(*args)
        super().__init__(state_enum=service_state, message=message)
