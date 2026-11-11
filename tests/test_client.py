"""Tests for the Personal API data client."""

# Copyright 2026 Garmin Ltd. or its subsidiaries.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from garmin_personal_api import (
    DEFAULT_BASE_URL,
    GarminPersonalApiClient,
    GarminPersonalApiError,
    HttpError,
)
from garmin_personal_api.constants import BASE_URL_ENV_VAR

from .helpers import StubSession, make_response

START = "2026-08-20"
END = "2026-08-24"
RANGE = {"startDate": START, "endDate": END}


def test_download_returns_bytes_and_keeps_json_headers() -> None:
    response = make_response(None)
    response._content = b"PK\x03\x04binary\xff"
    session = StubSession(response)
    client = GarminPersonalApiClient("token", session=session, timeout=12)
    assert client.download_activity(123) == response.content
    _, url, kwargs = session.calls[0]
    assert url == f"{DEFAULT_BASE_URL}/download-service/files/activity/123"
    assert kwargs["headers"]["Accept"] == (
        "application/zip, application/x-zip-compressed, application/octet-stream"
    )
    assert kwargs["headers"]["Authorization"] == "Bearer token"
    assert kwargs["timeout"] == 12
    response._content = b'{"ok": true}'
    assert client.get("/example") == {"ok": True}
    assert session.calls[1][2]["headers"]["Accept"] == "application/json"


@pytest.mark.parametrize("activity_id", ["../file", "0", "-1", "abc", "１２３"])
def test_download_rejects_invalid_id(activity_id: str) -> None:
    with pytest.raises(GarminPersonalApiError, match="positive integer"):
        GarminPersonalApiClient("token", session=StubSession()).download_activity(activity_id)


@pytest.mark.parametrize("status", [401, 404, 429, 500])
def test_download_preserves_http_errors(status: int) -> None:
    session = StubSession(make_response({"error": "unavailable"}, status_code=status))
    with pytest.raises(HttpError) as raised:
        GarminPersonalApiClient("token", session=session).download_activity("123")
    assert raised.value.status_code == status


def test_download_rejects_empty_response() -> None:
    session = StubSession(make_response(None, raw_text=""))
    with pytest.raises(GarminPersonalApiError, match="empty"):
        GarminPersonalApiClient("token", session=session).download_activity(123)


EndpointCall = Callable[[GarminPersonalApiClient], Any]


@pytest.mark.parametrize(
    ("call", "path", "params"),
    [
        pytest.param(
            lambda c: c.get_daily_stress(date(2026, 8, 20), END),
            f"/usersummary-service/stats/stress/daily/{START}/{END}",
            None,
            id="stress",
        ),
        pytest.param(
            lambda c: c.get_daily_steps(START, date(2026, 8, 24)),
            f"/usersummary-service/stats/steps/daily/{START}/{END}",
            None,
            id="steps",
        ),
        pytest.param(
            lambda c: c.get_daily_hydration(START, END),
            f"/usersummary-service/stats/hydration/daily/{START}/{END}",
            None,
            id="hydration",
        ),
        pytest.param(
            lambda c: c.get_effective_weight_goals(START, END),
            f"/goal-service/goal/user/effective/weightgoal/{START}/{END}",
            None,
            id="effective-weight-goals",
        ),
        pytest.param(
            lambda c: c.get_weight_measurements(START, END),
            f"/weight-service/weight/range/{START}/{END}",
            {"includeAll": "true"},
            id="weight-measurements",
        ),
        pytest.param(
            lambda c: c.get_daily_food_logs(END),
            f"/nutrition-service/food/logs/{END}",
            None,
            id="food-logs",
        ),
        pytest.param(
            lambda c: c.get_user_profile_settings(),
            "/userprofile-service/userprofile/settings",
            None,
            id="profile-settings",
        ),
        pytest.param(
            lambda c: c.get_daily_sleep(END),
            "/sleep-service/sleep/dailySleep",
            {"date": END},
            id="sleep",
        ),
        pytest.param(
            lambda c: c.get_daily_sleep_summaries(START, END),
            "/sleep-service/sleep/dailySleepSummariesByDate",
            RANGE,
            id="sleep-summaries",
        ),
        pytest.param(
            lambda c: c.get_daily_body_battery(START, END),
            "/wellness-service/wellness/bodyBattery/reports/daily",
            RANGE,
            id="body-battery",
        ),
        pytest.param(
            lambda c: c.get_daily_body_battery(START, END, chunks=2),
            "/wellness-service/wellness/bodyBattery/reports/daily",
            {**RANGE, "chunks": 2},
            id="body-battery-chunks",
        ),
        pytest.param(
            lambda c: c.get_daily_summaries(START, END),
            "/usersummary-service/v2/dailysummaries",
            RANGE,
            id="daily-summaries",
        ),
        pytest.param(
            lambda c: c.get_daily_heart_rate(END),
            "/wellness-service/wellness/dailyHeartRate",
            {"date": END},
            id="heart-rate",
        ),
        pytest.param(
            lambda c: c.get_daily_hrv(END),
            f"/hrv-service/hrv/{END}",
            None,
            id="hrv",
        ),
        pytest.param(
            lambda c: c.get_daily_hrv_summaries(START, END),
            f"/hrv-service/hrv/daily/{START}/{END}",
            None,
            id="hrv-summaries",
        ),
        pytest.param(
            lambda c: c.get_heart_rate_zones(),
            "/biometric-service/heartRateZones/v2",
            None,
            id="heart-rate-zones",
        ),
        pytest.param(
            lambda c: c.get_menstrual_cycle_summary(END),
            f"/periodichealth-service/menstrualcycle/summary/{END}",
            None,
            id="menstrual-cycle-summary",
        ),
        pytest.param(
            lambda c: c.get_menstrual_cycle_day_view(START, END),
            f"/periodichealth-service/menstrualcycle/dayview/{START}",
            {"todayDate": END},
            id="menstrual-cycle-day-view",
        ),
        pytest.param(
            lambda c: c.get_fitness_age(END),
            f"/fitnessage-service/fitnessage/v2/{END}",
            None,
            id="fitness-age",
        ),
        pytest.param(
            lambda c: c.get_daily_spo2(END),
            f"/wellness-service/wellness/daily/spo2acclimation/{END}",
            None,
            id="spo2",
        ),
        pytest.param(
            lambda c: c.get_wellness_activity_summaries(START, END),
            f"/wellnessactivity-service/activity/summary/range/{START}/{END}",
            None,
            id="wellness-activity-summaries",
        ),
        pytest.param(
            lambda c: c.get_activity_types(),
            "/activity-service/activity/activityTypes/simple",
            None,
            id="activity-types",
        ),
        pytest.param(
            lambda c: c.search_activities(),
            "/activitylist-service/activities/search/activities",
            {"start": 0, "limit": 20},
            id="activities-defaults",
        ),
        pytest.param(
            lambda c: c.search_activities(
                start=5,
                limit=10,
                start_date=START,
                end_date=date(2026, 8, 24),
                activity_type="running",
            ),
            "/activitylist-service/activities/search/activities",
            {"start": 5, "limit": 10, **RANGE, "activityType": "running"},
            id="activities-filters",
        ),
        pytest.param(
            lambda c: c.get_activity(123456789),
            "/activity-service/activity/123456789",
            None,
            id="activity",
        ),
        pytest.param(
            lambda c: c.get_activity_workouts("123456789"),
            "/activity-service/activity/123456789/workouts",
            None,
            id="activity-workouts",
        ),
    ],
)
def test_endpoint_wrappers_send_the_expected_request(
    call: EndpointCall,
    path: str,
    params: dict[str, object] | None,
) -> None:
    session = StubSession(make_response({"ok": True}))

    assert call(GarminPersonalApiClient("token", session=session)) == {"ok": True}
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == f"{DEFAULT_BASE_URL}{path}"
    assert kwargs["params"] == params


@pytest.mark.parametrize(
    "payload",
    [[], [{"key": "running"}, {"key": "trail_running", "parent": "running"}]],
)
def test_activity_types_preserve_response(payload: list[dict[str, str]]) -> None:
    session = StubSession(make_response(payload))
    client = GarminPersonalApiClient("token", session=session)

    assert client.get_activity_types() == payload
    assert len(session.calls) == 1


def test_single_day_summaries_preserve_collection_response() -> None:
    payload = {"data": [{"calendarDate": END, "movement": {"steps": 123}}]}
    session = StubSession(make_response(payload))
    client = GarminPersonalApiClient("token", session=session)

    assert client.get_daily_summaries(END, END) == payload
    assert len(session.calls) == 1
    for _, url, kwargs in session.calls:
        assert url.endswith("/usersummary-service/v2/dailysummaries")
        assert kwargs["params"] == {"startDate": END, "endDate": END}


@pytest.mark.parametrize(
    "method",
    [
        "get_effective_weight_goal",
        "get_daily_summary",
        "get_weight_data",
        "get_body_battery",
        "get_hrv",
        "get_hrv_range",
        "get_menstrual_cycle_detail",
        "get_wellness_activity_summary",
    ],
)
def test_replaced_python_names_are_removed(method: str) -> None:
    assert not hasattr(GarminPersonalApiClient, method)


def test_requests_send_the_bearer_token_and_log_the_path_without_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = StubSession(make_response({}))
    client = GarminPersonalApiClient("secret-bearer-token", session=session, timeout=12)

    with caplog.at_level("INFO", logger="garmin_personal_api.client"):
        client.get_daily_sleep(END)

    kwargs = session.calls[0][2]
    assert kwargs["headers"]["Authorization"] == "Bearer secret-bearer-token"
    assert kwargs["timeout"] == 12
    assert f"GET /sleep-service/sleep/dailySleep?date={END}" in caplog.text
    assert "secret-bearer-token" not in caplog.text


def test_update_bearer_token_is_used_for_subsequent_requests() -> None:
    session = StubSession(make_response({}))
    client = GarminPersonalApiClient("old-token", session=session)

    client.update_bearer_token("new-token")
    client.get_user_profile_settings()

    assert session.calls[0][2]["headers"]["Authorization"] == "Bearer new-token"


def test_get_supports_endpoints_without_a_wrapper() -> None:
    session = StubSession(make_response({"custom": True}))
    client = GarminPersonalApiClient("token", session=session)

    assert client.get("/custom-service/resource", params={"page": 2}) == {"custom": True}
    _, url, kwargs = session.calls[0]
    assert url == f"{DEFAULT_BASE_URL}/custom-service/resource"
    assert kwargs["params"] == {"page": 2}


def test_empty_response_returns_none() -> None:
    session = StubSession(make_response(None, status_code=204, raw_text=""))

    assert GarminPersonalApiClient("token", session=session).get_daily_hrv(END) is None


@pytest.mark.parametrize("status_code", [429, 500])
def test_http_errors_include_status_and_response_body(status_code: int) -> None:
    session = StubSession(make_response({"message": "try later"}, status_code=status_code))

    with pytest.raises(HttpError) as raised:
        GarminPersonalApiClient("token", session=session).get_daily_hrv(END)

    assert raised.value.status_code == status_code
    assert raised.value.response_text == '{"message": "try later"}'
    assert f"HTTP {status_code}" in str(raised.value)
    assert "try later" in str(raised.value)


def test_base_url_can_be_overridden_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BASE_URL_ENV_VAR, "https://example.test/")

    assert GarminPersonalApiClient("token").base_url == "https://example.test"


def test_context_manager_closes_the_session() -> None:
    session = StubSession()
    with GarminPersonalApiClient("token", session=session):
        pass
    assert session.closed is True


def test_repr_does_not_include_the_bearer_token() -> None:
    assert "secret-token" not in repr(GarminPersonalApiClient("secret-token"))
