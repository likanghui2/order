"""
@Project     : zhongyi_flight
@Author      : ciwei
@Date        : 2024/7/3 13:50
@Description :
@versions    : 1.0.0.0
"""
import threading
import time
from typing import Optional

from common.utils.log_util import LogUtil


class MachineCache:

    def __init__(self):
        self.__data = []
        self.__locker = threading.Lock()
        self.__log = LogUtil("machineCache")

    def set_data(self, value: any, timeout_seconds: Optional[int] = None, timeout_time: Optional[int] = None):

        t = None
        if timeout_time:
            if int(time.time() < timeout_time):
                t = timeout_time
            else:
                return
        if t is None:
            t = int(time.time()) + timeout_seconds

        with self.__locker:
            self.__data.append({
                'value': value,
                'timeOut': t
            })

    def get_data(self):
        with self.__locker:
            result_data = None
            t = int(time.time())
            remove_list = []
            self.__log.info(f"当前缓存数量：{len(self.__data)}")
            for index, value in enumerate(self.__data):
                if t > value['timeOut']:
                    remove_list.append(index)

            for index in reversed(remove_list):
                self.__data.pop(index)

            if len(self.__data) == 0:
                return None

            result_data = self.__data.pop(0)
            return result_data
