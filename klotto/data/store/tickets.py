from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast
from uuid import uuid4

from klotto.config import APP_CONFIG
from klotto.core.lotto_rules import calculate_rank, normalize_numbers, normalize_positive_int, safe_int
from klotto.core.pension720_engine import normalize_pension720_request
from klotto.core.pension720_strategy_catalog import create_default_pension720_strategy_request
from klotto.core.strategy_catalog import create_default_strategy_request
from klotto.core.strategy_filters import sanitize_filters
from klotto.data.pension720 import normalize_six_digits
from klotto.data.store_utils import load_json_data, save_json_atomic
from klotto.logging import logger
from klotto.net.http import normalize_proxy_url
from klotto.data.store.api import StoreAPI



class TicketStoreMixin(StoreAPI):
    def get_winning_draw_by_no(self, winning_data: Sequence[Dict[str, Any]], draw_no: int) -> Optional[Dict[str, Any]]:
        target_draw_no = max(1, int(draw_no or 0))
        for draw in winning_data:
            if int(draw.get('draw_no', 0)) == target_draw_no:
                return draw
        return None

    def settle_ticket_entry_if_possible(self, ticket: Dict[str, Any], winning_data: Sequence[Dict[str, Any]]) -> bool:
        if not ticket or ticket.get('checked'):
            return False
        target_draw_no = int(ticket.get('targetDrawNo') or 0)
        if target_draw_no <= 0 or not winning_data:
            return False
        latest_draw_no = max(int(draw.get('draw_no', 0)) for draw in winning_data)
        if target_draw_no > latest_draw_no:
            return False
        draw = self.get_winning_draw_by_no(winning_data, target_draw_no)
        if not draw:
            return False
        winning_numbers = normalize_numbers(draw.get('numbers'))
        bonus = normalize_positive_int(draw.get('bonus'))
        ticket_numbers = normalize_numbers(ticket.get('numbers'))
        if not winning_numbers or ticket_numbers is None or bonus is None:
            return False
        matched = len(set(ticket_numbers) & set(winning_numbers))
        rank = calculate_rank(matched, bonus in ticket_numbers)
        ticket['checked'] = {
            'drawNo': target_draw_no,
            'rank': 0 if rank is None else rank,
            'checkedAt': dt.datetime.now().isoformat(),
        }
        return True

    def settle_tickets_if_possible(self, tickets: Sequence[Dict[str, Any]], winning_data: Sequence[Dict[str, Any]]) -> int:
        settled = 0
        for ticket in tickets:
            if self.settle_ticket_entry_if_possible(ticket, winning_data):
                settled += self.get_ticket_quantity(ticket)
        return settled

    def add_ticket(self, numbers: Sequence[int], *, source: str = 'import', target_draw_no: int = 0, campaign_id: str = '', strategy_request: Optional[Dict[str, Any]] = None, memo: str = '', winning_data: Optional[Sequence[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        normalized = normalize_numbers(numbers)
        target = normalize_positive_int(target_draw_no)
        if not normalized or target is None:
            return None
        ticket = self.normalize_ticket_entry({
            'numbers': normalized,
            'targetDrawNo': target,
            'source': source,
            'campaignId': campaign_id,
            'strategyRequest': strategy_request,
            'memo': memo,
            'quantity': 1,
        })
        if not ticket:
            return None
        key = self.build_ticket_key(ticket)
        for current in self.state['ticketBook']:
            if self.build_ticket_key(current) == key:
                current['quantity'] = self.normalize_ticket_quantity(self.get_ticket_quantity(current) + 1)
                if winning_data:
                    self.settle_tickets_if_possible([current], winning_data)
                self.save()
                return {'ticket': current, 'inserted': False, 'incremented': True, 'quantity': current['quantity']}
        self.state['ticketBook'].insert(0, ticket)
        if winning_data:
            self.settle_tickets_if_possible([ticket], winning_data)
        self.save()
        return {'ticket': ticket, 'inserted': True, 'incremented': False, 'quantity': ticket['quantity']}

    def add_tickets_bulk(self, items: Sequence[Any], *, winning_data: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, int]:
        key_to_ticket = {self.build_ticket_key(ticket): ticket for ticket in self.state['ticketBook']}
        inserted_rows = 0
        incremented_rows = 0
        added_quantity = 0
        touched: List[Dict[str, Any]] = []
        for raw in items:
            ticket = self.normalize_ticket_entry(raw)
            if not ticket:
                continue
            key = self.build_ticket_key(ticket)
            quantity = self.get_ticket_quantity(ticket)
            added_quantity += quantity
            if key in key_to_ticket:
                current = key_to_ticket[key]
                current['quantity'] = self.normalize_ticket_quantity(self.get_ticket_quantity(current) + quantity)
                touched.append(current)
                incremented_rows += 1
            else:
                self.state['ticketBook'].insert(0, ticket)
                key_to_ticket[key] = ticket
                touched.append(ticket)
                inserted_rows += 1
        if touched and winning_data:
            self.settle_tickets_if_possible(touched, winning_data)
        if inserted_rows or incremented_rows:
            self.save()
        return {
            'insertedRows': inserted_rows,
            'incrementedRows': incremented_rows,
            'addedQuantity': added_quantity,
            'affectedRows': inserted_rows + incremented_rows,
        }

    def remove_ticket(self, ticket_id: str) -> bool:
        before = len(self.state['ticketBook'])
        self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if ticket.get('id') != ticket_id]
        removed = before != len(self.state['ticketBook'])
        if removed:
            self.prune_orphan_campaigns(save=False)
            self.save()
        return removed

    def clear_ticket_book(self, filter_name: str = 'all') -> int:
        def is_pending(ticket: Dict[str, Any]) -> bool:
            return not ticket.get('checked')

        def is_win(ticket: Dict[str, Any]) -> bool:
            return bool(ticket.get('checked')) and int(ticket['checked'].get('rank', 0)) > 0

        def is_lose(ticket: Dict[str, Any]) -> bool:
            return bool(ticket.get('checked')) and int(ticket['checked'].get('rank', 0)) == 0

        before = self.get_total_ticket_count()
        if filter_name == 'pending':
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if not is_pending(ticket)]
        elif filter_name == 'win':
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if not is_win(ticket)]
        elif filter_name == 'lose':
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if not is_lose(ticket)]
        else:
            self.state['ticketBook'] = []
        removed = before - self.get_total_ticket_count()
        self.prune_orphan_campaigns(save=False)
        self.save()
        return removed

