"""
Ingestion Layer — loads Excel project plans into the common internal shape.

Handles two distinct schemas (S2P_Project and Project_Plan_B) by mapping
whatever columns exist to the common ProjectData model. Missing columns
result in None fields, never silent defaults. Malformed cells are logged
in data_gaps, not dropped silently.

Column names used here come exclusively from SCHEMA_REFERENCE.md.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.models import Comment, ProjectData, ProjectSummary, Task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_duration_or_variance(val) -> Optional[float]:
    """Parse values like '-2d', '262d', '0' into float days.

    Returns None for unparseable values rather than a silent default.
    """
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s == "" or s == "#UNPARSEABLE":
        return None
    # Strip trailing 'd' if present
    s = re.sub(r"[dD]$", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _parse_bool_flag(val) -> Optional[bool]:
    """Parse boolean flag columns (At Risk?, On Hold?, Not Applicable?, Critical ?).

    These columns use 1.0 for True and NaN for False/absent in the actual data.
    """
    if pd.isna(val):
        return None
    try:
        return bool(float(val))
    except (ValueError, TypeError):
        # Might be a string like 'TRUE'/'FALSE'
        s = str(val).strip().upper()
        if s in ("TRUE", "YES", "1"):
            return True
        if s in ("FALSE", "NO", "0"):
            return False
        return None


def _parse_date(val) -> Optional[date]:
    """Convert a cell value to a date.

    Handles: pandas Timestamps, datetime objects, Excel serial numbers,
    and date strings. Returns None (not a default date) for unparseable values.
    """
    if pd.isna(val):
        return None
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if s == "" or s == "#UNPARSEABLE":
        return None
    # Try Excel serial number (integer or float)
    try:
        serial = float(s)
        if 30000 < serial < 60000:
            # Excel serial date: days since 1899-12-30
            ts = pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(serial))
            return ts.date()
    except ValueError:
        pass
    # Try common date string formats
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_percent(val) -> Optional[float]:
    """Parse percentage values (0.0 to 1.0 range)."""
    if pd.isna(val):
        return None
    try:
        v = float(val)
        return v
    except (ValueError, TypeError):
        return None


def _safe_str(val) -> Optional[str]:
    """Convert to string, returning None for NaN/empty/#UNPARSEABLE."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s == "" or s == "#UNPARSEABLE":
        return None
    return s


def _safe_int(val) -> Optional[int]:
    """Convert to int, returning None for NaN."""
    if pd.isna(val):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    """Convert to float, returning None for NaN."""
    if pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Column mapping — maps actual column names to Task model fields
# ---------------------------------------------------------------------------

# Columns present in both files (SCHEMA_REFERENCE.md)
COMMON_COLUMN_MAP = {
    "Task Name": "task_name",
    "Phase/Milestone": "phase_milestone",
    "Status": "status",
    "Start Date": "start_date",
    "End Date": "end_date",
    "Baseline Start": "baseline_start",
    "Baseline Finish": "baseline_finish",
    "Variance": "variance",
    "% Complete": "percent_complete",
    "Critical ?": "is_critical",
    "On Hold?": "on_hold",
    "Not Applicable?": "not_applicable",
    "Schedule Health": "schedule_health",
    "Status Comment": "status_comment",
    "At Risk?": "at_risk",
    "Owner": "owner",
    "Area": "area",
    "Priority": "priority",
    "Duration": "duration",
    "Total Float": "total_float",
    "Project Name": "project_name",
}

# Columns only in S2P_Project (SCHEMA_REFERENCE.md)
S2P_EXTRA_COLUMNS = {
    "RAG": "rag",
    "Level": "level",
}


# ---------------------------------------------------------------------------
# Sheet loaders
# ---------------------------------------------------------------------------


def _detect_main_sheet(xls: pd.ExcelFile) -> str:
    """Find the main task sheet — it's the one that isn't 'Comments' or 'Summary'."""
    for name in xls.sheet_names:
        if str(name).lower() not in ("comments", "summary"):
            return str(name)
    # Shouldn't happen with our known files, but fail explicitly
    raise ValueError(
        f"Could not identify main task sheet. Sheets found: {xls.sheet_names}"
    )


def _load_tasks(df: pd.DataFrame, data_gaps: list[str]) -> tuple[list[Task], bool]:
    """Parse the main task sheet into Task objects.

    Returns (tasks, has_rag_column).
    """
    tasks = []
    columns = set(df.columns)
    has_rag = "RAG" in columns

    if not has_rag:
        data_gaps.append(
            "No task-level RAG column in source file — "
            "only Schedule Health available for status comparison"
        )

    # Track #UNPARSEABLE occurrences
    unparseable_count = 0

    for idx, row in df.iterrows():
        # Check for #UNPARSEABLE in any cell
        for col in columns:
            val = row.get(col)
            if isinstance(val, str) and val.strip() == "#UNPARSEABLE":
                unparseable_count += 1

        # Skip rows that are entirely empty (no task name and no status)
        task_name = _safe_str(row.get("Task Name"))
        status = _safe_str(row.get("Status"))
        if task_name is None and status is None:
            continue

        task = Task(
            task_name=task_name,
            phase_milestone=_safe_str(row.get("Phase/Milestone")),
            status=status,
            start_date=_parse_date(row.get("Start Date")),
            end_date=_parse_date(row.get("End Date")),
            baseline_start=_parse_date(row.get("Baseline Start")),
            baseline_finish=_parse_date(row.get("Baseline Finish")),
            variance=_parse_duration_or_variance(row.get("Variance")),
            percent_complete=_parse_percent(row.get("% Complete")),
            is_critical=_parse_bool_flag(row.get("Critical ?")),
            on_hold=_parse_bool_flag(row.get("On Hold?")),
            not_applicable=_parse_bool_flag(row.get("Not Applicable?")),
            rag=_safe_str(row.get("RAG")) if has_rag else None,
            schedule_health=_safe_str(row.get("Schedule Health")),
            status_comment=_safe_str(row.get("Status Comment")),
            at_risk=_parse_bool_flag(row.get("At Risk?")),
            owner=_safe_str(row.get("Owner")),
            area=_safe_str(row.get("Area")),
            priority=_safe_str(row.get("Priority")),
            duration=_parse_duration_or_variance(row.get("Duration")),
            total_float=_safe_float(row.get("Total Float")),
            project_name=_safe_str(row.get("Project Name")),
            level=_safe_int(row.get("Level")) if "Level" in columns else None,
        )
        tasks.append(task)

    if unparseable_count > 0:
        data_gaps.append(
            f"{unparseable_count} cells contain '#UNPARSEABLE' — "
            "logged and excluded from calculations"
        )

    return tasks, has_rag


def _load_comments(xls: pd.ExcelFile, data_gaps: list[str]) -> list[Comment]:
    """Load the Comments sheet.

    The Comments sheet has no header row in S2P_Project — columns are:
    [row_reference, comment_text, author, timestamp].
    For Plan B the sheet is empty (0 rows).
    """
    try:
        df = pd.read_excel(xls, sheet_name="Comments", header=None)
    except Exception as e:
        data_gaps.append(f"Failed to read Comments sheet: {e}")
        logger.error("Failed to read Comments sheet: %s", e)
        return []

    if df.empty:
        data_gaps.append("Comments sheet is empty — no sentiment data from comments")
        return []

    comments = []
    for _, row in df.iterrows():
        # Skip entirely empty rows
        vals = [v for v in row if not pd.isna(v)]
        if not vals:
            continue

        # The 4 columns are: row_reference, text, author, timestamp
        text = _safe_str(row.iloc[1]) if len(row) > 1 else None
        author = _safe_str(row.iloc[2]) if len(row) > 2 else None
        comment_date = None
        if len(row) > 3:
            raw_date = row.iloc[3]
            # Try parsing the timestamp format "06/26/26 2:25 PM"
            if isinstance(raw_date, str):
                for fmt in ("%m/%d/%y %I:%M %p", "%m/%d/%Y %I:%M %p", "%m/%d/%y"):
                    try:
                        comment_date = datetime.strptime(raw_date.strip(), fmt).date()
                        break
                    except ValueError:
                        continue
            else:
                comment_date = _parse_date(raw_date)

        extra_val = _safe_str(row.iloc[0]) if len(row) > 0 else None

        if text is not None:
            comments.append(Comment(
                text=text,
                author=author,
                comment_date=comment_date,
                extra=extra_val,
            ))

    return comments


def _load_summary(xls: pd.ExcelFile, data_gaps: list[str]) -> Optional[ProjectSummary]:
    """Load the Summary sheet (vertical key-value layout, no real header).

    The sheet has two columns: field name in col 0, value in col 1.
    First row is 'Project Name' with a NaN value — this is a section label, not data.
    """
    try:
        df = pd.read_excel(xls, sheet_name="Summary", header=None)
    except Exception as e:
        data_gaps.append(f"Failed to read Summary sheet: {e}")
        logger.error("Failed to read Summary sheet: %s", e)
        return None

    if df.empty:
        data_gaps.append("Summary sheet is empty")
        return None

    # Build a key-value dict from the two columns
    kv = {}
    for _, row in df.iterrows():
        key = _safe_str(row.iloc[0])
        val = row.iloc[1] if len(row) > 1 else None
        if key is not None:
            kv[key] = val

    return ProjectSummary(
        project_manager=_safe_str(kv.get("Project Manager")),
        project_start_date=_parse_date(kv.get("Project Start Date")),
        project_end_date=_parse_date(kv.get("Project End Date")),
        not_started_count=_safe_int(kv.get("Not Started")),
        in_progress_count=_safe_int(kv.get("In Progress")),
        completed_count=_safe_int(kv.get("Completed")),
        on_hold_count=_safe_int(kv.get("On Hold")),
        at_risk=_safe_str(kv.get("At Risk")),
        project_stage=_safe_str(kv.get("Project Stage")),
        percent_complete=_parse_percent(kv.get("% Complete")),
        schedule_health=_safe_str(kv.get("Schedule Health")),
        todays_date=_parse_date(kv.get("Today's Date")),
        duration=_safe_int(kv.get("Duration")),
        project_status=_safe_str(kv.get("Project Status")),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_project(filepath: Path) -> ProjectData:
    """Load a project plan Excel file into the common internal shape.

    Works with both S2P_Project.xlsx and Project_Plan_B.xlsx schemas.
    Missing columns → None fields. Malformed cells → data_gaps entries.
    Never silently defaults to Green/0/any other value.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Project file not found: {filepath}")

    data_gaps: list[str] = []
    logger.info("Loading project file: %s", filepath)

    try:
        xls = pd.ExcelFile(filepath)
    except Exception as e:
        raise RuntimeError(f"Failed to open Excel file {filepath}: {e}") from e

    # Identify sheets
    logger.info("Sheets found: %s", xls.sheet_names)
    main_sheet = _detect_main_sheet(xls)
    logger.info("Main task sheet: %s", main_sheet)

    # Load main task sheet
    try:
        main_df = pd.read_excel(xls, sheet_name=main_sheet)
    except Exception as e:
        raise RuntimeError(
            f"Failed to read main sheet '{main_sheet}' from {filepath}: {e}"
        ) from e

    logger.info(
        "Main sheet: %d rows × %d cols", len(main_df), len(main_df.columns)
    )

    # Check for missing columns that we expect
    expected_core = {"Task Name", "Status", "Start Date", "End Date", "% Complete"}
    missing_core = expected_core - set(main_df.columns)
    if missing_core:
        data_gaps.append(
            f"Missing expected core columns: {sorted(missing_core)} — "
            "affected dimensions will be marked Not Assessed"
        )

    # No cost/budget columns in either file per SCHEMA_REFERENCE.md
    data_gaps.append("No cost/budget columns present in source file")

    # Check Status Comment column
    if "Status Comment" in main_df.columns:
        non_null = main_df["Status Comment"].notna().sum()
        if non_null == 0:
            data_gaps.append(
                "Status Comment column is entirely empty — "
                "sentiment analysis will rely on Comments sheet only"
            )

    # Parse tasks
    tasks, has_rag = _load_tasks(main_df, data_gaps)
    logger.info("Parsed %d tasks (has_rag=%s)", len(tasks), has_rag)

    # Load comments
    comments = _load_comments(xls, data_gaps)
    logger.info("Parsed %d comments", len(comments))

    # Load summary
    summary = _load_summary(xls, data_gaps)
    if summary:
        logger.info(
            "Summary: PM=%s, schedule_health=%s, at_risk=%s",
            summary.project_manager,
            summary.schedule_health,
            summary.at_risk,
        )

    # Derive project name from summary or main sheet or filename
    project_name = None
    if summary and summary.project_manager:
        # Use the main sheet name as project identifier
        project_name = main_sheet
    if project_name is None:
        # Fall back to first non-null project name in tasks
        for t in tasks:
            if t.project_name:
                project_name = t.project_name
                break
    if project_name is None:
        project_name = filepath.stem

    # Map generic or sheet names to clean business client names: UniSan and Titan
    if project_name == "Project Plan" or "UniSan" in str(project_name):
        project_name = "UniSan"
    elif project_name == "Outokumpu- S2P Project" or "Titan" in str(project_name) or "Outokumpu" in str(project_name):
        project_name = "Titan"

    return ProjectData(
        project_name=project_name,
        file_path=str(filepath),
        tasks=tasks,
        comments=comments,
        summary=summary,
        data_gaps=data_gaps,
        has_rag_column=has_rag,
    )
