from __future__ import annotations

import pytest

from klotto.qr_utils import parse_lotto_qr_url
from klotto.ui.scanner import decode_qr_text, is_lotto_qr_url


def test_decode_qr_text_rejects_non_utf8_bytes():
    assert decode_qr_text(b'\xff\xfe\x00invalid') is None


def test_decode_qr_text_round_trips_valid_url():
    url = 'http://m.dhlottery.co.kr/?v=1234m010203040506'
    assert decode_qr_text(url.encode('utf-8')) == url


def test_is_lotto_qr_url_classifies_foreign_qr():
    assert is_lotto_qr_url('http://m.dhlottery.co.kr/?v=1234m010203040506') is True
    assert is_lotto_qr_url('https://example.com/hello') is False
    assert is_lotto_qr_url('') is False


def test_parse_lotto_qr_url_reports_skipped_games():
    result = parse_lotto_qr_url('http://m.dhlottery.co.kr/?v=1234m010203040506nXYZ')

    assert result['draw_no'] == 1234
    assert result['sets'] == [[1, 2, 3, 4, 5, 6]]
    assert result['skipped'] == 1


def test_parse_lotto_qr_url_counts_out_of_range_game_as_skipped():
    result = parse_lotto_qr_url('http://m.dhlottery.co.kr/?v=1234m010203040506n990099009900')

    assert result['sets'] == [[1, 2, 3, 4, 5, 6]]
    assert result['skipped'] == 1


def test_parse_lotto_qr_url_without_skips_reports_zero():
    result = parse_lotto_qr_url('http://m.dhlottery.co.kr/?v=1234m010203040506')

    assert result['skipped'] == 0


def test_parse_lotto_qr_url_still_rejects_empty_games():
    with pytest.raises(ValueError):
        parse_lotto_qr_url('http://m.dhlottery.co.kr/?v=1234mXYZ')
