"""
Pydantic models for the Project Health Reporting Agent.

Defines the common internal shape that both Excel files get normalized into,
plus the output schemas for signals and weekly reports.

All field names here correspond to columns documented in SCHEMA_REFERENCE.md.
Optional fields are nullable because not every file has every column
(e.g., Project_Plan_B has no RAG column at all).
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# RAG status type used across all scoring dimensions
# "Not Assessed" is required by Methodology.md for dimensions with no data
# ---------------------------------------------------------------------------
RAGStatus = Literal["Green", "Amber", "Red", "Not Assessed"]


# ---------------------------------------------------------------------------
# Ingestion output models — the common internal shape
# Architecture doc: {tasks[], milestones[], comments[], baseline_dates, schedule_health}
# ---------------------------------------------------------------------------


class Task(BaseModel):
    """A single task row from the main project sheet.

    Field names map to SCHEMA_REFERENCE.md columns. Fields that exist in one
    file but not the other (e.g. 'rag' only in S2P_Project) are Optional.
    """

    task_name: Optional[str] = None                     # "Task Name"
    phase_milestone: Optional[str] = None               # "Phase/Milestone"
    status: Optional[str] = None                        # "Status" — Completed / Not Started / In Progress / On Hold / Not Applicable
    start_date: Optional[date] = None                   # "Start Date"
    end_date: Optional[date] = None                     # "End Date"
    baseline_start: Optional[date] = None               # "Baseline Start"
    baseline_finish: Optional[date] = None              # "Baseline Finish"
    variance: Optional[float] = None                    # "Variance" — days of slip (negative = ahead)
    percent_complete: Optional[float] = None            # "% Complete" — 0.0 to 1.0
    is_critical: Optional[bool] = None                  # "Critical ?" — TRUE/FALSE
    on_hold: Optional[bool] = None                      # "On Hold?"
    not_applicable: Optional[bool] = None               # "Not Applicable?"
    rag: Optional[str] = None                           # "RAG" — only in S2P_Project, absent from Plan B
    schedule_health: Optional[str] = None               # "Schedule Health"
    status_comment: Optional[str] = None                # "Status Comment" — empty in both files per SCHEMA_REFERENCE
    at_risk: Optional[bool] = None                      # "At Risk?"
    owner: Optional[str] = None                         # "Owner"
    area: Optional[str] = None                          # "Area"
    priority: Optional[str] = None                      # "Priority"
    duration: Optional[float] = None                    # "Duration"
    total_float: Optional[float] = None                 # "Total Float"
    project_name: Optional[str] = None                  # "Project Name"
    level: Optional[int] = None                         # "Level" — only in S2P_Project


class Comment(BaseModel):
    """A row from the Comments sheet.

    Column names for the Comments sheet are not fully documented in
    SCHEMA_REFERENCE.md (only row/col counts are given: 24×4 for S2P,
    0 rows for Plan B). Fields here are populated during ingestion by
    reading whatever columns actually exist in the sheet.
    """

    text: Optional[str] = None
    author: Optional[str] = None
    comment_date: Optional[date] = None
    extra: Optional[str] = None  # 4th column — name discovered at ingestion


class ProjectSummary(BaseModel):
    """Project-level rollup from the Summary sheet (19 rows × 2 cols).

    This is a vertical key-value layout, not a tabular one.
    Field names match the keys shown in SCHEMA_REFERENCE.md exactly.
    """

    project_manager: Optional[str] = None               # "Project Manager"
    project_start_date: Optional[date] = None           # "Project Start Date"
    project_end_date: Optional[date] = None             # "Project End Date"
    not_started_count: Optional[int] = None             # "Not Started"
    in_progress_count: Optional[int] = None             # "In Progress"
    completed_count: Optional[int] = None               # "Completed"
    on_hold_count: Optional[int] = None                 # "On Hold"
    at_risk: Optional[str] = None                       # "At Risk" — e.g. "High"
    project_stage: Optional[str] = None                 # "Project Stage"
    percent_complete: Optional[float] = None            # "% Complete" — 0.0 to 1.0
    schedule_health: Optional[str] = None               # "Schedule Health" — Green / Red / Yellow
    todays_date: Optional[date] = None                  # "Today's Date"
    duration: Optional[int] = None                      # "Duration"
    project_status: Optional[str] = None                # "Project Status"


class ProjectData(BaseModel):
    """The common internal shape that both Excel files are normalized into.

    This is the single structure passed from the Ingestion Layer to the
    Signal Engine. Any column that didn't exist in the source file results
    in None fields, never silent defaults. Missing data is tracked in
    data_gaps for explicit reporting.
    """

    project_name: str
    file_path: str
    tasks: list[Task] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    summary: Optional[ProjectSummary] = None
    data_gaps: list[str] = Field(default_factory=list)

    # Whether the source file had a task-level RAG column at all
    has_rag_column: bool = False


# ---------------------------------------------------------------------------
# Signal Engine output models
# ---------------------------------------------------------------------------


class PhasePerformance(BaseModel):
    """Calculated and reported RAG status + completion for a specific project phase."""

    phase_name: str
    percent_complete: float
    computed_rag: RAGStatus
    source_reported_rag: Optional[str] = None
    root_cause: str


class SubScores(BaseModel):
    """Five independent RAG dimensions per Methodology.md.

    Each dimension is scored independently; "Not Assessed" is used when the
    source data doesn't contain the necessary columns (e.g., no cost/budget
    columns exist in either sample file → budget_burn = "Not Assessed").
    """

    schedule: RAGStatus = "Not Assessed"
    milestone_health: RAGStatus = "Not Assessed"
    blockers: RAGStatus = "Not Assessed"
    budget_burn: RAGStatus = "Not Assessed"
    stakeholder_sentiment: RAGStatus = "Not Assessed"


class SignalResult(BaseModel):
    """Complete output of the Signal Engine for one project.

    Carries the sub-scores, overall RAG (worst-of-dimensions per Methodology),
    the source-reported status for disagreement detection, the specific
    evidence that drove each score, any data gaps encountered, and the
    granular breakdown per project phase.
    """

    sub_scores: SubScores = Field(default_factory=SubScores)
    overall_rag: RAGStatus = "Not Assessed"

    # From the Summary sheet's "Schedule Health" field — compared against
    # computed overall_rag to produce the disagreement flag
    source_reported_rag: Optional[str] = None
    disagreement_flag: bool = False

    evidence: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    phase_performances: list[PhasePerformance] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Weekly report output — matches ARCHITECTURE.md Section 6 JSON schema
# ---------------------------------------------------------------------------


class WeeklyReport(BaseModel):
    """The final weekly output per project per run.

    Schema matches ARCHITECTURE.md Section 6 exactly. This is what gets
    written to data/weekly/{project_name}/{YYYY-MM-DD}.json.
    """

    project_name: str
    run_date: str                                       # ISO date string YYYY-MM-DD
    overall_rag: RAGStatus
    source_reported_rag: Optional[str] = None
    disagreement_flag: bool = False
    sub_scores: SubScores
    evidence: list[str] = Field(default_factory=list)
    reasoning: str = ""                                 # LLM-generated paragraph from Reasoning Agent
    data_gaps: list[str] = Field(default_factory=list)
    phase_performances: list[PhasePerformance] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Synthesis / Deck output models
# ---------------------------------------------------------------------------


class SlideContent(BaseModel):
    """Content for a single slide in the exec deck."""

    title: str
    bullets: list[str] = Field(default_factory=list)
    notes: Optional[str] = None                         # Speaker notes


class SynthesisResult(BaseModel):
    """Output of the Synthesis Agent — structured content for 5-7 slides.

    The Synthesis Agent is prompted to compare across projects and surface
    patterns, never to recap one project at a time (per ARCHITECTURE.md §5).
    """

    slides: list[SlideContent] = Field(default_factory=list)
    cross_project_trends: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
