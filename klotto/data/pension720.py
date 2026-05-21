from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from klotto.config import APP_CONFIG
from klotto.net.http import fetch_text

PENSION720_OFFICIAL_LIST_URL = 'https://www.dhlottery.co.kr/pt720/selectPstPt720WnList.do'

PENSION720_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 klotto-generator pension720 sync',
}


def normalize_pension720_date(raw_value: Any = '') -> str:
    raw = str(raw_value or '').strip()
    normalized = f'{raw[:4]}-{raw[4:6]}-{raw[6:8]}' if re.fullmatch(r'\d{8}', raw) else raw
    try:
        parsed = dt.date.fromisoformat(normalized)
    except ValueError:
        return ''
    return parsed.isoformat()


def normalize_six_digits(raw_value: Any = '') -> Optional[Dict[str, Any]]:
    text = str(raw_value if raw_value is not None else '').strip()
    if not re.fullmatch(r'\d{6}', text):
        return None
    return {'number': text, 'digits': [int(char) for char in text]}


def normalize_pension720_draw(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    draw_value = raw.get('draw_no')
    if draw_value is None:
        draw_value = raw.get('psltEpsd')
    group_value = raw.get('group')
    if group_value is None:
        group_value = raw.get('wnBndNo')
    try:
        draw_no = int(str(draw_value))
        group = int(str(group_value))
    except (TypeError, ValueError):
        return None
    primary = normalize_six_digits(raw.get('number', raw.get('wnRnkVl')))
    bonus = normalize_six_digits(raw.get('bonus_number', raw.get('bnsRnkVl')))
    date = normalize_pension720_date(raw.get('date', raw.get('psltRflYmd')))
    if draw_no < 1 or group < 1 or group > 5 or not primary or not bonus or not date:
        return None
    return {
        'draw_no': draw_no,
        'date': date,
        'group': group,
        'digits': primary['digits'],
        'number': primary['number'],
        'bonus_digits': bonus['digits'],
        'bonus_number': bonus['number'],
    }


def extract_pension720_list(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get('data')
        if isinstance(data, dict) and isinstance(data.get('result'), list):
            return list(data['result'])
        if isinstance(payload.get('result'), list):
            return list(payload['result'])
    return []


def normalize_pension720_stats(items: Any) -> List[Dict[str, Any]]:
    by_draw: Dict[int, Dict[str, Any]] = {}
    source_items = extract_pension720_list(items)
    for item in source_items:
        normalized = normalize_pension720_draw(item)
        if normalized:
            by_draw[int(normalized['draw_no'])] = normalized
    return sorted(by_draw.values(), key=lambda row: int(row['draw_no']), reverse=True)


def get_bundled_pension720_path() -> Path:
    return Path(APP_CONFIG.get('PENSION720_STATS_FILE') or (Path(__file__).resolve().parent.parent.parent / 'data' / 'pension720_stats.json'))


def load_pension720_static_data(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    target = path or get_bundled_pension720_path()
    if not target.exists():
        return []
    with target.open('r', encoding='utf-8') as handle:
        return normalize_pension720_stats(json.load(handle))


def fetch_pension720_official_stats(*, proxy_url: str = '') -> List[Dict[str, Any]]:
    raw = fetch_text(
        PENSION720_OFFICIAL_LIST_URL,
        headers=PENSION720_HEADERS,
        timeout=int(APP_CONFIG['API_TIMEOUT']),
        proxy_url=proxy_url,
    )
    return normalize_pension720_stats(json.loads(raw))


def count_trailing_matches(left: Any = '', right: Any = '') -> int:
    a = str(left or '')
    b = str(right or '')
    count = 0
    for offset in range(1, 7):
        if len(a) < offset or len(b) < offset or a[-offset] != b[-offset]:
            break
        count += 1
    return count


def evaluate_pension720_ticket(ticket: Any, draw: Any) -> Optional[Dict[str, Any]]:
    normalized_draw = normalize_pension720_draw(draw)
    if not isinstance(ticket, dict) or not normalized_draw:
        return None
    try:
        group = int(str(ticket.get('group')))
    except (TypeError, ValueError):
        return None
    number = normalize_six_digits(ticket.get('number'))
    if group < 1 or group > 5 or not number:
        return None

    base = {
        'drawNo': normalized_draw['draw_no'],
        'date': normalized_draw['date'],
        'group': group,
        'number': number['number'],
        'rank': 0,
        'label': '낙첨',
        'prizeLabel': '-',
        'trailingMatches': 0,
        'matchType': 'none',
    }

    if group == normalized_draw['group'] and number['number'] == normalized_draw['number']:
        return {
            **base,
            'rank': 1,
            'label': '1등',
            'prizeLabel': '월 700만 원 x 20년',
            'trailingMatches': 7,
            'matchType': 'primary',
        }

    if number['number'] == normalized_draw['bonus_number']:
        return {
            **base,
            'rank': 'bonus',
            'label': '보너스',
            'prizeLabel': '월 100만 원 x 10년',
            'trailingMatches': 6,
            'matchType': 'bonus',
        }

    trailing = count_trailing_matches(number['number'], normalized_draw['number'])
    prize_by_match = {
        6: (2, '2등', '월 100만 원 x 10년'),
        5: (3, '3등', '100만 원'),
        4: (4, '4등', '10만 원'),
        3: (5, '5등', '5만 원'),
        2: (6, '6등', '5천 원'),
        1: (7, '7등', '1천 원'),
    }
    if trailing in prize_by_match:
        rank, label, prize = prize_by_match[trailing]
        return {
            **base,
            'rank': rank,
            'label': label,
            'prizeLabel': prize,
            'trailingMatches': trailing,
            'matchType': 'primary',
        }
    return {**base, 'trailingMatches': trailing}


def resolve_pension720_ticket_check(ticket: Dict[str, Any], stats: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_stats = normalize_pension720_stats(list(stats))
    latest = normalized_stats[0] if normalized_stats else None
    latest_draw_no = int(latest.get('draw_no', 0)) if latest else 0
    target_draw_no = int(ticket.get('targetDrawNo') or 0)

    if target_draw_no >= 1:
        if not latest_draw_no or target_draw_no > latest_draw_no:
            return {
                'ticket': ticket,
                'status': 'pending',
                'statusLabel': '대기',
                'checkBasis': 'target',
                'drawNo': target_draw_no,
                'draw': None,
                'result': None,
            }
        draw = next((row for row in normalized_stats if int(row.get('draw_no', 0)) == target_draw_no), None)
        if not draw:
            return {
                'ticket': ticket,
                'status': 'missing',
                'statusLabel': '데이터 없음',
                'checkBasis': 'target',
                'drawNo': target_draw_no,
                'draw': None,
                'result': None,
            }
        return {
            'ticket': ticket,
            'status': 'target',
            'statusLabel': '대상 회차',
            'checkBasis': 'target',
            'drawNo': target_draw_no,
            'draw': draw,
            'result': evaluate_pension720_ticket(ticket, draw),
        }

    return {
        'ticket': ticket,
        'status': 'reference',
        'statusLabel': '참고 비교',
        'checkBasis': 'latest_reference',
        'drawNo': latest_draw_no or None,
        'draw': latest,
        'result': evaluate_pension720_ticket(ticket, latest) if latest else None,
    }


def protect_spreadsheet_formula(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return f"'{value}" if value.startswith(('=', '+', '-', '@')) else value


def build_pension720_ticket_csv(tickets: Iterable[Dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['group', 'number', 'targetDrawNo', 'campaignId', 'source', 'score', 'memo', 'createdAt'])
    for ticket in tickets:
        writer.writerow(
            [
                ticket.get('group', ''),
                str(ticket.get('number') or ''),
                ticket.get('targetDrawNo') or '',
                ticket.get('campaignId') or '',
                ticket.get('source') or '',
                ticket.get('score') or 0,
                protect_spreadsheet_formula(str(ticket.get('memo') or '')),
                ticket.get('createdAt') or '',
            ]
        )
    return output.getvalue()


__all__ = [
    'PENSION720_HEADERS',
    'PENSION720_OFFICIAL_LIST_URL',
    'build_pension720_ticket_csv',
    'count_trailing_matches',
    'evaluate_pension720_ticket',
    'fetch_pension720_official_stats',
    'get_bundled_pension720_path',
    'load_pension720_static_data',
    'normalize_pension720_date',
    'normalize_pension720_draw',
    'normalize_pension720_stats',
    'normalize_six_digits',
    'protect_spreadsheet_formula',
    'resolve_pension720_ticket_check',
]
