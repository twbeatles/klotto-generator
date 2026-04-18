import datetime as dt
from typing import Any, Dict, Iterable, List, Mapping, Optional
from zoneinfo import ZoneInfo

from klotto.core.lotto_rules import safe_int

try:
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = dt.timezone(dt.timedelta(hours=9), name="Asia/Seoul")
DRAW_BASE_DATE = dt.date(2002, 12, 7)
DRAW_OPEN_HOUR_KST = 21


def _coerce_kst_datetime(now: Optional[dt.datetime] = None) -> dt.datetime:
    current = now or dt.datetime.now(tz=KST)
    if current.tzinfo is None:
        return current.replace(tzinfo=KST)
    return current.astimezone(KST)


def estimate_latest_draw(now: Optional[dt.datetime] = None) -> int:
    """Estimate the latest available draw using the Saturday 21:00 KST draw schedule."""
    current = _coerce_kst_datetime(now)
    today = current.date()
    days_diff = (today - DRAW_BASE_DATE).days
    estimated_draw = days_diff // 7 + 1
    if current.weekday() == 5 and current.hour < DRAW_OPEN_HOUR_KST:
        estimated_draw -= 1
    return max(1, estimated_draw)


def split_missing_draws(
    existing_draws: Iterable[int],
    latest_draw: int,
    *,
    current_draw: Optional[int] = None,
    recent_window: int = 20,
    allowed_missing: Iterable[int] = (),
) -> Dict[str, List[int]]:
    normalized_latest = max(0, int(latest_draw or 0))
    if normalized_latest <= 0:
        return {"all": [], "recent": [], "historical": []}

    existing = {int(draw_no) for draw_no in existing_draws if int(draw_no) > 0}
    allowed = {int(draw_no) for draw_no in allowed_missing if int(draw_no) > 0}
    current = max(normalized_latest, int(current_draw or normalized_latest))
    recent_start = max(1, current - max(0, int(recent_window or 0)))
    missing_all = [draw_no for draw_no in range(1, normalized_latest + 1) if draw_no not in existing and draw_no not in allowed]
    recent_missing = [draw_no for draw_no in missing_all if draw_no >= recent_start]
    historical_missing = [draw_no for draw_no in missing_all if draw_no < recent_start]
    return {
        "all": missing_all,
        "recent": recent_missing,
        "historical": historical_missing,
    }


def format_draw_date(date_str: str) -> str:
    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str


def convert_new_api_response(payload: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert the current API response shape into the legacy widget payload."""
    try:
        data_list = payload.get("data", {}).get("list", [])
        if not data_list:
            return None

        item = data_list[0]
        return {
            "returnValue": "success",
            "drwNo": item.get("ltEpsd"),
            "drwNoDate": format_draw_date(str(item.get("ltRflYmd", ""))),
            "drwtNo1": item.get("tm1WnNo"),
            "drwtNo2": item.get("tm2WnNo"),
            "drwtNo3": item.get("tm3WnNo"),
            "drwtNo4": item.get("tm4WnNo"),
            "drwtNo5": item.get("tm5WnNo"),
            "drwtNo6": item.get("tm6WnNo"),
            "bnusNo": item.get("bnsWnNo"),
            "firstWinamnt": item.get("rnk1WnAmt", 0),
            "firstPrzwnerCo": item.get("rnk1WnNope", 0),
            "totSellamnt": item.get("rlvtEpsdSumNtslAmt", 0),
        }
    except Exception:
        return None


def normalize_legacy_draw_payload(payload: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize the legacy widget payload into a canonical draw record."""
    draw_no = safe_int(payload.get("drwNo"))
    numbers = [
        safe_int(payload.get("drwtNo1")),
        safe_int(payload.get("drwtNo2")),
        safe_int(payload.get("drwtNo3")),
        safe_int(payload.get("drwtNo4")),
        safe_int(payload.get("drwtNo5")),
        safe_int(payload.get("drwtNo6")),
    ]
    bonus = safe_int(payload.get("bnusNo"))
    if draw_no <= 0 or any(number < 1 or number > 45 for number in numbers) or bonus < 1 or bonus > 45:
        return None

    date_value = payload.get("drwNoDate")
    return {
        "draw_no": draw_no,
        "date": date_value if isinstance(date_value, str) else "",
        "numbers": numbers,
        "bonus": bonus,
        "first_prize": safe_int(payload.get("firstWinamnt")),
        "first_winners": safe_int(payload.get("firstPrzwnerCo")),
        "total_sales": safe_int(payload.get("totSellamnt")),
    }


__all__ = [
    "DRAW_BASE_DATE",
    "DRAW_OPEN_HOUR_KST",
    "KST",
    "_coerce_kst_datetime",
    "convert_new_api_response",
    "estimate_latest_draw",
    "format_draw_date",
    "normalize_legacy_draw_payload",
    "split_missing_draws",
]
