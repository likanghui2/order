from common.decorators.task_decorator import task_decorator
from common.errors.service_error import ServiceError
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.malaysiaairlines_mh.service.web_service import WebService
from task.MHweb import session_cache
from task.MHweb.utils import web_date


CELERY_APP = celery_util.create(
    GlobalVariable.RABBITMQ_USERNAME,
    GlobalVariable.RABBITMQ_PASSWORD,
)
LOG = log_util.LogUtil("malaysiaAirlinesWebSearch")


def airport_data(search_data: RequestSearchTaskDataModel) -> list[tuple[str, str, str]]:
    result = [(
        search_data.dep_airport,
        search_data.arr_airport,
        web_date(search_data.dep_date),
    )]
    if search_data.ret_date:
        result.append((
            search_data.arr_airport,
            search_data.dep_airport,
            web_date(search_data.ret_date),
        ))
    return result


def run_search(service: WebService, search_data: RequestSearchTaskDataModel):
    routes = airport_data(search_data)
    promo_code = search_data.private_code[0] if search_data.private_code else ""
    if promo_code:
        service.prepare_search(
            routes,
            search_data.adult_number,
            search_data.child_number,
            promo_code,
        )
    if service.currency != search_data.currency_code:
        service.initialization(search_data.currency_code)
    return service.search(
        airport_data=routes,
        adult_count=search_data.adult_number,
        child_count=search_data.child_number,
        promo_code=promo_code,
    )


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    cached = session_cache.CACHE.get_data()
    service = cached["value"] if cached is not None else None
    if service is None:
        service = WebService(proxy_info_from_ext(search_data.ext))
        service.initialize_session()
        service.initialize_security()
    else:
        LOG.info(f"复用MH搜索会话，缓存过期时间[{cached['timeOut']}]")

    try:
        response = run_search(service, search_data)
    except ServiceError as error:
        if session_cache.can_reuse_service(error):
            session_cache.cache_service(service, cached)
        raise
    session_cache.cache_service(service, cached)
    return response


if __name__ == "__main__":
    for u in range(10):
        print(main({
        "taskId": "mhweb-local-search",
        "source": "MHWEB",
        "taskType": "search",
        "taskData": {
            "depAirport": "KUL",
            "arrAirport": "BKI",
            "depDate": "20260901",
            "retDate": "",
            "adultNumber": 1,
            "childNumber": 0,
            "currencyCode": "MYR",
            "freightRateType": "PT",
            "privateCode": [],
            "ext": {
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
                }
            }
        },
    }))
