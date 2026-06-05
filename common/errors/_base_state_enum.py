"""
Module: _base_state_enum
Author: Ciwei
Date: 2024-09-13

Description:
    状态基础Enum类，其他状态实现继承此类
"""
from enum import Enum


class BaseStateEnum(Enum):
    """

    """

    @classmethod
    def get_value(cls,name):
        try:
            return cls[name].value
        except KeyError:
            return None
