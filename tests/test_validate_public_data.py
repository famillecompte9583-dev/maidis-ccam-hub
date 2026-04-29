from __future__ import annotations

from scripts.validate_public_data import CODE_RE, public_url, parse_iso_date


def test_code_regex_accepts_valid_ccam_code() -> None:
    assert CODE_RE.match("HBKD140")


def test_code_regex_rejects_invalid_ccam_code() -> None:
    assert not CODE_RE.match("HBK140")
    assert not CODE_RE.match("hbkd140")


def test_public_url_accepts_http_and_https() -> None:
    assert public_url("https://www.ameli.fr")
    assert public_url("http://example.org/path")


def test_public_url_rejects_non_public_scheme() -> None:
    assert not public_url("javascript:alert(1)")
    assert not public_url("mailto:test@example.org")


def test_parse_iso_date_handles_valid_and_invalid_values() -> None:
    assert parse_iso_date("2026-04-29") is not None
    assert parse_iso_date("29/04/2026") is None
