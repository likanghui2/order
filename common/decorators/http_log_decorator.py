"""
Module: _http_decorator
Author: Ciwei
Date: 2024-09-24

Description:
    HTTP日志实现
"""
import functools
import json
import time
import traceback
from typing import Optional



from common.global_variable import GlobalVariable
from common.model.response_info_model import ResponseInfoModel
from common.utils.log_util import LogUtil
from common.utils.log_redaction import redact_sensitive

lob_object = LogUtil("HttpLog")
def http_log_decorator():
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            start_time = time.time()
            log_data = {
                'url': kwargs['url'],
                'method': func.__name__,
                'headers': kwargs['headers'],
                'data': kwargs.get('data'),
            }

            if GlobalVariable.OUTPUT_HTTP_LOG:
                lob_object.info(json.dumps(redact_sensitive(log_data)), "HTTP请求开始")
            response: Optional[ResponseInfoModel] = None
            try:
                response = func(self, *args, **kwargs)
                log_data['responseText'] = response.to_text()
                log_data['responseStatus'] = response.status
                log_data['responseHeaders'] = response.headers
                log_data['time'] = time.time() - start_time
                if GlobalVariable.OUTPUT_HTTP_LOG:
                    lob_object.info(json.dumps(redact_sensitive(log_data)), "HTTP请求响应")
            except Exception:
                log_data["time"] = time.time() - start_time
                log_data["error"] = traceback.format_exc()
                lob_object.error(json.dumps(redact_sensitive(log_data)), "HTTP请求异常")
                raise

            return response

        return wrapper

    return decorator
