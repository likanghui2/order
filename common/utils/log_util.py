"""
Module: log_util
Author: Ciwei
Date: 2024-09-13

Description: 
    This module provides functionalities for ...
"""
import json
import logging
import threading
from typing import Optional

from common.utils.log_redaction import redact_sensitive

LOCAL_DATA = threading.local()


class JsonFormatter(logging.Formatter):

    def format(self, record):
        """
        日志自定义格式
        :param record:
        :return:
        """
        log_record = {
            '@timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z'),
            'level': record.levelname,
            'message': record.getMessage()
        }

        if 'options' in LOCAL_DATA.__dict__:
            for key, value in LOCAL_DATA.options['options'].items():
                log_record[key] = value

        extra_info = record.__dict__
        if extra_info is not None and 'options' in extra_info:
            for key, value in extra_info['options'].items():
                log_record[key] = value

        if 'logName' in extra_info:
            log_record['logName'] = extra_info['logName']

        log_record['type'] = record.name
        return json.dumps(log_record, ensure_ascii=False)


class LogUtil:

    def __init__(self, name: str):
        self._log = self._create_log(name=name)

    def info(self, message: str, name: str = "", extra=None):
        if extra is None:
            extra = {}
        extra['logName'] = name
        try:
            self._log.info(msg=redact_sensitive(message), extra=extra)
        except Exception:
            self._log.info(msg=redact_sensitive(message), extra=extra)

    def error(self, message: str, name: str = "", extra=None):
        if extra is None:
            extra = {}
        extra['logName'] = name
        self._log.error(msg=redact_sensitive(message), extra=extra)

    def warning(self, message: str, name: str = "", extra=None):
        if extra is None:
            extra = {}
        extra['logName'] = name
        self._log.warning(msg=redact_sensitive(message), extra=extra)

    def add_log_name(self, log_name: Optional[str]):
        extra = {}
        if log_name is not None:
            extra['logName'] = log_name

        return extra

    def _create_log(self, name: str, level: int = logging.INFO):
        logger = logging.getLogger(name=name)
        if not logger.handlers:  # 如果没有处理器，则添加一个新的
            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter())
            logger.setLevel(level)
            logger.addHandler(handler)
        logger.propagate = False
        return logger

    def set_options(self, options):
        LOCAL_DATA.options = options
