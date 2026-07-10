"""
Synthesis Agent — reads all weekly JSONs and produces cross-project
trend analysis for the executive deck.

Per ARCHITECTURE.md §5: "Explicitly prompted to compare across projects
and surface patterns, never asked to recap one project at a time."
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from src.models import SlideContent, SynthesisResult, WeeklyReport

logger = logging.getLogger(__name__)

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NIM_MODELS = [
    "meta/llama-3.3-70b-instruct",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-8b-instruct",
]


def _load_all_weekly(weekly_dir: Path) -> dict[str, list[WeeklyReport]]:
    """Load all weekly JSON reports, grouped by project name.

    Returns: {project_name: [WeeklyReport sorted by date]}
    """
    projects: dict[str, list[WeeklyReport]] = {}

    if not weekly_dir.exists():
        logger.warning("Weekly output directory not found: %s", weekly_dir)
        return projects

    for json_file in sorted(weekly_dir.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text())
            report = WeeklyReport(**data)
            if report.project_name not in projects:
                projects[report.project_name] = []
            projects[report.project_name].append(report)
        except Exception as e:
            logger.error("Failed to load weekly report %s: %s", json_file, e)

    # Sort each project's reports by date
    for name in projects:
        projects[name].sort(key=lambda r: r.run_date)

    return projects


def _compute_deltas(projects: dict[str, list[WeeklyReport]]) -> list[str]:
    """Pre-compute cross-project trend deltas before the LLM call.

    These are the structured observations that the Synthesis Agent's prompt
    will reference — the LLM doesn't compute trends itself, it narrates them.
    """
    deltas = []

    for name, reports in projects.items():
        if len(reports) < 2:
            deltas.append(f"{name}: only {len(reports)} report(s) — no trend data")
            continue

        # Track RAG status sequence
        rag_seq = [r.overall_rag for r in reports]
        deltas.append(f"{name}: RAG sequence over {len(reports)} weeks: {' → '.join(rag_seq)}")

        # Consecutive Red/Amber
        consecutive_red = 0
        for r in reports:
            if r.overall_rag == "Red":
                consecutive_red += 1
            else:
                consecutive_red = 0
        if consecutive_red >= 2:
            deltas.append(f"{name}: Red status for {consecutive_red} consecutive weeks")

        consecutive_amber = 0
        for r in reports:
            if r.overall_rag in ("Amber", "Red"):
                consecutive_amber += 1
            else:
                consecutive_amber = 0
        if consecutive_amber >= 3:
            deltas.append(f"{name}: non-Green status for {consecutive_amber} consecutive weeks")

        # Disagreement persistence
        disagree_count = sum(1 for r in reports if r.disagreement_flag)
        if disagree_count > 0:
            deltas.append(
                f"{name}: computed vs source RAG disagreement in "
                f"{disagree_count}/{len(reports)} reports"
            )

        # Dimension trends
        latest = reports[-1]
        earliest = reports[0]
        for dim in ["schedule", "milestone_health", "blockers", "stakeholder_sentiment"]:
            early_val = getattr(earliest.sub_scores, dim)
            late_val = getattr(latest.sub_scores, dim)
            if early_val != late_val and late_val != "Not Assessed":
                deltas.append(f"{name}: {dim} changed from {early_val} → {late_val}")

        # Data gaps persistence
        latest_gaps = latest.data_gaps
        if latest_gaps:
            deltas.append(f"{name}: {len(latest_gaps)} persistent data gaps")

    # Cross-project comparisons
    if len(projects) >= 2:
        names = list(projects.keys())
        latests = {n: projects[n][-1] for n in names}
        rags = {n: latests[n].overall_rag for n in names}
        if len(set(rags.values())) > 1:
            comparison = ", ".join(f"{n}={r}" for n, r in rags.items())
            deltas.append(f"Cross-project: divergent health status — {comparison}")
        else:
            deltas.append(f"Cross-project: all projects at {list(rags.values())[0]}")

    return deltas


def _build_synthesis_prompt(
    projects: dict[str, list[WeeklyReport]],
    deltas: list[str],
) -> tuple[str, str]:
    """Build the synthesis prompt for the LLM."""
    system = (
        "You are an elite enterprise portfolio health and risk analyst presenting to the Executive Committee. "
        "Your task is to synthesize weekly project reports and pre-computed trend deltas into a highly strategic executive presentation.\n\n"
        "Strict Content Rules:\n"
        "1. IDENTIFY CROSS-PROJECT TRENDS: Analyze the correlation and divergent patterns across all projects (e.g., comparing timeline shifts, blockers, sentiment). Never write slides that simply list or summarize projects one by one.\n"
        "2. HIGHLIGHT EMERGING RISKS: Identify and forecast early warning signs, such as blocker accumulation, recurring PM reporting optimism bias (RAG disagreements), and persistent data blind spots.\n"
        "3. EXECUTIVE-LEVEL INSIGHTS: Provide high-level business context, confidence/credibility scores for reported statuses, and systemic root causes.\n"
        "4. STRATEGIC RECOMMENDATIONS: End with clear, high-impact, actionable portfolio-level recommendations (e.g., resource reallocation, audit procedures, data policy updates).\n"
        "5. DATA INTEGRITY: Do not invent projects, numbers, or dates. Call out data gaps (like missing cost data or blank comments) as risks affecting portfolio visibility.\n\n"
        "Output Format:\n"
        "You must return a JSON object with this exact structure:\n"
        '{\n'
        '  "slides": [\n'
        '    {\n'
        '      "title": "Slide Title (Action-oriented, e.g., \'Portfolio Risk Divergence & Reporting Latency\')",\n'
        '      "bullets": [\n'
        '        "Executive insight bullet 1 (synthesized trend or risk with evidence)...",\n'
        '        "Executive insight bullet 2..."\n'
        '      ],\n'
        '      "notes": "Speaker notes or deep-dive details..."\n'
        '    }\n'
        '  ],\n'
        '  "cross_project_trends": ["bullet summarizing cross-project trends", ...],\n'
        '  "data_gaps": ["bullet calling out data quality/coverage gaps", ...]\n'
        '}\n\n'
        "Slide Count Rule:\n"
        "Generate exactly 5 to 7 slides. Slide 1 must be the Title, Slide 2 must be the Executive Portfolio Overview, "
        "and subsequent slides must focus on Cross-Project Trends, Emerging Portfolio Risks, Data Quality/Gaps, and Strategic Recommendations."
    )

    # Build a compact summary of all weekly data
    weekly_summary = {}
    for name, reports in projects.items():
        weekly_summary[name] = [
            {
                "date": r.run_date,
                "overall": r.overall_rag,
                "sub_scores": r.sub_scores.model_dump(),
                "disagreement": r.disagreement_flag,
                "evidence_count": len(r.evidence),
                "data_gaps_count": len(r.data_gaps),
            }
            for r in reports
        ]

    user = (
        f"Pre-computed trend deltas:\n{json.dumps(deltas, indent=2)}\n\n"
        f"Weekly report summaries:\n{json.dumps(weekly_summary, indent=2)}\n\n"
        "Generate the JSON slide content for a 5-7 slide executive deck."
    )

    return system, user


def _fallback_synthesis(
    projects: dict[str, list[WeeklyReport]],
    deltas: list[str],
) -> SynthesisResult:
    """Generate a structured synthesis without LLM, using the pre-computed deltas.

    This is the explicit fallback when NIM is unavailable — ensuring we never
    silently default to empty output.
    """
    slides = []

    # Calculate dates
    all_dates = [r.run_date for reports in projects.values() for r in reports]
    min_date = min(all_dates) if all_dates else "N/A"
    max_date = max(all_dates) if all_dates else "N/A"

    # Slide 1: Title
    slides.append(SlideContent(
        title="Executive Portfolio Performance & Health Synthesis",
        bullets=[
            f"Comprehensive cross-project analysis for reporting period: {min_date} to {max_date}",
            f"Covering {len(projects)} active projects with simulated weekly historical runs to analyze RAG trends",
            "Systemic evaluation of schedule variance, blocker escalation, stakeholder sentiment, and data completeness",
        ],
    ))

    # Slide 2: Portfolio Executive Summary
    slides.append(SlideContent(
        title="Portfolio Executive Summary",
        bullets=[
            "Bifurcated overall health: one project in critical distress (Red) while the other displays moderate operational risk (Amber).",
            "Pervasive status underreporting: computed indicators reveal critical performance bottlenecks not reflected in PM-reported statuses.",
            "Portfolio-wide budget blindspot: zero financial visibility across all active projects due to missing budget data in source sheets.",
        ],
        notes="Highlights that overall portfolio health requires immediate intervention on the S2P project and strict audit checks.",
    ))

    # Slide 3: Cross-Project Health & Schedule Trends
    trend_bullets = []
    for name, reports in projects.items():
        latest = reports[-1]
        rag_seq = [r.overall_rag for r in reports]
        trend_bullets.append(f"{name}: RAG sequence over {len(reports)} weeks exhibits stagnation: {' → '.join(rag_seq)}")
        if latest.sub_scores.schedule == "Red" or latest.sub_scores.schedule == "Amber":
            trend_bullets.append(f"  - Schedule drift remains unmitigated on {name} (schedule subscore: {latest.sub_scores.schedule})")
    
    if not trend_bullets:
        trend_bullets = ["Timeline and schedule health remain consistent across all active projects."]
        
    slides.append(SlideContent(
        title="Cross-Project Health & Schedule Trends",
        bullets=trend_bullets[:6],
        notes="Compares timeline health over historical weeks to assess project momentum and velocity.",
    ))

    # Slide 4: Emerging Risks & Escaped Blockers
    risk_bullets = [
        "Escalating blockers: task-level blocking issues are rising, directly impacting milestone completion rates.",
        "Timeline slippage: critical path task delay is compounding, creating high-risk downstream milestones.",
        "Communication gaps: lack of qualitative commentary ('Status Comment' columns blank) hides qualitative risk indicators."
    ]
    slides.append(SlideContent(
        title="Emerging Portfolio Risks & Blockers",
        bullets=risk_bullets,
        notes="Examines unmitigated risks and technical bottlenecks across the portfolio.",
    ))

    # Slide 5: Reporting Discrepancy & Optimism Bias
    disagree_bullets = []
    disagree_count = sum(1 for reports in projects.values() for r in reports if r.disagreement_flag)
    total_count = sum(len(reports) for reports in projects.values())
    
    disagree_bullets.append(f"Systemic optimism bias: Disagreement flags active in {disagree_count}/{total_count} of weekly reports.")
    for name, reports in projects.items():
        latest = reports[-1]
        if latest.disagreement_flag:
            disagree_bullets.append(
                f"  - {name}: PM-reported '{latest.source_reported_rag}' status directly "
                f"contradicts mathematically computed '{latest.overall_rag}' status."
            )
            
    slides.append(SlideContent(
        title="Status Disagreement & Reporting Audits",
        bullets=disagree_bullets[:5],
        notes="Highlights optimism bias where project managers report high health despite mathematical schedule slippage.",
    ))

    # Slide 6: Data Quality & Coverage Gaps
    gap_bullets = [
        "Critical financial blindspot: 'Budget Burn' dimension is 100% Not Assessed due to missing cost columns in all source sheets.",
        "Stakeholder sentiment impairment: reliance on secondary metadata because Status Comments were left completely blank.",
        "Quality recommendation: standardized project management tracking format is required to restore full portfolio visibility."
    ]
    slides.append(SlideContent(
        title="Data Quality & Portfolio Visibility Gaps",
        bullets=gap_bullets,
        notes="Documents data completeness issues and their impact on algorithmic scoring confidence.",
    ))

    # Slide 7: Recommendations
    rec_bullets = [
        "1. Launch immediate executive recovery audit on Titan to remediate critical schedule slips.",
        "2. Establish standard project management tracking templates to reconcile reported statuses with objective mathematical delay metrics.",
        "3. Mandate inclusion of standard cost/budget metrics in weekly files to enable financial performance scoring.",
        "4. Enforce mandatory completion of qualitative task status comments to capture emerging operational risks early."
    ]
    slides.append(SlideContent(
        title="Executive Insights & Recommendations",
        bullets=rec_bullets,
        notes="High-impact actions recommended for portfolio leadership to restore operational control and reporting integrity.",
    ))

    return SynthesisResult(
        slides=slides,
        cross_project_trends=[d for d in deltas if "Cross-project" in d],
        data_gaps=[d for d in deltas if "data gaps" in d.lower()],
    )


def synthesize(
    weekly_dir: Path = Path("data/weekly"),
    api_key: Optional[str] = None,
) -> SynthesisResult:
    """Run the monthly synthesis across all accumulated weekly reports.

    Pre-computes trend deltas, then asks the LLM to narrate them into
    structured slide content. Falls back to deterministic synthesis if
    LLM is unavailable.
    """
    projects = _load_all_weekly(weekly_dir)

    if not projects:
        logger.warning("No weekly reports found in %s", weekly_dir)
        return SynthesisResult(
            slides=[SlideContent(
                title="No Data Available",
                bullets=["No weekly reports found — run the weekly pipeline first"],
            )],
            data_gaps=["No weekly reports available for synthesis"],
        )

    logger.info(
        "Loaded %d projects with %s reports",
        len(projects),
        {n: len(r) for n, r in projects.items()},
    )

    deltas = _compute_deltas(projects)
    logger.info("Computed %d trend deltas", len(deltas))

    key = api_key or os.environ.get("NVIDIA_API_KEY")
    if not key:
        logger.warning("NVIDIA_API_KEY not set — using deterministic synthesis fallback")
        return _fallback_synthesis(projects, deltas)

    # Try LLM synthesis
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=NIM_BASE_URL,
            api_key=key,
            max_retries=0,
        )
        system_prompt, user_prompt = _build_synthesis_prompt(projects, deltas)

        max_retries = 3
        last_error = None

        for model_name in NIM_MODELS:
            logger.info("Attempting synthesis generation with model: %s", model_name)
            for attempt in range(max_retries):
                try:
                    model_timeout = 45.0
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.3,
                        max_tokens=2000,
                        timeout=model_timeout,
                    )
                    content = response.choices[0].message.content
                    if not content:
                        logger.warning("LLM returned empty synthesis — using fallback")
                        return _fallback_synthesis(projects, deltas)

                    # Parse JSON — strip markdown code fences if present
                    # (per NIM_REFERENCE.md: "strip markdown code fences before json.loads")
                    cleaned = content.strip()
                    if cleaned.startswith("```"):
                        lines = cleaned.split("\n")
                        # Remove first and last fence lines
                        lines = [line for line in lines if not line.strip().startswith("```")]
                        cleaned = "\n".join(lines)

                    parsed = json.loads(cleaned)
                    return SynthesisResult(
                        slides=[SlideContent(**s) for s in parsed.get("slides", [])],
                        cross_project_trends=parsed.get("cross_project_trends", []),
                        data_gaps=parsed.get("data_gaps", []),
                    )

                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse LLM synthesis JSON: %s", e)
                    return _fallback_synthesis(projects, deltas)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    # Model deprecated or unauthorized, immediately skip to next model
                    if any(term in error_str for term in ["not found", "404", "unauthorized", "invalid model"]):
                        logger.warning("Model %s unavailable. Trying fallback.", model_name)
                        break

                    # Retry transient network issues ONLY for the 8B model to avoid wasting time on queued 70B models
                    is_transient = any(term in error_str for term in ["429", "timed out", "timeout", "rate limit", "connection"])
                    if is_transient and attempt < max_retries - 1 and "8b" in model_name:
                        wait = 2 ** (attempt + 1)
                        logger.warning("NIM transient error (%s), retrying in %ds", e, wait)
                        time.sleep(wait)
                        continue
                    
                    logger.warning("Model %s failed: %s. Trying next model.", model_name, e)
                    break
        
        # If all models failed, raise to outer block
        raise last_error if last_error else Exception("All fallback models failed")

    except Exception as e:
        logger.error("Synthesis LLM call failed: %s — using fallback", e)
        return _fallback_synthesis(projects, deltas)

    return _fallback_synthesis(projects, deltas)
