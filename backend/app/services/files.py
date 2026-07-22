"""Spreadsheet import/export helpers (CSV + XLSX)."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from app.core.config import settings

OUTPUT_COLUMNS = [
    "Original Company",
    "Clean Company Name",
    "Official Domain",
    "Verification Status",
    "Confidence",
    "Source Used",
    "Search URL",
    "Processing Time",
]


def ensure_dirs() -> None:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.RESULT_DIR, exist_ok=True)


def read_dataframe(path: str, content_type: str, filename: str) -> pd.DataFrame:
    """Read an uploaded CSV/XLSX into a DataFrame, with dtype preserved as str."""
    lowered = filename.lower()
    if lowered.endswith(".csv") or "csv" in content_type:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if lowered.endswith((".xlsx", ".xlsm", ".xls")) or "sheet" in content_type or "excel" in content_type:
        return pd.read_excel(path, dtype=str, keep_default_na=False)
    # Fallback: try CSV then Excel.
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception:  # noqa: BLE001
        return pd.read_excel(path, dtype=str, keep_default_na=False)


def dataframe_preview(df: pd.DataFrame, limit: int = 20) -> dict[str, Any]:
    head = df.head(limit).fillna("")
    return {
        "columns": list(df.columns),
        "rows": head.to_dict(orient="records"),
        "total_rows": int(len(df)),
    }


def build_results_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Assemble the enriched output DataFrame in the required column order."""
    normalized = []
    for r in rows:
        normalized.append(
            {
                "Original Company": r.get("original_company", ""),
                "Clean Company Name": r.get("clean_company", ""),
                "Official Domain": r.get("official_domain") or "NOT FOUND",
                "Verification Status": r.get("verification_status", ""),
                "Confidence": r.get("confidence", 0.0),
                "Source Used": r.get("source_used") or "",
                "Search URL": r.get("search_url") or "",
                "Processing Time": f"{r.get('processing_time_ms', 0)} ms",
            }
        )
    return pd.DataFrame(normalized, columns=OUTPUT_COLUMNS)


def write_results(job_id: str, rows: list[dict[str, Any]]) -> tuple[str, str]:
    """Write both XLSX and CSV outputs; return their paths."""
    ensure_dirs()
    df = build_results_dataframe(rows)
    xlsx_path = os.path.join(settings.RESULT_DIR, f"{job_id}.xlsx")
    csv_path = os.path.join(settings.RESULT_DIR, f"{job_id}.csv")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
    df.to_csv(csv_path, index=False)
    return xlsx_path, csv_path
