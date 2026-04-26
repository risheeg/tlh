"""D1-backed Gemini quota ledger and pre-flight checks.

RPD (requests per day) matches the Gemini API: quotas **reset at midnight
Pacific time** (per project), not a rolling 24-hour window. See
https://ai.google.dev/gemini-api/docs/rate-limits
"""

import random
from datetime import date, datetime, timedelta, timezone

from util.js_interop import js_to_py

DEFAULT_EXPECTED_CALLS = 1
_COUNTED_OUTCOMES = ("ok", "rate_limit", "transient")

_PST = timezone(timedelta(hours=-8))
_PDT = timezone(timedelta(hours=-7))

_RPM_WINDOW_SECONDS = 65
_MIN_RPM_WAIT_SECONDS = 15
_MIN_RPD_WAIT_SECONDS = 10
_MAX_QUEUE_DELAY_SECONDS = 24 * 3600
_RPD_JITTER_MAX_SECONDS = 120
_RPM_JITTER_MAX_SECONDS = 30


def _day_of_nth_weekday_of_month(year, month, weekday, n):
    c = 0
    for d in range(1, 32):
        try:
            if date(year, month, d).weekday() == weekday:
                c += 1
                if c == n:
                    return d
        except ValueError:
            break
    raise ValueError("nth weekday not found")


def _spring_forward_utc_aware(year):
    d = _day_of_nth_weekday_of_month(year, 3, 6, 2)
    return datetime(year, 3, d, 2, 0, 0, tzinfo=_PST).astimezone(timezone.utc)


def _fall_back_utc_aware(year):
    d = _day_of_nth_weekday_of_month(year, 11, 6, 1)
    return datetime(year, 11, d, 2, 0, 0, tzinfo=_PDT).astimezone(timezone.utc)


def _pacific_in_dst(utc):
    utc = utc.astimezone(timezone.utc)
    y = utc.year
    for yr in (y - 1, y, y + 1):
        sp = _spring_forward_utc_aware(yr)
        fl = _fall_back_utc_aware(yr)
        if sp <= utc < fl:
            return True
    return False


def _pacific_utc_offset_hours(utc):
    return 7 if _pacific_in_dst(utc) else 8


def _pacific_date_from_utc(utc):
    u = utc.astimezone(timezone.utc)
    off = _pacific_utc_offset_hours(u)
    naive_utc = u.replace(tzinfo=None)
    nlu = naive_utc - timedelta(hours=off)
    return nlu.date()


def _pacific_midnight_utc(d):
    y, m, day = d.year, d.month, d.day
    for z in (_PST, _PDT):
        tloc = datetime(y, m, day, 0, 0, 0, tzinfo=z)
        u = tloc.astimezone(timezone.utc)
        if u.astimezone(z) != tloc:
            continue
        off = _pacific_utc_offset_hours(u)
        nlu = u.replace(tzinfo=None) - timedelta(hours=off)
        if nlu.date() == d and nlu.hour == 0 and nlu.minute == 0 and nlu.second == 0:
            return u
    raise RuntimeError(f"pacific midnight not found for {d!r}")


def _jittered_delay_capped(base_seconds, jitter_max):
    base_seconds = max(0, int(base_seconds))
    j = random.randint(0, jitter_max) if jitter_max > 0 else 0
    return min(base_seconds + j, _MAX_QUEUE_DELAY_SECONDS)


def _now_utc():
    return datetime.now(timezone.utc)


def _iso(dt):
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _parse_iso(value):
    if not value:
        return None
    try:
        s = str(value).rstrip("Z")
        if "." in s:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _pt_day_start_end_utc_iso(now_utc):
    u = now_utc.astimezone(timezone.utc)
    d = _pacific_date_from_utc(u)
    start_utc = _pacific_midnight_utc(d)
    end_utc = _pacific_midnight_utc(d + timedelta(days=1))
    return _iso(start_utc), _iso(end_utc)


def _seconds_until_next_pt_midnight_utc(now_utc):
    u = now_utc.astimezone(timezone.utc)
    d = _pacific_date_from_utc(u)
    m_next = _pacific_midnight_utc(d + timedelta(days=1))
    return max(0, int((m_next.replace(tzinfo=None) - u.replace(tzinfo=None)).total_seconds()) + 3)


async def check_gemini_quota(db, *, rpm_limit, rpd_limit, model=None, expected_calls=DEFAULT_EXPECTED_CALLS):
    if rpm_limit <= 0 or rpd_limit <= 0:
        return True, 0, "quota_disabled"
    now = _now_utc()
    day_start_iso, day_end_iso = _pt_day_start_end_utc_iso(now)
    rpd_count = await _count_calls_in_pt_day(db, day_start_iso, day_end_iso, model=model)
    if rpd_count + expected_calls > rpd_limit:
        wait = _seconds_until_next_pt_midnight_utc(now)
        wait = max(_MIN_RPD_WAIT_SECONDS, min(wait, _MAX_QUEUE_DELAY_SECONDS))
        wait = _jittered_delay_capped(wait, _RPD_JITTER_MAX_SECONDS)
        scope = model or "all_models"
        return False, wait, f"rpd_exhausted ({scope}: {rpd_count}/{rpd_limit})"
    minute_cutoff_iso = _iso(now - timedelta(seconds=_RPM_WINDOW_SECONDS))
    row = await _count_recent_calls(db, minute_cutoff_iso, model=model)
    rpm_count = int(row.get("c") or 0)
    if rpm_count + expected_calls > rpm_limit:
        oldest = _parse_iso(row.get("oldest"))
        if oldest is not None:
            wait = int((oldest + timedelta(seconds=_RPM_WINDOW_SECONDS + 2) - now).total_seconds())
        else:
            wait = _RPM_WINDOW_SECONDS
        wait = max(_MIN_RPM_WAIT_SECONDS, wait)
        wait = _jittered_delay_capped(wait, _RPM_JITTER_MAX_SECONDS)
        scope = model or "all_models"
        return False, wait, f"rpm_exhausted ({scope}: {rpm_count}/{rpm_limit})"
    return True, 0, "ok"


async def record_gemini_call(db, *, model="", outcome="ok"):
    try:
        await db.prepare(
            "INSERT INTO gemini_request_log (called_at, model, outcome) VALUES (?, ?, ?)"
        ).bind(_iso(_now_utc()), model or "", outcome or "ok").run()
    except Exception as exc:
        print(f"gemini_quota: failed to record call ({outcome}): {exc!s}")


async def _count_calls_in_pt_day(db, day_start_iso, day_end_iso, *, model=None):
    outcomes_sql = ",".join(f"'{x}'" for x in _COUNTED_OUTCOMES)
    if model:
        row = await db.prepare(
            "SELECT COUNT(*) AS c FROM gemini_request_log "
            f"WHERE called_at >= ? AND called_at < ? AND outcome IN ({outcomes_sql}) AND model = ?"
        ).bind(day_start_iso, day_end_iso, model).first()
    else:
        row = await db.prepare(
            "SELECT COUNT(*) AS c FROM gemini_request_log "
            f"WHERE called_at >= ? AND called_at < ? AND outcome IN ({outcomes_sql})"
        ).bind(day_start_iso, day_end_iso).first()
    return int((js_to_py(row) or {}).get("c") or 0)


async def _count_recent_calls(db, cutoff_iso, *, model=None):
    outcomes_sql = ",".join(f"'{x}'" for x in _COUNTED_OUTCOMES)
    if model:
        row = await db.prepare(
            "SELECT COUNT(*) AS c, MIN(called_at) AS oldest "
            "FROM gemini_request_log "
            f"WHERE called_at >= ? AND outcome IN ({outcomes_sql}) AND model = ?"
        ).bind(cutoff_iso, model).first()
    else:
        row = await db.prepare(
            "SELECT COUNT(*) AS c, MIN(called_at) AS oldest "
            "FROM gemini_request_log "
            f"WHERE called_at >= ? AND outcome IN ({outcomes_sql})"
        ).bind(cutoff_iso).first()
    return js_to_py(row) or {}
