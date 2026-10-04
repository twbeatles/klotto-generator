from __future__ import annotations

from pathlib import Path

from klotto.data.exporter import DataExporter


def test_export_to_csv_escapes_formula_memo(tmp_path: Path):
    filepath = str(tmp_path / 'favorites.csv')

    assert DataExporter.export_to_csv(
        [{'numbers': [1, 2, 3, 4, 5, 6], 'memo': '=1+1', 'created_at': '2026-04-01'}],
        filepath,
        'favorites',
    ) is True

    content = Path(filepath).read_text(encoding='utf-8-sig')
    assert "'=1+1" in content
    assert ',=1+1,' not in content


def test_export_to_csv_keeps_plain_memo(tmp_path: Path):
    filepath = str(tmp_path / 'favorites.csv')

    assert DataExporter.export_to_csv(
        [{'numbers': [1, 2, 3, 4, 5, 6], 'memo': 'first win', 'created_at': '2026-04-01'}],
        filepath,
        'favorites',
    ) is True

    content = Path(filepath).read_text(encoding='utf-8-sig')
    assert 'first win' in content
