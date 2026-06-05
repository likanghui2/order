"""
Module: _base_error
Author: Ciwei
Date: 2024-09-13

Description:
    基础错误类，其他错误类实现继承此类
"""
from typing import Optional

from common.errors._base_state_enum import BaseStateEnum


class MyBaseError(Exception):
    """

    """

    def __init__(self, state_enum: BaseStateEnum, message: str):
        self.__message = message
        super().__init__(message)
        self.__state = state_enum.name

    @property
    def code(self):
        return self.__state

    @property
    def message(self):
        return self.__message
