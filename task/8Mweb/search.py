from common.decorators.task_decorator import task_decorator
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.myanmarairways.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("myanmarAirwaysWebSearch")
CACHE = machine_cache_util.MachineCache()


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        LOG.info("重新初始化对象")
        service = WebService(None)
        service.initialize_session()
    else:
        LOG.info("使用缓存对象")
        service = script_cache['value']
        service.initialize_session()

    response = service.search(
        search_data.dep_airport, search_data.arr_airport, search_data.dep_date,
        search_data.adult_number, search_data.child_number, search_data.currency_code,
        "BUSINESS" if search_data.cabin_level == "C" else "ECONOMY",
    )
    if script_cache is None:
        CACHE.set_data(service, 300)
    else:
        CACHE.set_data(script_cache['value'], None, script_cache['timeOut'])
    return response


if __name__ == "__main__":
    for i in range(10):
        print(main({
            "taskId": "8mweb-local-search",
            "taskType": "search",
            "source": "8MWEB",
            "taskData": {
                "depAirport": "RGN",
                "arrAirport": "CAN",
                "depDate": "20260811",
                "retDate": "",
                "adultNumber": 1,
                "childNumber": 0,
                "currencyCode": "USD",
                "freightRateType": "PT",
                "privateCode": [],
                "ext": {
                    "proxy": {
                        "source": "8MWEB",
                        "host": "proxy.iproyal.net",
                        "port": 9000,
                        "username": "rakdvjweb01",
                        "password": "rakdvjvj01",
                        "region": "sg",
                        "sessId": None,
                        "sessionTime": 10,
                        "format": (
                            "http://client-{username}_area-{region}_session-{sessId}_life-"
                            "{sessionTime}:{password}@{host}:{port}"
                        ),
                    },
                },
            },
        }))
