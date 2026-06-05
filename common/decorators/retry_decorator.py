"""
Module: retry_decorator
Author: Ciwei
Date: 2024-10-23

Description:
    This module provides functionalities for ...
"""
import functools
from typing import List, Tuple, Any

from common.errors import MyBaseError, BaseStateEnum
from common.utils.log_util import LogUtil


def retry_decorator(retry_service_error_list: List[Tuple[BaseStateEnum, Any]],
                    retry_max_number: int = 3):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            log = LogUtil("retryDecorator")
            t = 0
            while t <= retry_max_number:
                log.info(f'第{t+1}次执行函数！')
                t += 1
                try:
                    result = func(self, *args, **kwargs)
                    return result
                except MyBaseError as e:
                    if t >= retry_max_number:
                        raise e

                    f = next((x for x in retry_service_error_list if x[0].name == e.code), None)
                    if not f:
                        raise

                    if f[1]:
                        if type(f[1]) == list:
                            for i in f[1]:
                                i(self)
                        else:
                            f[1](self)

        return wrapper

    return decorator
