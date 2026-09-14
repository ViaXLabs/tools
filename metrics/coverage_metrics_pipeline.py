#!/usr/bin/env python3
"""
coverage_metrics_pipeline.py

Monthly customer metrics pipeline (Harness job body).

WHAT THIS DOES
--------------
1. Downloads one raw metrics workbook from EACH configured S3 bucket
   (non-prod account).
2. Normalizes labels in each workbook (e.g. "team" -> "Program",
   "measured" -> "Coverage") per the CONFIG map below.
3. Filters down to the coverage metric rows, pulls the numeric score,
   and flags any row where score == 0 as needing remediation.
4. Merges the (now-cleaned) workbooks from all buckets into a single
   customer-facing workbook, with the zero-coverage rows called out
   on their own sheet and highlighted on the main sheet.

WHY IT'S SHAPED THIS WAY
------------------------
You mentioned you're going from memory on your friend's doc. Rather
than hard-code guesses about exact column names, every business rule
lives in the CONFIG block below. Nothing else in the file should need
to change once you confirm the real column names / values.

REQUIREMENTS
------------
pip install boto3 pandas openpyxl --break-system-packages
(Harness runner should already have AWS creds available via its
 IAM role / connector -- boto3 will pick them up automatically.)
"""

import io
import logging
import sys
from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("coverage_pipeline")


# =====================================================================
# CONFIG -- edit this block once you confirm the real doc/column names.
# Nothing below this block should need to change for typical tweaks.
# =====================================================================

@dataclass
class SourceConfig:
    """One S3 source to pull and normalize."""
    name: str                 # short label used in logs / merged output
    bucket: str
    key: str                  # exact S3 object key (path) of the XLSX
    sheet_name: str = 0       # sheet name/index to read, if not the first


# --- The two (or more) buckets you mentioned. Add more entries here
#     if a third bucket shows up later -- everything downstream already
#     loops over this list. ---
SOURCES: List[SourceConfig] = [
    SourceConfig(
        name="bucket_a",
        bucket="REPLACE-ME-non-prod-bucket-a",
        key="path/to/metrics-export.xlsx",
    ),
    SourceConfig(
        name="bucket_b",
        bucket="REPLACE-ME-non-prod-bucket-b",
        key="path/to/other-metrics-export.xlsx",
    ),
]

# --- Column names as they appear in the RAW source workbook. Fix these
#     once you check the actual file / your friend's doc. ---
RAW_CATEGORY_COLUMN = "Team"      # column that identifies team/grouping
RAW_METRIC_COLUMN = "Measured"    # column that names which metric a row is
RAW_SCORE_COLUMN = "Score"        # column with the numeric value

# --- Value relabeling. Left side = raw value (case-insensitive match),
#     right side = what it should become in the cleaned output. Add
#     more pairs as needed; anything not listed is left as-is. ---
CATEGORY_RELABEL: Dict[str, str] = {
    "team": "Program",
}
METRIC_RELABEL: Dict[str, str] = {
    "measured": "Coverage",
}

# --- After relabeling, which metric value identifies the coverage rows
#     we actually care about? (Matched against the RENAMED column.) ---
COVERAGE_METRIC_VALUE = "Coverage"

# --- Output column names in the cleaned/merged workbook. ---
OUT_CATEGORY_COLUMN = "Program"
OUT_SCORE_COLUMN = "Coverage %"
OUT_REMEDIATION_COLUMN = "Needs Remediation"

# --- Where the final workbook goes. Set UPLOAD_TO_S3 = False to only
#     write locally (e.g. if Harness picks it up as an artifact instead). ---
UPLOAD_TO_S3 = True
OUTPUT_BUCKET = "REPLACE-ME-output-bucket"
OUTPUT_KEY_TEMPLATE = "monthly-metrics/{year}-{month:02d}-coverage-report.xlsx"
LOCAL_OUTPUT_PATH = "coverage-report.xlsx"

# =====================================================================
# END CONFIG
# =====================================================================


def download_workbook(source: SourceConfig, s3_client=None) -> pd.DataFrame:
    """Pull one XLSX object from S3 and load it into a DataFrame."""
    if s3_client is None:
        import boto3
        s3_client = boto3.client("s3")
    log.info("Downloading s3://%s/%s (%s)", source.bucket, source.key, source.name)
    obj = s3_client.get_object(Bucket=source.bucket, Key=source.key)
    raw_bytes = obj["Body"].read()
    df = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=source.sheet_name)
    log.info("  -> loaded %d rows, %d columns", len(df), len(df.columns))
    return df


def relabel_values(df: pd.DataFrame, column: str, mapping: Dict[str, str]) -> pd.DataFrame:
    """Case-insensitively replace values in `column` per `mapping`.
    Values not in the mapping are left untouched.
    """
    if column not in df.columns:
        log.warning("  column %r not found -- skipping relabel", column)
        return df
    lower_map = {k.lower(): v for k, v in mapping.items()}

    def _relabel(val):
        if pd.isna(val):
            return val
        return lower_map.get(str(val).strip().lower(), val)

    df[column] = df[column].apply(_relabel)
    return df


def normalize(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Apply the CONFIG-driven relabeling + column renames to one raw
    source DataFrame. Returns a cleaned frame with standardized column
    names: OUT_CATEGORY_COLUMN, "Metric", RAW_SCORE_COLUMN.
    """
    df = df.copy()

    missing = [c for c in (RAW_CATEGORY_COLUMN, RAW_METRIC_COLUMN, RAW_SCORE_COLUMN)
               if c not in df.columns]
    if missing:
        raise ValueError(
            f"[{source_name}] Expected column(s) {missing} not found. "
            f"Actual columns: {list(df.columns)}. "
            "Fix RAW_CATEGORY_COLUMN / RAW_METRIC_COLUMN / RAW_SCORE_COLUMN "
            "in CONFIG to match the real file."
        )

    df = relabel_values(df, RAW_CATEGORY_COLUMN, CATEGORY_RELABEL)
    df = relabel_values(df, RAW_METRIC_COLUMN, METRIC_RELABEL)

    df = df.rename(columns={
        RAW_CATEGORY_COLUMN: OUT_CATEGORY_COLUMN,
        RAW_METRIC_COLUMN: "Metric",
        RAW_SCORE_COLUMN: OUT_SCORE_COLUMN,
    })

    # Drop fully blank rows (common junk from Excel exports).
    df = df.dropna(how="all")

    # Keep only rows that are actually about coverage, now that the
    # metric column has been relabeled.
    before = len(df)
    df = df[df["Metric"].astype(str).str.strip().str.lower()
             == COVERAGE_METRIC_VALUE.lower()].copy()
    log.info("  [%s] kept %d/%d rows matching metric=%r",
              source_name, len(df), before, COVERAGE_METRIC_VALUE)

    # Coerce score to numeric; anything unparsable becomes NaN and gets
    # dropped (adjust here if you'd rather keep/flag those instead).
    df[OUT_SCORE_COLUMN] = pd.to_numeric(df[OUT_SCORE_COLUMN], errors="coerce")
    unparsable = df[OUT_SCORE_COLUMN].isna().sum()
    if unparsable:
        log.warning("  [%s] dropping %d row(s) with non-numeric score",
                    source_name, unparsable)
    df = df.dropna(subset=[OUT_SCORE_COLUMN])

    # Flag remediation candidates.
    df[OUT_REMEDIATION_COLUMN] = df[OUT_SCORE_COLUMN] == 0

    df["Source"] = source_name
    return df[[OUT_CATEGORY_COLUMN, OUT_SCORE_COLUMN, OUT_REMEDIATION_COLUMN, "Source"]]


def merge_sources(cleaned_frames: List[pd.DataFrame]) -> pd.DataFrame:
    """Stack the cleaned per-bucket frames into one combined table.
    If two buckets report the same Program, both rows are kept (with a
    Source column) rather than silently overwritten -- change this to
    a pivot/groupby if you actually want one row per program instead.
    """
    merged = pd.concat(cleaned_frames, ignore_index=True)
    merged = merged.sort_values([OUT_CATEGORY_COLUMN, "Source"]).reset_index(drop=True)
    return merged


def write_report(merged: pd.DataFrame, path: str) -> None:
    """Write the merged table to XLSX with:
      - a main sheet, zero-coverage rows highlighted red
      - a separate 'Remediation' sheet listing only the zero-coverage rows
    """
    remediation = merged[merged[OUT_REMEDIATION_COLUMN]].copy()

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        merged.to_excel(writer, sheet_name="Coverage", index=False)
        remediation.to_excel(writer, sheet_name="Remediation", index=False)

        ws = writer.sheets["Coverage"]
        red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        remediation_col_idx = merged.columns.get_loc(OUT_REMEDIATION_COLUMN) + 1  # 1-based
        for row_idx in range(2, ws.max_row + 1):  # skip header
            cell = ws.cell(row=row_idx, column=remediation_col_idx)
            if cell.value is True:
                for col_idx in range(1, ws.max_column + 1):
                    ws.cell(row=row_idx, column=col_idx).fill = red_fill

        # Basic column widths so it's readable without manual resizing.
        for sheet in (writer.sheets["Coverage"], writer.sheets["Remediation"]):
            for col_idx, col_name in enumerate(merged.columns, start=1):
                width = max(12, len(str(col_name)) + 4)
                sheet.column_dimensions[get_column_letter(col_idx)].width = width

    log.info("Wrote report to %s (%d total rows, %d flagged for remediation)",
              path, len(merged), len(remediation))


def upload_report(path: str, bucket: str, key: str, s3_client=None) -> None:
    if s3_client is None:
        import boto3
        s3_client = boto3.client("s3")
    s3_client.upload_file(path, bucket, key)
    log.info("Uploaded report to s3://%s/%s", bucket, key)


def main() -> int:
    try:
        cleaned = []
        for source in SOURCES:
            raw = download_workbook(source)
            cleaned.append(normalize(raw, source.name))

        merged = merge_sources(cleaned)
        write_report(merged, LOCAL_OUTPUT_PATH)

        if UPLOAD_TO_S3:
            import datetime
            now = datetime.date.today()
            key = OUTPUT_KEY_TEMPLATE.format(year=now.year, month=now.month)
            upload_report(LOCAL_OUTPUT_PATH, OUTPUT_BUCKET, key)

        return 0
    except Exception:
        log.exception("Pipeline failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
