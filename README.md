# Garmin Connect Personal API Client

A small Python client for reading data from [Garmin's Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api). It is a
concrete example of how to query Garmin data using Personal API
authentication, and other projects can reuse its parts independently:

- `PersonalApiAuthenticator` caches bearer tokens and exchanges a Personal API
  key for a new token when needed.
- `GarminPersonalApiClient` makes authenticated GET requests with any bearer
  token and provides convenience wrappers for Personal API data sets.
- `gc-personal` is a command-line interface built on those same wrappers. Its
  direct commands work in scripts and one-off queries, and an optional
  interactive menu is included for demonstrating and exploring the data.

## Requirements and installation

You need Python 3.12 or newer and a Garmin Connect Personal API key. The
package installs `requests` automatically.

Create a virtual environment, activate it, and install the package:

```shell
python3 -m venv .venv
source .venv/bin/activate
python -m pip install garmin-connect-personal-api-python
```

On Windows, create and activate the environment with:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install garmin-connect-personal-api-python
```

The base package supports authentication, data access, and direct CLI
commands. Install the optional `interactive` extra to add `rich`, which
interactive mode requires:

```shell
python -m pip install 'garmin-connect-personal-api-python[interactive]'
```

### Install from source

To install without PyPI, run one of these commands from a clone of this
repository:

```shell
python -m pip install .                 # library and direct CLI commands
python -m pip install '.[interactive]'  # adds interactive mode
python -m pip install -e '.[dev]'       # editable, with interactive mode and dev tools
```

## Authentication

The package does not create Personal API keys. Create a key on
[Garmin Connect](https://connect.garmin.com/app/settings/personalApiToken).

### Command-line key sources

`gc-personal` reads the key from one of these sources:

1. **Key file:** `~/.config/garmin/connect-personal-api-key`, or another path
   passed with `--api-key-file`. On Windows, `~` is your user profile folder
   (`%USERPROFILE%`). The file should contain only the API key; surrounding
   whitespace, including a trailing newline, is ignored.
2. **Environment variable:** `GARMIN_PERSONAL_API_KEY`.
3. **Command-line argument:** `--api-key`.

If more than one source is provided, precedence is:

1. Explicit key: `--api-key`.
2. Explicit key file: `--api-key-file`, even if it names the default path.
3. Environment variable: `GARMIN_PERSONAL_API_KEY`.
4. Default key file, when neither explicit option nor the environment variable
   supplies a key.

A missing, unreadable, or empty explicitly selected file is an error, not a
reason to fall back to the environment or default file. An empty explicit key
or environment variable is also an error. **A key passed with `--api-key` may
be exposed through shell history or the process list.**

```shell
# Use the default key file.
gc-personal profile-settings

# Use a key file at another path.
gc-personal --api-key-file ~/my-garmin-key profile-settings

# Use the environment variable.
export GARMIN_PERSONAL_API_KEY='your-personal-api-key'
gc-personal profile-settings

# Pass the key directly (exposed to shell history and the process list).
gc-personal --api-key 'your-personal-api-key' profile-settings
```

### Python key sources

`obtain_token()` requires an explicit key and doesn't discover one itself;
see [Explicit API key](#explicit-api-key).
To opt into key discovery, pass the result of `resolve_api_key()` to
`obtain_token()`; see [Key discovery](#key-discovery).
An explicit `api_key` takes precedence over `key_file=`, which takes precedence
over `GARMIN_PERSONAL_API_KEY`. When neither argument is supplied, discovery
checks the environment variable and then the default key file.

### Bearer-token cache

The authenticator exchanges the API key for a bearer token and caches it by
default in `~/.config/garmin/connect-personal-api-bearer-token.json`. Use
`--bearer-token-cache-file` in the CLI, or `bearer_token_cache_file` in
Python, to choose another location:

```shell
gc-personal --bearer-token-cache-file /path/to/bearer-token-cache.json profile-settings
```

A cached token is reused only when it was issued for the current API key and
has more than one hour remaining before expiration, based on the JWT `exp`
claim. Otherwise, the authenticator obtains and caches a new token. Each
direct command, interactive session, and `obtain_token()` call checks the
cache this way, so expired tokens are replaced automatically. The cache can't
be disabled.

Rarely, a token stops working before it expires, for example because it was
revoked. Requests then fail with `401`, and the client doesn't retry them. To
recover, obtain a new token:

- **Direct commands:** run `gc-personal refresh-token`, or delete the cache
  file, then rerun the command.
- **Interactive mode:** choose **Reload Bearer Token** from the menu.
- **Python:** call `obtain_token(api_key, force_refresh=True)`, then pass the
  new token's `access_token` to `client.update_bearer_token()`.

### Protecting credential files

The bearer-token cache, and the key file if you use one, hold plain-text
credentials. Keep them readable only by your user and out of version control.
On POSIX systems, the package logs a warning, but continues, when either file
is readable by group or other users. This check isn't performed on Windows.

- **Key file:** Applies only when you provide the key through a key file
  rather than the environment variable or an explicit argument. You create
  this file, and it must contain only the key. Restrict its permissions
  yourself, for example with `chmod 600`.
- **Bearer-token cache:** The authenticator creates this file with `0600`
  permissions on POSIX systems, so you don't need to set them yourself. An
  existing cache file keeps its current permissions.

## Command-line interface

Use `--help` to list every command and shared option, or add it after a
command to see that command's options and defaults:

```shell
gc-personal --help
gc-personal steps --help
```

Run `gc-personal` with a command to retrieve data, download an activity file,
or replace the cached bearer token:

```shell
gc-personal profile-settings
gc-personal sleep --date 2026-08-24
gc-personal steps --start-date 2026-08-20 --end-date 2026-08-24
gc-personal activities --start 0 --limit 20 --start-date 2026-08-01
gc-personal activity-types
gc-personal activity 123456789
gc-personal activity-workouts 123456789
gc-personal activity-download 123456789
gc-personal activity-download 123456789 -o ./run.zip
gc-personal refresh-token
gc-personal --api-key-file /path/to/key --timeout 20 --quiet profile-settings
```

Most date options default to today when omitted. Shared options such as `--api-key-file` and `--timeout` go before the command. Use
`--quiet` to suppress request logs for non-interactive commands; interactive
status lines remain visible.

Data commands print JSON to stdout. Request logs, status messages, and errors
go to stderr, so output can be piped to other tools, such as `jq`. The command
exits with a non-zero status on failure.

`activity-download` saves a ZIP file as `activity-ID.zip` in the current
directory unless `-o PATH` is given, and doesn't replace an existing file
unless you pass `--force`. Use `-o -` to write the ZIP bytes to stdout; the
command refuses to write them to a terminal.

### Interactive Mode

Interactive mode is a demonstration and data-exploration tool. Run
`gc-personal` without a command to open its menu. Interactive mode requires
the `interactive` extra. It loads the token through the same
cache-aware authentication path as direct commands, reuses it for the session,
and can force a new token to be obtained and cached from the menu.

```shell
gc-personal
```

Select an activity in the activity browser to view its details or workouts,
or choose **download activity file** to save its ZIP file. The menu
prompts for a destination and confirms before replacing an existing file.

## Library usage

The usual flow is to obtain a token, then pass it to the data client.

### Explicit API key

Pass your application's API key directly to `obtain_token()`. For example,
an application with its own secret store can use:

```python
from garmin_personal_api import (
    GarminPersonalApiClient,
    PersonalApiAuthenticator,
)

api_key = my_app_secret_manager.get("garmin-personal-api-key")
with PersonalApiAuthenticator() as authenticator:
    token = authenticator.obtain_token(api_key)

with GarminPersonalApiClient(token.access_token) as client:
    sleep = client.get_daily_sleep("2026-08-24")
    steps = client.get_daily_steps("2026-08-20", "2026-08-24")
```

`obtain_token()` returns a `BearerToken` with the token string in
`access_token` and its expiration, in seconds since the epoch, in `expires_at`.
Pass `force_refresh=True` to explicitly obtain and cache a new token.

### Key discovery

Alternatively, use `resolve_api_key()` to discover the key:

```python
from garmin_personal_api import PersonalApiAuthenticator, resolve_api_key

with PersonalApiAuthenticator() as authenticator:
    token = authenticator.obtain_token(resolve_api_key())
```

To explicitly select a key file, use
`resolve_api_key(key_file="~/my-garmin-key")`. This overrides the environment
variable, including when you explicitly select the default file path. If the
selected file is missing, unreadable, or empty, discovery raises an error
instead of trying another source.

### Bearer tokens from another source

Applications that already have a bearer token can skip the authenticator and
use the data client directly:

```python
from garmin_personal_api import GarminPersonalApiClient

with GarminPersonalApiClient(my_app_token_provider.get_token()) as client:
    profile = client.get_user_profile_settings()
```

### Configuration

Both classes accept an optional `requests.Session` and can be used as context
managers or closed explicitly.

Request activity is logged at `INFO` to the `garmin_personal_api` logger.
Configure Python logging to see it.

### Discovering activity types

`get_activity_types()` returns the available activity types as a JSON list.
Each entry has a `key` and an optional `parent`; entries without a parent omit
that field.

```python
with GarminPersonalApiClient(token.access_token) as client:
    activity_types = client.get_activity_types()
    activities = client.search_activities(activity_type="running")
```

Use a returned `key` as `activity_type`, or as the CLI's `--activity-type`
option. Run `gc-personal activity-types` or choose **Activity Types** in the
interactive menu to discover these keys. Searches don't automatically fetch
or validate against the list.

### Downloading activity files

`download_activity()` returns ZIP bytes without writing or extracting files:

```python
from pathlib import Path

with GarminPersonalApiClient(token.access_token) as client:
    content = client.download_activity(123456789)
    Path("activity-123456789.zip").write_bytes(content)
```

The whole ZIP is held in memory; streaming is not currently supported. Unlike the CLI,
`Path.write_bytes()` overwrites an existing file.

## Endpoint wrappers

The table contains every dedicated wrapper on
`GarminPersonalApiClient`. The CLI column shows the matching `gc-personal`
command. `activity`, `activity-workouts`, and `activity-download` are direct commands but are not
listed on the top-level interactive menu; see
[Interactive Mode](#interactive-mode) for how to reach them interactively.

Wrappers are added as a convenience and may lag behind new endpoints available
through Personal API. See the
[Personal API Swagger documentation](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)
for the full endpoint reference. Use `get()` for endpoints that don't have a wrapper;
see [Call an endpoint without a wrapper](#call-an-endpoint-without-a-wrapper).

| Python wrapper | CLI command | HTTP request |
| --- | --- | --- |
| `get_daily_stress(start_date, end_date)` | `stress` | `GET /usersummary-service/stats/stress/daily/{start_date}/{end_date}` |
| `get_daily_steps(start_date, end_date)` | `steps` | `GET /usersummary-service/stats/steps/daily/{start_date}/{end_date}` |
| `get_daily_hydration(start_date, end_date)` | `hydration` | `GET /usersummary-service/stats/hydration/daily/{start_date}/{end_date}` |
| `get_effective_weight_goals(start_date, end_date)` | `effective-weight-goals` | `GET /goal-service/goal/user/effective/weightgoal/{start_date}/{end_date}` |
| `get_weight_measurements(start_date, end_date)` | `weight-measurements` | `GET /weight-service/weight/range/{start_date}/{end_date}?includeAll=true` |
| `get_daily_food_logs(calendar_date)` | `food-logs` | `GET /nutrition-service/food/logs/{calendar_date}` |
| `get_user_profile_settings()` | `profile-settings` | `GET /userprofile-service/userprofile/settings` |
| `get_daily_sleep(calendar_date)` | `sleep` | `GET /sleep-service/sleep/dailySleep?date={calendar_date}` |
| `get_daily_sleep_summaries(start_date, end_date)` | `sleep-summaries` | `GET /sleep-service/sleep/dailySleepSummariesByDate?startDate={start_date}&endDate={end_date}` |
| `get_daily_body_battery(start_date, end_date, *, chunks=None)` | `body-battery` | `GET /wellness-service/wellness/bodyBattery/reports/daily?startDate={start_date}&endDate={end_date}[&chunks={chunks}]` |
| `get_daily_summaries(start_date, end_date)` | `daily-summaries` | `GET /usersummary-service/v2/dailysummaries?startDate={start_date}&endDate={end_date}` |
| `get_daily_heart_rate(calendar_date)` | `heart-rate` | `GET /wellness-service/wellness/dailyHeartRate?date={calendar_date}` |
| `get_daily_hrv(calendar_date)` | `hrv` | `GET /hrv-service/hrv/{calendar_date}` |
| `get_daily_hrv_summaries(start_date, end_date)` | `hrv-summaries` | `GET /hrv-service/hrv/daily/{start_date}/{end_date}` |
| `get_heart_rate_zones()` | `heart-rate-zones` | `GET /biometric-service/heartRateZones/v2` |
| `get_menstrual_cycle_summary(calendar_date)` | `menstrual-cycle-summary` | `GET /periodichealth-service/menstrualcycle/summary/{calendar_date}` |
| `get_menstrual_cycle_day_view(calendar_date, today_date)` | `menstrual-cycle-day-view` | `GET /periodichealth-service/menstrualcycle/dayview/{calendar_date}?todayDate={today_date}` |
| `get_fitness_age(calendar_date)` | `fitness-age` | `GET /fitnessage-service/fitnessage/v2/{calendar_date}` |
| `get_daily_spo2(calendar_date)` | `spo2` | `GET /wellness-service/wellness/daily/spo2acclimation/{calendar_date}` |
| `get_wellness_activity_summaries(start_date, end_date)` | `wellness-activity-summaries` | `GET /wellnessactivity-service/activity/summary/range/{start_date}/{end_date}` |
| `search_activities(*, start=0, limit=20, start_date=None, end_date=None, activity_type=None)` | `activities` | `GET /activitylist-service/activities/search/activities?start={start}&limit={limit}[&startDate={start_date}&endDate={end_date}&activityType={activity_type}]` |
| `get_activity_types()` | `activity-types` | `GET /activity-service/activity/activityTypes/simple` |
| `get_activity(activity_id)` | `activity` | `GET /activity-service/activity/{activity_id}` |
| `get_activity_workouts(activity_id)` | `activity-workouts` | `GET /activity-service/activity/{activity_id}/workouts` |
| `download_activity(activity_id)` | `activity-download` | `GET /download-service/files/activity/{activity_id}` (ZIP bytes) |

Dates accept `datetime.date` objects or `YYYY-MM-DD` strings. Validation of
dates, ranges, and other arguments is left to the API, except download activity
IDs, which must be positive integers.

### Call an endpoint without a wrapper

Use `GarminPersonalApiClient.get()` for another Personal API GET endpoint:

```python
with GarminPersonalApiClient(token.access_token) as client:
    custom_data = client.get(
        "/some-service/some-resource",
        params={"calendarDate": "2026-08-24"},
    )
```

The client adds bearer-token authorization and returns decoded JSON. A
successful response with no content returns `None`.

## Errors

- `GarminPersonalApiError` for missing or empty credentials, invalid local
  settings such as a non-positive timeout or an invalid download activity ID,
  an empty download response, or a token response that is not a JWT with an
  `exp` claim.
- `HttpError`, a subclass of `GarminPersonalApiError`, for unsuccessful token
  or data responses. It exposes `status_code`, `method`, `url`, and
  `response_text`.
- `OSError` when an existing key file can't be read, or the bearer-token cache
  can't be read or written, for example because of file permissions.

Network failures and invalid JSON responses raise the underlying `requests`
exceptions.

## Development

```shell
ruff check .
pyright
pytest
```

Tests use HTTP test doubles and do not require credentials or network access.

## Links

- [Garmin Connect Personal API Tokens](https://connect.garmin.com/app/settings/personalApiToken)
- [Garmin Connect Personal API overview](https://developer.garmin.com/gc-developer-program/personal/personal-api)
- [Personal API Swagger documentation](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)
  
## License

Copyright 2026 Garmin Ltd. or its subsidiaries. Distributed under the Apache
2.0 License. See [LICENSE](LICENSE) for the complete license text.
