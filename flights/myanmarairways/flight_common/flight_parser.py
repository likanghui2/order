import json
import re
from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel


def _text(node, selector: str) -> str:
    found = node.select_one(selector)
    return found.get_text(" ", strip=True) if found else ""


def _flight_number(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _parse_time(block, side: str) -> datetime:
    info = block.select_one(f".desktop-route-block .info-block{'.text-right' if side == 'right' else ''}")
    if info is None:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "flight time")
    date_text = _text(info, ".date")
    time_text = _text(info, ".time")
    return datetime.strptime(f"{date_text} {time_text}", "%d/%m/%Y %H:%M")


def parse_availability(
    html: str,
    dep_airport: str,
    arr_airport: str,
    currency: str,
    requested_seats: int,
) -> list[FlightJourneyModel]:
    if "Just a moment" in html or "_cf_chl_opt" in html:
        raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)

    soup = BeautifulSoup(html, "html.parser")
    cid_node = soup.select_one("body[data-cid]")
    sid_node = soup.select_one("body[data-sid]")
    cid = cid_node.get("data-cid", "") if cid_node else ""
    sid = sid_node.get("data-sid", "") if sid_node else ""
    if not cid or not sid:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cid/sid")
    journeys = []
    for journey_index, block in enumerate(soup.select(".js-scheduled-flights-container > .js-journey")):
        flight_number = _flight_number(_text(block, ".desktop-route-block .flight-no"))
        if not flight_number:
            continue
        dep_time = _parse_time(block, "left")
        arr_time = _parse_time(block, "right")
        avail_index = journey_index
        fare_root = soup.select_one(f"#branded-fare-accordion-{avail_index}-0-0")
        fare_nodes = fare_root.select("[data-fare-id]") if fare_root else []
        if not fare_nodes:
            fare_nodes = []
            accordion_prefix = f"branded-fare-accordion-{journey_index}-"
            for accordion in soup.select('[id^="branded-fare-accordion-"]'):
                if str(accordion.get("id", "")).startswith(accordion_prefix):
                    fare_nodes.extend(accordion.select("[data-fare-id]"))
        if not fare_nodes:
            fare_nodes = soup.select(f'[data-journey-index="{journey_index}"][data-fare-id]')
        if not fare_nodes:
            fare_nodes = block.select("[data-fare-id]")
        bundles = []
        for button in fare_nodes:
            fare = button.find_parent(class_="branded-fare-type-column") or button.parent
            fare_avail_index = int(button.get("data-avail-index") or 0)
            title = _text(fare, ".flight-table__flight-type-column-title") or "ECONOMY"
            price_match = re.search(r"([0-9][0-9,]*\.?[0-9]*)", button.get_text(" ", strip=True))
            if not price_match:
                continue
            basket_total = Decimal(price_match.group(1).replace(",", ""))
            total = basket_total
            fare_id = button.get("data-fare-id", "")
            seat_match = re.search(r"\b(\d+)\b", _text(fare, ".branded-fare-last-seat-align"))
            seat = int(seat_match.group(1)) if seat_match else 3
            bundles.append(FlightBundleModel(
                priceInfo=FlightBundlePriceModel(
                    adultTicketPrice=total,
                    adultTaxPrice=Decimal("0"),
                    childTicketPrice=total,
                    childTaxPrice=Decimal("0"),
                    currency=currency,
                ),
                ssrInfo=FlightSsrInfoModel(),
                code=title,
                cabinLevel="Y",
                cabin="Y",
                fareKey=fare_id,
                productTag=title,
                seat=seat,
                freightRateType=FreightRateTypeEnum.PT,
                ext={
                    "availIndex": fare_avail_index,
                    "journeyIndex": 0,
                    "fareReferenceId": fare_id,
                    "cid": cid,
                    "sid": sid,
                },
            ))
        segment = FlightSegmentModel(
            segmentKey=f"{flight_number}-{dep_time:%Y%m%d%H%M}",
            depAirport=dep_airport,
            arrAirport=arr_airport,
            depTime=dep_time,
            arrTime=arr_time,
            flightNumber=flight_number,
            carrier="8M",
            operatingCarrier="8M",
            operatingFlightNumber=flight_number,
            legIndex=1,
            routeIndex=1,
        )
        journeys.append(FlightJourneyModel(
            segments=[segment],
            bundles=bundles,
            journeyKey=f"0:{journey_index}",
            depAirport=dep_airport,
            arrAirport=arr_airport,
            depTime=dep_time,
            arrTime=arr_time,
            ext={"availIndex": avail_index, "journeyIndex": 0, "cid": cid, "sid": sid},
        ))
    return journeys


def parse_booking_id(html: str) -> str:
    match = re.search(r"window\.gtmData\s*=\s*(\{.*?\});", html, re.DOTALL)
    if match:
        try:
            value = json.loads(match.group(1))["ecommerce"]["add"]["actionField"]["id"]
            if value:
                return str(value)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    fallback = re.search(r'"actionField"\s*:\s*\{[^{}]*"id"\s*:\s*"([A-Za-z0-9]+)"', html)
    if fallback:
        return fallback.group(1)
    raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "booking id")
