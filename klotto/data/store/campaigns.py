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


def campaign_size_error(weeks: Any, sets_per_unit: Any) -> Optional[str]:
    """묶음 총량이 상한을 초과하면 오류 메시지, 아니면 None을 반환한다."""
    try:
        total = int(weeks) * int(sets_per_unit)
    except (TypeError, ValueError):
        return '묶음 개수를 확인할 수 없습니다.'
    cap = int(APP_CONFIG['MAX_CAMPAIGN_TOTAL_TICKETS'])
    if total > cap:
        return f'묶음 번호가 {total}개로 한도({cap}개)를 넘었어요. 주 수나 회차마다 개수를 줄여주세요.'
    return None


class CampaignStoreMixin(StoreAPI):
    def prune_orphan_campaigns(self, *, save: bool = True) -> Dict[str, Any]:
        linked_ids = {str(ticket.get('campaignId') or '').strip() for ticket in self.state['ticketBook'] if ticket.get('campaignId')}
        kept = []
        removed = []
        for campaign in self.state['campaigns']:
            campaign_id = str(campaign.get('id') or '').strip()
            if campaign_id and campaign_id in linked_ids:
                kept.append(campaign)
            else:
                removed.append(campaign)
        if removed:
            self.state['campaigns'] = kept
            if save:
                self.save()
        return {'campaigns': self.state['campaigns'], 'removed': removed}

    def add_campaign(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        normalized = self.normalize_campaign_entry(entry)
        if not normalized:
            return None
        self.state['campaigns'].insert(0, normalized)
        self.save()
        return normalized

    def remove_campaign(self, campaign_id: str, *, cascade_tickets: bool = True) -> Dict[str, Any]:
        before_campaigns = len(self.state['campaigns'])
        self.state['campaigns'] = [campaign for campaign in self.state['campaigns'] if campaign.get('id') != campaign_id]
        removed_campaign = before_campaigns != len(self.state['campaigns'])
        removed_tickets = 0
        if cascade_tickets:
            before_tickets = self.get_total_ticket_count()
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if ticket.get('campaignId') != campaign_id]
            removed_tickets = before_tickets - self.get_total_ticket_count()
        if removed_campaign or removed_tickets:
            self.save()
        return {'removedCampaign': removed_campaign, 'removedTickets': removed_tickets}

    def clear_campaigns(self, *, cascade_tickets: bool = True) -> Dict[str, int]:
        campaign_ids = [campaign.get('id') for campaign in self.state['campaigns'] if campaign.get('id')]
        removed_campaigns = len(campaign_ids)
        removed_tickets = 0
        self.state['campaigns'] = []
        if cascade_tickets and campaign_ids:
            before_tickets = self.get_total_ticket_count()
            id_set = set(campaign_ids)
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if ticket.get('campaignId') not in id_set]
            removed_tickets = before_tickets - self.get_total_ticket_count()
        self.save()
        return {'removedCampaigns': removed_campaigns, 'removedTickets': removed_tickets}

