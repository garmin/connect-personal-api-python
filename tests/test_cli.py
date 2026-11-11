"""Smoke tests for the command-line entry points."""

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

import json
from datetime import date
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import pytest

from garmin_personal_api import (
    DEFAULT_BASE_URL,
    BearerToken,
    GarminPersonalApiClient,
    GarminPersonalApiError,
    HttpError,
    __version__,
    api_keys,
    cli,
)
from garmin_personal_api.downloads import save_download

from .helpers import StubSession, make_response

TODAY = date.today().isoformat()


def test_missing_interactive_dependency_shows_install_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def missing_rich(name: str) -> None:
        assert name == "rich"
        raise ModuleNotFoundError(name="rich")

    monkeypatch.setattr(cli.importlib, "import_module", missing_rich)

    assert cli.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "pip install 'garmin-connect-personal-api-python[interactive]'" in captured.err


def test_interactive_menu_titles_and_order() -> None:
    from garmin_personal_api.interactive import _INTERACTIVE_MENU_ITEMS

    expected = [
        ("Activities", "activities"),
        ("Daily Stress", "stress"),
        ("Daily Steps", "steps"),
        ("Daily Hydration", "hydration"),
        ("Effective Weight Goals", "effective-weight-goals"),
        ("Weight Measurements", "weight-measurements"),
        ("Food Logs", "food-logs"),
        ("User Profile Settings", "profile-settings"),
        ("Daily Sleep", "sleep"),
        ("Daily Sleep Summaries", "sleep-summaries"),
        ("Daily Body Battery", "body-battery"),
        ("User Daily Summaries", "daily-summaries"),
        ("Daily Heart Rate", "heart-rate"),
        ("Daily HRV", "hrv"),
        ("Daily HRV Summaries", "hrv-summaries"),
        ("Heart Rate Zones", "heart-rate-zones"),
        ("Menstrual Cycle Summary", "menstrual-cycle-summary"),
        ("Menstrual Cycle Day View", "menstrual-cycle-day-view"),
        ("Fitness Age", "fitness-age"),
        ("Daily SpO2", "spo2"),
        ("Wellness Activity Summaries", "wellness-activity-summaries"),
        ("Activity Types", "activity-types"),
        ("Reload Bearer Token", "refresh-token"),
    ]
    assert (
        tuple((number, label, command) for number, (label, command) in enumerate(expected, start=1))
        == _INTERACTIVE_MENU_ITEMS
    )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("hrv", "heart rate variability (HRV) summary and readings"),
        ("hrv-summaries", "daily heart rate variability (HRV) summaries"),
    ],
)
def test_hrv_help_describes_response_granularity(
    command: str, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args([command, "--help"])
    assert raised.value.code == 0
    assert expected in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize(
    "command",
    [
        "weight-goal",
        "weight",
        "profile",
        "summary",
        "daily-summary",
        "summaries",
        "hrv-range",
        "menstrual-cycle",
        "wellness-activity",
    ],
)
def test_replaced_cli_names_are_rejected(command: str) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args([command])
    assert raised.value.code == 2


@pytest.mark.parametrize("argv", [["--help"], ["activity-download", "--help"]])
def test_download_help_uses_natural_action_description(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(argv)
    assert raised.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "Download original activity file." in help_text
    assert "Get download" not in help_text
    if argv[0] == "activity-download":
        assert "Activity ID to download." in help_text


@pytest.fixture
def download_client(monkeypatch: pytest.MonkeyPatch) -> GarminPersonalApiClient:
    response = make_response(None)
    response._content = b"PK\x03\x04binary\xff"
    client = GarminPersonalApiClient("token", session=StubSession(response))
    monkeypatch.setattr(cli, "PersonalApiAuthenticator", _stub_authenticator([]))
    monkeypatch.setattr(cli, "GarminPersonalApiClient", lambda *args, **kwargs: client)
    return client


def test_download_cli_file_options(
    download_client: GarminPersonalApiClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    args = ["--api-key", "personal-key", "activity-download", "123"]
    assert cli.main(args) == 0
    destination = tmp_path / "activity-123.zip"
    assert destination.read_bytes() == b"PK\x03\x04binary\xff"
    destination.write_bytes(b"existing")
    assert cli.main(args) == 1
    assert destination.read_bytes() == b"existing"
    assert cli.main([*args, "--force"]) == 0
    assert destination.read_bytes() == b"PK\x03\x04binary\xff"
    assert cli.main([*args, "-o", "custom.zip"]) == 0
    assert (tmp_path / "custom.zip").read_bytes() == destination.read_bytes()
    assert capsys.readouterr().out == ""
    assert sorted(p.name for p in tmp_path.iterdir()) == ["activity-123.zip", "custom.zip"]


def test_download_cli_stdout(
    download_client: GarminPersonalApiClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BinaryOutput:
        buffer = BytesIO()

        def isatty(self) -> bool:
            return False

    output = BinaryOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    assert cli.main(["--api-key", "personal-key", "activity-download", "123", "-o", "-"]) == 0
    assert output.buffer.getvalue() == b"PK\x03\x04binary\xff"


def test_download_cli_refuses_terminal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    assert cli.main(["activity-download", "123", "-o", "-"]) == 1
    assert "terminal" in capsys.readouterr().err


def test_failed_download_write_preserves_existing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "original.zip"
    destination.write_bytes(b"original")

    def fail_replace(*args: Any) -> None:
        raise OSError("disk error")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(GarminPersonalApiError, match="disk error"):
        save_download(b"new", destination, overwrite=True)
    assert destination.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [destination]


def test_download_file_refuses_dangling_symlink(tmp_path: Path) -> None:
    destination = tmp_path / "link.zip"
    destination.symlink_to(tmp_path / "missing")
    with pytest.raises(GarminPersonalApiError, match="already exists"):
        save_download(b"new", destination)
    assert destination.is_symlink()


@pytest.mark.parametrize("overwrite", ["y", "n"])
def test_interactive_activity_download(
    download_client: GarminPersonalApiClient,
    tmp_path: Path,
    overwrite: str,
) -> None:
    from garmin_personal_api.interactive import _show_activity

    destination = tmp_path / "original.zip"
    destination.write_bytes(b"existing")
    answers = iter(["3", str(destination), overwrite, "b"])
    output, errors = StringIO(), StringIO()
    _show_activity(
        download_client,
        {"activityId": 123},
        input_func=lambda prompt: next(answers),
        output=output,
        error_output=errors,
        color=False,
    )
    expected = b"PK\x03\x04binary\xff" if overwrite == "y" else b"existing"
    assert destination.read_bytes() == expected
    assert "3 download activity file" in " ".join(output.getvalue().split())
    assert errors.getvalue() == ""


def test_interactive_download_default_and_error_recovery(
    download_client: GarminPersonalApiClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from garmin_personal_api.interactive import _show_activity

    monkeypatch.chdir(tmp_path)
    answers = iter(["3", "missing/run.zip", "3", "b", "3", "", "b"])
    output, errors = StringIO(), StringIO()
    _show_activity(
        download_client,
        {"activityId": 123},
        input_func=lambda prompt: next(answers),
        output=output,
        error_output=errors,
        color=False,
    )
    assert (tmp_path / "activity-123.zip").read_bytes() == b"PK\x03\x04binary\xff"
    assert "Cannot save" in errors.getvalue()
    assert "Saved activity-123.zip" in output.getvalue()


def _stub_authenticator(tokens: list[bool]) -> type:
    class StubAuthenticator:
        def __init__(self, **kwargs: Any) -> None:
            self.options = kwargs

        def __enter__(self) -> StubAuthenticator:
            return self

        def __exit__(self, *exc_info: object) -> None:
            pass

        def obtain_token(self, api_key: str, *, force_refresh: bool = False) -> BearerToken:
            assert api_key == "personal-key"
            tokens.append(force_refresh)
            return BearerToken(f"token-{len(tokens)}", expires_at=0)

    return StubAuthenticator


def test_refresh_token_command_forces_a_new_token_without_calling_the_api(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tokens: list[bool] = []

    def unexpected_client(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("refresh-token must not create a data client")

    monkeypatch.setattr(cli, "PersonalApiAuthenticator", _stub_authenticator(tokens))
    monkeypatch.setattr(cli, "GarminPersonalApiClient", unexpected_client)

    assert cli.main(["--api-key", "personal-key", "refresh-token"]) == 0

    assert tokens == [True]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Cached a new bearer token that expires at" in captured.err
    assert "token-1" not in captured.err


@pytest.mark.parametrize(
    "source",
    ["explicit-key", "explicit-file", "explicit-default-file", "environment", "default-file"],
)
def test_cli_key_source_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    default_file = tmp_path / "default-key"
    default_file.write_text(
        "personal-key" if source in {"explicit-default-file", "default-file"} else "other-key",
        encoding="utf-8",
    )
    key_file = tmp_path / "explicit-key"
    key_file.write_text(
        "personal-key" if source == "explicit-file" else "other-key", encoding="utf-8"
    )
    monkeypatch.setattr(api_keys, "DEFAULT_API_KEY_FILE", default_file)
    if source == "default-file":
        monkeypatch.delenv("GARMIN_PERSONAL_API_KEY", raising=False)
    else:
        monkeypatch.setenv(
            "GARMIN_PERSONAL_API_KEY", "personal-key" if source == "environment" else "other-key"
        )
    tokens: list[bool] = []
    monkeypatch.setattr(cli, "PersonalApiAuthenticator", _stub_authenticator(tokens))
    argv: list[str] = []
    if source == "explicit-key":
        argv = ["--api-key", "personal-key", "--api-key-file", str(key_file)]
    elif source == "explicit-file":
        argv = ["--api-key-file", str(key_file)]
    elif source == "explicit-default-file":
        argv = ["--api-key-file", str(default_file)]

    assert cli.main([*argv, "refresh-token"]) == 0
    assert tokens == [True]


@pytest.mark.parametrize("file_state", ["missing", "empty", "directory"])
def test_cli_reports_invalid_explicit_key_file_without_falling_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    file_state: str,
) -> None:
    key_file = tmp_path / "key"
    if file_state == "empty":
        key_file.write_text(" \n", encoding="utf-8")
    elif file_state == "directory":
        key_file.mkdir()
    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", "personal-key")
    tokens: list[bool] = []
    monkeypatch.setattr(cli, "PersonalApiAuthenticator", _stub_authenticator(tokens))

    assert cli.main(["--api-key-file", str(key_file), "refresh-token"]) == 1

    assert tokens == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Error:" in captured.err
    assert str(key_file) in captured.err


def test_omitted_key_file_option_is_distinct_from_an_explicit_file() -> None:
    assert cli.build_parser().parse_args(["profile-settings"]).api_key_file is None


def test_version_flag_prints_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(["--version"])

    assert raised.value.code == 0
    assert __version__ in capsys.readouterr().out


@pytest.mark.parametrize(
    ("option_args", "destination", "expected"),
    [
        (["--api-key", "personal-key"], "api_key", "personal-key"),
        (["--api-key-file", "api-key"], "api_key_file", Path("api-key")),
        (
            ["--bearer-token-cache-file", "bearer-token.json"],
            "bearer_token_cache_file",
            Path("bearer-token.json"),
        ),
        (["--timeout", "12"], "timeout", 12.0),
        (["--quiet"], "quiet", True),
        (["--no-color"], "no_color", True),
    ],
)
def test_shared_options_are_parsed_before_the_command(
    option_args: list[str],
    destination: str,
    expected: object,
) -> None:
    args = cli.build_parser().parse_args([*option_args, "profile-settings"])

    assert getattr(args, destination) == expected


@pytest.mark.parametrize(
    ("argv", "path", "params"),
    [
        (["profile-settings"], "/userprofile-service/userprofile/settings", None),
        (["activity-types"], "/activity-service/activity/activityTypes/simple", None),
        (
            ["effective-weight-goals"],
            f"/goal-service/goal/user/effective/weightgoal/{TODAY}/{TODAY}",
            None,
        ),
        (
            ["weight-measurements"],
            f"/weight-service/weight/range/{TODAY}/{TODAY}",
            {"includeAll": "true"},
        ),
        (
            ["daily-summaries"],
            "/usersummary-service/v2/dailysummaries",
            {"startDate": TODAY, "endDate": TODAY},
        ),
        (
            ["daily-summaries", "--start-date", "2026-08-20", "--end-date", "2026-08-24"],
            "/usersummary-service/v2/dailysummaries",
            {"startDate": "2026-08-20", "endDate": "2026-08-24"},
        ),
        (["hrv"], f"/hrv-service/hrv/{TODAY}", None),
        (
            ["hrv-summaries"],
            f"/hrv-service/hrv/daily/{TODAY}/{TODAY}",
            None,
        ),
        (
            ["wellness-activity-summaries"],
            f"/wellnessactivity-service/activity/summary/range/{TODAY}/{TODAY}",
            None,
        ),
        (["sleep"], "/sleep-service/sleep/dailySleep", {"date": TODAY}),
        (
            ["sleep", "--date", "2026-08-24"],
            "/sleep-service/sleep/dailySleep",
            {"date": "2026-08-24"},
        ),
        (
            ["steps", "--start-date", "2026-08-20", "--end-date", "2026-08-24"],
            "/usersummary-service/stats/steps/daily/2026-08-20/2026-08-24",
            None,
        ),
        (
            ["steps", "--start-date", "2026-08-20"],
            f"/usersummary-service/stats/steps/daily/2026-08-20/{TODAY}",
            None,
        ),
        (
            ["steps", "--end-date", "2026-08-24"],
            f"/usersummary-service/stats/steps/daily/{TODAY}/2026-08-24",
            None,
        ),
        (
            ["body-battery", "--chunks", "3"],
            "/wellness-service/wellness/bodyBattery/reports/daily",
            {"startDate": TODAY, "endDate": TODAY, "chunks": 3},
        ),
        (
            ["menstrual-cycle-day-view", "--date", "2026-08-20", "--today-date", "2026-08-24"],
            "/periodichealth-service/menstrualcycle/dayview/2026-08-20",
            {"todayDate": "2026-08-24"},
        ),
        (
            ["activities"],
            "/activitylist-service/activities/search/activities",
            {"start": 0, "limit": 20},
        ),
        (["activity", "987654321"], "/activity-service/activity/987654321", None),
        (
            ["activity-workouts", "987654321"],
            "/activity-service/activity/987654321/workouts",
            None,
        ),
    ],
)
def test_commands_dispatch_to_client_methods(
    argv: list[str],
    path: str,
    params: dict[str, Any] | None,
) -> None:
    session = StubSession(make_response({"ok": True}))
    client = GarminPersonalApiClient("token", session=session)

    result = cli._execute_command(client, cli.build_parser().parse_args(argv))

    [(method, url, kwargs)] = session.calls
    assert (method, url, kwargs["params"]) == ("GET", f"{DEFAULT_BASE_URL}{path}", params)
    assert result == {"ok": True}


@pytest.mark.parametrize(
    "argv",
    [["steps", "2026-08-20", "2026-08-24"], ["activity"], ["activity-workouts"]],
)
def test_invalid_command_arguments_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(argv)

    assert raised.value.code == 2


def test_activity_types_interactive_command_needs_no_input() -> None:
    payload = [{"key": "running"}, {"key": "trail_running", "parent": "running"}]
    session = StubSession(make_response(payload))
    output = StringIO()
    error_output = StringIO()
    answers = iter(["activity-types", "q"])

    assert (
        cli.run_interactive(
            GarminPersonalApiClient("token", session=session),
            input_func=lambda prompt: next(answers),
            output=output,
            error_output=error_output,
            color=False,
        )
        == 0
    )

    assert json.dumps(payload, indent=2) in output.getvalue()
    assert error_output.getvalue() == ""
    [(method, url, kwargs)] = session.calls
    assert (method, url, kwargs["params"]) == (
        "GET",
        f"{DEFAULT_BASE_URL}/activity-service/activity/activityTypes/simple",
        None,
    )


def test_activity_commands_are_excluded_from_the_interactive_menu() -> None:
    output = StringIO()
    error_output = StringIO()
    answers = iter(["activity", "activity-workouts", "q"])

    cli.run_interactive(
        GarminPersonalApiClient("token", session=StubSession()),
        input_func=lambda prompt: next(answers),
        output=output,
        error_output=error_output,
        color=False,
    )

    assert "Activity Details" not in output.getvalue()
    assert "Activity Workouts" not in output.getvalue()
    assert error_output.getvalue().count("Invalid selection") == 2


def test_main_executes_a_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    tokens: list[bool] = []
    authenticators: list[Any] = []
    stub_authenticator = _stub_authenticator(tokens)

    def make_authenticator(**kwargs: Any) -> Any:
        authenticators.append(stub_authenticator(**kwargs))
        return authenticators[-1]

    session = StubSession(make_response({"ok": True}))
    client = GarminPersonalApiClient("unused", session=session)
    client_tokens: list[str] = []

    class StubClient:
        def __init__(self, bearer_token: str, **kwargs: Any) -> None:
            client_tokens.append(bearer_token)

        def __enter__(self) -> GarminPersonalApiClient:
            return client

        def __exit__(self, *exc_info: object) -> None:
            pass

    monkeypatch.setattr(cli, "PersonalApiAuthenticator", make_authenticator)
    monkeypatch.setattr(cli, "GarminPersonalApiClient", StubClient)
    cache_file = tmp_path / "bearer-token.json"

    exit_code = cli.main(
        [
            "--api-key",
            "personal-key",
            "--bearer-token-cache-file",
            str(cache_file),
            "daily-summaries",
            "--start-date",
            "2026-08-24",
            "--end-date",
            "2026-08-24",
        ]
    )

    assert exit_code == 0
    assert authenticators[0].options["bearer_token_cache_file"] == cache_file
    assert client_tokens == ["token-1"]
    [(_, url, kwargs)] = session.calls
    assert url.endswith("/usersummary-service/v2/dailysummaries")
    assert kwargs["params"] == {"startDate": "2026-08-24", "endDate": "2026-08-24"}
    assert json.loads(capsys.readouterr().out) == {"ok": True}


def test_main_reports_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FailingClient:
        def __init__(self, bearer_token: str, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> FailingClient:
            return self

        def __exit__(self, *exc_info: object) -> None:
            pass

        def get(self, path: str, **kwargs: Any) -> None:
            raise HttpError(status_code=500, method="GET", url="/x", response_text="boom")

    monkeypatch.setattr(cli, "PersonalApiAuthenticator", _stub_authenticator([]))
    monkeypatch.setattr(cli, "GarminPersonalApiClient", FailingClient)

    assert cli.main(["--api-key", "personal-key", "profile-settings"]) == 1
    assert "Error: GET /x returned HTTP 500: boom" in capsys.readouterr().err


def test_interactive_menu_shows_the_request_and_invokes_the_client() -> None:
    session = StubSession(make_response({"ok": True}))
    output = StringIO()
    answers = iter(["stress", "2026-08-20", "2026-08-24", "q"])

    exit_code = cli.run_interactive(
        GarminPersonalApiClient("token", session=session),
        input_func=lambda prompt: next(answers),
        output=output,
        error_output=StringIO(),
        color=False,
    )

    path = "/usersummary-service/stats/stress/daily/2026-08-20/2026-08-24"
    assert exit_code == 0
    assert session.calls[0][1].endswith(path)
    assert f"> GET {path}" in output.getvalue()


def test_main_forces_token_refresh_from_interactive_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens: list[bool] = []
    updated_tokens: list[str] = []

    class StubClient:
        def __init__(self, bearer_token: str, **kwargs: Any) -> None:
            assert bearer_token == "token-1"

        def __enter__(self) -> StubClient:
            return self

        def __exit__(self, *exc_info: object) -> None:
            pass

        def update_bearer_token(self, bearer_token: str) -> None:
            updated_tokens.append(bearer_token)

    def fake_run_interactive(client: StubClient, **kwargs: Any) -> int:
        kwargs["refresh_token"]()
        return 0

    monkeypatch.setattr(cli, "_ensure_interactive_dependency", lambda: True)
    monkeypatch.setattr(cli, "PersonalApiAuthenticator", _stub_authenticator(tokens))
    monkeypatch.setattr(cli, "GarminPersonalApiClient", StubClient)
    monkeypatch.setattr(cli, "run_interactive", fake_run_interactive)

    assert cli.main(["--api-key", "personal-key", "--no-color"]) == 0
    assert tokens == [False, True]
    assert updated_tokens == ["token-2"]
