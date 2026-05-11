# Zappos Review Extractor

Extract structured insights from Zappos sneaker/athletic shoe reviews using the Claude AI API.

Feed raw unstructured customer reviews → get back clean JSON with **sentiment**, **topics**, **urgency**, and actionable flags.

```
Product: Nike Air Zoom Pegasus 40 | Rating: 2/5
"The outsole started peeling after only two weeks..."

→ {
    "sentiment": "negative",
    "sentiment_score": 0.08,
    "topics": ["quality_and_durability", "customer_service"],
    "urgency": "high",
    "requires_action": true,
    "key_phrases": ["sole came apart", "two weeks of normal use", "3 weeks to get a refund"],
    "summary": "Reviewer experienced sole delamination after two weeks and difficult return process."
  }
```

## Features

- **Live Zappos scraping** — hits Zappos internal catalog + review APIs with BeautifulSoup/`__NEXT_DATA__` HTML fallback
- **Structured Claude extraction** — uses `client.messages.parse()` with Pydantic for guaranteed JSON schema
- **Prompt caching** — system prompt cached across all extraction calls to reduce API costs
- **Batch API support** — async bulk processing at ~50% cost savings (`--batch` flag)
- **Footwear topic taxonomy** — 12 predefined topics tailored to sneakers and athletic shoes
- **Rich CLI** — progress bars, summary tables, colorized output
- **Demo mode** — run extraction on bundled sample data without scraping Zappos

## Requirements

- Python 3.11+
- [Anthropic API key](https://console.anthropic.com/)

## Installation

```bash
git clone https://github.com/your-username/zappos-review-extractor.git
cd zappos-review-extractor

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## Usage

### Demo mode (no Zappos scraping required)

Run extraction on 7 bundled sample sneaker reviews to verify your setup:

```bash
python main.py demo
```

Output saved to `output/demo_results.json`.

### Live mode (scrapes Zappos)

```bash
# Search for running shoes, scrape 3 products × 20 reviews each
python main.py run --query "running shoes" --max-products 3 --max-reviews 20

# Custom query and output path
python main.py run --query "basketball sneakers" --max-products 5 --output output/basketball.json

# Use Batch API for cheaper async processing (recommended for large runs)
python main.py run --query "trail running shoes" --max-products 10 --max-reviews 50 --batch

# Slow down requests to avoid rate limiting
python main.py run --query "hiking boots" --delay 3.0
```

### All flags

| Flag | Default | Description |
|------|---------|-------------|
| `--query` | `running shoes` | Zappos search query |
| `--max-products` | `3` | Max products to scrape |
| `--max-reviews` | `20` | Max reviews per product |
| `--output` | `output/results.json` | Output file path |
| `--batch` | off | Use Batch API (async, ~50% cheaper) |
| `--delay` | `1.5` | Seconds between Zappos requests |
| `-v` / `--verbose` | off | Enable debug logging |

## Output format

Each entry in the output JSON follows the `ProcessedReview` schema:

```json
{
  "raw": {
    "product_id": "...",
    "product_name": "Nike Air Zoom Pegasus 40",
    "brand": "Nike",
    "reviewer": "RunnerJane",
    "rating": 5.0,
    "title": "Best running shoe I've owned",
    "body": "...",
    "date": "2024-11-15",
    "verified_purchase": true
  },
  "extraction": {
    "sentiment": "positive",
    "sentiment_score": 0.95,
    "topics": ["comfort", "fit_and_sizing", "breathability", "performance"],
    "urgency": "low",
    "key_phrases": ["cushioning is perfect", "true to size", "wide toe box"],
    "summary": "Reviewer found the shoe excellent for long-distance running with ideal fit and breathability.",
    "requires_action": false
  },
  "processed_at": "2025-01-10T14:32:00+00:00"
}
```

### Topic taxonomy

| Topic | Description |
|-------|-------------|
| `fit_and_sizing` | True to size, runs large/small, length |
| `comfort` | General comfort, padding, feel |
| `quality_and_durability` | Build quality, materials, longevity |
| `performance` | Athletic performance, responsiveness |
| `style_and_aesthetics` | Look, colorways, design |
| `price_and_value` | Value for money |
| `shipping_and_delivery` | Delivery speed and packaging |
| `customer_service` | Returns, exchanges, support |
| `arch_support` | Arch support and foot support |
| `breathability` | Ventilation and heat dissipation |
| `traction` | Grip on different surfaces |
| `width` | Shoe width, narrow/wide fit |

## Project structure

```
zappos-review-extractor/
├── main.py                  # CLI entry point
├── src/
│   ├── models.py            # Pydantic data models
│   ├── scraper.py           # Zappos scraper (API + HTML fallback)
│   ├── extractor.py         # Claude API extraction with caching
│   └── pipeline.py          # Orchestration + Rich UI
├── data/
│   └── sample_reviews.json  # Bundled demo reviews
├── output/                  # Generated results (gitignored)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Cost considerations

The default model is `claude-opus-4-7`. For large-scale bulk extraction, consider:

1. **Switch to Haiku** — edit `MODEL` in `src/extractor.py`:
   ```python
   MODEL = "claude-haiku-4-5"  # ~5× cheaper, slightly lower quality
   ```

2. **Use the Batch API** — pass `--batch` to get ~50% off async processing. Best for runs of 50+ reviews where you don't need real-time results.

3. **Prompt caching** — already enabled. The system prompt is cached after the first call, reducing input tokens on all subsequent calls.

## Disclaimer

This project uses Zappos's undocumented internal APIs for educational/personal use. Zappos's terms of service may restrict automated access — use responsibly, respect rate limits, and do not scrape at scale commercially. The HTML fallback paths may break if Zappos updates their frontend.

## License

MIT
