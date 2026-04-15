"""Zotero integration: archive HIGH-relevance papers with metadata, AI tags, notes, and PDFs."""

import logging
import os
import time
from typing import Optional

from pyzotero import zotero as zotero_client

from src.search.models import AnalyzedPaper, RelevanceTier, Paper
from src.config.models import ZoteroConfig

logger = logging.getLogger(__name__)


class ZoteroArchiver:
    """Archives high-relevance papers to Zotero library.

    For each HIGH-tier paper:
    - Creates a journal article item with full metadata (ZTR-01)
    - Adds AI-extracted keywords as Zotero tags (ZTR-02)
    - Attaches structured HTML note with analysis (ZTR-03)
    - Links PDF URL as attachment when available (ZTR-04)
    - Skips duplicates by DOI/title check (ZTR-05)
    """

    def __init__(self, config: ZoteroConfig):
        self.config = config
        self._zot = None
        self._collection_cache: dict[str, str] = {}

    @property
    def zot(self):
        """Lazy-initialized pyzotero client."""
        if self._zot is None:
            user_id = os.environ.get(self.config.user_id_env, "")
            api_key = os.environ.get(self.config.api_key_env, "")
            if not user_id or not api_key:
                raise ValueError(
                    f"Missing Zotero credentials: set {self.config.user_id_env} and {self.config.api_key_env}"
                )
            self._zot = zotero_client.Zotero(user_id, "user", api_key)
        return self._zot

    # -- Retry helper --

    def _retry(self, operation, name, retries=3, base_delay=1.0):
        """Retry Zotero API operation with exponential backoff."""
        for attempt in range(retries):
            try:
                return operation()
            except Exception as e:
                if isinstance(e, AttributeError):
                    raise
                if attempt == retries - 1:
                    raise
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "%s failed (attempt %d/%d): %s, retrying in %.1fs",
                    name, attempt + 1, retries, e, delay,
                )
                time.sleep(delay)

    # -- Main entry point --

    async def archive_papers(self, papers: list[AnalyzedPaper]) -> dict:
        """Archive HIGH-relevance papers to Zotero.

        Returns dict: {archived: int, skipped_existing: int, errors: list[str]}
        """
        high_papers = [ap for ap in papers if ap.analysis.tier == RelevanceTier.HIGH]
        if not high_papers:
            logger.info("No HIGH-relevance papers to archive")
            return {"archived": 0, "skipped_existing": 0, "errors": []}

        if not self.config.enabled:
            logger.info("Zotero archiving disabled, skipping %d papers", len(high_papers))
            return {"archived": 0, "skipped_existing": 0, "errors": []}

        # Build collection structure for all topics
        topic_names = list({ap.topic_name for ap in high_papers})
        topic_to_key = self._ensure_collection_structure(topic_names)

        archived = 0
        skipped = 0
        errors = []

        for ap in high_papers:
            try:
                # ZTR-05: dedup check
                existing_key = self._find_existing_item(ap.paper)
                if existing_key:
                    logger.info("Skipping existing paper: %s", ap.paper.title[:60])
                    skipped += 1
                    continue

                collection_key = topic_to_key.get(ap.topic_name)
                if not collection_key:
                    errors.append(f"No collection for topic '{ap.topic_name}'")
                    continue

                # ZTR-01: create item with metadata
                item_key = self._create_item(ap.paper, collection_key)
                if not item_key:
                    errors.append(f"Failed to create item: {ap.paper.title[:60]}")
                    continue

                # ZTR-02: add AI tags
                self._add_tags(item_key, ap.analysis.extracted_keywords)

                # ZTR-03: attach analysis note
                self._add_note(item_key, ap.analysis)

                # ZTR-04: attach PDF link
                self._attach_pdf(item_key, ap.paper)

                archived += 1
                logger.info("Archived: %s", ap.paper.title[:60])

            except Exception as e:
                error_msg = f"Error archiving '{ap.paper.title[:40]}': {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        logger.info(
            "Zotero archiving complete: %d archived, %d skipped, %d errors",
            archived, skipped, len(errors),
        )
        return {"archived": archived, "skipped_existing": skipped, "errors": errors}

    # -- Collection management --

    def _ensure_collection_structure(self, topic_names: list[str]) -> dict[str, str]:
        """Ensure root collection and topic sub-collections exist.

        Returns dict: topic_name -> collection_key
        """
        result: dict[str, str] = {}

        # Get all existing collections
        all_collections = self._retry(
            lambda: self.zot.everything(self.zot.collections()),
            "Fetch collections",
        )

        # Find or create root collection
        root_key = self._find_or_create_root(all_collections)
        if not root_key:
            logger.error("Failed to establish root collection")
            return result

        # Find or create topic sub-collections
        for topic_name in topic_names:
            collection_key = self._find_or_create_subcollection(
                all_collections, root_key, topic_name
            )
            if collection_key:
                result[topic_name] = collection_key

        return result

    def _find_or_create_root(self, all_collections: list) -> Optional[str]:
        """Find or create the root collection (e.g. DailyPapers)."""
        root_name = self.config.collection_root
        root_candidates = []

        for coll in all_collections:
            data = coll.get("data", {})
            parent = data.get("parentCollection")
            if data.get("name") == root_name and not parent:
                root_candidates.append(coll)

        if root_candidates:
            # Use oldest if multiple exist
            root_candidates.sort(key=lambda x: x.get("data", {}).get("dateAdded", ""))
            return root_candidates[0]["key"]

        # Create root collection
        resp = self._retry(
            lambda: self.zot.create_collections([{"name": root_name}]),
            f"Create root collection '{root_name}'",
        )
        if "0" not in resp.get("successful", {}):
            raise RuntimeError(f"Failed to create root collection: {resp.get('failed')}")
        root_key = resp["successful"]["0"]["key"]
        logger.info("Created root collection '%s': %s", root_name, root_key)
        return root_key

    def _find_or_create_subcollection(
        self, all_collections: list, root_key: str, name: str
    ) -> Optional[str]:
        """Find or create a sub-collection under the root."""
        for coll in all_collections:
            data = coll.get("data", {})
            if data.get("name") == name and data.get("parentCollection") == root_key:
                return coll["key"]

        # Create sub-collection
        resp = self._retry(
            lambda: self.zot.create_collections([
                {"name": name, "parentCollection": root_key}
            ]),
            f"Create sub-collection '{name}'",
        )
        if "0" not in resp.get("successful", {}):
            logger.error("Failed to create sub-collection '%s': %s", name, resp.get("failed"))
            return None
        sub_key = resp["successful"]["0"]["key"]
        logger.info("Created sub-collection '%s': %s", name, sub_key)
        return sub_key

    # -- Dedup (ZTR-05) --

    def _find_existing_item(self, paper: Paper) -> Optional[str]:
        """Check if item already exists by DOI, fallback to title match.

        Returns item key if found, None otherwise.
        """
        if paper.doi:
            doi_clean = paper.doi.lower().strip()
            try:
                results = self._retry(
                    lambda: self.zot.items(q=paper.doi, limit=10),
                    f"Search by DOI '{paper.doi}'",
                )
                for item in results:
                    data = item.get("data", {})
                    item_doi = (data.get("DOI") or "").lower().strip()
                    if item_doi == doi_clean:
                        return item["key"]
            except Exception as e:
                logger.warning("DOI search failed for '%s': %s", paper.doi, e)

        # Fallback: case-insensitive title match
        title_clean = paper.title.lower().strip()
        try:
            results = self._retry(
                lambda: self.zot.items(q=paper.title, limit=10),
                f"Search by title '{paper.title[:40]}'",
            )
            for item in results:
                data = item.get("data", {})
                item_title = (data.get("title") or "").lower().strip()
                if item_title == title_clean:
                    return item["key"]
        except Exception as e:
            logger.warning("Title search failed for '%s': %s", paper.title[:40], e)

        return None

    # -- Item creation (ZTR-01) --

    def _create_item(self, paper: Paper, collection_key: str) -> Optional[str]:
        """Create a Zotero journal article item with full metadata.

        Maps: title, authors, DOI, abstract, published_date, source_url.
        Returns item key on success.
        """
        template = self.zot.item_template("journalArticle")
        template["title"] = paper.title
        template["DOI"] = paper.doi or ""
        template["abstractNote"] = paper.abstract or ""
        template["date"] = (
            paper.published_date.strftime("%Y-%m-%d") if paper.published_date else ""
        )
        template["url"] = paper.source_url or ""
        template["creators"] = [
            {"creatorType": "author", "name": author}
            for author in paper.authors
        ]
        template["collections"] = [collection_key]

        resp = self._retry(
            lambda: self.zot.create_items([template]),
            f"Create item '{paper.title[:40]}'",
        )

        successful = resp.get("successful", {})
        if "0" not in successful:
            logger.error(
                "Failed to create item for '%s': %s",
                paper.title[:40], resp.get("failed"),
            )
            return None

        item_key = successful["0"]["key"]
        logger.info("Created Zotero item: %s -> %s", paper.title[:40], item_key)
        return item_key

    # -- Tags (ZTR-02) --

    def _add_tags(self, item_key: str, keywords: list[str]):
        """Add AI-extracted keywords as Zotero tags."""
        if not keywords:
            return

        try:
            # Get the item to update it with tags
            item = self._retry(
                lambda: self.zot.item(item_key),
                f"Fetch item for tagging '{item_key}'",
            )
            data = item.get("data", {})
            existing_tags = {t.get("tag", "") for t in data.get("tags", [])}
            new_tags = [{"tag": kw} for kw in keywords if kw not in existing_tags]
            if new_tags:
                data["tags"] = data.get("tags", []) + new_tags
                self._retry(
                    lambda: self.zot.update_item(item),
                    f"Add {len(new_tags)} tags to '{item_key}'",
                )
                logger.debug("Added %d tags to %s", len(new_tags), item_key)
        except Exception as e:
            logger.warning("Failed to add tags to %s: %s", item_key, e)

    # -- Note (ZTR-03) --

    def _add_note(self, item_key: str, analysis):
        """Attach structured HTML note with analysis sections.

        Sections: Summary, Key Contributions, Methodology Evaluation,
        Limitations, Future Directions.
        """
        html = "<h2>AI Analysis Summary</h2>"
        if analysis.summary:
            html += f"<p>{analysis.summary}</p>"
        if analysis.key_contributions:
            html += "<h2>Key Contributions</h2><ul>"
            for c in analysis.key_contributions:
                html += f"<li>{c}</li>"
            html += "</ul>"
        if analysis.methodology_evaluation:
            html += f"<h2>Methodology Evaluation</h2><p>{analysis.methodology_evaluation}</p>"
        if analysis.limitations:
            html += "<h2>Limitations</h2><ul>"
            for l in analysis.limitations:
                html += f"<li>{l}</li>"
            html += "</ul>"
        if analysis.future_directions:
            html += "<h2>Future Directions</h2><ul>"
            for d in analysis.future_directions:
                html += f"<li>{d}</li>"
            html += "</ul>"

        note_template = self.zot.item_template("note")
        note_template["note"] = html
        note_template["parentItem"] = item_key

        self._retry(
            lambda: self.zot.create_items([note_template]),
            f"Create note for '{item_key}'",
        )
        logger.debug("Attached analysis note to %s", item_key)

    # -- PDF attachment (ZTR-04) --

    def _attach_pdf(self, item_key: str, paper: Paper):
        """Attach PDF as linked URL to Zotero item.

        Since this runs in CI (no local files), we link to the PDF URL.
        Only attaches when paper has pdf_url and full_text.
        """
        if not paper.pdf_url or not paper.full_text:
            return

        try:
            att_template = self.zot.item_template("attachment")
            att_template["linkMode"] = "linked_url"
            att_template["title"] = "Full Text PDF"
            att_template["url"] = paper.pdf_url
            att_template["parentItem"] = item_key

            self._retry(
                lambda: self.zot.create_items([att_template]),
                f"Attach PDF to '{item_key}'",
            )
            logger.debug("Attached PDF link to %s", item_key)
        except Exception as e:
            logger.warning("Failed to attach PDF to %s: %s", item_key, e)
