# import json
#
# from common.decorators.task_decorator import task_decorator
# from common.errors.service_error import ServiceStateEnum
# from common.global_variable import GlobalVariable
# from common.model.task.request_order_detail_task_model import RequestOrderDetailTaskModel
# from common.utils import celery_util, log_util, machine_cache_util
# from flights.batik.service.web_service import WebService
#
# CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
# LOG = log_util.LogUtil('orderDetail')
# CACHE = machine_cache_util.MachineCache()
#
#
# @CELERY_APP.task(bind=True)
# @task_decorator(LOG)
# def main(self, request_order_detail: RequestOrderDetailTaskModel):
#     script_cache = CACHE.get_data()
#     if script_cache is None:
#         service = WebService(GlobalVariable.PROXY_INFO_DATA)
#         service.init_cloudflare()
#     else:
#         service = script_cache['value']
#     response_data = service.get_order_info(pnr=request_order_detail.pnr,
#                                            last_name=request_order_detail.last_name,
#                                            first_name=request_order_detail.first_name)
#     if script_cache is None:
#         CACHE.set_data(t, 600)
#     else:
#         CACHE.set_data(script_cache['value'], None, script_cache['timeOut'])
#     return response_data
#
#
# if __name__ == '__main__':
#     data = {
#         'lastName': 'KOAY',
#         'firstName': 'EWE GHEE',
#         'pnr': 'UHXKRA',
#         'email': '',
#     }
#
#     data = {
#         'lastName': 'TAN',
#         'firstName': 'CHUJUN',
#         'pnr': 'NQKIIE',
#         'email': '',
#     }
#
#     # data = {
#     #     'lastName':'LIU',
#     #     'firstName':'ZHI',
#     #     'pnr':'AYP8VQ',
#     #     'email':'304157565@qq.com',
#     # }
#
#     t = {
#         "taskId": "SSSS11111",
#         "source": "UOapp",
#         "taskType": "orderDetail",
#         "taskData": data
#     }
#
#     print(json.dumps(t, ensure_ascii=False))
#     main(t)
