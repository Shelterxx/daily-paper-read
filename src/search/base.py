"""Abstract base class for literature search sources.

All search adapters (arXiv, PubMed, OpenAlex, etc.) implement this interface.
Adding a new source = implement SearchSource + add to config.
No changes to pipeline logic required.
"""

from abc import ABC, abstractmethod
from src.search.models import Paper, SearchQuery


class SearchSource(ABC):
    """Abstract interface for any literature search source.

    Each source adapter normalizes its raw results into the unified Paper model.
    The search() method is async to support parallel execution via asyncio.gather().
    """

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[Paper]:
        """Search for papers matching the query.

        Args:
            query: Search parameters including keywords, timeframe, and max results.

        Returns:
            List of normalized Paper objects from this source.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Source identifier, e.g. 'arxiv', 'pubmed', 'openalex'."""
        ...
