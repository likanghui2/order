from common.decorators.task_decorator import task_decorator
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.date_util import DateUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.lionairthai.service.web_service_v2 import WebServiceV2


CELERY_APP = celery_util.create(
    GlobalVariable.RABBITMQ_USERNAME,
    GlobalVariable.RABBITMQ_PASSWORD,
)
LOG = log_util.LogUtil("lionairthaiWebSearch")
CACHE = machine_cache_util.MachineCache()


def _web_date(value: str) -> str:
    return DateUtil.string_to_target_format(value, "%Y-%m-%d")


def _run_search(service: WebServiceV2, search_data: RequestSearchTaskDataModel):
    return service.search(
        dep_airport=search_data.dep_airport,
        arr_airport=search_data.arr_airport,
        date=_web_date(search_data.dep_date),
        adt_number=search_data.adult_number,
        chd_number=search_data.child_number,
        currency_code=search_data.currency_code,
        promo_code=search_data.private_code[0] if search_data.private_code else "",
        ret_date=_web_date(search_data.ret_date) if search_data.ret_date else None,
    )


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    script_cache = CACHE.get_data()
    service = (
        WebServiceV2(proxy_info_from_ext(search_data.ext))
        if script_cache is None
        else script_cache["value"]
    )
    response = _run_search(service, search_data)
    if script_cache is None:
        CACHE.set_data(service, 250)
    else:
        CACHE.set_data(service, None, script_cache["timeOut"])
    return response


if __name__ == "__main__":
    print(main({
        "taskId": "slweb-local-search",
        "source": "SLWEB",
        "taskType": "search",
        "taskData": {
            "depAirport": "DMK",
            "arrAirport": "UBP",
            "depDate": "20261203",
            "retDate": "",
            "adultNumber": 1,
            "childNumber": 0,
            "currencyCode": "THB",
            "freightRateType": "PT",
            "privateCode": [],
            "ext": {"passengerCount": 5,
                "proxy": {
                    "source": "VJWEB",
                    "host": "proxy.iproyal.net",
                    "port": 9000,
                    "username": "rakdvjweb01",
                    "password": "rakdvjvj01",
                    "region": "sg",
                    "sessId": None,
                    "sessionTime": 10,
                    "format": "http://client-{username}_area-{region}_session-{sessId}_life-{sessionTime}:{password}@{host}:{port}"

            }},
        },
    }))
