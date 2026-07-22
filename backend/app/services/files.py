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


_DELIMITERS = [",", ";", "\t", "|"]


def _detect_delimiter(header_line: str) -> str:
    """Pick the delimiter that appears most in the header, defaulting to comma.

    This is deliberately simpler and more predictable than ``csv.Sniffer``,
    which guesses stray letters as delimiters on single-column files.
    """
    best = ","
    best_count = 0
    for delim in _DELIMITERS:
        count = header_line.count(delim)
        if count > best_count:
            best, best_count = delim, count
    return best


def _read_csv_robust(path: str) -> pd.DataFrame:
    """Read a CSV tolerating unknown encodings and delimiters.

    - Tries UTF-8 (BOM-aware) first, then common fallbacks, so files exported
      from Excel/Windows don't blow up on decoding.
    - Detects the delimiter (comma/semicolon/tab/pipe) from the header line.
    - ``on_bad_lines='skip'`` keeps a few malformed rows from failing the whole
      upload.
    """
    last_exc: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(path, encoding=encoding) as fh:
                first_line = fh.readline()
            delimiter = _detect_delimiter(first_line)
            return pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                sep=delimiter,
                engine="python",
                encoding=encoding,
                on_bad_lines="skip",
            )
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    raise ValueError("Unable to parse CSV file.")


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Clean up a freshly parsed frame so downstream code can trust it."""
    # Stringify and de-duplicate column names (pandas appends .1, .2 already,
    # but blank headers become "Unnamed: N" — make those human-friendly).
    new_cols: list[str] = []
    seen: dict[str, int] = {}
    for i, col in enumerate(df.columns):
        name = str(col).strip() or f"Column {i + 1}"
        if name.startswith("Unnamed:"):
            name = f"Column {i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 0
        new_cols.append(name)
    df.columns = new_cols

    # Drop fully-empty columns and rows.
    df = df.replace({None: ""}).fillna("")
    df = df.loc[:, ~(df == "").all(axis=0)]
    df = df.loc[~(df == "").all(axis=1)]
    return df.reset_index(drop=True)


def read_dataframe(path: str, content_type: str, filename: str) -> pd.DataFrame:
    """Read an uploaded CSV/XLSX into a normalized string DataFrame."""
    lowered = filename.lower()
    is_csv = lowered.endswith(".csv") or "csv" in (content_type or "")
    is_excel = (
        lowered.endswith((".xlsx", ".xlsm", ".xls"))
        or "sheet" in (content_type or "")
        or "excel" in (content_type or "")
    )

    if is_csv:
        df = _read_csv_robust(path)
    elif is_excel:
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
    else:
        # Unknown extension: try CSV first, then Excel.
        try:
            df = _read_csv_robust(path)
        except Exception:  # noqa: BLE001
            df = pd.read_excel(path, dtype=str, keep_default_na=False)

    return _normalize_frame(df)


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
