from pydantic import BaseModel, Field
from typing import Literal


TOPIC_TAXONOMY = [
    "fit_and_sizing",
    "comfort",
    "quality_and_durability",
    "performance",
    "style_and_aesthetics",
    "price_and_value",
    "shipping_and_delivery",
    "customer_service",
    "arch_support",
    "breathability",
    "traction",
    "width",
]


class RawReview(BaseModel):
    product_id: str
    product_name: str
    brand: str
    reviewer: str
    rating: float = Field(ge=1.0, le=5.0)
    title: str
    body: str
    date: str
    verified_purchase: bool = False


class ReviewExtraction(BaseModel):
    sentiment: Literal["positive", "neutral", "negative"]
    sentiment_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the sentiment (0=very negative, 1=very positive)",
    )
    topics: list[str] = Field(
        description=f"Relevant topics from this taxonomy: {TOPIC_TAXONOMY}"
    )
    urgency: Literal["low", "medium", "high"] = Field(
        description="low=general feedback, medium=notable issue, high=defect/safety/return"
    )
    key_phrases: list[str] = Field(
        description="Up to 5 verbatim short phrases that capture the reviewer's main points"
    )
    summary: str = Field(
        description="One sentence neutral summary of the review"
    )
    requires_action: bool = Field(
        description="True if the review signals a defect, safety issue, or urgent complaint"
    )


class ProcessedReview(BaseModel):
    raw: RawReview
    extraction: ReviewExtraction
    processed_at: str
