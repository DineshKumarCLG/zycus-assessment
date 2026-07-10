#!/usr/bin/env python3
"""
run.py — CLI entrypoint for the Project Health Reporting Agent.

Usage:
    python run.py weekly --file "data/samples/S2P Project.xlsx"
    python run.py weekly --all
    python run.py weekly --all --effective-date 2026-06-15
    python run.py synthesis
    python run.py deck
    python run.py schedule    (bonus: APScheduler weekly run)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Loads variables from .env if present

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SAMPLES_DIR = Path("data/samples")
WEEKLY_DIR = Path("data/weekly")


def cmd_weekly(args: argparse.Namespace) -> None:
    """Run the weekly pipeline for one or all project files."""
    from src.orchestrator import run_weekly

    effective = None
    if args.effective_date:
        effective = datetime.strptime(args.effective_date, "%Y-%m-%d").date()

    files = []
    if args.all:
        files = sorted(SAMPLES_DIR.glob("*.xlsx"))
        if not files:
            logger.error("No .xlsx files found in %s", SAMPLES_DIR)
            sys.exit(1)
    elif args.file:
        f = Path(args.file)
        if not f.exists():
            logger.error("File not found: %s", f)
            sys.exit(1)
        files = [f]
    else:
        logger.error("Specify --file or --all")
        sys.exit(1)

    for filepath in files:
        logger.info("=" * 60)
        logger.info("Processing: %s", filepath.name)
        logger.info("=" * 60)
        report = run_weekly(
            filepath,
            effective_date=effective,
            output_dir=WEEKLY_DIR,
            api_key=args.api_key if hasattr(args, "api_key") else None,
        )
        print(json.dumps(report.model_dump(), indent=2))
        print()
        import time
        time.sleep(1.5)


def cmd_synthesis(args: argparse.Namespace) -> None:
    """Run the monthly synthesis across all weekly outputs."""
    from src.synthesis_agent import synthesize

    result = synthesize(
        weekly_dir=WEEKLY_DIR,
        api_key=args.api_key if hasattr(args, "api_key") else None,
    )
    print(json.dumps(result.model_dump(), indent=2))


def cmd_deck(args: argparse.Namespace) -> None:
    """Generate the executive presentation from synthesis output."""
    from src.synthesis_agent import synthesize
    from src.deck_builder import build_deck

    synthesis = synthesize(
        weekly_dir=WEEKLY_DIR,
        api_key=args.api_key if hasattr(args, "api_key") else None,
    )
    output_path = Path(args.output) if hasattr(args, "output") and args.output else Path("output/exec_deck.pptx")
    path = build_deck(synthesis, output_path)
    print(f"Deck written to: {path}")


def cmd_schedule(args: argparse.Namespace) -> None:
    """Run the pipeline on a weekly schedule using APScheduler."""
    from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore
    from src.orchestrator import run_weekly

    scheduler = BlockingScheduler()

    def weekly_job():
        logger.info("Scheduled weekly run triggered")
        for filepath in sorted(SAMPLES_DIR.glob("*.xlsx")):
            try:
                run_weekly(filepath, output_dir=WEEKLY_DIR)
            except Exception as e:
                logger.error("Scheduled run failed for %s: %s", filepath, e)

    # Run every Monday at 9:00 AM
    scheduler.add_job(weekly_job, "cron", day_of_week="mon", hour=9, minute=0)
    logger.info("Scheduler started — weekly runs every Monday at 9:00 AM")
    logger.info("Press Ctrl+C to stop")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


def cmd_simulate(args: argparse.Namespace) -> None:
    """Generate simulated weekly runs by advancing the effective date.

    Per ARCHITECTURE.md limitation #4: with a 2-3 day build window, we
    simulate 3-4 weekly runs by manually advancing the effective date.
    """
    from src.orchestrator import run_weekly

    dates = [
        date(2026, 6, 15),
        date(2026, 6, 22),
        date(2026, 6, 29),
        date(2026, 7, 6),
    ]

    for filepath in sorted(SAMPLES_DIR.glob("*.xlsx")):
        for d in dates:
            logger.info("Simulated run: %s @ %s", filepath.name, d)
            try:
                run_weekly(
                    filepath,
                    effective_date=d,
                    output_dir=WEEKLY_DIR,
                    api_key=args.api_key if hasattr(args, "api_key") else None,
                )
                import time
                time.sleep(1.5)
            except Exception as e:
                logger.error("Simulated run failed for %s @ %s: %s", filepath.name, d, e)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project Health Reporting Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api-key",
        help="NVIDIA NIM API key (or set NVIDIA_API_KEY env var)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # weekly
    p_weekly = subparsers.add_parser("weekly", help="Run weekly analysis")
    p_weekly.add_argument("--file", help="Path to a single .xlsx file")
    p_weekly.add_argument("--all", action="store_true", help="Process all files in data/samples/")
    p_weekly.add_argument("--effective-date", help="Override today's date (YYYY-MM-DD) for simulated runs")

    # simulate
    subparsers.add_parser("simulate", help="Generate 4 simulated weekly runs per project")

    # synthesis
    subparsers.add_parser("synthesis", help="Run monthly synthesis across weekly outputs")

    # deck
    p_deck = subparsers.add_parser("deck", help="Generate executive PowerPoint deck")
    p_deck.add_argument("--output", default="output/exec_deck.pptx", help="Output .pptx path")

    # schedule
    subparsers.add_parser("schedule", help="Run on weekly APScheduler cron")

    args = parser.parse_args()

    commands = {
        "weekly": cmd_weekly,
        "simulate": cmd_simulate,
        "synthesis": cmd_synthesis,
        "deck": cmd_deck,
        "schedule": cmd_schedule,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
