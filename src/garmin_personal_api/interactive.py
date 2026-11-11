"""Interactive reference UI for exploring the Personal API."""

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
import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from typing import Any, TextIO

import requests

from .client import GarminPersonalApiClient
from .commands import COMMANDS, TOKEN_REFRESH_COMMAND, CommandSpec
from .downloads import save_download
from .errors import GarminPersonalApiError

_ACTIVITY_PAGE_SIZE = 10
# Activity commands need an activity ID, so they are reached from the activity browser.
_MENU_COMMANDS = tuple(spec for spec in COMMANDS if spec.input_kind != "activity")
_MENU_COMMANDS_BY_NAME = {spec.command: spec for spec in _MENU_COMMANDS}
_INTERACTIVE_MENU_ITEMS = tuple(
    (number, spec.label, spec.command) for number, spec in enumerate(_MENU_COMMANDS, start=1)
)
_INTERACTIVE_MENU_ITEMS += (
    (len(_INTERACTIVE_MENU_ITEMS) + 1, "Reload Bearer Token", TOKEN_REFRESH_COMMAND),
)
_INTERACTIVE_MENU_ACTIONS = {str(number): command for number, _, command in _INTERACTIVE_MENU_ITEMS}


@dataclass
class _InteractiveDateState:
    last_date: str
    last_end_date: str


class _InteractiveBack(Exception):
    """Return from the current interactive screen."""


class _InteractiveExit(Exception):
    """Leave the interactive client from any screen."""


def run_interactive(
    client: GarminPersonalApiClient,
    *,
    input_func: Callable[[str], str] | None = None,
    output: TextIO | None = None,
    error_output: TextIO | None = None,
    color: bool | None = None,
    show_header: bool = True,
    refresh_token: Callable[[], None] | None = None,
) -> int:
    """Run the reference client's interactive menu."""
    input_func = input if input_func is None else input_func
    actual_output: TextIO = sys.stdout if output is None else output
    actual_error_output: TextIO = sys.stderr if error_output is None else error_output
    with _route_logs_to_status(output=actual_output, color=color):
        return _run_interactive_session(
            client,
            input_func=input_func,
            actual_output=actual_output,
            actual_error_output=actual_error_output,
            color=color,
            show_header=show_header,
            refresh_token=refresh_token,
        )


def _run_interactive_session(
    client: GarminPersonalApiClient,
    *,
    input_func: Callable[[str], str],
    actual_output: TextIO,
    actual_error_output: TextIO,
    color: bool | None,
    show_header: bool,
    refresh_token: Callable[[], None] | None,
) -> int:
    today = date.today().isoformat()
    date_state = _InteractiveDateState(last_date=today, last_end_date=today)

    if show_header:
        print_heading("Garmin Personal API", output=actual_output, width=56, color=color)

    while True:
        _print_interactive_menu(output=actual_output, color=color)
        try:
            choice = input_func("\nSelection: ").strip().lower()
            if choice in {"q", "quit", "exit"}:
                print("\nGoodbye.", file=actual_output)
                return 0
            if choice in {"b", "back"}:
                print("Already at the main menu.", file=actual_error_output)
                continue

            command = _INTERACTIVE_MENU_ACTIONS.get(choice, choice)
            if command == TOKEN_REFRESH_COMMAND:
                if refresh_token is None:
                    print("Bearer token refresh is unavailable.", file=actual_error_output)
                    continue
                refresh_token()
                print("Bearer token refreshed.", file=actual_output)
                continue
            spec = _MENU_COMMANDS_BY_NAME.get(command)
            if spec is None:
                print(
                    f"Invalid selection. Choose 1 through {len(_INTERACTIVE_MENU_ITEMS)} or q.",
                    file=actual_error_output,
                )
                continue
            if spec.input_kind == "activities":
                _browse_activities(
                    client,
                    input_func=input_func,
                    output=actual_output,
                    error_output=actual_error_output,
                    color=color,
                )
                continue

            result = _run_interactive_command(
                client,
                spec,
                date_state=date_state,
                input_func=input_func,
                output=actual_output,
                color=color,
            )
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.", file=actual_output)
            return 0
        except _InteractiveBack:
            continue
        except _InteractiveExit:
            print("\nGoodbye.", file=actual_output)
            return 0
        except (GarminPersonalApiError, requests.RequestException) as exc:
            print(f"Error: {exc}", file=actual_error_output)
            continue

        _print_json(result, output=actual_output, color=color)


def _run_interactive_command(
    client: GarminPersonalApiClient,
    spec: CommandSpec,
    *,
    date_state: _InteractiveDateState,
    input_func: Callable[[str], str],
    output: TextIO,
    color: bool | None,
) -> Any:
    method = partial(spec.method, client)
    if spec.input_kind == "date":
        requested_date = _prompt_with_default(
            input_func,
            "Date",
            date_state.last_date,
            output=output,
        )
        date_state.last_date = requested_date
        return _run_interactive_operation(
            lambda: method(requested_date),
            heading=f"{spec.label} | {requested_date}",
            output=output,
            color=color,
        )

    if spec.input_kind == "date_with_today":
        requested_date = _prompt_with_default(
            input_func,
            "Date",
            date_state.last_date,
            output=output,
        )
        today_date = _prompt_with_default(
            input_func,
            "Today date",
            date_state.last_end_date,
            output=output,
        )
        date_state.last_date = requested_date
        date_state.last_end_date = today_date
        return _run_interactive_operation(
            lambda: method(requested_date, today_date),
            heading=f"{spec.label} | {requested_date} (today: {today_date})",
            output=output,
            color=color,
        )

    if spec.input_kind == "date_range":
        start_date = _prompt_with_default(
            input_func,
            "Start date",
            date_state.last_date,
            output=output,
        )
        end_date = _prompt_with_default(
            input_func,
            "End date",
            date_state.last_end_date,
            output=output,
        )
        date_state.last_date = start_date
        date_state.last_end_date = end_date
        if spec.command == "vo2-max":
            requested_sports = input_func(
                "Sport filters (comma-separated, leave blank for all): "
            ).strip()
            sports = [sport.strip() for sport in requested_sports.split(",") if sport.strip()]
            return _run_interactive_operation(
                lambda: method(start_date, end_date, sport=sports or None),
                heading=f"{spec.label} | {start_date} to {end_date}",
                output=output,
                color=color,
            )
        return _run_interactive_operation(
            lambda: method(start_date, end_date),
            heading=f"{spec.label} | {start_date} to {end_date}",
            output=output,
            color=color,
        )

    return _run_interactive_operation(method, heading=spec.label, output=output, color=color)


def _browse_activities(
    client: GarminPersonalApiClient,
    *,
    input_func: Callable[[str], str],
    output: TextIO,
    error_output: TextIO,
    color: bool | None,
) -> None:
    print_heading("Activities", output=output, width=56, color=color)
    activities = _activity_records(client.search_activities(limit=30))
    if not activities:
        print("No activities found.", file=output)
        return

    page = 0
    while True:
        page_start = page * _ACTIVITY_PAGE_SIZE
        page_end = min(page_start + _ACTIVITY_PAGE_SIZE, len(activities))
        page_activities = activities[page_start:page_end]
        _print_activity_table(
            page_activities,
            page_start=page_start,
            total=len(activities),
            output=output,
            color=color,
        )
        navigation = ["number  view activity", "b  back"]
        if page > 0:
            navigation.append("p  previous page")
        if page_end < len(activities):
            navigation.append("n  next page")
        navigation.append("q  quit")
        _print_navigation_line(navigation, output=output, color=color)

        try:
            choice = input_func("\nActivity: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if choice in {"b", "back", "q", "quit", "exit"}:
            if choice in {"q", "quit", "exit"}:
                raise _InteractiveExit
            return
        if choice in {"n", "next"}:
            if page_end < len(activities):
                page += 1
            else:
                print("Already on the last page.", file=error_output)
            continue
        if choice in {"p", "previous", "prev"}:
            if page > 0:
                page -= 1
            else:
                print("Already on the first page.", file=error_output)
            continue
        try:
            activity_index = page_start + int(choice) - 1
        except ValueError:
            print(
                "Invalid selection. Choose an activity number, n, p, b, or q.",
                file=error_output,
            )
            continue
        if not page_start <= activity_index < page_end:
            print(
                "Invalid selection. Choose an activity number from this page.",
                file=error_output,
            )
            continue
        _show_activity(
            client,
            activities[activity_index],
            input_func=input_func,
            output=output,
            error_output=error_output,
            color=color,
        )


def _show_activity(
    client: GarminPersonalApiClient,
    activity: dict[str, Any],
    *,
    input_func: Callable[[str], str],
    output: TextIO,
    error_output: TextIO,
    color: bool | None,
) -> None:
    activity_id = activity.get("activityId")
    if activity_id is None:
        print("Selected activity does not contain an activityId.", file=error_output)
        return

    print_heading(
        f"Activity | {_activity_date(activity)} | {_activity_title(activity)}",
        output=output,
        width=56,
        color=color,
    )
    _print_json(activity, output=output, color=color)
    actions = {
        "1": ("Activity Details", client.get_activity),
        "2": ("Activity Workouts", client.get_activity_workouts),
    }

    while True:
        _print_navigation_line(
            [
                "1  activity details",
                "2  activity workouts",
                "3  download activity file",
                "b  back to activities",
                "q  quit",
            ],
            output=output,
            color=color,
        )
        try:
            choice = input_func("\nActivity option: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if choice in {"b", "back", "q", "quit", "exit"}:
            if choice in {"q", "quit", "exit"}:
                raise _InteractiveExit
            return
        if choice == "3":
            try:
                entered = input_func(
                    f"Save as [default: activity-{activity_id}.zip] (b to cancel): "
                ).strip()
                if entered.lower() in {"q", "quit", "exit"}:
                    raise _InteractiveExit
                if entered.lower() in {"b", "back"}:
                    continue
                destination = Path(entered or f"activity-{activity_id}.zip").expanduser()
                overwrite = False
                if destination.exists() or destination.is_symlink():
                    answer = input_func(f"Replace {destination}? [y/N]: ").strip().lower()
                    if answer in {"q", "quit", "exit"}:
                        raise _InteractiveExit
                    if answer not in {"y", "yes"}:
                        print("Download cancelled.", file=output)
                        continue
                    overwrite = True
                content = client.download_activity(activity_id)
                saved = save_download(content, destination, overwrite=overwrite)
                print(f"Saved {saved} ({len(content)} bytes)", file=output)
            except (GarminPersonalApiError, requests.RequestException, OSError) as exc:
                print(f"Error: {exc}", file=error_output)
            except (EOFError, KeyboardInterrupt):
                return
            continue
        if choice not in actions:
            print("Invalid selection. Choose 1, 2, 3, b, or q.", file=error_output)
            continue

        title, method = actions[choice]
        result = _run_interactive_operation(
            lambda method=method: method(activity_id),
            heading=title,
            output=output,
            color=color,
        )
        _print_json(result, output=output, color=color)


def print_heading(
    title: str,
    *,
    output: TextIO,
    width: int,
    color: bool | None = None,
) -> None:
    separator = "=" * max(width, len(title))
    console = _interactive_console(output=output, color=color)
    console.print()
    console.print(_rich_text(separator, style="dim"))
    console.print(_rich_text(title, style="bold cyan"))
    console.print(_rich_text(separator, style="dim"))


def _print_interactive_menu(*, output: TextIO, color: bool | None) -> None:
    print_heading("Available data sets", output=output, width=56, color=color)
    from rich.table import Table

    table = Table(box=None, show_header=False, pad_edge=False, expand=False)
    table.add_column("Selection")
    for number, label, _ in _INTERACTIVE_MENU_ITEMS:
        table.add_row(f"{number:<2} {label}")
    table.add_row("q   Quit", style="dim")
    _interactive_console(output=output, color=color).print(table)


def _interactive_console(*, output: TextIO, color: bool | None) -> Any:
    from rich.console import Console

    return Console(
        file=output,
        force_terminal=color,
        no_color=True if color is False else None,
        highlight=False,
    )


def _rich_text(value: str, *, style: str) -> Any:
    from rich.text import Text

    return Text(value, style=style)


def print_request_status(
    message: str,
    *,
    output: TextIO,
    color: bool | None,
) -> None:
    _interactive_console(output=output, color=color).print(
        _rich_text(f"> {message}", style="dim"),
        soft_wrap=True,
    )


def _run_interactive_operation(
    operation: Callable[[], Any],
    *,
    heading: str | None = None,
    output: TextIO,
    color: bool | None,
) -> Any:
    if heading is not None:
        print_heading(heading, output=output, width=56, color=color)
    return operation()


class _StatusLineLogHandler(logging.Handler):
    """Render package log records as interactive status lines."""

    def __init__(self, *, output: TextIO, color: bool | None) -> None:
        super().__init__(logging.INFO)
        self._output = output
        self._color = color

    def emit(self, record: logging.LogRecord) -> None:
        print_request_status(record.getMessage(), output=self._output, color=self._color)


@contextmanager
def _route_logs_to_status(*, output: TextIO, color: bool | None) -> Iterator[None]:
    logger = logging.getLogger(__package__)
    if any(isinstance(existing, _StatusLineLogHandler) for existing in logger.handlers):
        yield
        return

    handler = _StatusLineLogHandler(output=output, color=color)
    previous_level, previous_propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def _prompt_with_default(
    input_func: Callable[[str], str],
    label: str,
    default: str,
    *,
    output: TextIO | None = None,
) -> str:
    actual_output: TextIO = sys.stdout if output is None else output
    if input_func is input and _can_use_arrow_date_prompt(actual_output):
        return _prompt_date_with_arrows(label, default, output=actual_output)
    entered = input_func(f"{label} [default: {default}]: ").strip()
    if entered.lower() in {"q", "quit", "exit"}:
        raise _InteractiveExit
    if entered.lower() in {"b", "back"}:
        raise _InteractiveBack
    return entered or default


def _can_use_arrow_date_prompt(output: TextIO) -> bool:
    # TODO: Add a Windows key-reading backend for cross-platform arrow navigation.
    if sys.platform != "darwin":
        return False
    try:
        return bool(sys.stdin.isatty() and output.isatty())
    except (AttributeError, OSError):
        return False


def _prompt_date_with_arrows(
    label: str,
    default: str,
    *,
    output: TextIO,
    terminal_fd: int | None = None,
) -> str:
    import termios
    import tty

    prompt = f"{label} [up/down changes the date]: "
    entered = ""
    displayed = default
    default_date = _try_parse_date(default)
    file_descriptor = sys.stdin.fileno() if terminal_fd is None else terminal_fd
    original_terminal = termios.tcgetattr(file_descriptor)
    try:
        tty.setraw(file_descriptor)
        _render_date_prompt(output, prompt, displayed)
        while True:
            key = _read_terminal_key()
            if key in {"\r", "\n"}:
                output.write("\r\n")
                output.flush()
                return entered or default
            if key == "\x03":
                raise KeyboardInterrupt
            if key == "\x04":
                raise EOFError
            if key.lower() == "q":
                raise _InteractiveExit
            if key.lower() == "b":
                raise _InteractiveBack
            if key in {"\x08", "\x7f"}:
                entered = entered[:-1]
            elif key == "\x15":
                entered = ""
            elif key in {"\x1b[A", "\x1bOA", "\x1b[B", "\x1bOB"}:
                candidate = _try_parse_date(entered) or default_date
                if candidate is not None:
                    change = 1 if key in {"\x1b[A", "\x1bOA"} else -1
                    entered = (candidate + timedelta(days=change)).isoformat()
            elif len(key) == 1 and (key.isdigit() or key == "-"):
                entered += key
            else:
                continue
            displayed = entered or default
            _render_date_prompt(output, prompt, displayed)
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, original_terminal)


def _read_terminal_key() -> str:
    key = sys.stdin.read(1)
    if key != "\x1b":
        return key
    next_key = sys.stdin.read(1)
    if next_key not in {"[", "O"}:
        return key + next_key
    return key + next_key + sys.stdin.read(1)


def _render_date_prompt(output: TextIO, prompt: str, value: str) -> None:
    output.write(f"\r\x1b[2K{prompt}{value}")
    output.flush()


def _try_parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _print_activity_table(
    activities: list[dict[str, Any]],
    *,
    page_start: int,
    total: int,
    output: TextIO,
    color: bool | None,
) -> None:
    from rich.table import Table

    page_end = page_start + len(activities)
    print_heading(
        f"Activities {page_start + 1}-{page_end} of {total}",
        output=output,
        width=56,
        color=color,
    )
    table = Table(box=None, pad_edge=False, show_lines=False)
    table.add_column("#", justify="right", style="bold")
    table.add_column("Activity")
    for index, activity in enumerate(activities, start=1):
        table.add_row(str(index), f"{_activity_date(activity)} | {_activity_title(activity)}")
    _interactive_console(output=output, color=color).print(table)


def _print_navigation_line(
    actions: list[str],
    *,
    output: TextIO,
    color: bool | None,
) -> None:
    _interactive_console(output=output, color=color).print(
        _rich_text("  " + "   ".join(actions), style="dim")
    )


def _activity_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [record for record in value if isinstance(record, dict)]
    if isinstance(value, dict):
        for key in ("activities", "activityList"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [record for record in nested if isinstance(record, dict)]
    return []


def _activity_date(activity: dict[str, Any]) -> str:
    for key in ("startTimeLocal", "startTimeGMT", "activityDate", "date"):
        value = activity.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return "Unknown date"


def _activity_title(activity: dict[str, Any]) -> str:
    for key in ("activityName", "title", "name"):
        value = activity.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return "Untitled activity"


def _print_json(
    value: Any,
    *,
    output: TextIO | None = None,
    color: bool | None = None,
) -> None:
    actual_output: TextIO = sys.stdout if output is None else output
    serialized = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    from rich.syntax import Syntax

    console = _interactive_console(output=actual_output, color=color)
    console.print(
        Syntax(
            serialized,
            "json",
            theme="ansi_dark",
            background_color="default",
            word_wrap=False,
        )
    )
