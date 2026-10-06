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


class BackupStoreMixin(StoreAPI):
    def export_backup_payload(self) -> Dict[str, Any]:
        return {
            'app': APP_CONFIG['APP_NAME'],
            'version': APP_CONFIG['VERSION'],
            'exportedAt': dt.datetime.now().isoformat(),
            'state': self.clone_serializable_value(self.state),
        }

    def import_backup_payload(self, payload: Dict[str, Any], *, mode: str = 'merge', winning_data: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, int]:
        incoming_state = payload.get('state') if isinstance(payload.get('state'), dict) else payload
        if not isinstance(incoming_state, dict):
            raise ValueError('백업 형식이 올바르지 않습니다.')
        if isinstance(payload.get('settings'), dict):
            settings = cast(Dict[str, Any], payload.get('settings'))
            if isinstance(settings.get('strategyPrefs'), dict) and 'strategyPrefs' not in incoming_state:
                incoming_state = {**incoming_state, 'strategyPrefs': settings['strategyPrefs']}
        normalized = self.merge_state(incoming_state)
        if mode == 'overwrite':
            self.state = normalized
        else:
            self.state['favorites'] = [*self.state['favorites']]
            self.add_favorites_many(normalized['favorites'])
            self.state['history'] = self.merge_history_entries(normalized['history'], self.state['history'])
            self.state['ticketBook'] = self.merge_ticket_entries(self.state['ticketBook'], normalized['ticketBook'])
            existing_campaign_ids = {item.get('id') for item in self.state['campaigns']}
            for campaign in normalized['campaigns']:
                if campaign.get('id') not in existing_campaign_ids:
                    self.state['campaigns'].append(campaign)
            self.state['pension720Tickets'] = self.merge_pension720_tickets(self.state['pension720Tickets'], normalized['pension720Tickets'])
            existing_p720_campaign_ids = {item.get('id') for item in self.state['pension720Campaigns']}
            for campaign in normalized['pension720Campaigns']:
                if campaign.get('id') not in existing_p720_campaign_ids:
                    self.state['pension720Campaigns'].append(campaign)
            # Merge mode keeps the live app's own preferences/health and only
            # unions stored data: importing an old backup must not roll back
            # the user's current strategy choices or sync metadata.
            existing_preset_ids = {item.get('id') for item in self.state['strategyPresets']}
            for preset in normalized['strategyPresets']:
                if preset.get('id') not in existing_preset_ids:
                    self.state['strategyPresets'].append(preset)
                    existing_preset_ids.add(preset.get('id'))
            max_presets = int(APP_CONFIG['MAX_STRATEGY_PRESETS'])
            self.state['strategyPresets'] = self.state['strategyPresets'][:max_presets]
        if winning_data:
            self.settle_tickets_if_possible(self.state['ticketBook'], winning_data)
        self.prune_orphan_campaigns(save=False)
        self.prune_pension720_campaigns_without_tickets(save=False)
        self.save()
        return {
            'favorites': len(self.state['favorites']),
            'history': len(self.state['history']),
            'tickets': self.get_total_ticket_count(),
            'campaigns': len(self.state['campaigns']),
            'pension720Tickets': len(self.state['pension720Tickets']),
            'pension720Campaigns': len(self.state['pension720Campaigns']),
        }


