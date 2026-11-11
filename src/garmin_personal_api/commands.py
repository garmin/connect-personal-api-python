"""The command list shared by the CLI and interactive menu."""

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
from dataclasses import dataclass
from typing import Literal

from .client import GarminPersonalApiClient as Client
from .client import JsonValue

InputKind = Literal[
    "date", "date_range", "date_with_today", "none", "activities", "activity"
]
# Shared by the CLI subcommand and the interactive menu action; not a data command.
TOKEN_REFRESH_COMMAND = "refresh-token"


@dataclass(frozen=True)
class CommandSpec:
    """Describe how the CLI and interactive menu invoke one client method."""

    command: str
    label: str
    method: Callable[..., JsonValue | bytes]
    input_kind: InputKind
    output_kind: Literal["json", "download"] = "json"
    description: str | None = None


COMMANDS = (
    CommandSpec("activities", "Activities", Client.search_activities, "activities"),
    CommandSpec("stress", "Daily Stress", Client.get_daily_stress, "date_range"),
    CommandSpec("steps", "Daily Steps", Client.get_daily_steps, "date_range"),
    CommandSpec("hydration", "Daily Hydration", Client.get_daily_hydration, "date_range"),
    CommandSpec(
        "effective-weight-goals",
        "Effective Weight Goals",
        Client.get_effective_weight_goals,
        "date_range",
    ),
    CommandSpec(
        "weight-measurements", "Weight Measurements", Client.get_weight_measurements, "date_range"
    ),
    CommandSpec("food-logs", "Food Logs", Client.get_daily_food_logs, "date"),
    CommandSpec(
        "profile-settings", "User Profile Settings", Client.get_user_profile_settings, "none"
    ),
    CommandSpec("sleep", "Daily Sleep", Client.get_daily_sleep, "date"),
    CommandSpec(
        "sleep-summaries", "Daily Sleep Summaries", Client.get_daily_sleep_summaries, "date_range"
    ),
    CommandSpec("body-battery", "Daily Body Battery", Client.get_daily_body_battery, "date_range"),
    CommandSpec(
        "daily-summaries",
        "User Daily Summaries",
        Client.get_daily_summaries,
        "date_range",
    ),
    CommandSpec("heart-rate", "Daily Heart Rate", Client.get_daily_heart_rate, "date"),
    CommandSpec(
        "hrv",
        "Daily HRV",
        Client.get_daily_hrv,
        "date",
        description="Get heart rate variability (HRV) summary and readings for a calendar date.",
    ),
    CommandSpec(
        "hrv-summaries",
        "Daily HRV Summaries",
        Client.get_daily_hrv_summaries,
        "date_range",
        description="Get daily heart rate variability (HRV) summaries for an inclusive date range.",
    ),
    CommandSpec(
        "vo2-max",
        "Daily VO2 Max",
        Client.get_daily_vo2_max,
        "date_range",
        description="Get daily VO2 Max data for an inclusive date range.",
    ),
    CommandSpec("heart-rate-zones", "Heart Rate Zones", Client.get_heart_rate_zones, "none"),
    CommandSpec(
        "menstrual-cycle-summary",
        "Menstrual Cycle Summary",
        Client.get_menstrual_cycle_summary,
        "date",
    ),
    CommandSpec(
        "menstrual-cycle-day-view",
        "Menstrual Cycle Day View",
        Client.get_menstrual_cycle_day_view,
        "date_with_today",
    ),
    CommandSpec("fitness-age", "Fitness Age", Client.get_fitness_age, "date"),
    CommandSpec("spo2", "Daily SpO2", Client.get_daily_spo2, "date"),
    CommandSpec(
        "wellness-activity-summaries",
        "Wellness Activity Summaries",
        Client.get_wellness_activity_summaries,
        "date_range",
    ),
    CommandSpec("activity", "Activity Details", Client.get_activity, "activity"),
    CommandSpec("activity-workouts", "Activity Workouts", Client.get_activity_workouts, "activity"),
    CommandSpec(
        "activity-download",
        "Download original activity file",
        Client.download_activity,
        "activity",
        "download",
    ),
)

COMMANDS_BY_NAME = {spec.command: spec for spec in COMMANDS}
