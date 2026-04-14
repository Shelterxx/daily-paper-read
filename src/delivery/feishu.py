"""Feishu webhook notifier with rich message cards and tiered display."""

import json
import logging
import os
from typing import Optional
from collections import defaultdict

import httpx
import jinja2

from src.delivery.base import Notifier
from src.search.models import AnalyzedPaper, RelevanceTier

logger = logging.getLogger(__name__)

# Feishu webhook post content has ~30KB limit; use 28KB conservatively
MAX_CONTENT_BYTES = 28000


class FeishuNotifier(Notifier):
    """Feishu webhook notifier with rich message cards and tiered display."""

    def __init__(self, webhook_url: Optional[str] = None, language: str = "zh"):
        self.webhook_url = webhook_url
        self.language = language
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader("templates"),
            autoescape=False,
        )

    async def send(self, papers: list[AnalyzedPaper], topic_stats: dict) -> bool:
        """Send tiered paper digest to Feishu.

        Splits into multiple messages if content exceeds size limit.
        """
        if not self.webhook_url:
            logger.warning("Feishu webhook URL not configured, skipping notification")
            return False

        if not papers:
            return await self._send_no_papers(topic_stats)

        # Build message content grouped by topic
        messages = self._build_messages(papers, topic_stats)
        all_ok = True

        async with httpx.AsyncClient() as client:
            for i, content in enumerate(messages):
                ok = await self._post_message(client, content)
                if not ok:
                    all_ok = False
                    logger.error(f"Failed to send message {i+1}/{len(messages)}")

        return all_ok

    def _build_messages(
        self, papers: list[AnalyzedPaper], topic_stats: dict
    ) -> list[dict]:
        """Build one or more Feishu post messages, splitting if needed."""
        # Header with stats
        header = self._build_stats_header(topic_stats)

        # Group papers by topic
        by_topic: dict[str, list[AnalyzedPaper]] = defaultdict(list)
        for ap in papers:
            by_topic[ap.topic_name].append(ap)

        # Build content sections
        all_sections = [header]
        for topic_name, topic_papers in by_topic.items():
            topic_header = self._make_text(
                f"\n{'='*20} {topic_name} {'='*20}\n"
            )
            all_sections.append(topic_header)

            # Sort: high first, then medium, then low
            sorted_papers = sorted(
                topic_papers,
                key=lambda p: (
                    p.analysis.relevance_score,
                    0 if p.analysis.tier == RelevanceTier.HIGH else 1,
                ),
                reverse=True,
            )

            for ap in sorted_papers:
                section = self._build_paper_section(ap)
                all_sections.extend(section)

        # Split into multiple messages if content is too large
        return self._split_messages(all_sections, topic_stats)

    def _build_stats_header(self, topic_stats: dict) -> dict:
        """Build header section with summary statistics."""
        total = sum(s.get("total", 0) for s in topic_stats.values())
        high = sum(s.get("high", 0) for s in topic_stats.values())
        medium = sum(s.get("medium", 0) for s in topic_stats.values())
        low = sum(s.get("low", 0) for s in topic_stats.values())

        if self.language == "en":
            text = (
                f"Today's Literature Digest\n"
                f"Total new papers: {total} | "
                f"High relevance: {high} | Medium: {medium} | Low: {low}\n"
            )
        else:
            text = (
                f"Daily Literature Digest\n"
                f"Total new papers: {total} | "
                f"High: {high} | Medium: {medium} | Low: {low}\n"
            )

        return self._make_text(text)

    def _build_paper_section(self, ap: AnalyzedPaper) -> list[dict]:
        """Build Feishu rich text section for one paper based on tier."""
        sections: list[dict] = []
        tier = ap.analysis.tier
        score = ap.analysis.relevance_score
        paper = ap.paper

        # Title with score badge
        tier_emoji = (
            ">>>"
            if tier == RelevanceTier.HIGH
            else (">>" if tier == RelevanceTier.MEDIUM else ">")
        )
        title_text = f"{tier_emoji} [{score}/10] {paper.title}\n"
        sections.append(self._make_text(title_text))

        if tier == RelevanceTier.HIGH:
            # Full analysis
            if paper.authors:
                authors_str = ", ".join(paper.authors[:3])
                if len(paper.authors) > 3:
                    authors_str += f" +{len(paper.authors)-3}"
                sections.append(self._make_text(f"  Authors: {authors_str}\n"))

            if ap.analysis.summary:
                sections.append(
                    self._make_text(f"  Summary: {ap.analysis.summary[:500]}\n")
                )

            if ap.analysis.key_contributions:
                contribs = "\n".join(
                    f"    - {c}" for c in ap.analysis.key_contributions[:3]
                )
                sections.append(
                    self._make_text(f"  Key Contributions:\n{contribs}\n")
                )

            if ap.analysis.potential_applications:
                apps = ", ".join(ap.analysis.potential_applications[:3])
                sections.append(self._make_text(f"  Applications: {apps}\n"))

            # Link
            if paper.source_url:
                sections.append(self._make_link("  Paper Link", paper.source_url))
                sections.append(self._make_text("\n"))

        elif tier == RelevanceTier.MEDIUM:
            # Compact info
            if paper.authors:
                authors_str = ", ".join(paper.authors[:3])
                sections.append(self._make_text(f"  Authors: {authors_str}\n"))

            if ap.analysis.summary:
                sections.append(
                    self._make_text(f"  Summary: {ap.analysis.summary[:300]}\n")
                )

            if ap.analysis.key_contributions:
                contribs = ", ".join(ap.analysis.key_contributions[:3])
                sections.append(
                    self._make_text(f"  Contributions: {contribs}\n")
                )

            if paper.source_url:
                sections.append(self._make_link("Link", paper.source_url))
                sections.append(self._make_text("\n"))

        else:
            # Low: title + link + score only (title already shown above)
            if paper.source_url:
                sections.append(self._make_link("  Link", paper.source_url))
                sections.append(self._make_text("\n"))

        # Separator
        sections.append(self._make_text("\n"))
        return sections

    def _split_messages(
        self, all_sections: list[dict], topic_stats: dict
    ) -> list[dict]:
        """Split sections into multiple messages if content exceeds size limit."""
        messages: list[dict] = []
        current_sections: list[dict] = []
        current_size = 0

        for section in all_sections:
            section_json = json.dumps(section, ensure_ascii=False)
            section_size = len(section_json.encode("utf-8"))

            if current_size + section_size > MAX_CONTENT_BYTES and current_sections:
                messages.append(self._make_message(current_sections, topic_stats))
                current_sections = []
                current_size = 0

            current_sections.append(section)
            current_size += section_size

        if current_sections:
            messages.append(self._make_message(current_sections, topic_stats))

        return messages

    def _make_message(self, sections: list[dict], topic_stats: dict) -> dict:
        """Build a complete Feishu webhook message from content sections."""
        total = sum(s.get("total", 0) for s in topic_stats.values())
        title = f"Literature Digest ({total} papers)"

        template = self._env.get_template("feishu_card.json.j2")
        rendered = template.render(
            language=self.language,
            title=title,
            content=sections,
        )
        return json.loads(rendered)

    async def _post_message(
        self, client: httpx.AsyncClient, message: dict
    ) -> bool:
        """Send a single message to Feishu webhook."""
        try:
            response = await client.post(
                self.webhook_url,
                json=message,
                timeout=15,
            )
            result = response.json()
            if result.get("StatusCode") == 0 or result.get("code") == 0:
                logger.info("Feishu notification sent successfully")
                return True
            else:
                logger.error(f"Feishu API error: {result}")
                return False
        except Exception as e:
            logger.error(f"Feishu notification failed: {e}")
            return False

    async def _send_no_papers(self, topic_stats: dict) -> bool:
        """Send notification when no new papers found."""
        message = {
            "msg_type": "text",
            "content": {
                "text": "Literature Digest: No new papers found today."
            },
        }
        async with httpx.AsyncClient() as client:
            return await self._post_message(client, message)

    @staticmethod
    def _make_text(text: str) -> dict:
        """Create a Feishu rich text tag element."""
        return {"tag": "text", "text": text}

    @staticmethod
    def _make_link(text: str, href: str) -> dict:
        """Create a Feishu rich text link tag element."""
        return {"tag": "a", "text": text, "href": href}
