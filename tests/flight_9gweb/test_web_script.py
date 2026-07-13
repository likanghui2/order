import base64
import json

import pytest

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.response_info_model import ResponseInfoModel
from flights.sunphuquocairways_9g.config import Config
from flights.sunphuquocairways_9g.script.web_script import WebScript


class FakeTls:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.initialized_with = None
        self.calls = []

    def initialize(self, proxy_info, **kwargs):
        self.initialized_with = (proxy_info, kwargs)

    def _request(self, method, **kwargs):
        self.calls.append({"method": method, **kwargs})
        return self.responses.pop(0)

    def post(self, **kwargs):
        return self._request("POST", **kwargs)

    def patch(self, **kwargs):
        return self._request("PATCH", **kwargs)

    def get(self, **kwargs):
        return self._request("GET", **kwargs)


class FakeCaptcha:
    def __init__(self):
        self.calls = []

    def incapsula_token_get(self, **kwargs):
        self.calls.append(kwargs)
        return "risk-token-1"


class FakeHcaptcha:
    def __init__(self):
        self.calls = []

    def hcaptcha(self, **kwargs):
        self.calls.append(kwargs)
        return {"data": {"token": "hcaptcha-token-1"}}


class FakeProxy:
    def get_proxy_info_to_string(self):
        return "http://proxy.example:4600"


def response(data, status=200):
    body = data if isinstance(data, str) else json.dumps(data)
    return ResponseInfoModel(
        data_bytes=body.encode(),
        status=status,
        headers={},
        url="https://api-des.sunphuquocairways.com/test",
    )


def authenticated_script(*responses):
    script = WebScript(None, tls=FakeTls(responses), captcha=FakeCaptcha(), hcaptcha=FakeHcaptcha())
    script.authorization = "Bearer token-1"
    script.country_code = "VN"
    script.currency = "VND"
    script.client_facts = script.build_client_facts("VN")
    script.x_d_token = "risk-token-1"
    return script


def test_authenticate_solves_incapsula_and_requests_oauth(monkeypatch):
    monkeypatch.setattr(Config, "WEB_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setattr(Config, "WEB_OAUTH_CLIENT_SECRET", "client-secret")
    tls = FakeTls([response({"access_token": "token-1"})])
    captcha = FakeCaptcha()
    script = WebScript(FakeProxy(), tls=tls, captcha=captcha, hcaptcha=FakeHcaptcha())

    script.initialize_session()
    result = script.authenticate("VND")

    assert tls.initialized_with[1] == {"impersonate": "chrome146"}
    assert len(captcha.calls) == 1
    assert captcha.calls[0]["verify_url"] == Config.INCAPSULA_URL
    assert captcha.calls[0]["proxy_data"] == "http://proxy.example:4600"
    assert script.authorization == "Bearer token-1"
    assert script.country_code == "VN"
    assert result["access_token"] == "token-1"
    oauth_data = tls.calls[0]["data"]
    assert "grant_type=client_credentials" in oauth_data
    assert "%22countryCode%22" in oauth_data


def test_client_facts_contains_selected_country():
    token = WebScript.build_client_facts("CN").split(".")[1]
    payload = json.loads(base64.urlsafe_b64decode(token + "=="))
    assert payload == {"sub": "fact", "countryCode": "CN"}


def test_search_builds_current_round_trip_payload_and_headers():
    script = authenticated_script(response({"data": {"airBoundGroups": []}}))

    result = script.search(
        [("SGN", "PQC", "2026-08-01T00:00:00"), ("PQC", "SGN", "2026-08-04T00:00:00")],
        2,
        1,
        "SAVE",
    )

    call = script.tls.calls[-1]
    payload = json.loads(call["data"])
    assert len(payload["itineraries"]) == 2
    assert [item["passengerTypeCode"] for item in payload["travelers"]] == ["ADT", "ADT", "CHD"]
    assert payload["promotion"] == {"code": "SAVE"}
    assert call["headers"]["authorization"] == "Bearer token-1"
    assert call["headers"]["ama-client-facts"] == script.client_facts
    assert result == {"data": {"airBoundGroups": []}}


def test_mutation_wrappers_send_one_request_each_with_exact_status_codes():
    script = authenticated_script(
        response({"data": {"id": "cart-1"}}, 201),
        response({"data": {}}, 200),
        response({"data": []}, 201),
        response({"data": [{"id": "ABC123"}]}, 201),
        response({"data": []}, 200),
        response({"data": {}}, 201),
    )

    assert script.create_cart(["bound-1"])["data"]["id"] == "cart-1"
    script.update_traveler("cart-1", "traveler-1", {"id": "traveler-1"}, "DOE")
    script.add_contacts("cart-1", [{"contactType": "Email"}], "DOE")
    script.purchase_order("cart-1")
    script.services_by_order("ABC123", "DOE")
    script.add_services("ABC123", "DOE", [{"serviceId": "bag-1"}])

    assert [call["method"] for call in script.tls.calls] == [
        "POST", "PATCH", "POST", "POST", "GET", "POST"
    ]
    assert json.loads(script.tls.calls[0]["data"]) == {"airBoundIds": ["bound-1"]}
    assert "cartId=cart-1" in script.tls.calls[3]["url"]
    assert len(script.tls.calls) == 6


def test_payment_and_order_detail_wrappers_use_current_contracts():
    script = authenticated_script(
        response({"data": {"availablePaymentMethods": []}}),
        response({"jwt": "jwt-1"}),
        response({"data": {}}, 201),
        response({"data": {}}),
        response({"data": {}}),
    )

    script.payment_methods("ABC123", "DOE")
    script.payment_action({"PPID": "pp-1", "action": "tdsinit"})
    script.payment_records("ABC123", "DOE", {"paymentRequests": []})
    script.get_itinerary("ABC123", "DOE")
    script.get_baggage("ABC123", "DOE")

    assert "payment-methods?lastName=DOE" in script.tls.calls[0]["url"]
    assert script.tls.calls[1]["url"].endswith("/1ASIATP/ARIAPP/pay")
    assert "payment-records?lastName=DOE" in script.tls.calls[2]["url"]
    assert script.tls.calls[3]["method"] == "GET"
    assert script.tls.calls[4]["method"] == "GET"


def test_challenge_and_invalid_json_map_to_current_errors():
    challenge = '<html><iframe src="/_Incapsula_Resource?incident_id=abc-123&cts=456"></iframe></html>'
    script = authenticated_script(response(challenge, 403), response("not-json", 200))

    with pytest.raises(ServiceError) as risk_error:
        script.create_cart(["bound-1"])
    assert risk_error.value.code == ServiceStateEnum.ROBOT_CHECK.name
    assert "dai=123" in script.incapsula_url

    with pytest.raises(ServiceError) as json_error:
        script.search([("SGN", "PQC", "2026-08-01T00:00:00")], 1, 0)
    assert json_error.value.code == ServiceStateEnum.DATA_VALIDATION_FAILED.name


def test_no_flight_and_http_error_map_to_current_errors():
    script = authenticated_script(
        response({"errors": [{"detail": "NO FLIGHTS FOUND"}]}, 400),
        response({"errors": [{"detail": "bad request"}]}, 400),
    )

    with pytest.raises(ServiceError) as no_flight:
        script.search([("SGN", "PQC", "2026-08-01T00:00:00")], 1, 0)
    assert no_flight.value.code == ServiceStateEnum.NO_FLIGHT_DATA.name

    with pytest.raises(ServiceError) as http_error:
        script.search([("SGN", "PQC", "2026-08-01T00:00:00")], 1, 0)
    assert http_error.value.code == ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY.name


def test_solve_hcaptcha_submits_token_once(monkeypatch):
    monkeypatch.setattr(Config, "WEB_HCAPTCHA_API_KEY", "captcha-key")
    hcaptcha = FakeHcaptcha()
    script = authenticated_script(response("<html>verified</html>", 200))
    script.hcaptcha = hcaptcha
    script.incapsula_url = (
        "https://api-des.sunphuquocairways.com/_Incapsula_Resource?SWCGHOEL=v2&dai=123&cts=456"
    )

    script.solve_hcaptcha()

    assert len(hcaptcha.calls) == 1
    assert "g-recaptcha-response=hcaptcha-token-1" in script.tls.calls[0]["data"]
