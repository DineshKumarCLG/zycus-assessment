"""
Orchestrator — ties Ingestion → Signal Engine → Reasoning Agent into a
single weekly run pipeline. Writes output to data/weekly/{project}/{date}.json.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from src.ingestion import load_project
from src.models import WeeklyReport
from src.reasoning_agent import generate_reasoning
from src.signal_engine import compute_signals

logger = logging.getLogger(__name__)


def run_weekly(
    filepath: Path,
    effective_date: Optional[date] = None,
    output_dir: Path = Path("data/weekly"),
    api_key: Optional[str] = None,
) -> WeeklyReport:
    """Execute the full weekly pipeline for one project file.

    1. Ingest the Excel file into the common shape
    2. Compute signals (5 sub-RAGs + overall)
    3. Generate LLM reasoning (or fallback)
    4. Assemble and validate the WeeklyReport
    5. Write to data/weekly/{project_name}/{YYYY-MM-DD}.json
    """
    run_date = effective_date or date.today()
    logger.info("Starting weekly run for %s (date=%s)", filepath, run_date)

    # Step 1: Ingestion
    project = load_project(filepath)
    logger.info("Ingested project: %s (%d tasks)", project.project_name, len(project.tasks))

    # Step 2: Signal Engine
    signals = compute_signals(project, effective_date=effective_date)
    logger.info(
        "Signals computed: overall=%s, disagreement=%s",
        signals.overall_rag, signals.disagreement_flag,
    )

    # Step 3: Reasoning Agent
    reasoning = generate_reasoning(signals, project.project_name, api_key=api_key)
    logger.info("Reasoning generated (%d chars)", len(reasoning))

    # Step 4: Assemble WeeklyReport (validates against Pydantic model)
    report = WeeklyReport(
        project_name=project.project_name,
        run_date=run_date.isoformat(),
        overall_rag=signals.overall_rag,
        source_reported_rag=signals.source_reported_rag,
        disagreement_flag=signals.disagreement_flag,
        sub_scores=signals.sub_scores,
        evidence=signals.evidence,
        reasoning=reasoning,
        data_gaps=signals.data_gaps,
        phase_performances=signals.phase_performances,
    )

    # Step 5: Write to JSON
    # Sanitize project name for filesystem path
    safe_name = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "_"
        for c in project.project_name
    ).strip()
    project_dir = output_dir / safe_name
    project_dir.mkdir(parents=True, exist_ok=True)

    output_path = project_dir / f"{run_date.isoformat()}.json"
    output_path.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False) + "\n"
    )
    logger.info("Weekly report written to %s", output_path)

    return report
