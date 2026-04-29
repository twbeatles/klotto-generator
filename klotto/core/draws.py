import datetime
from typing import Any, Dict, Mapping, Optional

from klotto.core.lotto_rules import safe_int


KST = datetime.timezone(datetime.timedelta(hours=9))


def _to_kst(now: Optional[datetime.datetime]) -> datetime.datetime:
    if now is None:
        return datetime.datetime.now(KST)
    if now.tzinfo is None:
        return now.replace(tzinfo=KST)
    return now.astimezone(KST)


def estimate_latest_draw(now: Optional[datetime.datetime] = None) -> int:
    """Estimate the latest available draw based on the Korean weekly draw schedule."""
    current = _to_kst(now)
    base_date = datetime.date(2002, 12, 7)
    today = current.date()
    days_diff = (today - base_date).days
    estimated_draw = days_diff // 7 + 1
    if today.weekday() == 5 and current.hour < 22:
        estimated_draw -= 1
    return max(1, estimated_draw)


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
    "convert_new_api_response",
    "estimate_latest_draw",
    "format_draw_date",
    "normalize_legacy_draw_payload",
]
