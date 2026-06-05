"""
Module: date_util
Author: Ciwei
Date: 2024-09-13

Description:
    日期时间工具类
"""
from datetime import datetime


class DateUtil:
    __POSSIBLE_DATE_FORMATS = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",  # 2024-09-13 14:45:00
        "%Y-%m-%d",  # 2024-09-13
        "%Y%m%d",  # 20240913
        "%Y%m%d%H%M",  # 202404091945
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M",
        "%m.%d.%Y %H:%M",  # 01.10.2024 02:55
        "%a. %d %b. %Y, %H%M",  # Mon. 18 Nov. 2024, 1025
        # "%m/%d/%Y" #11/25/2024
        "%m/%d/%Y %I:%M:%S %p", # 11/29/2024 2:45:00 PM
        "%Y-%m-%d %H:%M:%SZ",
        "%d-%b-%Y %H:%M", #'02-Jan-2025 22:25',
        '%a, %d %b %Y %H:%M', # Tue, 09 Sep 2025 14:20,
        '%d-%b-%Y %H:%M' # "13-Nov-2025 20:25
    ]

    @classmethod
    def string_to_date_auto(cls, date_str):
        """
            字符串转Date自动匹配
        Args:
            date_str:

        Returns:

        """

        for fmt in cls.__POSSIBLE_DATE_FORMATS:  # 通过 cls 访问类变量
            try:
                result_date = datetime.strptime(date_str, fmt)
                return result_date
            except Exception:
                continue
        return None

    @classmethod
    def string_to_target_format(cls,date_str: str,target_format: str):
        input_date = cls.string_to_date_auto(date_str)
        return input_date.strftime(target_format)

    @classmethod
    def get_time_difference_points(cls, time1, time2):
        return int(round((time2 - time1).total_seconds() / 60))
