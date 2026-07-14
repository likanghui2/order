import copy
import json
from datetime import datetime
from typing import List, Optional

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.sham_booking_util import ShamBookingUtil
from flights.thaiairways_tg.service.web_service import WebService as NewWebService
from flights.thaiairways_tg.service.web_service_bak import WebService as WwwWebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil('TGShamBooking')
MAX_NUM = 9
MAX_PRESS_ROUND = 5


def _normalize_flight_number(flight_number: str) -> str:
    if not flight_number or len(flight_number) <= 2:
        return flight_number
    return flight_number[:2] + flight_number[2:].lstrip('0')


def _number_filter(journeys: List[FlightJourneyModel], flight_number: str) -> List[FlightJourneyModel]:
    target = _normalize_flight_number(flight_number)
    return [
        journey for journey in journeys
        if ",".join([_normalize_flight_number(segment.flight_number) for segment in journey.segments]) == target
    ]


def _select_bundle(journey: FlightJourneyModel,
                   cabin: Optional[str],
                   product_tag: str = '') -> FlightBundleModel:
    if not journey.bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    bundles = journey.bundles
    if cabin:
        bundles = [
            bundle for bundle in bundles
            if bundle.cabin == cabin or cabin in (bundle.cabin or '').replace('^', '|').split('|')
        ]
        if not bundles:
            current_cabin = '|'.join([bundle.cabin or '' for bundle in journey.bundles])
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, cabin, current_cabin)

    if product_tag:
        bundles = [bundle for bundle in bundles if bundle.product_tag == product_tag or bundle.code == product_tag]
        if not bundles:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    return bundles[0]


def _search_target_journey(service,
                           sham_booking_data: RequestShamBookingTaskDataModel,
                           seat_count: int,
                           cabin_level: str,
                           promo_code: str) -> FlightJourneyModel:
    journey_list = service.search(
        dep_airport=sham_booking_data.dep_airport,
        arr_airport=sham_booking_data.arr_airport,
        dep_date=datetime.strptime(sham_booking_data.dep_date, "%Y%m%d").strftime("%Y-%m-%d"),
        adt_number=seat_count,
        chd_number=0,
        currency_code=sham_booking_data.booking_config.currency_code,
        cabin_level=cabin_level,
        promo_code=promo_code,
    )
    journey_list = _number_filter(journey_list, sham_booking_data.flight_number)
    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)
    return journey_list[0]


def _sham_booking_by_site(self,
                          sham_booking_data: RequestShamBookingTaskDataModel,
                          response_order_data: ResponseOrderInfoModel,
                          target_cabin: str,
                          site_name: str,
                          service_class):
    ext = sham_booking_data.ext or {}
    cabin_level = ext.get('cabinLevel') or 'Y'
    private_code = ext.get('privateCode') or []
    if isinstance(private_code, str):
        private_code = [private_code] if private_code else []
    promo_code = private_code[0] if private_code else ''
    product_tag = ext.get('productTag') or ''

    LOG.info(f"TG押位使用站点[{site_name}]", "押位流程")
    service = service_class(proxy_info_from_ext(ext))
    service.initialize_session()

    journey = _search_target_journey(
        service=service,
        sham_booking_data=sham_booking_data,
        seat_count=1,
        cabin_level=cabin_level,
        promo_code=promo_code,
    )
    use_bundle = _select_bundle(journey, target_cabin, product_tag)
    if use_bundle.seat <= 0:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, target_cabin, use_bundle.cabin)

    target_cabin = use_bundle.cabin
    remaining = use_bundle.seat
    pnr_list = []
    all_passengers: List[PassengerInfoModel] = []
    last_journey = journey
    last_bundle = use_bundle
    last_contact_info = None
    total_amount = response_order_data.total_amount

    press_round = 0
    while remaining > 0 and press_round < MAX_PRESS_ROUND:
        seat_count = min(remaining, MAX_NUM)
        LOG.info(f"TG站点[{site_name}]本轮押位人数[{seat_count}]，目标舱位[{target_cabin}]，剩余[{remaining}]", "押位流程")

        try:
            round_journey = _search_target_journey(
                service=service,
                sham_booking_data=sham_booking_data,
                seat_count=seat_count,
                cabin_level=cabin_level,
                promo_code=promo_code,
            )
            round_bundle = _select_bundle(round_journey, target_cabin, product_tag)
            if round_bundle.seat <= 0:
                break

            passengers = ShamBookingUtil.build_sham_passenger_info(seat_count, False)
            contact_info = ShamBookingUtil.build_sham_contact_info()
            contact_info.last_name = passengers[0].last_name
            contact_info.first_name = passengers[0].first_name

            round_order = copy.deepcopy(response_order_data)
            service.booking(
                journey=round_journey,
                bundle=round_bundle,
                passengers=passengers,
                contact_info=contact_info,
                response_order_data=round_order,
            )

            if not round_order.pnr:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, 'TG押位未返回PNR')

            pnr_list.append(round_order.pnr)
            all_passengers.extend(passengers)
            total_amount += round_order.total_amount
            last_journey = round_journey
            last_bundle = round_bundle
            last_contact_info = contact_info
            remaining -= seat_count
            press_round += 1
            LOG.info(f"TG站点[{site_name}]押位成功PNR[{round_order.pnr}]，累计人数[{len(all_passengers)}]", "押位流程")
        except ServiceError as e:
            if pnr_list and e.code in [
                ServiceStateEnum.NO_AVAILABLE_CABIN.name,
                ServiceStateEnum.NO_AVAILABLE_BUNDLE.name,
                ServiceStateEnum.NO_FLIGHT_DATA.name,
                ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER.name,
            ]:
                LOG.info(f"TG站点[{site_name}]后续押位无库存，返回已押位PNR，错误[{e.message}]", "押位流程")
                break
            if pnr_list:
                LOG.error(f"TG站点[{site_name}]后续押位失败，返回已押位PNR，错误[{e.message}]", "押位流程")
                break
            raise
        except Exception as e:
            if pnr_list:
                LOG.error(f"TG站点[{site_name}]后续押位异常，返回已押位PNR，错误[{e}]", "押位流程")
                break
            raise

    if not pnr_list:
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"TG站点[{site_name}]占座失败，未生成任何PNR")

    response_order_data.pnr = "|".join(pnr_list)
    response_order_data.order_number = response_order_data.pnr
    response_order_data.passengers = all_passengers
    response_order_data.currency_code = last_bundle.price_info.currency
    response_order_data.total_amount = total_amount
    response_order_data.journeys = [last_journey]
    response_order_data.journeys[0].bundles = [last_bundle]
    response_order_data.contact_info = last_contact_info
    response_order_data.order_state = OrderStateEnum.HOLD
    return response_order_data


def _sham_booking(self,
                  sham_booking_data: RequestShamBookingTaskDataModel,
                  response_order_data: ResponseOrderInfoModel):
    raw_cabin = sham_booking_data.cabin or ""
    target_cabin = raw_cabin.replace("00", "")
    try:
        return _sham_booking_by_site(
            self=self,
            sham_booking_data=sham_booking_data,
            response_order_data=response_order_data,
            target_cabin=target_cabin,
            site_name='WWW',
            service_class=WwwWebService,
        )
    except ServiceError as e:
        if e.code not in [
            ServiceStateEnum.NO_FLIGHT_DATA.name,
            ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER.name,
        ]:
            raise
        LOG.info(f"TG老站无航班数据，切换新站，错误[{e.message}]", "押位流程")

    return _sham_booking_by_site(
        self=self,
        sham_booking_data=sham_booking_data,
        response_order_data=response_order_data,
        target_cabin=target_cabin,
        site_name='NEW',
        service_class=NewWebService,

    )


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, sham_booking_data: RequestShamBookingTaskDataModel, response_order_data: ResponseOrderInfoModel):
    return _sham_booking(self, sham_booking_data, response_order_data)


if __name__ == '__main__':
    for i in range(100000000000):
        task_data = {
            "taskId": "dfb4e68082e046ada18392970b862153",
            "taskType": "shamBooking",
            "source": "TGWEB",
            "taskData": {
                "depAirport": "PEK",
                "arrAirport": "BKK",
                "depDate": "20260728",
                "flightNumber": "TG615",
                "cabin": "00",
                "bookingConfig": {
                    "bookRate": 5,
                    "currencyCode": "CNY"
                },
                "callbackData": {
                    "callData": "",
                    "callUrl": "http://trip-api.bjrakd.com/triplex-foreign-external/external/task/pressureback/seatNewCallback"
                },
                'ext':{
                    "usePassport": True,
                    "pnrValidMinutes": 30,
                    "passengerCount": 1,
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
            }
        }
        print(json.dumps(task_data))
        main(task_data)
