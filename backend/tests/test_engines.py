from datetime import date

from app.pipeline.extract import parse_date, programme_key
from app.pipeline.text import PageText, Word


def test_parse_date_formats():
    assert parse_date("12 March 2026") == date(2026, 3, 12)
    assert parse_date("09 Nov 2026") == date(2026, 11, 9)
    assert parse_date("12/03/2026") == date(2026, 3, 12)
    assert parse_date("2026-03-12") == date(2026, 3, 12)
    assert parse_date("1st July, 2023") == date(2023, 7, 1)
    assert parse_date("not a date") is None


def test_programme_key_normalises_variants():
    k = programme_key("B.Tech Computer Science and Engineering")
    assert k == programme_key("B. Tech - Computer Science and Engineering")
    assert k == programme_key("BTech Computer Science and Engineering Programme")


def test_table_cells_on_one_row_form_one_line():
    words = [Word(70, 100, 80, 111, "1."), Word(115, 100, 150, 111, "B.Tech"),
             Word(155, 100, 200, 111, "Civil"), Word(500, 101, 515, 112, "60"),
             Word(70, 130, 80, 141, "2."), Word(115, 130, 140, 141, "MBA"), Word(500, 130, 515, 141, "60")]
    page = PageText(1, 595, 842, "text", words)
    assert page.text.splitlines() == ["1. B.Tech Civil 60", "2. MBA 60"]
