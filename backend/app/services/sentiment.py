"""Headline sentiment with FinBERT, run locally. Optional: without it, headlines still show."""

from __future__ import annotations

import importlib.util
import logging
import threading
from typing import Any, Protocol

MODEL_ID = "ProsusAI/finbert"
LABELS = ("positive", "neutral", "negative")
logger = logging.getLogger("investment_tracker.sentiment")


class Scorer(Protocol):
    model: str

    def score(self, texts: list[str]) -> list[dict[str, float]]:
        """Probabilities for positive, neutral, and negative, one dict per text."""
        ...


def finbert_installed() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("torch", "transformers"))


class FinBertScorer:
    """Loads the model on first use (a one-time download of about 440 MB) and keeps it in memory."""

    model = MODEL_ID

    def __init__(self) -> None:
        self._pipeline: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._pipeline is None:
                from transformers import pipeline

                logger.info("Loading %s", MODEL_ID)
                self._pipeline = pipeline("text-classification", model=MODEL_ID, top_k=None, device="cpu")
        return self._pipeline

    def score(self, texts: list[str]) -> list[dict[str, float]]:
        if not texts:
            return []
        outputs = self._load()(texts, batch_size=16, truncation=True)
        results = []
        for output in outputs:
            by_label = {row["label"].lower(): row["score"] for row in output}
            results.append({label: round(float(by_label.get(label, 0.0)), 4) for label in LABELS})
        return results


def default_scorer() -> Scorer | None:
    return FinBertScorer() if finbert_installed() else None


def label_for(probabilities: dict[str, float]) -> str:
    return max(LABELS, key=lambda label: probabilities.get(label, 0.0))


def net_score(probabilities: dict[str, float]) -> float:
    """From -1 (certainly negative) to +1 (certainly positive)."""
    return round(probabilities.get("positive", 0.0) - probabilities.get("negative", 0.0), 4)
