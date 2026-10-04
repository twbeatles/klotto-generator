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


def test_export_backup_payload_uses_current_app_brand(configured_paths: dict[str, Path]):
    store = AppStateStore(configured_paths['app_state'])

    payload = store.export_backup_payload()

    assert payload['app'] == APP_CONFIG['APP_NAME'] == '로또·연금복권 프로'
    assert payload['version'] == APP_CONFIG['VERSION']
    assert isinstance(payload['state'], dict)


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

    assert result == {
        'favorites': 1,
        'history': 1,
        'tickets': 1,
        'campaigns': 1,
        'pension720Tickets': 0,
        'pension720Campaigns': 0,
    }
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


def test_load_state_recovers_malformed_strategy_and_generator_options(configured_paths: dict[str, Path]):
    _write_json(
        configured_paths['app_state'],
        {
            'strategyPrefs': {
                'generator': {
                    'strategyId': 'unknown',
                    'params': {
                        'simulationCount': 'bad',
                        'lookbackWindow': 9999,
                        'wheelPoolSize': '2',
                        'wheelGuarantee': 'bad',
                        'seed': 'seed',
                        'payoutMode': 'bad',
                    },
                    'filters': {
                        'oddEven': ['x', 99],
                        'sumRange': [300, 1],
                        'maxConsecutivePairs': '99',
                        'endDigitUniqueMin': '0',
                    },
                },
            },
            'generatorOptions': {
                'num_sets': '9999',
                'fixed_nums': '1, 2',
                'exclude_nums': '3, 4',
                'check_consecutive': 'false',
                'consecutive_limit': '99',
            },
        },
    )

    store = AppStateStore(configured_paths['app_state'])
    request = store.state['strategyPrefs']['generator']

    assert request['strategyId'] == 'ensemble_weighted'
    assert request['params']['simulationCount'] == 5000
    assert request['params']['lookbackWindow'] == 120
    assert request['params']['wheelPoolSize'] == 7
    assert request['params']['seed'] is None
    assert request['filters']['maxConsecutivePairs'] == 5
    assert request['filters']['endDigitUniqueMin'] == 1
    assert request['filters']['sumRange'] == [1, 300]
    assert store.state['generatorOptions']['num_sets'] == int(APP_CONFIG['MAX_SETS'])
    assert store.state['generatorOptions']['check_consecutive'] is False
    assert store.state['generatorOptions']['consecutive_limit'] == 5


def test_import_backup_tolerates_malformed_values(configured_paths: dict[str, Path]):
    store = AppStateStore(configured_paths['app_state'])

    result = store.import_backup_payload(
        {
            'state': {
                'ticketBook': [
                    {
                        'numbers': [1, 2, 3, 4, 5, 6],
                        'targetDrawNo': 140,
                        'quantity': 'bad',
                        'checked': {'drawNo': 140, 'rank': 'bad'},
                    }
                ],
                'strategyPrefs': {
                    'generator': {'strategyId': 'random', 'params': {'simulationCount': 'bad'}, 'filters': {}},
                },
                'generatorOptions': {'num_sets': 'bad', 'check_consecutive': 'off'},
            }
        },
        mode='overwrite',
    )

    assert result['tickets'] == 1
    assert store.state['ticketBook'][0]['quantity'] == 1
    assert store.state['ticketBook'][0]['checked']['rank'] == 0
    assert store.state['strategyPrefs']['generator']['strategyId'] == 'random_baseline'
    assert store.state['strategyPrefs']['generator']['params']['simulationCount'] == 5000
    assert store.state['generatorOptions']['num_sets'] == 5
    assert store.state['generatorOptions']['check_consecutive'] is False


def test_corrupt_app_state_is_preserved_and_flagged(configured_paths: dict[str, Path]):
    raw = '{broken json,,,'
    configured_paths['app_state'].parent.mkdir(parents=True, exist_ok=True)
    configured_paths['app_state'].write_text(raw, encoding='utf-8')

    store = AppStateStore(configured_paths['app_state'])

    assert store.state['favorites'] == []
    backups = list(configured_paths['app_state'].parent.glob('app_state.corrupt-*.json'))
    assert len(backups) == 1
    assert backups[0].read_text(encoding='utf-8') == raw
    assert store.state_load_issue
    # A fresh, valid state file now exists at the original path.
    json.loads(configured_paths['app_state'].read_text(encoding='utf-8'))


def test_valid_app_state_has_no_load_issue(configured_paths: dict[str, Path]):
    _write_json(configured_paths['app_state'], {'favorites': []})

    store = AppStateStore(configured_paths['app_state'])

    assert store.state_load_issue is None


def test_history_merge_dedupes_identical_entries(configured_paths: dict[str, Path]):
    store = AppStateStore(configured_paths['app_state'])
    entry = {'numbers': [1, 2, 3, 4, 5, 6], 'date': '2026-04-01T10:00:00'}

    merged = store.merge_history_entries([entry], [dict(entry)])

    assert len(merged) == 1


def test_import_backup_twice_keeps_history_stable(configured_paths: dict[str, Path]):
    store = AppStateStore(configured_paths['app_state'])
    payload = {
        'state': {
            'history': [{'numbers': [1, 2, 3, 4, 5, 6], 'date': '2026-04-01T10:00:00'}],
        }
    }

    store.import_backup_payload(payload, mode='merge')
    first = len(store.state['history'])
    store.import_backup_payload(payload, mode='merge')

    assert first == 1
    assert len(store.state['history']) == 1


def test_file_lock_serializes_concurrent_saves(tmp_path: Path):
    import threading

    from klotto.data.store_utils import _lock_path_for, save_json_atomic

    path = tmp_path / 'data.json'
    errors: list[BaseException] = []

    def _save(value: int) -> None:
        try:
            assert save_json_atomic(path, {'i': value}, 'probe') is True
        except BaseException as exc:  # noqa: BLE001 - collected for assertion
            errors.append(exc)

    threads = [threading.Thread(target=_save, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors
    assert json.loads(path.read_text(encoding='utf-8'))['i'] in range(8)
    assert not _lock_path_for(path).exists()


def test_stale_lock_is_broken(tmp_path: Path):
    import os
    import time

    from klotto.data.store_utils import _lock_path_for, save_json_atomic

    path = tmp_path / 'data.json'
    lock = _lock_path_for(path)
    lock.write_text('999999', encoding='utf-8')
    stale = time.time() - 120
    os.utime(lock, (stale, stale))

    assert save_json_atomic(path, {'ok': True}, 'probe') is True
    assert json.loads(path.read_text(encoding='utf-8')) == {'ok': True}
    assert not lock.exists()


def test_campaign_size_error_flags_over_cap(configured_paths: dict[str, Path]):
    from klotto.data.store.campaigns import campaign_size_error

    assert campaign_size_error(4, 5) is None
    assert campaign_size_error(15, 20) is None
    assert campaign_size_error(16, 20) is not None
    assert campaign_size_error(24, 20) is not None


def test_pension720_ticket_settles_and_keeps_checked(configured_paths: dict[str, Path]):
    from klotto.data.pension720 import normalize_pension720_stats

    store = AppStateStore(configured_paths['app_state'])
    stats = normalize_pension720_stats(
        [
            {
                'draw_no': 3,
                'date': '2026-05-14',
                'group': 2,
                'digits': [5, 3, 7, 5, 3, 0],
                'number': '537530',
                'bonus_digits': [3, 5, 8, 1, 2, 7],
                'bonus_number': '358127',
            }
        ]
    )
    store.add_pension720_ticket(
        {'group': 2, 'number': '537530', 'source': 'recommendation', 'targetDrawNo': 3}
    )
    future = store.add_pension720_ticket(
        {'group': 2, 'number': '000000', 'source': 'recommendation', 'targetDrawNo': 99}
    )

    settled = store.settle_pension720_tickets_if_possible(store.state['pension720Tickets'], stats)

    assert settled == 1
    checked = store.state['pension720Tickets'][1]['checked']
    assert checked['drawNo'] == 3
    assert checked['rank'] == 1
    assert future['ticket']['checked'] is None
    # Checked state survives a normalize round-trip (backup merge path).
    renormalized = store.normalize_pension720_ticket(store.state['pension720Tickets'][1])
    assert renormalized is not None
    assert renormalized['checked'] == checked


def test_campaign_entry_rejects_over_total_ticket_cap(configured_paths: dict[str, Path]):
    store = AppStateStore(configured_paths['app_state'])

    assert (
        store.normalize_campaign_entry({'startDrawNo': 1000, 'weeks': 24, 'setsPerWeek': 20})
        is None
    )
    assert (
        store.normalize_pension720_campaign({'startDrawNo': 100, 'weeks': 24, 'setsPerDraw': 20})
        is None
    )


def test_pension720_state_dedupes_campaigns_and_backup_v5(configured_paths: dict[str, Path]):
    store = AppStateStore(configured_paths['app_state'])
    request = store.normalize_pension720_strategy_request(
        {
            'strategyId': 'trailing_match',
            'params': {'seed': 720, 'lookbackWindow': 3, 'candidatePoolSize': 80},
            'filters': {'groups': [2]},
        }
    )

    first = store.add_pension720_ticket({'group': 2, 'number': '060727', 'source': 'recommendation'})
    duplicate = store.add_pension720_ticket({'group': 2, 'number': '060727', 'source': 'recommendation'})
    next_draw = store.add_pension720_ticket(
        {'group': 2, 'number': '060727', 'targetDrawNo': 316, 'source': 'campaign', 'campaignId': 'p720_campaign_a'}
    )
    bulk = store.add_pension720_tickets_bulk(
        [
            {'group': 1, 'number': '060727', 'source': 'recommendation', 'strategyRequest': request},
            {'group': 2, 'number': '060727', 'source': 'recommendation', 'strategyRequest': request},
            {'group': 3, 'number': '060727', 'source': 'recommendation', 'strategyRequest': request},
        ]
    )

    assert first['inserted'] is True
    assert duplicate['duplicate'] is True
    assert next_draw['inserted'] is True
    assert bulk['inserted'] == 2
    assert len(store.state['pension720Tickets']) == 4

    campaign = store.add_pension720_campaign(
        {'id': 'p720_campaign_a', 'name': '연금 캠페인', 'startDrawNo': 316, 'weeks': 1, 'setsPerDraw': 1}
    )
    assert campaign is not None
    assert store.count_pension720_tickets_by_campaign_id('p720_campaign_a') == 1
    removed = store.remove_pension720_campaign('p720_campaign_a', cascade_tickets=True)
    assert removed['removedCampaign'] is True
    assert removed['removedTickets'] == 1

    payload = {
        'version': 5,
        'pension720Tickets': [
            {'id': 'p720_a', 'group': 2, 'number': '060727', 'targetDrawNo': 316, 'campaignId': 'p720_camp_a'},
            {'id': 'p720_b', 'group': 2, 'number': '060727', 'targetDrawNo': 316, 'campaignId': 'p720_camp_a'},
            {'id': 'p720_c', 'group': 2, 'number': '060727', 'targetDrawNo': 317, 'campaignId': 'p720_camp_a'},
        ],
        'pension720Campaigns': [
            {'id': 'p720_camp_a', 'name': '연금 캠페인', 'startDrawNo': 316, 'weeks': 2, 'setsPerDraw': 1}
        ],
        'settings': {'strategyPrefs': {'pension720': request}},
    }
    result = store.import_backup_payload(payload, mode='overwrite')

    assert result['pension720Tickets'] == 2
    assert result['pension720Campaigns'] == 1
    assert store.state['pension720Tickets'][0]['number'] == '060727'
    assert store.state['strategyPrefs']['pension720']['strategyId'] == 'trailing_match'
