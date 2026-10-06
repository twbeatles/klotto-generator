from __future__ import annotations

import sqlite3

from scripts.scrape_lotto_history import fetch_and_save, find_gap_draws, save_draw


def _make_conn(draw_nos: list[int]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE draws (draw_no INTEGER PRIMARY KEY, date TEXT,"
        " num1 INTEGER, num2 INTEGER, num3 INTEGER, num4 INTEGER, num5 INTEGER,"
        " num6 INTEGER, bonus INTEGER, prize_amount INTEGER,"
        " winners_count INTEGER, total_sales INTEGER)"
    )
    conn.executemany(
        "INSERT INTO draws (draw_no) VALUES (?)", [(n,) for n in draw_nos]
    )
    return conn


def test_find_gap_draws_reports_hole_inside_known_range():
    conn = _make_conn([1, 2, 4])
    try:
        assert find_gap_draws(conn, 4) == [3]
    finally:
        conn.close()


def test_find_gap_draws_empty_when_contiguous():
    conn = _make_conn([1, 2, 3])
    try:
        assert find_gap_draws(conn, 3) == []
    finally:
        conn.close()


def test_find_gap_draws_empty_db_has_no_gaps():
    conn = _make_conn([])
    try:
        assert find_gap_draws(conn, 0) == []
    finally:
        conn.close()


def test_save_draw_rejects_empty_api_list_without_raising():
    conn = _make_conn([])
    try:
        assert save_draw(conn, {"data": {"list": []}}) is False
        assert conn.execute("SELECT COUNT(*) FROM draws").fetchone()[0] == 0
    finally:
        conn.close()


def test_fetch_and_save_treats_failed_draw_as_failure(monkeypatch):
    conn = _make_conn([])
    try:
        monkeypatch.setattr(
            "scripts.scrape_lotto_history.fetch_draw",
            lambda draw_no, verify_ssl=True: {"returnValue": "fail"},
        )
        assert fetch_and_save(conn, 9999) is False
    finally:
        conn.close()
