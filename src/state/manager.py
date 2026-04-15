"""Persistent state manager for seen-paper tracking and run history."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path


class StateManager:
    """Tracks seen papers and run history across pipeline executions."""

    def __init__(self, state_dir: str = "state") -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.seen_file = self.state_dir / "seen_papers.json"
        self._seen_keys: set[str] = self._load_seen()
        self.history_file = self.state_dir / "analyzed_papers_history.json"
        self._history: list[dict] = self._load_history()

    def _load_seen(self) -> set[str]:
        """Load seen paper dedup keys from JSON file."""
        if not self.seen_file.exists():
            return set()
        try:
            with open(self.seen_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("seen_keys", []))
        except (json.JSONDecodeError, OSError):
            return set()

    def _save_seen(self) -> None:
        """Atomic write of seen keys to JSON file."""
        data = {
            "seen_keys": sorted(list(self._seen_keys)),
            "last_updated": datetime.now().isoformat(),
        }
        # Atomic write: write to temp file then rename
        fd, tmp_path = tempfile.mkstemp(dir=str(self.state_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # On Windows, target must not exist for rename
            if self.seen_file.exists():
                self.seen_file.unlink()
            Path(tmp_path).rename(self.seen_file)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def is_seen(self, dedup_key: str) -> bool:
        """Check if a paper has been seen before."""
        return dedup_key in self._seen_keys

    def mark_seen(self, dedup_key: str) -> None:
        """Mark a single paper as seen."""
        self._seen_keys.add(dedup_key)

    def mark_seen_batch(self, dedup_keys: list[str]) -> None:
        """Mark multiple papers as seen and persist to disk."""
        for key in dedup_keys:
            self._seen_keys.add(key)
        self._save_seen()

    def filter_new(self, papers: list) -> list:
        """Filter out already-seen papers. Papers must have a dedup_key property."""
        return [p for p in papers if not self.is_seen(p.dedup_key)]

    @property
    def seen_count(self) -> int:
        """Number of unique papers seen across all runs."""
        return len(self._seen_keys)

    def _load_history(self) -> list[dict]:
        """Load analyzed papers history from JSON file."""
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("papers", [])
        except (json.JSONDecodeError, OSError):
            return []

    def _save_history(self) -> None:
        """Atomic write of history to JSON file, capped at 100 entries."""
        capped = self._history[-100:]
        data = {
            "papers": capped,
            "last_updated": datetime.now().isoformat(),
        }
        fd, tmp_path = tempfile.mkstemp(dir=str(self.state_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if self.history_file.exists():
                self.history_file.unlink()
            Path(tmp_path).rename(self.history_file)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def get_history_for_comparison(self, topic_name: str, keywords: list[str], limit: int = 5) -> list[dict]:
        """Retrieve historical papers for comparative analysis.

        Filters by topic_name match first, then ranks by keyword overlap,
        score, and date. Falls back to keyword-overlap-only matching across
        all topics if no same-topic papers are found.
        """
        # Try same-topic papers first
        same_topic = [hp for hp in self._history if hp.get("topic_name") == topic_name]

        if same_topic:
            candidates = same_topic
        else:
            # Fall back to all papers with keyword matching
            candidates = self._history

        def keyword_overlap(hp: dict) -> int:
            hp_keywords = set(hp.get("extracted_keywords", []))
            return len(set(keywords) & hp_keywords)

        candidates.sort(
            key=lambda hp: (
                keyword_overlap(hp),
                hp.get("score", 0),
                hp.get("date", ""),
            ),
            reverse=True,
        )

        return candidates[:limit]

    def add_to_history(self, analyzed_paper) -> None:
        """Add an analyzed paper to the history.

        Extracts key fields from the AnalyzedPaper object and persists to disk.
        History is capped at 100 entries (oldest dropped on save).
        """
        entry = {
            "title": analyzed_paper.paper.title,
            "abstract": analyzed_paper.paper.abstract or "",
            "summary": analyzed_paper.analysis.summary or "",
            "score": analyzed_paper.analysis.relevance_score,
            "date": datetime.now().isoformat(),
            "topic_name": analyzed_paper.topic_name,
            "doi": analyzed_paper.paper.doi or "",
            "extracted_keywords": analyzed_paper.analysis.extracted_keywords or [],
            "confirmed": True,
        }
        self._history.append(entry)
        self._save_history()
