from __future__ import annotations

import json
from pathlib import Path

import pytest

from klotto.config import APP_CONFIG
from klotto.core.strategy_catalog import create_default_strategy_request
from klotto.data.app_state import AppStateStore


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


@pytest.fixture()
def configured_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    state_dir = tmp_path / 'state'
    favorites_file = state_dir / 'favorites.json'
    history_file = state_dir / 'history.json'
    settings_file = state_dir / 'settings.json'
    app_state_file = state_dir / 'app_state.json'

    monkeypatch.setitem(APP_CONFIG, 'FAVORITES_FILE', favorites_file)
    monkeypatch.setitem(APP_CONFIG, 'HISTORY_FILE', history_file)
    monkeypatch.setitem(APP_CONFIG, 'SETTINGS_FILE', settings_file)
    monkeypatch.setitem(APP_CONFIG, 'APP_STATE_FILE', app_state_file)

    return {
        'favorites': favorites_file,
        'history': history_file,
        'settings': settings_file,
        'app_state': app_state_file,
    }


def test_migrate_legacy_files_into_app_state(configured_paths: dict[str, Path]):
    _write_json(
        configured_paths['favorites'],
        [
            {'numbers': [1, 2, 3, 4, 5, 6], 'memo': 'first'},
            {'numbers': [7, 8, 9, 10, 11, 12], 'memo': 'second'},
        ],
    )
    _write_json(
        configured_paths['history'],
        [
            {'numbers': [1, 2, 3, 4, 5, 6], 'date': '2026-04-01T10:00:00'},
            {'numbers': [1, 2, 3, 4, 5, 6], 'created_at': '2026-04-02T10:00:00'},
        ],
    )
    _write_json(
        configured_paths['settings'],
        {
            'theme': 'dark',
            'window_geometry': 'abc123',
            'options': {'num_sets': 8, 'consecutive_limit': 1},
        },
    )

    store = AppStateStore(configured_paths['app_state'])

    assert configured_paths['app_state'].exists()
    assert len(store.state['favorites']) == 2
    assert len(store.state['history']) == 2
    assert store.state['history'][0]['date'] == '2026-04-02T10:00:00'
    assert store.state['theme'] == 'dark'
    assert store.state['windowGeometry'] == 'abc123'
    assert store.state['generatorOptions']['num_sets'] == 8
    assert store.add_favorite([1, 2, 3, 4, 5, 6]) is False


def test_ticket_quantity_merge_and_past_draw_settlement(configured_paths: dict[str, Path]):
    store = AppStateStore(configured_paths['app_state'])
    request = create_default_strategy_request('ensemble_weighted')
    winning_data = [
        {'draw_no': 120, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'first_prize': 1000000000},
    ]

    result = store.add_tickets_bulk(
        [
            {
                'numbers': [1, 2, 3, 4, 5, 6],
                'targetDrawNo': 120,
                'source': 'ai',
                'campaignId': 'campaign-1',
                'strategyRequest': request,
                'quantity': 1,
            },
            {
                'numbers': [1, 2, 3, 4, 5, 6],
                'targetDrawNo': 120,
                'source': 'ai',
                'campaignId': 'campaign-1',
                'strategyRequest': request,
                'quantity': 1,
            },
        ],
        winning_data=winning_data,
    )

    assert result == {
        'insertedRows': 1,
        'incrementedRows': 1,
        'addedQuantity': 2,
        'affectedRows': 2,
    }
    assert len(store.state['ticketBook']) == 1
    assert store.state['ticketBook'][0]['quantity'] == 2
    assert store.state['ticketBook'][0]['checked']['rank'] == 1
    assert store.get_total_ticket_count() == 2


def test_import_backup_restores_sync_meta_and_prunes_orphans(configured_paths: dict[str, Path]):
    store = AppStateStore(configured_paths['app_state'])
    request = create_default_strategy_request('auto_ensemble_top3')
    payload = {
        'state': {
            'favorites': [{'numbers': [3, 8, 13, 21, 34, 42], 'memo': 'fav'}],
            'history': [{'numbers': [4, 9, 14, 19, 24, 29], 'date': '2026-04-15T09:00:00'}],
            'ticketBook': [
                {
                    'id': 'ticket-1',
                    'numbers': [1, 2, 3, 4, 5, 6],
                    'targetDrawNo': 121,
                    'source': 'generator',
                    'campaignId': 'campaign-linked',
                    'strategyRequest': request,
                    'quantity': 1,
                }
            ],
            'campaigns': [
                {
                    'id': 'campaign-linked',
                    'name': 'linked',
                    'startDrawNo': 121,
                    'weeks': 2,
                    'setsPerWeek': 1,
                    'strategyRequest': request,
                },
                {
                    'id': 'campaign-orphan',
                    'name': 'orphan',
                    'startDrawNo': 121,
                    'weeks': 2,
                    'setsPerWeek': 1,
                    'strategyRequest': request,
                },
            ],
            'strategyPrefs': {
                'generator': create_default_strategy_request('ensemble_weighted'),
                'ai': create_default_strategy_request('auto_recent_top'),
                'backtest': create_default_strategy_request('random_baseline'),
            },
            'strategyPresets': [],
            'alertPrefs': {
                'enableInApp': True,
                'enableSystemNotification': True,
                'notifyOnNewResult': True,
            },
            'syncMeta': {
                'mode': 'manual_import',
                'currentSource': 'backup',
                'lastSuccessAt': '2026-04-15T12:00:00',
                'lastSuccessDrawNo': 121,
                'lastFailureAt': '',
                'lastFailureMessage': '',
                'lastWarningAt': '',
                'lastWarningMessage': '',
            },
            'dataHealth': {
                'availability': 'partial',
                'source': 'backup',
                'latestDrawNo': 121,
                'message': 'restored from backup',
            },
            'theme': 'dark',
            'windowGeometry': None,
            'proxyUrl': 'http://localhost:8080',
            'generatorOptions': {
                'num_sets': 9,
                'fixed_nums': '',
                'exclude_nums': '',
                'check_consecutive': True,
                'consecutive_limit': 2,
            },
        }
    }

    result = store.import_backup_payload(
        payload,
        mode='overwrite',
        winning_data=[
            {'draw_no': 121, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'first_prize': 1000000000},
        ],
    )

    assert result == {'favorites': 1, 'history': 1, 'tickets': 1, 'campaigns': 1}
    assert store.state['syncMeta']['mode'] == 'manual_import'
    assert store.state['syncMeta']['lastSuccessDrawNo'] == 121
    assert store.state['dataHealth']['availability'] == 'partial'
    assert store.state['theme'] == 'dark'
    assert store.state['generatorOptions']['num_sets'] == 9
    assert len(store.state['campaigns']) == 1
    assert store.state['campaigns'][0]['id'] == 'campaign-linked'
    assert store.state['ticketBook'][0]['checked']['rank'] == 1


def test_load_state_recovers_from_malformed_ticket_fields(configured_paths: dict[str, Path]):
    _write_json(
        configured_paths['app_state'],
        {
            'ticketBook': [
                {
                    'numbers': [1, 2, 3, 4, 5, 6],
                    'targetDrawNo': 121,
                    'source': 'generator',
                    'quantity': 'oops',
                    'checked': {
                        'drawNo': 121,
                        'rank': '9',
                    },
                },
                {
                    'numbers': [7, 8, 9, 10, 11, 12],
                    'targetDrawNo': 122,
                    'source': 'ai',
                    'quantity': -5,
                    'checked': {
                        'drawNo': 'bad',
                        'rank': 'NaN',
                    },
                },
                None,
                'broken',
            ],
            'proxyUrl': 'socks5://localhost:9999',
        },
    )

    store = AppStateStore(configured_paths['app_state'])

    assert len(store.state['ticketBook']) == 2
    first, second = store.state['ticketBook']
    assert first['quantity'] == 1
    assert first['checked']['rank'] == 5
    assert second['quantity'] == 1
    assert second['checked'] is None
    assert store.state['proxyUrl'] == ''
