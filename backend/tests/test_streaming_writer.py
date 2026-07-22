"""Tests for the bounded-memory streaming result writer."""

import csv

import pytest
from openpyxl import load_workbook

from app.core.config import settings
from app.services.files import OUTPUT_COLUMNS, StreamingResultWriter


@pytest.fixture()
def _result_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RESULT_DIR", str(tmp_path))
    return tmp_path


def test_streaming_writer_csv_and_xlsx(_result_dir):
    writer = StreamingResultWriter("job-123")
    writer.write_row(
        {
            "original_company": "CEO at Microsoft",
            "clean_company": "Microsoft",
            "official_domain": "microsoft.com",
            "verification_status": "VERIFIED",
            "confidence": 0.97,
            "source_used": "wikipedia",
            "search_url": "https://wikidata",
            "processing_time_ms": 42,
        }
    )
    writer.write_row({"original_company": "Owner, ABC Traders", "clean_company": "ABC Traders"})
    writer.close()

    # CSV
    with open(writer.csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == OUTPUT_COLUMNS
    assert rows[1][2] == "microsoft.com"
    assert rows[2][2] == "NOT FOUND"  # missing domain defaults to NOT FOUND
    assert len(rows) == 3

    # XLSX
    wb = load_workbook(writer.xlsx_path)
    ws = wb["Results"]
    values = list(ws.iter_rows(values_only=True))
    assert list(values[0]) == OUTPUT_COLUMNS
    assert values[1][2] == "microsoft.com"
    assert values[2][2] == "NOT FOUND"


def test_close_is_idempotent(_result_dir):
    writer = StreamingResultWriter("job-idem")
    writer.write_row({"original_company": "X", "clean_company": "X"})
    writer.close()
    writer.close()  # must not raise
