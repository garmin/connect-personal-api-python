"""Endpoint wrappers for the Garmin Personal API."""

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

import logging
import os
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any
from urllib.parse import urlencode

import requests

from .constants import BASE_URL_ENV_VAR, DEFAULT_BASE_URL, DEFAULT_TIMEOUT_SECONDS
from .errors import GarminPersonalApiError, HttpError

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
QueryParams = Mapping[
    str,
    str | int | float | bool | Sequence[str | int | float | bool],
]
_LOGGER = logging.getLogger(__name__)


class GarminPersonalApiClient:
    """Read Garmin data using an already-issued bearer token."""

    def __init__(
        self,
        bearer_token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        if timeout <= 0:
            raise GarminPersonalApiError("timeout must be greater than zero")
        self.base_url = os.environ.get(BASE_URL_ENV_VAR, DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self.update_bearer_token(bearer_token)

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def __enter__(self) -> GarminPersonalApiClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self.base_url!r}, timeout={self.timeout!r})"

    def update_bearer_token(self, bearer_token: str) -> None:
        """Replace the token used for subsequent requests."""
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        }

    def get_daily_stress(self, start_date: str | date, end_date: str | date) -> JsonValue:
        """Return daily stress statistics for an inclusive calendar date range."""
        return self.get(
            f"/usersummary-service/stats/stress/daily/{_iso(start_date)}/{_iso(end_date)}"
        )

    def get_daily_steps(self, start_date: str | date, end_date: str | date) -> JsonValue:
        """Return daily step statistics for an inclusive calendar date range."""
        return self.get(
            f"/usersummary-service/stats/steps/daily/{_iso(start_date)}/{_iso(end_date)}"
        )

    def get_daily_hydration(self, start_date: str | date, end_date: str | date) -> JsonValue:
        """Return daily hydration statistics for an inclusive calendar date range."""
        return self.get(
            f"/usersummary-service/stats/hydration/daily/{_iso(start_date)}/{_iso(end_date)}"
        )

    def get_effective_weight_goals(
        self,
        start_date: str | date,
        end_date: str | date,
    ) -> JsonValue:
        """Return effective weight goals for an inclusive calendar date range."""
        return self.get(
            f"/goal-service/goal/user/effective/weightgoal/{_iso(start_date)}/{_iso(end_date)}"
        )

    def get_weight_measurements(self, start_date: str | date, end_date: str | date) -> JsonValue:
        """Return all weight data for an inclusive calendar date range."""
        return self.get(
            f"/weight-service/weight/range/{_iso(start_date)}/{_iso(end_date)}",
            params={"includeAll": "true"},
        )

    def get_daily_food_logs(self, calendar_date: str | date) -> JsonValue:
        """Return nutrition food logs for a calendar date."""
        return self.get(f"/nutrition-service/food/logs/{_iso(calendar_date)}")

    def get_user_profile_settings(self) -> JsonValue:
        """Return the current user's profile settings."""
        return self.get("/userprofile-service/userprofile/settings")

    def get_daily_sleep(self, calendar_date: str | date) -> JsonValue:
        """Return daily sleep data for a calendar date."""
        return self.get(
            "/sleep-service/sleep/dailySleep",
            params={"date": _iso(calendar_date)},
        )

    def get_daily_sleep_summaries(
        self,
        start_date: str | date,
        end_date: str | date,
    ) -> JsonValue:
        """Return daily sleep summaries for an inclusive calendar date range."""
        return self.get(
            "/sleep-service/sleep/dailySleepSummariesByDate",
            params={"startDate": _iso(start_date), "endDate": _iso(end_date)},
        )

    def get_daily_body_battery(
        self,
        start_date: str | date,
        end_date: str | date,
        *,
        chunks: int | None = None,
    ) -> JsonValue:
        """Return daily Body Battery data for an inclusive calendar date range."""
        params: dict[str, str | int] = {"startDate": _iso(start_date), "endDate": _iso(end_date)}
        if chunks is not None:
            params["chunks"] = chunks
        return self.get("/wellness-service/wellness/bodyBattery/reports/daily", params=params)

    def get_daily_summaries(
        self,
        start_date: str | date,
        end_date: str | date,
    ) -> JsonValue:
        """Return user daily summaries for an inclusive calendar date range.

        Use the same start and end date for a single day. The response preserves
        the endpoint's object containing a data array, even for one day.
        """
        return self.get(
            "/usersummary-service/v2/dailysummaries",
            params={"startDate": _iso(start_date), "endDate": _iso(end_date)},
        )

    def get_daily_hrv(self, calendar_date: str | date) -> JsonValue:
        """Return heart rate variability (HRV) summary and readings for a calendar date."""
        return self.get(f"/hrv-service/hrv/{_iso(calendar_date)}")

    def get_daily_hrv_summaries(self, start_date: str | date, end_date: str | date) -> JsonValue:
        """Return daily heart rate variability (HRV) summaries for an inclusive date range."""
        return self.get(f"/hrv-service/hrv/daily/{_iso(start_date)}/{_iso(end_date)}")

    def get_daily_vo2_max(
        self,
        start_date: str | date,
        end_date: str | date,
        *,
        sport: Sequence[str] | None = None,
    ) -> JsonValue:
        """Return daily VO2 Max data for an inclusive date range, optionally filtered by sport."""
        params = {"sport": sport} if sport else None
        return self.get(
            f"/metrics-service/metrics/maxmet/daily/{_iso(start_date)}/{_iso(end_date)}",
            params=params,
        )

    def get_heart_rate_zones(self) -> JsonValue:
        """Return the current user's heart rate zones."""
        return self.get("/biometric-service/heartRateZones/v2")

    def get_fitness_age(self, calendar_date: str | date) -> JsonValue:
        """Return fitness age data for a calendar date."""
        return self.get(f"/fitnessage-service/fitnessage/v2/{_iso(calendar_date)}")

    def get_daily_heart_rate(self, calendar_date: str | date) -> JsonValue:
        """Return daily heart rate data for a calendar date."""
        return self.get(
            "/wellness-service/wellness/dailyHeartRate",
            params={"date": _iso(calendar_date)},
        )

    def get_menstrual_cycle_summary(self, calendar_date: str | date) -> JsonValue:
        """Return menstrual-cycle summary data for a calendar date."""
        return self.get(f"/periodichealth-service/menstrualcycle/summary/{_iso(calendar_date)}")

    def get_menstrual_cycle_day_view(
        self,
        calendar_date: str | date,
        today_date: str | date,
    ) -> JsonValue:
        """Return the menstrual-cycle day view for a calendar date."""
        return self.get(
            f"/periodichealth-service/menstrualcycle/dayview/{_iso(calendar_date)}",
            params={"todayDate": _iso(today_date)},
        )

    def get_daily_spo2(self, calendar_date: str | date) -> JsonValue:
        """Return daily SpO2 and acclimation data for a calendar date."""
        return self.get(f"/wellness-service/wellness/daily/spo2acclimation/{_iso(calendar_date)}")

    def get_wellness_activity_summaries(
        self,
        start_date: str | date,
        end_date: str | date,
    ) -> JsonValue:
        """Return wellness activity summaries for an inclusive calendar date range."""
        return self.get(
            f"/wellnessactivity-service/activity/summary/range/{_iso(start_date)}/{_iso(end_date)}"
        )

    def search_activities(
        self,
        *,
        start: int = 0,
        limit: int = 20,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
        activity_type: str | None = None,
    ) -> JsonValue:
        """Return summarized activities matching the supplied search filters."""
        params: dict[str, str | int] = {"start": start, "limit": limit}
        if start_date is not None:
            params["startDate"] = _iso(start_date)
        if end_date is not None:
            params["endDate"] = _iso(end_date)
        if activity_type is not None:
            params["activityType"] = activity_type
        return self.get("/activitylist-service/activities/search/activities", params=params)

    def get_activity(self, activity_id: int | str) -> JsonValue:
        """Return the activity summary/details for an activity ID."""
        return self.get(f"/activity-service/activity/{activity_id}")

    def get_activity_workouts(self, activity_id: int | str) -> JsonValue:
        """Return workouts associated with an activity ID."""
        return self.get(f"/activity-service/activity/{activity_id}/workouts")

    def download_activity(self, activity_id: int | str) -> bytes:
        """Return the original activity file as ZIP bytes, without extracting it."""
        activity_id = str(activity_id)
        if not activity_id.isascii() or not activity_id.isdecimal() or int(activity_id) <= 0:
            raise GarminPersonalApiError("activity_id must be a positive integer")
        response = self._get_response(
            f"/download-service/files/activity/{activity_id}",
            accept="application/zip, application/x-zip-compressed, application/octet-stream",
        )
        if not response.content:
            raise GarminPersonalApiError("The original activity file response was empty")
        return response.content

    def get(self, path: str, *, params: QueryParams | None = None) -> JsonValue:
        """GET a Personal API path and return decoded JSON, or ``None`` if empty."""
        response = self._get_response(path, params=params)
        if not response.content:
            return None
        return response.json()

    def _get_response(
        self,
        path: str,
        *,
        params: QueryParams | None = None,
        accept: str = "application/json",
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        _LOGGER.info("GET %s", f"{path}?{urlencode(params, doseq=True)}" if params else path)
        response = self._session.get(
            url,
            headers={**self._headers, "Accept": accept},
            params=params,
            timeout=self.timeout,
        )
        if not response.ok:
            raise HttpError(
                status_code=response.status_code,
                method="GET",
                url=url,
                response_text=response.text,
            )
        return response


def _iso(value: str | date) -> str:
    """Format a date as YYYY-MM-DD; strings are passed through to the API unchanged."""
    return value.isoformat() if isinstance(value, date) else value
