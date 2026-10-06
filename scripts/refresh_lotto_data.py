"""DB + 엑셀 원클릭 갱신 오케스트레이터 (update_lotto.bat에서 호출)."""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

try:
    from scripts.common import get_repo_root, resolve_db_path
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.common import get_repo_root, resolve_db_path


def _ensure_utf8_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    _ensure_utf8_stdout()
    from scripts.export_to_excel import export_to_excel
    from scripts.scrape_lotto_history import main as scrape_main

    print("=" * 50)
    print("로또 DB 및 엑셀 갱신을 시작합니다.")
    print("=" * 50)

    try:
        scrape_main()
    except Exception:
        print("DB 수집 중 오류가 발생했습니다.")
        traceback.print_exc()
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = get_repo_root() / f"lotto_history_{timestamp}.xlsx"
    if not export_to_excel(output_path):
        print("엑셀 내보내기에 실패했습니다.")
        return 1

    print("=" * 50)
    print(f"갱신 완료: {output_path.name}")
    print(f"DB 위치: {resolve_db_path()}")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
