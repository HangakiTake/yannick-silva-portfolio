import datetime as dt
import pytest
import pipeline as p

@pytest.mark.parametrize("raw,exp", [
    (1234.5, 1234.5), ("1234.56", 1234.56), ("1 234,56", 1234.56), ("1\u00a0234,56", 1234.56),
    ("1.234,56", 1234.56), ("1,234.56", 1234.56), ("12,5", 12.5), ("-500", -500.0), ("-1.234,50", -1234.5),
    ("1,234", None), ("1.234", None), ("1.234.567", None), ("n/a", None), ("ca. 500", None), ("", None), (None, None), (True, None),
    ("500 zł", None), ("€500", None)])
def test_amount(raw, exp):
    assert p.parse_amount(raw) == exp

@pytest.mark.parametrize("raw,exp", [
    (dt.datetime(2026, 6, 3, 0, 0), dt.date(2026, 6, 3)), (dt.date(2026, 6, 3), dt.date(2026, 6, 3)),
    ("03.06.2026", dt.date(2026, 6, 3)), ("2026-06-03", dt.date(2026, 6, 3)),
    ("31.02.2026", None), ("TBC", None), (46176, None), ("06/03/2026", None)])
def test_date(raw, exp):
    assert p.parse_date(raw) == exp

def test_norm_name():
    assert p.norm_name("  Nord  Metal Sp.z o.o. ") == p.norm_name("NORD METAL SP. Z O.O.")
    assert p.norm_name("Müller Bau GmbH") != p.norm_name("Mueller Bau GmbH")  # deliberate: no transliteration
