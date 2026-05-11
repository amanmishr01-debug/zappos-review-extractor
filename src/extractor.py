import json
import logging
import re
from datetime import datetime, timezone

import anthropic

from .models import RawReview, ReviewExtraction, ProcessedReview, TOPIC_TAXONOMY

logger = logging.getLogger(__name__)

# Switch to claude-haiku-4-5 for cost-efficient bulk workloads
MODEL = "claude-opus-4-7"

SYSTEM_PROMPT = f"""You are a product review analyst specializing in footwear and athletic shoes.
Your task is to extract structured insights from raw customer reviews.

Respond with ONLY a valid JSON object — no markdown fences, no extra text.

The JSON must have exactly these fields:
- sentiment: "positive", "neutral", or "negative"
- sentiment_score: float 0.0 (most negative) to 1.0 (most positive)
- topics: array of strings from this taxonomy — {TOPIC_TAXONOMY}
- urgency: "low", "medium", or "high"  (low=general feedback, medium=notable issue, high=defect/safety/return)
- key_phrases: array of up to 5 short verbatim phrases from the review
- summary: one neutral sentence summarising the review
- requires_action: true if the review signals a defect, safety concern, or urgent complaint

Be concise, accurate, and objective. Base everything strictly on the review text."""


class ReviewExtractor:
    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key)

    def extract_single(self, review: RawReview) -> ProcessedReview:
        user_message = self._build_user_message(review)
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # Cache the system prompt — reused across all extraction calls
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        text = response.content[0].text
        extraction = ReviewExtraction.model_validate_json(self._clean_json(text))
        return ProcessedReview(
            raw=review,
            extraction=extraction,
            processed_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _clean_json(text: str) -> str:
        """Strip markdown code fences if Claude adds them anyway."""
        text = text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if match:
            return match.group(1).strip()
        return text

    def extract_batch(self, reviews: list[RawReview]) -> list[ProcessedReview]:
        """Submit all reviews as a single Batch API job (async, ~50% cheaper).

        Polls until the batch is complete, then returns results in order.
        For large datasets this is preferred over extract_single in a loop.
        """
        import time

        requests = [
            {
                "model": MODEL,
                "max_tokens": 1024,
                "system": [
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [
                    {"role": "user", "content": self._build_user_message(review)}
                ],
            }
            for review in reviews
        ]

        batch = self.client.messages.batches.create(
            requests=[
                {"custom_id": f"review-{i}", "params": req}  # type: ignore[arg-type]
                for i, req in enumerate(requests)
            ]
        )
        logger.info("Batch submitted: %s (%d requests)", batch.id, len(reviews))

        # Poll until complete
        while True:
            batch = self.client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            logger.info(
                "Batch %s processing... (%d/%d done)",
                batch.id,
                batch.request_counts.succeeded + batch.request_counts.errored,
                len(reviews),
            )
            time.sleep(10)

        # Collect results in original order
        results_map: dict[int, ReviewExtraction] = {}
        for result in self.client.messages.batches.results(batch.id):
            idx = int(result.custom_id.split("-")[1])
            if result.result.type == "succeeded":
                msg = result.result.message
                # Parse structured output from the raw message content
                try:
                    extraction = ReviewExtraction.model_validate_json(
                        self._clean_json(msg.content[0].text)
                    )
                    results_map[idx] = extraction
                except Exception as exc:
                    logger.warning("Failed to parse result for review %d: %s", idx, exc)

        now = datetime.now(timezone.utc).isoformat()
        processed = []
        for i, review in enumerate(reviews):
            if i in results_map:
                processed.append(
                    ProcessedReview(
                        raw=review,
                        extraction=results_map[i],
                        processed_at=now,
                    )
                )
            else:
                logger.warning("No result for review %d (%s)", i, review.product_id)
        return processed

    @staticmethod
    def _build_user_message(review: RawReview) -> str:
        return (
            f"Product: {review.product_name} by {review.brand}\n"
            f"Rating: {review.rating}/5\n"
            f"Title: {review.title}\n"
            f"Review: {review.body}\n"
            f"Date: {review.date}\n"
            f"Verified purchase: {review.verified_purchase}"
        )
