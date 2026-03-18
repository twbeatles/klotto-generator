import json
import datetime
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, cast

from klotto.config import APP_CONFIG
from klotto.core.lotto_rules import normalize_bonus, normalize_numbers, normalize_positive_int, safe_int
from klotto.logging import logger

WinningRecord = Dict[str, Any]
UpsertStatus = str


# ============================================================
# 역대 당첨 번호 통계 관리
# ============================================================
class WinningStatsManager:
    """역대 당첨 번호 통계 관리 (SQLite DB 우선, JSON 폴백)"""

    def __init__(self):
        self.stats_file: Path = cast(Path, APP_CONFIG["WINNING_STATS_FILE"])
        self.db_path: Path = cast(Path, APP_CONFIG["LOTTO_HISTORY_DB"])
        self.winning_data: List[WinningRecord] = []
        self._draw_index: Dict[int, WinningRecord] = {}
        self._frequency_cache: Optional[Dict[str, Any]] = None
        self._range_cache: Optional[Dict[str, int]] = None
        self._pair_cache: Optional[Dict[str, Any]] = None
        self._load()

    def _invalidate_analysis_cache(self):
        self._frequency_cache = None
        self._range_cache = None
        self._pair_cache = None

    @staticmethod
    def _normalize_metadata_value(value: Any) -> int:
        parsed = safe_int(value, default=0)
        return parsed if parsed > 0 else 0

    def _build_record(
        self,
        draw_no: int,
        numbers: Sequence[int],
        bonus: int,
        *,
        draw_date: str = "",
        first_prize: int = 0,
        first_winners: int = 0,
        total_sales: int = 0,
    ) -> WinningRecord:
        return {
            "draw_no": int(draw_no),
            "date": draw_date,
            "numbers": list(numbers),
            "bonus": int(bonus),
            "first_prize": self._normalize_metadata_value(first_prize),
            "first_winners": self._normalize_metadata_value(first_winners),
            "total_sales": self._normalize_metadata_value(total_sales),
        }

    def _normalize_draw_input(
        self,
        draw_no: Any,
        numbers: Sequence[Any],
        bonus: Any,
        *,
        draw_date: Optional[str] = None,
        first_prize: Any = None,
        first_winners: Any = None,
        total_sales: Any = None,
    ) -> Optional[WinningRecord]:
        """입력 당첨 데이터 정규화 및 검증"""
        parsed_draw_no = normalize_positive_int(draw_no)
        parsed_numbers = normalize_numbers(numbers)
        if parsed_draw_no is None or parsed_numbers is None:
            return None
        parsed_bonus = normalize_bonus(bonus, parsed_numbers)
        if parsed_bonus is None:
            return None

        normalized_date = draw_date if isinstance(draw_date, str) else ""
        return self._build_record(
            parsed_draw_no,
            parsed_numbers,
            parsed_bonus,
            draw_date=normalized_date,
            first_prize=self._normalize_metadata_value(first_prize),
            first_winners=self._normalize_metadata_value(first_winners),
            total_sales=self._normalize_metadata_value(total_sales),
        )

    def _merge_records(self, existing: Optional[WinningRecord], incoming: WinningRecord) -> WinningRecord:
        if existing is None:
            return self._build_record(
                incoming["draw_no"],
                incoming["numbers"],
                incoming["bonus"],
                draw_date=incoming.get("date", ""),
                first_prize=incoming.get("first_prize", 0),
                first_winners=incoming.get("first_winners", 0),
                total_sales=incoming.get("total_sales", 0),
            )

        return self._build_record(
            incoming["draw_no"],
            incoming["numbers"],
            incoming["bonus"],
            draw_date=incoming.get("date") or existing.get("date", ""),
            first_prize=incoming.get("first_prize", 0) or existing.get("first_prize", 0),
            first_winners=incoming.get("first_winners", 0) or existing.get("first_winners", 0),
            total_sales=incoming.get("total_sales", 0) or existing.get("total_sales", 0),
        )

    @staticmethod
    def _records_equal(left: WinningRecord, right: WinningRecord) -> bool:
        return (
            int(left.get("draw_no", 0)) == int(right.get("draw_no", 0))
            and list(left.get("numbers", [])) == list(right.get("numbers", []))
            and int(left.get("bonus", 0)) == int(right.get("bonus", 0))
            and str(left.get("date", "")) == str(right.get("date", ""))
            and int(left.get("first_prize", 0)) == int(right.get("first_prize", 0))
            and int(left.get("first_winners", 0)) == int(right.get("first_winners", 0))
            and int(left.get("total_sales", 0)) == int(right.get("total_sales", 0))
        )

    def _record_from_row(self, row: Sequence[Any]) -> Optional[WinningRecord]:
        if len(row) < 12:
            return None
        return self._normalize_draw_input(
            row[0],
            [row[2], row[3], row[4], row[5], row[6], row[7]],
            row[8],
            draw_date=row[1],
            first_prize=row[9],
            first_winners=row[10],
            total_sales=row[11],
        )

    def _set_winning_data(self, data: List[WinningRecord]):
        self.winning_data = sorted(
            [dict(record) for record in data if isinstance(record, dict)],
            key=lambda record: int(record.get("draw_no", 0)),
            reverse=True,
        )
        self._draw_index = {}
        for row in self.winning_data:
            try:
                draw_no = int(row.get("draw_no", 0))
            except (TypeError, ValueError):
                continue
            if draw_no > 0:
                self._draw_index[draw_no] = row
        self._invalidate_analysis_cache()

    def _store_cached_record(self, record: WinningRecord):
        draw_no = int(record["draw_no"])
        stored = dict(record)
        for index, existing in enumerate(self.winning_data):
            if int(existing.get("draw_no", 0)) == draw_no:
                self.winning_data[index] = stored
                break
        else:
            self.winning_data.append(stored)

        self.winning_data.sort(key=lambda item: int(item.get("draw_no", 0)), reverse=True)
        self._draw_index[draw_no] = stored
        self._invalidate_analysis_cache()

    def _trim_json_cache(self):
        if self.db_path and self.db_path.exists():
            return

        cache_size = cast(int, APP_CONFIG["WINNING_STATS_CACHE_SIZE"])
        if len(self.winning_data) > cache_size:
            self._set_winning_data(self.winning_data[:cache_size])

    def _ensure_db_schema(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS draws (
                draw_no INTEGER PRIMARY KEY,
                date TEXT,
                num1 INTEGER, num2 INTEGER, num3 INTEGER,
                num4 INTEGER, num5 INTEGER, num6 INTEGER,
                bonus INTEGER,
                prize_amount INTEGER,
                winners_count INTEGER,
                total_sales INTEGER
            )
            """
        )

    def _load(self):
        """데이터 로드 - DB 우선, JSON 폴백"""
        if self.db_path and self.db_path.exists() and self._load_from_db():
            return
        self._load_from_json()

    def _load_from_db(self) -> bool:
        """SQLite DB에서 데이터 로드"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT draw_no, date, num1, num2, num3, num4, num5, num6, bonus,
                           prize_amount, winners_count, total_sales
                    FROM draws
                    ORDER BY draw_no DESC
                    """
                )
                rows = cursor.fetchall()

            if not rows:
                return False

            parsed_data: List[WinningRecord] = []
            invalid_count = 0
            for row in rows:
                record = self._record_from_row(row)
                if record is None:
                    invalid_count += 1
                    continue
                parsed_data.append(record)

            if invalid_count:
                logger.warning("Skipped %s invalid winning records from DB", invalid_count)

            if not parsed_data:
                return False

            self._set_winning_data(parsed_data)
            logger.info("Loaded %s winning records from DB", len(self.winning_data))
            return True
        except Exception as exc:
            logger.error("Failed to load from DB: %s", exc)
            return False

    def _load_record_from_db(self, draw_no: int) -> Optional[WinningRecord]:
        if not self.db_path or not self.db_path.exists():
            return None

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT draw_no, date, num1, num2, num3, num4, num5, num6, bonus,
                           prize_amount, winners_count, total_sales
                    FROM draws
                    WHERE draw_no = ?
                    LIMIT 1
                    """,
                    (draw_no,),
                )
                row = cursor.fetchone()
        except Exception as exc:
            logger.error("Failed to query draw #%s from DB: %s", draw_no, exc)
            return None

        if not row:
            return None
        return self._record_from_row(row)

    def _get_existing_record(self, draw_no: int) -> Optional[WinningRecord]:
        db_record = self._load_record_from_db(draw_no)
        if db_record:
            return db_record

        cached = self._draw_index.get(draw_no)
        if not cached:
            return None

        return self._build_record(
            cached["draw_no"],
            cached["numbers"],
            cached["bonus"],
            draw_date=str(cached.get("date", "")),
            first_prize=int(cached.get("first_prize", 0)),
            first_winners=int(cached.get("first_winners", 0)),
            total_sales=int(cached.get("total_sales", 0)),
        )

    def _save_record_to_db(self, record: WinningRecord) -> bool:
        if not self.db_path:
            return False

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                self._ensure_db_schema(conn)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO draws (
                        draw_no, date, num1, num2, num3, num4, num5, num6, bonus,
                        prize_amount, winners_count, total_sales
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(draw_no) DO UPDATE SET
                        date = CASE
                            WHEN excluded.date <> '' THEN excluded.date
                            ELSE draws.date
                        END,
                        num1 = excluded.num1,
                        num2 = excluded.num2,
                        num3 = excluded.num3,
                        num4 = excluded.num4,
                        num5 = excluded.num5,
                        num6 = excluded.num6,
                        bonus = excluded.bonus,
                        prize_amount = CASE
                            WHEN excluded.prize_amount > 0 THEN excluded.prize_amount
                            ELSE draws.prize_amount
                        END,
                        winners_count = CASE
                            WHEN excluded.winners_count > 0 THEN excluded.winners_count
                            ELSE draws.winners_count
                        END,
                        total_sales = CASE
                            WHEN excluded.total_sales > 0 THEN excluded.total_sales
                            ELSE draws.total_sales
                        END
                    """,
                    (
                        record["draw_no"],
                        record.get("date", ""),
                        record["numbers"][0],
                        record["numbers"][1],
                        record["numbers"][2],
                        record["numbers"][3],
                        record["numbers"][4],
                        record["numbers"][5],
                        record["bonus"],
                        record.get("first_prize", 0),
                        record.get("first_winners", 0),
                        record.get("total_sales", 0),
                    ),
                )
                conn.commit()
            return True
        except Exception as exc:
            logger.error("Failed to save winning stats to DB: %s", exc)
            return False

    def _load_from_json(self):
        """JSON 파일에서 통계 데이터 로드 (폴백)"""
        try:
            if self.stats_file and self.stats_file.exists():
                with open(self.stats_file, "r", encoding="utf-8") as file:
                    loaded = json.load(file)

                parsed_data: List[WinningRecord] = []
                seen_draws = set()
                for item in loaded if isinstance(loaded, list) else []:
                    if not isinstance(item, dict):
                        continue

                    record = self._normalize_draw_input(
                        item.get("draw_no"),
                        item.get("numbers", []),
                        item.get("bonus"),
                        draw_date=item.get("date"),
                        first_prize=item.get("first_prize"),
                        first_winners=item.get("first_winners"),
                        total_sales=item.get("total_sales"),
                    )
                    if not record:
                        continue

                    draw_no = int(record["draw_no"])
                    if draw_no in seen_draws:
                        continue

                    parsed_data.append(record)
                    seen_draws.add(draw_no)

                self._set_winning_data(parsed_data)
                logger.info("Loaded %s winning records from JSON", len(self.winning_data))
            else:
                self._set_winning_data([])
        except Exception as exc:
            logger.error("Failed to load winning stats: %s", exc)
            self._set_winning_data([])

    def _save(self):
        """통계 데이터 저장 (JSON - 캐시용)"""
        if not self.stats_file:
            return

        temp_file: Optional[Path] = None
        try:
            self.stats_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.stats_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as file:
                json.dump(self.winning_data, file, ensure_ascii=False, indent=2)
            if self.stats_file.exists():
                os.replace(temp_file, self.stats_file)
            else:
                os.rename(temp_file, self.stats_file)
        except Exception as exc:
            logger.error("Failed to save winning stats: %s", exc)
            try:
                if temp_file and temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass

    def upsert_winning_data(
        self,
        draw_no: int,
        numbers: List[int],
        bonus: int,
        *,
        draw_date: Optional[str] = None,
        first_prize: Any = None,
        first_winners: Any = None,
        total_sales: Any = None,
    ) -> UpsertStatus:
        """당첨 데이터를 저장하거나 갱신한다."""
        incoming = self._normalize_draw_input(
            draw_no,
            numbers,
            bonus,
            draw_date=draw_date,
            first_prize=first_prize,
            first_winners=first_winners,
            total_sales=total_sales,
        )
        if not incoming:
            logger.warning("Invalid winning data ignored: draw_no=%s", draw_no)
            return "invalid"

        existing = self._get_existing_record(int(incoming["draw_no"]))
        merged = self._merge_records(existing, incoming)

        if existing is None:
            status: UpsertStatus = "inserted"
        elif self._records_equal(existing, merged):
            status = "unchanged"
        else:
            status = "updated"

        if status != "unchanged" and self.db_path:
            if not self._save_record_to_db(merged):
                if self.db_path.exists():
                    self._load_from_db()
                return "invalid"

        cached = self._draw_index.get(int(merged["draw_no"]))
        if status != "unchanged" or cached is None or not self._records_equal(cached, merged):
            self._store_cached_record(merged)
            self._trim_json_cache()
            self._save()

        return status

    def add_winning_data(
        self,
        draw_no: int,
        numbers: List[int],
        bonus: int,
        draw_date: Optional[str] = None,
        *,
        first_prize: Any = None,
        first_winners: Any = None,
        total_sales: Any = None,
    ) -> UpsertStatus:
        """호환용 별칭: 내부 구현은 upsert_winning_data로 통일한다."""
        return self.upsert_winning_data(
            draw_no,
            numbers,
            bonus,
            draw_date=draw_date,
            first_prize=first_prize,
            first_winners=first_winners,
            total_sales=total_sales,
        )

    def get_draw_data(self, draw_no: int) -> Optional[WinningRecord]:
        """특정 회차 데이터 반환"""
        try:
            target = int(draw_no)
        except (TypeError, ValueError):
            return None

        if target <= 0:
            return None

        cached = self._draw_index.get(target)
        if cached:
            return dict(cached)

        record = self._load_record_from_db(target)
        if record:
            self._store_cached_record(record)
            return dict(record)

        return None

    def reload_from_db(self):
        """DB에서 데이터 다시 로드 (수동 새로고침용)"""
        if self.db_path and self.db_path.exists():
            self._load_from_db()

    def get_frequency_analysis(self) -> Dict[str, Any]:
        """번호별 출현 빈도 분석"""
        if self._frequency_cache is not None:
            return dict(self._frequency_cache)

        if not self.winning_data:
            return {}

        number_counts = {i: 0 for i in range(1, 46)}
        bonus_counts = {i: 0 for i in range(1, 46)}

        for data in self.winning_data:
            for num in data["numbers"]:
                if num in number_counts:
                    number_counts[num] += 1
            bonus = data.get("bonus")
            if bonus in bonus_counts:
                bonus_counts[bonus] += 1

        sorted_by_count = sorted(number_counts.items(), key=lambda item: item[1], reverse=True)

        self._frequency_cache = {
            "total_draws": len(self.winning_data),
            "number_counts": number_counts,
            "bonus_counts": bonus_counts,
            "hot_numbers": sorted_by_count[:10],
            "cold_numbers": sorted_by_count[-10:],
        }
        return dict(self._frequency_cache)

    def get_range_distribution(self) -> Dict[str, int]:
        """번호대별 분포 분석"""
        if self._range_cache is not None:
            return dict(self._range_cache)

        if not self.winning_data:
            return {}

        frequency = self.get_frequency_analysis()
        number_counts = frequency.get("number_counts", {})
        if not isinstance(number_counts, dict):
            return {}

        ranges = {
            "1-10": sum(number_counts.get(i, 0) for i in range(1, 11)),
            "11-20": sum(number_counts.get(i, 0) for i in range(11, 21)),
            "21-30": sum(number_counts.get(i, 0) for i in range(21, 31)),
            "31-40": sum(number_counts.get(i, 0) for i in range(31, 41)),
            "41-45": sum(number_counts.get(i, 0) for i in range(41, 46)),
        }
        self._range_cache = ranges
        return dict(ranges)

    def get_pair_analysis(self) -> Dict[str, Any]:
        """연속 당첨 쌍 분석 (같이 나온 번호 쌍)"""
        if self._pair_cache is not None:
            return dict(self._pair_cache)

        if not self.winning_data:
            return {}

        pair_counts: Dict[tuple[int, int], int] = {}
        for data in self.winning_data:
            nums = data["numbers"]
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    pair = (nums[i], nums[j])
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1

        sorted_pairs = sorted(pair_counts.items(), key=lambda item: item[1], reverse=True)
        self._pair_cache = {"top_pairs": sorted_pairs[:10]}
        return dict(self._pair_cache)

    def get_recent_trend(self, count: int = 10) -> List[WinningRecord]:
        """최근 N회차 트렌드"""
        return [dict(item) for item in self.winning_data[:count]]
