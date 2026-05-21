from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from klotto.data.pension720 import fetch_pension720_official_stats, load_pension720_static_data


def main() -> int:
    parser = argparse.ArgumentParser(description='Fetch or validate Pension720+ official statistics.')
    parser.add_argument('--out', default='data/pension720_stats.json', help='Output JSON path.')
    parser.add_argument('--check', action='store_true', help='Validate the existing output without writing.')
    args = parser.parse_args()

    output_path = Path(args.out)
    rows = load_pension720_static_data(output_path) if args.check else fetch_pension720_official_stats()
    if not rows:
        raise SystemExit('pension720_stats.json must contain at least one draw row')

    latest = rows[0]
    print(
        json.dumps(
            {
                'ok': True,
                'outputPath': str(output_path),
                'count': len(rows),
                'latestDrawNo': latest['draw_no'],
                'latestDate': latest['date'],
                'latestNumber': f"{latest['group']}조 {latest['number']}",
                'latestBonus': latest['bonus_number'],
                'checkedOnly': args.check,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if not args.check:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
