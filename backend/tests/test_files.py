"""Tests for robust file parsing."""

import pandas as pd
import pytest

from app.services.files import build_results_dataframe, read_dataframe


def test_reads_utf8_bom_and_semicolon(tmp_path):
    p = tmp_path / "data.csv"
    # BOM + semicolon delimiter + an accented character.
    p.write_bytes("Name;Company\nJosé;Nestlé\nAmy;Google\n".encode("utf-8-sig"))
    df = read_dataframe(str(p), "text/csv", "data.csv")
    assert list(df.columns) == ["Name", "Company"]
    assert df.iloc[0]["Company"] == "Nestlé"
    assert len(df) == 2


def test_reads_latin1_encoding(tmp_path):
    p = tmp_path / "legacy.csv"
    p.write_bytes("Company\nNestlé\n".encode("latin-1"))
    df = read_dataframe(str(p), "text/csv", "legacy.csv")
    assert len(df) == 1
    assert df.columns[0] == "Company"


def test_blank_and_duplicate_headers_are_normalized(tmp_path):
    p = tmp_path / "messy.csv"
    p.write_text("Company,,Company\nA,x,B\n")
    df = read_dataframe(str(p), "text/csv", "messy.csv")
    # No duplicate or empty column names remain.
    assert len(set(df.columns)) == len(df.columns)
    assert all(str(c).strip() for c in df.columns)


def test_empty_rows_dropped(tmp_path):
    p = tmp_path / "gaps.csv"
    p.write_text("Company\nGoogle\n\n\nApple\n")
    df = read_dataframe(str(p), "text/csv", "gaps.csv")
    assert len(df) == 2


def test_excel_roundtrip(tmp_path):
    src = pd.DataFrame({"Company": ["Microsoft", "Infosys Ltd"]})
    xlsx = tmp_path / "in.xlsx"
    src.to_excel(xlsx, index=False)
    df = read_dataframe(str(xlsx), "application/vnd.ms-excel", "in.xlsx")
    assert list(df["Company"]) == ["Microsoft", "Infosys Ltd"]


def test_build_results_dataframe_defaults_not_found():
    rows = [{"original_company": "X", "clean_company": "X"}]
    out = build_results_dataframe(rows)
    assert out.iloc[0]["Official Domain"] == "NOT FOUND"
    assert out.iloc[0]["Processing Time"].endswith("ms")
