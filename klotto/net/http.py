from __future__ import annotations

import urllib.request
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from klotto.config import APP_CONFIG, DHLOTTERY_API_URL

LOTTO_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.dhlottery.co.kr/lt645/result",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
}


def normalize_proxy_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path or "", "", ""))


def build_url_opener(proxy_url: str = "") -> urllib.request.OpenerDirector:
    normalized = normalize_proxy_url(proxy_url)
    if not normalized:
        return urllib.request.build_opener()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler(
            {
                "http": normalized,
                "https": normalized,
            }
        )
    )


def fetch_text(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: int | None = None,
    proxy_url: str = "",
) -> str:
    request = urllib.request.Request(url, headers=dict(headers or {}))
    opener = build_url_opener(proxy_url)
    with opener.open(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_lotto_api_text(draw_no: int, *, proxy_url: str = "") -> str:
    return fetch_text(
        DHLOTTERY_API_URL.format(draw_no),
        headers=LOTTO_API_HEADERS,
        timeout=int(APP_CONFIG["API_TIMEOUT"]),
        proxy_url=proxy_url,
    )


__all__ = [
    "LOTTO_API_HEADERS",
    "build_url_opener",
    "fetch_lotto_api_text",
    "fetch_text",
    "normalize_proxy_url",
]
