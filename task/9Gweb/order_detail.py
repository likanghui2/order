from common.decorators.task_decorator import task_decorator
from common.global_variable import GlobalVariable
from common.model.task.request_order_detail_task_model import RequestOrderDetailTaskModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.sunphuquocairways_9g.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()
LOG = log_util.LogUtil("sunPhuQuocAirwaysWebOrderDetail")


def _run_order_detail(service: WebService, request: RequestOrderDetailTaskModel):
    return service.order_detail(request.pnr, request.last_name, request.currency_code)


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, request: RequestOrderDetailTaskModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        service = WebService(proxy_info_from_ext(request.ext))
        service.initialize_session()
    else:
        service = script_cache["value"]

    response = _run_order_detail(service, request)
    if script_cache is None:
        CACHE.set_data(service, 480)
    else:
        CACHE.set_data(script_cache["value"], None, script_cache["timeOut"])
    return response


if __name__ == "__main__":
    print(main({
        "taskId": "9gweb-local-order-detail",
        "taskType": "orderDetail",
        "source": "9GWEB",
        "taskData": {
            "pnr": "ABC123",
            "lastName": "LOVELACE",
            "firstName": "ADA",
            "email": "ada@example.com",
            "currencyCode": "VND",
            "ext": {
                "proxy": {
                    "host": "proxy.example.com",
                    "port": 8080,
                    "username": "YOUR_USERNAME",
                    "password": "YOUR_PASSWORD",
                    "region": "vn",
                    "sessId": None,
                    "sessionTime": 10,
                    "format": "http://{username}:{password}@{host}:{port}",
                }
            },
        },
    }))
