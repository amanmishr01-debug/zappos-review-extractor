import json
import logging
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from .models import ProcessedReview, RawReview
from .scraper import ZapposScraper
from .extractor import ReviewExtractor

logger = logging.getLogger(__name__)
console = Console()


class Pipeline:
    def __init__(
        self,
        api_key: str | None = None,
        scrape_delay: float = 2.0,
        use_batch_api: bool = False,
    ):
        self.scraper = ZapposScraper(delay=scrape_delay)
        self.extractor = ReviewExtractor(api_key=api_key)
        self.use_batch_api = use_batch_api

    def run(
        self,
        query: str,
        max_products: int = 3,
        max_reviews_per_product: int = 20,
        output_path: Path | None = None,
    ) -> list[ProcessedReview]:
        console.rule("[bold blue]Zappos Review Extractor")

        # ── 1. Scrape ──────────────────────────────────────────────────────────
        console.print(f"\n[cyan]Searching Zappos for:[/cyan] {query}")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task("Fetching product list...", total=None)
            products = self.scraper.search_products(query, max_products)
            progress.update(task, description=f"Found {len(products)} products")

        if not products:
            console.print("[red]No products found. Try a different search query.[/red]")
            return []

        self._print_products_table(products)

        all_raw: list[RawReview] = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            task = progress.add_task("Scraping reviews...", total=len(products))
            for p in products:
                reviews = self.scraper.get_reviews(
                    p["product_id"],
                    p["name"],
                    p["brand"],
                    max_reviews_per_product,
                )
                all_raw.extend(reviews)
                progress.advance(task)

        console.print(f"\n[green]Scraped {len(all_raw)} reviews[/green]")

        if not all_raw:
            console.print("[yellow]No reviews found. Exiting.[/yellow]")
            return []

        # ── 2. Extract ─────────────────────────────────────────────────────────
        console.print("\n[cyan]Extracting insights with Claude...[/cyan]")
        processed: list[ProcessedReview] = []

        if self.use_batch_api:
            console.print("[dim]Using Batch API (async, ~50% cheaper) — this may take a few minutes[/dim]")
            processed = self.extractor.extract_batch(all_raw)
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
            ) as progress:
                task = progress.add_task("Extracting...", total=len(all_raw))
                for review in all_raw:
                    try:
                        result = self.extractor.extract_single(review)
                        processed.append(result)
                    except Exception as exc:
                        logger.warning("Failed to extract review: %s", exc)
                    progress.advance(task)

        console.print(f"[green]Processed {len(processed)} reviews[/green]")

        # ── 3. Save ────────────────────────────────────────────────────────────
        if output_path:
            self._save(processed, output_path)

        self._print_summary(processed)
        return processed

    def run_from_raw(
        self,
        raw_reviews: list[RawReview],
        output_path: Path | None = None,
    ) -> list[ProcessedReview]:
        """Run only the extraction step on pre-loaded raw reviews (e.g. demo mode)."""
        console.print(f"\n[cyan]Extracting insights for {len(raw_reviews)} reviews...[/cyan]")
        processed: list[ProcessedReview] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            task = progress.add_task("Extracting...", total=len(raw_reviews))
            for review in raw_reviews:
                try:
                    result = self.extractor.extract_single(review)
                    processed.append(result)
                except Exception as exc:
                    logger.warning("Failed to extract review: %s", exc)
                progress.advance(task)

        if output_path:
            self._save(processed, output_path)

        self._print_summary(processed)
        return processed

    @staticmethod
    def _save(processed: list[ProcessedReview], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [p.model_dump() for p in processed]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        console.print(f"\n[green]Results saved to:[/green] {path}")

    @staticmethod
    def _print_products_table(products: list[dict]) -> None:
        table = Table(title="Products Found", show_header=True)
        table.add_column("ID", style="dim")
        table.add_column("Name")
        table.add_column("Brand")
        for p in products:
            table.add_row(p["product_id"], p["name"], p["brand"])
        console.print(table)

    @staticmethod
    def _print_summary(processed: list[ProcessedReview]) -> None:
        if not processed:
            return
        sentiments = [p.extraction.sentiment for p in processed]
        pos = sentiments.count("positive")
        neu = sentiments.count("neutral")
        neg = sentiments.count("negative")
        urgent = sum(1 for p in processed if p.extraction.urgency == "high")
        needs_action = sum(1 for p in processed if p.extraction.requires_action)

        table = Table(title="\nExtraction Summary", show_header=True)
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Total reviews", str(len(processed)))
        table.add_row("Positive", f"[green]{pos}[/green]")
        table.add_row("Neutral", f"[yellow]{neu}[/yellow]")
        table.add_row("Negative", f"[red]{neg}[/red]")
        table.add_row("High urgency", f"[bold red]{urgent}[/bold red]")
        table.add_row("Requires action", f"[bold orange1]{needs_action}[/bold orange1]")
        console.print(table)
