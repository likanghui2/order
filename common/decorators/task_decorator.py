import copy
import functools
import time
import traceback
import uuid
from typing import Any, Optional

from curl_cffi import requests

from common.decorators.retry_decorator import retry_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.enums.task_type_enum import TaskTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.task.request_booking_task_data_model import RequestBookingTaskDataModel
from common.model.task.request_cancel_order_task_model import RequestCancelOrderTaskModel
from common.model.task.request_order_detail_task_model import RequestOrderDetailTaskModel
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.request_task_info_model import RequestTaskInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.model.task.response_search_info_model import ResponseSearchInfoModel
from common.model.task.response_task_info_model import ResponseTaskInfoModel
from common.utils.flight_util import FlightUtil
from common.utils.log_redaction import redact_sensitive

SUCCESS = 0


def task_decorator(log):
    def decorator(func):

        def bundle_passenger_number(response_data, number):
            for i in response_data:
                for j in i.bundles:
                    if j.seat == -1:
                        j.seat = number

        @retry_decorator([(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, None)])
        def task_search(self, func, task_data: RequestSearchTaskDataModel) -> ResponseSearchInfoModel:
            response_data = func(self, task_data)
            FlightUtil.flight_data_check(response_data)
            if not response_data or len(response_data) == 0:
                raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
            if len(response_data) == 0:
                raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
            #bundle_passenger_number(response_data, task_data.adult_number + task_data.child_number)
            return ResponseSearchInfoModel(
                journeys=response_data,
            )

        def task_verify(self, func, task_data: RequestSearchTaskDataModel) -> ResponseSearchInfoModel:
            response_data = func(self, task_data)

            if task_data.flight_number:
                response_data = FlightUtil.number_filter(journeys=response_data, flight_number=task_data.flight_number)
                FlightUtil.flight_data_check(response_data)

            if not response_data or len(response_data) == 0:
                raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)

            #bundle_passenger_number(response_data, task_data.adult_number + task_data.child_number)
            return ResponseSearchInfoModel(
                journeys=response_data,
            )

        def task_booking(self, func, task_data: RequestBookingTaskDataModel,
                         response_order_data: ResponseOrderInfoModel) -> None:
            func(self, task_data, response_order_data)

        def task_sham_booking(self, func, task_data: RequestShamBookingTaskDataModel,
                              response_order_data: ResponseOrderInfoModel) -> None:
            func(self, task_data, response_order_data)

        def task_order_detail(self, func, task_data: RequestOrderDetailTaskModel) -> ResponseOrderInfoModel:
            return func(self, task_data)
        def task_cancel(self, func, task_data: RequestCancelOrderTaskModel) -> ResponseOrderInfoModel:
            return func(self, task_data)
        def build_success_response(message: str, data: Any) -> ResponseTaskInfoModel:
            response_search_data = ResponseTaskInfoModel(
                status=200,
                message=message,
                data=data,
                taskId='',
                source=''
            )

            return response_search_data

        def build_failure_response(message: str, data: Optional[Any] = None) -> ResponseTaskInfoModel:
            response_data = ResponseTaskInfoModel(
                status=0,
                message=message,
                taskId='',
                source=''
            )

            if data is not None:
                response_data.data = data

            return response_data

        def task_call(data: str, call_url: str) -> None:
            log.info(data, '回调数据')
            headers = {'Content-Type': 'application/json'}
            response = requests.post(call_url, data=data, headers=headers)
            log.info(response.text, '回调结果')

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            request_task_info = None
            response_data = None
            response_order_data = None
            callback_data = None
            start_time = time.perf_counter()
            try:
                __data = copy.deepcopy(args[0])
                request_task_info = RequestTaskInfoModel.model_validate(__data)

                if request_task_info.task_type == TaskTypeEnum.SHAM_BOOKING.value:
                    extra_option = {
                        'options': {
                            'taskId': request_task_info.task_id + "@" + str(uuid.uuid4()),
                        }
                    }
                else:
                    extra_option = {
                        'options': {
                            'taskId': request_task_info.task_id,
                        }
                    }

                log.set_options(extra_option)
                log.info(redact_sensitive(__data), '任务参数')

                if __data['taskData'].get('callbackData') is None:
                    callback_data = {}
                else:
                    callback_data = request_task_info.task_data['callbackData']

                task_type = request_task_info.task_type
                if task_type == TaskTypeEnum.SEARCH.value:
                    self.backend.expires = 60
                    task_data = RequestSearchTaskDataModel.model_validate(request_task_info.task_data)
                    result_data = task_search(self, func, task_data)
                    response_data = build_success_response('查询成功', result_data)
                elif task_type == TaskTypeEnum.VERIFY.value:
                    task_data = RequestSearchTaskDataModel.model_validate(request_task_info.task_data)
                    result_data = task_verify(self, func, task_data)
                    response_data = build_success_response('验价成功', result_data)
                elif task_type == TaskTypeEnum.BOOKING.value or task_type == TaskTypeEnum.SHAM_BOOKING.value:
                    self.backend.expires = 60 * 5
                    response_order_data = ResponseOrderInfoModel()
                    task_data = RequestShamBookingTaskDataModel.model_validate(
                        request_task_info.task_data) if task_type == TaskTypeEnum.SHAM_BOOKING.value else RequestBookingTaskDataModel.model_validate(
                        request_task_info.task_data)
                    try:
                        if task_type == TaskTypeEnum.SHAM_BOOKING.value:
                            task_sham_booking(self, func, task_data, response_order_data)
                        else:
                            task_booking(self, func, task_data, response_order_data)

                        response_data = build_success_response('请求成功', response_order_data)
                    except ServiceError as e:
                        log.error(traceback.format_exc())
                        response_order_data.order_state = OrderStateEnum.ABNORMAL
                        response_data = build_failure_response(e.message, response_order_data)
                    except Exception as e:
                        log.error(traceback.format_exc())
                        response_order_data.order_state = OrderStateEnum.ABNORMAL
                        response_data = build_failure_response('生单异常', response_order_data)

                elif task_type == TaskTypeEnum.ORDER_DETAIL.value:
                    self.backend.expires = 60
                    task_data = RequestOrderDetailTaskModel.model_validate(request_task_info.task_data)
                    result_data = task_order_detail(self, func, task_data)
                    response_data = build_success_response('查询成功', result_data)
                elif task_type == TaskTypeEnum.CANCEL.value:
                    self.backend.expires = 60
                    task_data = RequestCancelOrderTaskModel.model_validate(request_task_info.task_data)
                    result_data = task_cancel(self, func, task_data)
                    response_data = build_success_response('取消成功', result_data)
                else:
                    response_data = build_failure_response(message='无效任务')

            except ServiceError as e:
                log.error(traceback.format_exc())
                response_data = build_failure_response(e.message)
            except Exception as e:
                log.error(traceback.format_exc())
                response_data = build_failure_response(message='系统异常')

            try:
                log.info(f'任务耗时：{time.perf_counter() - start_time}')
                response_data.task_id = request_task_info.task_id
                response_data.source = request_task_info.source
                response_data = response_data.model_dump_json(by_alias=True)
                log.info(response_data, '任务结果')
            except Exception as e:
                log.error(traceback.format_exc())
                response_data = build_failure_response(message='系统异常')

            return response_data

        return wrapper

    return decorator
