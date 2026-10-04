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
from klotto.data.pension720 import (
    evaluate_pension720_ticket,
    normalize_pension720_stats,
    normalize_six_digits,
)
from klotto.data.store_utils import load_json_data, save_json_atomic
from klotto.logging import logger
from klotto.net.http import normalize_proxy_url
from klotto.data.store.api import StoreAPI



class Pension720StoreMixin(StoreAPI):
    def settle_pension720_ticket_if_possible(
        self, ticket: Dict[str, Any], stats: Sequence[Dict[str, Any]]
    ) -> bool:
        if not ticket or ticket.get('checked'):
            return False
        try:
            target_draw_no = int(ticket.get('targetDrawNo') or 0)
        except (TypeError, ValueError):
            return False
        if target_draw_no <= 0 or not stats:
            return False
        normalized_stats = normalize_pension720_stats(list(stats))
        if not normalized_stats:
            return False
        latest_draw_no = max(int(row.get('draw_no', 0)) for row in normalized_stats)
        if target_draw_no > latest_draw_no:
            return False
        draw = next(
            (row for row in normalized_stats if int(row.get('draw_no', 0)) == target_draw_no),
            None,
        )
        if not draw:
            return False
        result = evaluate_pension720_ticket(ticket, draw)
        if not result:
            return False
        ticket['checked'] = {
            'drawNo': target_draw_no,
            'rank': result.get('rank', 0),
            'label': str(result.get('label') or ''),
            'checkedAt': dt.datetime.now().isoformat(),
        }
        return True

    def settle_pension720_tickets_if_possible(
        self, tickets: Sequence[Dict[str, Any]], stats: Sequence[Dict[str, Any]]
    ) -> int:
        settled = 0
        for ticket in tickets or []:
            if isinstance(ticket, dict) and self.settle_pension720_ticket_if_possible(ticket, stats):
                settled += 1
        if settled:
            self.save()
        return settled

    def add_pension720_ticket(self, raw: Dict[str, Any], *, save: bool = True) -> Dict[str, Any]:
        source = raw or {}
        ticket = self.normalize_pension720_ticket({**source, 'source': source.get('source') or 'recommendation'})
        if not ticket:
            return {'inserted': False, 'duplicate': False, 'ticket': None}
        key = self.build_pension720_ticket_key(ticket)
        for current in self.state['pension720Tickets']:
            if self.build_pension720_ticket_key(current) == key:
                return {'inserted': False, 'duplicate': True, 'ticket': current}
        self.state['pension720Tickets'].insert(0, ticket)
        self.state['pension720Tickets'] = self.state['pension720Tickets'][: int(APP_CONFIG['MAX_PENSION720_TICKETS'])]
        if save:
            self.save()
        return {'inserted': True, 'duplicate': False, 'ticket': ticket}

    def add_pension720_tickets_bulk(self, items: Sequence[Any], *, save: bool = True) -> Dict[str, int]:
        before = self.merge_pension720_tickets([], self.state['pension720Tickets'])
        before_keys = {self.build_pension720_ticket_key(item) for item in before}
        normalized_incoming = [ticket for ticket in (self.normalize_pension720_ticket(item) for item in items or []) if ticket]
        incoming_keys = {self.build_pension720_ticket_key(item) for item in normalized_incoming}
        uncapped_by_key: Dict[str, Dict[str, Any]] = {}
        for item in [*before, *normalized_incoming]:
            key = self.build_pension720_ticket_key(item)
            if key not in uncapped_by_key:
                uncapped_by_key[key] = item
        uncapped_rows = sorted(uncapped_by_key.values(), key=lambda item: str(item.get('createdAt') or ''), reverse=True)
        merged = uncapped_rows[: int(APP_CONFIG['MAX_PENSION720_TICKETS'])]
        after_keys = {self.build_pension720_ticket_key(item) for item in merged}
        inserted = len([key for key in after_keys if key not in before_keys])
        duplicate = max(0, len(normalized_incoming) - len(incoming_keys) + len([key for key in incoming_keys if key in before_keys]))
        truncated = max(0, len(uncapped_rows) - int(APP_CONFIG['MAX_PENSION720_TICKETS']))
        self.state['pension720Tickets'] = merged
        if (inserted or duplicate) and save:
            self.save()
        return {'inserted': inserted, 'duplicate': duplicate, 'truncated': truncated}

    def remove_pension720_ticket(self, ticket_id: str) -> int:
        target_id = str(ticket_id or '').strip()
        before = len(self.state['pension720Tickets'])
        self.state['pension720Tickets'] = [ticket for ticket in self.state['pension720Tickets'] if ticket.get('id') != target_id]
        removed = before - len(self.state['pension720Tickets'])
        if removed:
            self.prune_pension720_campaigns_without_tickets(save=False)
            self.save()
        return removed

    def clear_pension720_tickets(self) -> int:
        removed = len(self.state['pension720Tickets'])
        self.state['pension720Tickets'] = []
        self.state['pension720Campaigns'] = []
        if removed:
            self.save()
        return removed

    def prune_pension720_campaigns_without_tickets(self, *, save: bool = True) -> Dict[str, Any]:
        linked_ids = {str(ticket.get('campaignId') or '').strip() for ticket in self.state['pension720Tickets'] if ticket.get('campaignId')}
        kept = []
        removed = []
        for campaign in self.state['pension720Campaigns']:
            campaign_id = str(campaign.get('id') or '').strip()
            if campaign_id and campaign_id in linked_ids:
                kept.append(campaign)
            else:
                removed.append(campaign)
        if removed:
            self.state['pension720Campaigns'] = kept
            if save:
                self.save()
        return {'campaigns': self.state['pension720Campaigns'], 'removed': removed}

    def add_pension720_campaign(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        campaign = self.normalize_pension720_campaign(entry)
        if not campaign:
            return None
        self.state['pension720Campaigns'] = self.merge_pension720_campaigns(self.state['pension720Campaigns'], [campaign])
        self.save()
        return campaign

    def count_pension720_tickets_by_campaign_id(self, campaign_id: str) -> int:
        target = str(campaign_id or '').strip()
        return len([ticket for ticket in self.state['pension720Tickets'] if str(ticket.get('campaignId') or '') == target])

    def remove_pension720_campaign(self, campaign_id: str, *, cascade_tickets: bool = True) -> Dict[str, Any]:
        target = str(campaign_id or '').strip()
        before_campaigns = len(self.state['pension720Campaigns'])
        self.state['pension720Campaigns'] = [campaign for campaign in self.state['pension720Campaigns'] if campaign.get('id') != target]
        removed_campaign = before_campaigns != len(self.state['pension720Campaigns'])
        removed_tickets = 0
        if cascade_tickets:
            before_tickets = len(self.state['pension720Tickets'])
            self.state['pension720Tickets'] = [ticket for ticket in self.state['pension720Tickets'] if ticket.get('campaignId') != target]
            removed_tickets = before_tickets - len(self.state['pension720Tickets'])
        if removed_campaign or removed_tickets:
            self.save()
        return {'removedCampaign': removed_campaign, 'removedTickets': removed_tickets}

    def clear_pension720_campaigns(self, *, cascade_tickets: bool = True) -> Dict[str, int]:
        campaign_ids = {str(campaign.get('id') or '') for campaign in self.state['pension720Campaigns']}
        removed_campaigns = len(campaign_ids)
        removed_tickets = 0
        self.state['pension720Campaigns'] = []
        if cascade_tickets and campaign_ids:
            before_tickets = len(self.state['pension720Tickets'])
            self.state['pension720Tickets'] = [ticket for ticket in self.state['pension720Tickets'] if str(ticket.get('campaignId') or '') not in campaign_ids]
            removed_tickets = before_tickets - len(self.state['pension720Tickets'])
        self.save()
        return {'removedCampaigns': removed_campaigns, 'removedTickets': removed_tickets}

