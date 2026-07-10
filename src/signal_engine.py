"""
Signal Engine — computes 5 sub-RAG scores + overall RAG from ProjectData.

All thresholds are from Methodology.md. Comments cite the specific rule
they implement. The engine is deterministic (no LLM) — the Reasoning Agent
in the next stage explains the scores, it never overrides them.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional, cast

from src.models import ProjectData, SignalResult, SubScores, RAGStatus

logger = logging.getLogger(__name__)


def compute_signals(
    project: ProjectData,
    effective_date: Optional[date] = None,
) -> SignalResult:
    """Run all five scoring dimensions and produce the final SignalResult.

    Args:
        project: The common internal shape from the Ingestion Layer.
        effective_date: Override for "today" — used for simulated weekly runs.
                        Falls back to the Summary sheet's Today's Date, then
                        actual today.
    """
    today = effective_date
    if today is None and project.summary and project.summary.todays_date:
        today = project.summary.todays_date
    if today is None:
        today = date.today()

    data_gaps = list(project.data_gaps)  # carry forward ingestion gaps
    evidence: list[str] = []

    schedule = _score_schedule(project, evidence, data_gaps)
    milestone = _score_milestone_health(project, today, evidence, data_gaps)
    blockers = _score_blockers(project, evidence, data_gaps)
    budget = _score_budget(project, evidence, data_gaps)
    sentiment = _score_sentiment(project, today, evidence, data_gaps)

    sub_scores = SubScores(
        schedule=schedule,
        milestone_health=milestone,
        blockers=blockers,
        budget_burn=budget,
        stakeholder_sentiment=sentiment,
    )

    # Overall RAG = worst-of-dimensions (Methodology.md: "one Red dimension
    # makes the project Red overall"). "Not Assessed" dimensions are excluded
    # from the worst-of calculation — they don't drag the score down, but they
    # are reported as data gaps.
    assessed = [
        v for v in [schedule, milestone, blockers, budget, sentiment]
        if v != "Not Assessed"
    ]

    if not assessed:
        overall = "Not Assessed"
        data_gaps.append("No dimensions could be assessed — all data missing")
    else:
        # Priority: Red > Amber > Green
        if "Red" in assessed:
            overall = "Red"
        elif "Amber" in assessed:
            overall = "Amber"
        else:
            overall = "Green"

    # Disagreement flag: compare computed overall RAG against the source file's
    # Schedule Health field from the Summary sheet (Methodology.md: "both are
    # shown side by side with the specific evidence driving the computed rating")
    source_rag = None
    if project.summary and project.summary.schedule_health:
        source_rag = project.summary.schedule_health
        # Normalize "Yellow" → "Amber" for comparison
        if source_rag == "Yellow":
            source_rag = "Amber"

    disagreement = False
    if source_rag and overall != "Not Assessed":
        disagreement = (overall != source_rag)
        if disagreement and project.summary:
            evidence.append(
                f"Disagreement: computed overall={overall} vs source "
                f"Schedule Health={project.summary.schedule_health}. "
                f"Source also reports At Risk={project.summary.at_risk}."
            )

    return SignalResult(
        sub_scores=sub_scores,
        overall_rag=cast(RAGStatus, overall),
        source_reported_rag=source_rag,
        disagreement_flag=disagreement,
        evidence=evidence,
        data_gaps=data_gaps,
    )


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------


def _score_schedule(
    project: ProjectData,
    evidence: list[str],
    data_gaps: list[str],
) -> RAGStatus:
    """Schedule slippage dimension.

    Methodology.md thresholds:
    - Green: ≤0 days slip
    - Amber: 1–10 days slip
    - Red: >10 days slip, OR any critical-path task slips at all
    """
    tasks_with_variance = [
        t for t in project.tasks
        if t.variance is not None and t.status not in ("Completed", "Not Applicable")
    ]

    if not tasks_with_variance:
        data_gaps.append(
            "Schedule: no active tasks with variance data — dimension not assessable"
        )
        return "Not Assessed"

    # Check for any critical-path task slipping (variance > 0)
    critical_slipping = [
        t for t in tasks_with_variance
        if t.is_critical and t.variance is not None and t.variance > 0
    ]

    if critical_slipping:
        names = ", ".join(
            f"{t.task_name} (+{t.variance:.0f}d)" for t in critical_slipping[:5]
        )
        evidence.append(
            f"Schedule RED: {len(critical_slipping)} critical-path task(s) "
            f"slipping: {names}"
        )
        return "Red"

    # Check maximum slip among active tasks
    max_slip = max(
        (t.variance for t in tasks_with_variance if t.variance is not None),
        default=0.0,
    )

    # Count tasks slipping significantly
    big_slips = [
        t for t in tasks_with_variance
        if t.variance is not None and t.variance > 10
    ]

    if big_slips:
        names = ", ".join(
            f"{t.task_name} (+{t.variance:.0f}d)" for t in big_slips[:5]
        )
        evidence.append(
            f"Schedule RED: {len(big_slips)} task(s) with >10-day slip: {names}"
        )
        return "Red"

    if max_slip > 0:
        slipping = [
            t for t in tasks_with_variance
            if t.variance is not None and t.variance > 0
        ]
        evidence.append(
            f"Schedule AMBER: {len(slipping)} task(s) slipping 1–10 days, "
            f"max slip={max_slip:.0f}d"
        )
        return "Amber"

    evidence.append("Schedule GREEN: no active tasks slipping")
    return "Green"


def _score_milestone_health(
    project: ProjectData,
    today: date,
    evidence: list[str],
    data_gaps: list[str],
) -> RAGStatus:
    """Milestone health dimension.

    Methodology.md thresholds:
    - Green: on or ahead of pace
    - Amber: up to 15% behind pace
    - Red: more than 15% behind pace
    """
    if not project.summary:
        data_gaps.append("Milestone: no Summary sheet — dimension not assessable")
        return "Not Assessed"

    summary = project.summary
    actual_pct = summary.percent_complete
    start = summary.project_start_date
    end = summary.project_end_date

    if actual_pct is None or start is None or end is None:
        data_gaps.append(
            "Milestone: missing % Complete, start, or end date in Summary — "
            "dimension not assessable"
        )
        return "Not Assessed"

    total_duration = (end - start).days
    if total_duration <= 0:
        data_gaps.append("Milestone: project duration is zero or negative")
        return "Not Assessed"

    elapsed = (today - start).days
    # Clamp elapsed to [0, total_duration]
    elapsed = max(0, min(elapsed, total_duration))
    expected_pct = elapsed / total_duration

    # Gap: positive = behind pace, negative = ahead
    gap = expected_pct - actual_pct

    if gap <= 0:
        evidence.append(
            f"Milestone GREEN: {actual_pct:.0%} complete vs {expected_pct:.0%} "
            f"expected ({elapsed}/{total_duration} days elapsed) — on/ahead of pace"
        )
        return "Green"
    elif gap <= 0.15:
        evidence.append(
            f"Milestone AMBER: {actual_pct:.0%} complete vs {expected_pct:.0%} "
            f"expected — {gap:.1%} behind pace"
        )
        return "Amber"
    else:
        evidence.append(
            f"Milestone RED: {actual_pct:.0%} complete vs {expected_pct:.0%} "
            f"expected — {gap:.1%} behind pace"
        )
        return "Red"


def _score_blockers(
    project: ProjectData,
    evidence: list[str],
    data_gaps: list[str],
) -> RAGStatus:
    """Blockers dimension.

    Methodology.md thresholds:
    - Green: <5% of tasks blocked
    - Amber: 5–15% blocked
    - Red: >15% blocked, OR any critical-path task on hold

    "Blocked" = On Hold + Not Applicable + task-level RAG=Red (when RAG column
    exists). Weighted toward critical tasks per methodology.
    """
    total = len(project.tasks)
    if total == 0:
        data_gaps.append("Blockers: no tasks — dimension not assessable")
        return "Not Assessed"

    # Count blocked tasks
    blocked_tasks = []
    for t in project.tasks:
        reasons = []
        if t.on_hold:
            reasons.append("On Hold")
        if t.not_applicable:
            reasons.append("Not Applicable")
        if project.has_rag_column and t.rag == "Red":
            reasons.append("RAG=Red")
        if reasons:
            blocked_tasks.append((t, reasons))

    blocked_count = len(blocked_tasks)
    pct = blocked_count / total

    # Check critical-path tasks on hold — immediate Red per methodology
    critical_on_hold = [
        (t, r) for t, r in blocked_tasks
        if t.is_critical and t.on_hold
    ]
    if critical_on_hold:
        names = ", ".join(t.task_name or "unnamed" for t, _ in critical_on_hold[:5])
        evidence.append(
            f"Blockers RED: {len(critical_on_hold)} critical-path task(s) "
            f"on hold: {names}"
        )
        return "Red"

    if pct > 0.15:
        evidence.append(
            f"Blockers RED: {blocked_count}/{total} tasks blocked ({pct:.1%})"
        )
        return "Red"
    elif pct >= 0.05:
        evidence.append(
            f"Blockers AMBER: {blocked_count}/{total} tasks blocked ({pct:.1%})"
        )
        return "Amber"
    else:
        evidence.append(
            f"Blockers GREEN: {blocked_count}/{total} tasks blocked ({pct:.1%})"
        )
        return "Green"


def _score_budget(
    project: ProjectData,
    evidence: list[str],
    data_gaps: list[str],
) -> RAGStatus:
    """Budget burn dimension.

    Neither sample file has cost/budget columns (SCHEMA_REFERENCE.md).
    Per Methodology.md: "marked 'Not Assessed' if no cost data exists —
    never estimated from a proxy."
    """
    # Both files confirmed to have no cost/budget columns
    evidence.append(
        "Budget: Not Assessed — no cost/budget columns in source file"
    )
    return "Not Assessed"


def _score_sentiment(
    project: ProjectData,
    today: date,
    evidence: list[str],
    data_gaps: list[str],
) -> RAGStatus:
    """Stakeholder sentiment dimension.

    Methodology.md thresholds:
    - Green: no unresolved asks
    - Amber: 1–2 stale asks (>1 week open)
    - Red: 3+ stale asks, or explicit escalation language

    Scans Comments sheet + Status Comment field for:
    - Open action items ("pending", "awaiting", "yet to receive", "need to")
    - Escalation language ("escalat", "block", "risk", "delay", "urgent")
    - Stale asks (comment with action language older than 7 days)
    """
    # Gather all text sources
    texts_with_dates: list[tuple[str, Optional[date]]] = []

    for c in project.comments:
        if c.text:
            texts_with_dates.append((c.text, c.comment_date))

    for t in project.tasks:
        if t.status_comment:
            texts_with_dates.append((t.status_comment, None))

    if not texts_with_dates:
        data_gaps.append(
            "Sentiment: no comments or status comments available — "
            "dimension not assessable"
        )
        return "Not Assessed"

    # Pattern matching for open asks and escalation
    ask_patterns = re.compile(
        r"(pending|awaiting|yet to receive|need to|need meeting|remain to|"
        r"to provd?e|to provide|sign[\s-]?off|feedback|mapping is pending|"
        r"need .* on calendar|repeating)",
        re.IGNORECASE,
    )
    escalation_patterns = re.compile(
        r"(escalat|block|critical risk|urgent|impacted|delay)",
        re.IGNORECASE,
    )

    open_asks = []
    escalations = []
    stale_asks = []

    for text, comment_date in texts_with_dates:
        has_ask = bool(ask_patterns.search(text))
        has_escalation = bool(escalation_patterns.search(text))

        if has_ask:
            open_asks.append(text[:80])
            # Check if stale (>7 days old)
            if comment_date and (today - comment_date).days > 7:
                stale_asks.append(text[:80])

        if has_escalation:
            escalations.append(text[:80])

    # Score
    if escalations or len(stale_asks) >= 3:
        detail = f"{len(stale_asks)} stale asks, {len(escalations)} escalation(s)"
        examples = (stale_asks + escalations)[:3]
        evidence.append(
            f"Sentiment RED: {detail}. Examples: "
            + "; ".join(f'"{e}"' for e in examples)
        )
        return "Red"
    elif len(stale_asks) >= 1:
        evidence.append(
            f"Sentiment AMBER: {len(stale_asks)} stale ask(s) (>7 days). "
            + "; ".join(f'"{s}"' for s in stale_asks[:3])
        )
        return "Amber"
    elif open_asks:
        # Recent asks that aren't stale yet
        evidence.append(
            f"Sentiment GREEN: {len(open_asks)} open ask(s) but none stale"
        )
        return "Green"
    else:
        evidence.append("Sentiment GREEN: no unresolved asks detected")
        return "Green"
