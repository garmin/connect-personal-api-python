"""Command-line reference application for Garmin Personal API reads."""

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

import argparse
import importlib
import json
import logging
import sys
from collections.abc import Sequence
from contextlib import nullcontext
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Any

import requests

from . import __version__
from .api_keys import resolve_api_key
from .auth import PersonalApiAuthenticator
from .client import GarminPersonalApiClient
from .commands import COMMANDS, COMMANDS_BY_NAME, TOKEN_REFRESH_COMMAND, CommandSpec
from .constants import (
    DEFAULT_API_KEY_FILE,
    DEFAULT_BEARER_TOKEN_CACHE_FILE,
    DEFAULT_TIMEOUT_SECONDS,
)
from .downloads import save_download
from .errors import GarminPersonalApiError
from .interactive import (
    _route_logs_to_status,
    print_heading,
    print_request_status,
    run_interactive,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser from the endpoint registry."""
    parser = argparse.ArgumentParser(
        prog="gc-personal",
        description="Retrieve Garmin data with a personal API key.",
    )
    parser.add_argument("--version", action="version", version=f"gc-personal {__version__}")
    parser.add_argument(
        "--api-key",
        help=(
            "Personal API key. Prefer the environment variable or key file to avoid "
            "shell-history and process-list exposure."
        ),
    )
    parser.add_argument(
        "--api-key-file",
        type=Path,
        help=(
            "Plain-text API key file; overrides GARMIN_PERSONAL_API_KEY unless --api-key "
            f"is given. Without either option, use the environment variable, then "
            f"{DEFAULT_API_KEY_FILE}."
        ),
    )
    parser.add_argument(
        "--bearer-token-cache-file",
        type=Path,
        default=DEFAULT_BEARER_TOKEN_CACHE_FILE,
        help=f"Bearer-token cache file (default: {DEFAULT_BEARER_TOKEN_CACHE_FILE}).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS:g}).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress request logging for non-interactive commands.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable interactive terminal colors.",
    )

    subparsers = parser.add_subparsers(dest="command")
    for spec in COMMANDS:
        help_text = spec.description or (
            f"{spec.label}." if spec.output_kind == "download" else f"Get {spec.label.lower()}."
        )
        subparser = subparsers.add_parser(spec.command, help=help_text, description=help_text)
        _add_command_arguments(subparser, spec)
    refresh_help = "Obtain and cache a new bearer token, replacing any cached token."
    subparsers.add_parser(TOKEN_REFRESH_COMMAND, help=refresh_help, description=refresh_help)
    return parser


def _add_command_arguments(
    parser: argparse.ArgumentParser,
    spec: CommandSpec,
) -> None:
    today = date.today().isoformat()
    if spec.input_kind == "date":
        parser.add_argument(
            "--date",
            metavar="DATE",
            default=today,
            help="Calendar date in YYYY-MM-DD format (default: today).",
        )
    elif spec.input_kind == "date_with_today":
        parser.add_argument(
            "--date",
            metavar="DATE",
            default=today,
            help="Calendar date in YYYY-MM-DD format (default: today).",
        )
        parser.add_argument(
            "--today-date",
            metavar="DATE",
            default=today,
            help="Reference today date in YYYY-MM-DD format (default: today).",
        )
    elif spec.input_kind == "date_range":
        parser.add_argument(
            "--start-date",
            metavar="START_DATE",
            default=today,
            help="Start date in YYYY-MM-DD format (default: today).",
        )
        parser.add_argument(
            "--end-date",
            metavar="END_DATE",
            default=today,
            help="End date in YYYY-MM-DD format (default: today).",
        )
        if spec.command == "body-battery":
            parser.add_argument(
                "--chunks",
                type=int,
                default=1,
                help="Number of min/max body battery pairs per day.",
            )
        elif spec.command == "vo2-max":
            parser.add_argument(
                "--sport",
                action="append",
                metavar="SPORT",
                help="Optional sport filter; repeat to include multiple sports. Available sport types are those found in the Garmin FIT SDK.",
            )
    elif spec.input_kind == "activities":
        parser.add_argument(
            "--start",
            type=int,
            default=0,
            help="Zero-based result offset (default: 0).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            metavar="COUNT",
            help="Maximum number of activities to return (default: 20).",
        )
        parser.add_argument(
            "--start-date",
            metavar="DATE",
            help="Optional start date in YYYY-MM-DD format.",
        )
        parser.add_argument(
            "--end-date",
            metavar="DATE",
            help="Optional end date in YYYY-MM-DD format.",
        )
        parser.add_argument(
            "--activity-type",
            metavar="TYPE",
            help="Optional activity type filter. " \
            "Available types can be discovered using the 'activity-types' command. " \
            "Only parent activity types are valid.",
        )
    elif spec.input_kind == "activity":
        parser.add_argument(
            "activity_id",
            metavar="ACTIVITY_ID",
            help=(
                "Activity ID to download."
                if spec.output_kind == "download"
                else "Activity ID to look up."
            ),
        )
    if spec.output_kind == "download":
        parser.add_argument(
            "-o",
            "--output",
            metavar="PATH",
            help="Save ZIP to PATH (default: activity-ID.zip); '-' writes binary stdout.",
        )
        parser.add_argument("--force", action="store_true", help="Replace an existing output file.")


def main(argv: Sequence[str] | None = None) -> int:
    """Authenticate once, then execute a command or open the interactive menu."""
    args = build_parser().parse_args(argv)
    interactive = args.command is None
    refresh_only = args.command == TOKEN_REFRESH_COMMAND
    if interactive and not _ensure_interactive_dependency():
        return 1
    _configure_logging(quiet=args.quiet or interactive)
    color = False if args.no_color else None

    try:
        download = (
            not interactive
            and not refresh_only
            and COMMANDS_BY_NAME[args.command].output_kind == "download"
        )
        if download and args.output == "-" and sys.stdout.isatty():
            raise GarminPersonalApiError("Refusing to write ZIP bytes to a terminal; use -o PATH")
        log_output = (
            _route_logs_to_status(output=sys.stdout, color=color) if interactive else nullcontext()
        )
        with log_output:
            api_key = resolve_api_key(args.api_key, key_file=args.api_key_file)
            with PersonalApiAuthenticator(
                timeout=args.timeout,
                bearer_token_cache_file=args.bearer_token_cache_file,
            ) as authenticator:
                if interactive:
                    print_heading("Garmin Personal API", output=sys.stdout, width=56, color=color)
                    print_request_status(
                        "Checking bearer-token cache",
                        output=sys.stdout,
                        color=color,
                    )
                token = authenticator.obtain_token(api_key, force_refresh=refresh_only)
                if refresh_only:
                    expires_at = datetime.fromtimestamp(token.expires_at).astimezone()
                    print(
                        "Cached a new bearer token that expires at "
                        f"{expires_at.isoformat(timespec='seconds')}",
                        file=sys.stderr,
                    )
                    return 0
                with GarminPersonalApiClient(token.access_token, timeout=args.timeout) as client:
                    if interactive:

                        def refresh_token() -> None:
                            refreshed = authenticator.obtain_token(api_key, force_refresh=True)
                            client.update_bearer_token(refreshed.access_token)

                        return run_interactive(
                            client,
                            color=color,
                            show_header=False,
                            refresh_token=refresh_token,
                        )
                    result = _execute_command(client, args)
                    if download:
                        if not isinstance(result, bytes):
                            raise GarminPersonalApiError("Expected binary download content")
                        if args.output == "-":
                            sys.stdout.buffer.write(result)
                            sys.stdout.buffer.flush()
                        else:
                            destination = save_download(
                                result,
                                Path(args.output or f"activity-{args.activity_id}.zip"),
                                overwrite=args.force,
                            )
                            print(f"Saved {destination} ({len(result)} bytes)", file=sys.stderr)
                        return 0
    except (GarminPersonalApiError, requests.RequestException, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _print_json(result)
    return 0


def _execute_command(client: GarminPersonalApiClient, args: argparse.Namespace) -> Any:
    spec = COMMANDS_BY_NAME[args.command]
    method = partial(spec.method, client)
    if spec.input_kind == "date":
        return method(args.date)
    if spec.input_kind == "date_with_today":
        return method(args.date, args.today_date)
    if spec.input_kind == "date_range":
        if spec.command == "body-battery":
            return method(args.start_date, args.end_date, chunks=args.chunks)
        if spec.command == "vo2-max":
            return method(args.start_date, args.end_date, sport=args.sport)
        return method(args.start_date, args.end_date)
    if spec.input_kind == "activities":
        return method(
            start=args.start,
            limit=args.limit,
            start_date=args.start_date,
            end_date=args.end_date,
            activity_type=args.activity_type,
        )
    if spec.input_kind == "activity":
        return method(args.activity_id)
    return method()


def _ensure_interactive_dependency() -> bool:
    try:
        importlib.import_module("rich")
    except ImportError:
        print(
            "Interactive mode requires the optional 'rich' dependency. "
            "Install it with: pip install 'garmin-connect-personal-api-python[interactive]'",
            file=sys.stderr,
        )
        return False
    return True


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def _configure_logging(*, quiet: bool) -> None:
    """Configure this package's logger without replacing application handlers."""
    level = logging.WARNING if quiet else logging.INFO
    logging.getLogger(__package__).setLevel(level)
    if not logging.root.handlers:
        logging.basicConfig(level=level, format="%(levelname)s %(message)s")
