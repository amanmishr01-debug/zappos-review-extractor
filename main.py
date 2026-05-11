#!/usr/bin/env python3
"""Zappos Review Extractor — CLI entry point."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zappos-extractor",
        description="Scrape Zappos reviews and extract structured insights with Claude AI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── run: live scrape + extract ──────────────────────────────────────────
    run = subparsers.add_parser("run", help="Scrape Zappos and extract insights")
    run.add_argument(
        "--query",
        default="running shoes",
        help="Search query (default: 'running shoes')",
    )
    run.add_argument(
        "--max-products",
        type=int,
        default=3,
        metavar="N",
        help="Max products to scrape (default: 3)",
    )
    run.add_argument(
        "--max-reviews",
        type=int,
        default=20,
        metavar="N",
        help="Max reviews per product (default: 20)",
    )
    run.add_argument(
        "--output",
        default="output/results.json",
        help="Output JSON file path (default: output/results.json)",
    )
    run.add_argument(
        "--batch",
        action="store_true",
        help="Use Batch API for async processing (~50%% cheaper, slower)",
    )
    run.add_argument(
        "--delay",
        type=float,
        default=1.5,
        metavar="SECONDS",
        help="Delay between Zappos requests in seconds (default: 1.5)",
    )

    # ── demo: use bundled sample data ───────────────────────────────────────
    demo = subparsers.add_parser(
        "demo",
        help="Run extraction on bundled sample reviews (no Zappos scraping needed)",
    )
    demo.add_argument(
        "--output",
        default="output/demo_results.json",
        help="Output JSON file path (default: output/demo_results.json)",
    )
    demo.add_argument(
        "--sample-file",
        default="data/sample_reviews.json",
        help="Path to sample reviews JSON (default: data/sample_reviews.json)",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[bold red]Error:[/bold red] ANTHROPIC_API_KEY not set.\n"
            "Copy [dim].env.example[/dim] to [dim].env[/dim] and add your key."
        )
        sys.exit(1)

    # Late import so --help works without installing packages
    from src.pipeline import Pipeline
    from src.models import RawReview

    if args.command == "run":
        pipeline = Pipeline(
            api_key=api_key,
            scrape_delay=args.delay,
            use_batch_api=args.batch,
        )
        pipeline.run(
            query=args.query,
            max_products=args.max_products,
            max_reviews_per_product=args.max_reviews,
            output_path=Path(args.output),
        )

    elif args.command == "demo":
        sample_path = Path(args.sample_file)
        if not sample_path.exists():
            console.print(f"[red]Sample file not found:[/red] {sample_path}")
            sys.exit(1)

        raw_data = json.loads(sample_path.read_text())
        raw_reviews = [RawReview(**r) for r in raw_data]

        pipeline = Pipeline(api_key=api_key)
        pipeline.run_from_raw(
            raw_reviews=raw_reviews,
            output_path=Path(args.output),
        )


if __name__ == "__main__":
    main()
