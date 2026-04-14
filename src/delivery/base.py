"""Abstract base class for notification delivery channels."""

from abc import ABC, abstractmethod
from src.search.models import AnalyzedPaper


class Notifier(ABC):
    """Abstract interface for notification delivery channels."""

    @abstractmethod
    async def send(self, papers: list[AnalyzedPaper], topic_stats: dict) -> bool:
        """Send notification with analyzed papers.

        Args:
            papers: List of analyzed papers grouped/sorted for display.
            topic_stats: Dict with topic_name -> {high: N, medium: N, low: N, total: N}

        Returns:
            True if notification was sent successfully.
        """
        ...
