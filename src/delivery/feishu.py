"""Feishu webhook notifier with interactive cards and tiered display."""

import json
import logging
from collections import defaultdict
from typing import Optional

import httpx

from src.delivery.base import Notifier
from src.search.models import AnalyzedPaper, RelevanceTier

logger = logging.getLogger(__name__)

# Feishu card payload limit ~30KB; use 28KB conservatively
MAX_CONTENT_BYTES = 28000


class FeishuNotifier(Notifier):
    """Feishu webhook notifier using interactive card format.

    Builds rich, visually-structured cards with colored headers,
    markdown text, action buttons, and tiered paper display.
    """

    def __init__(self, webhook_url: Optional[str] = None, language: str = "zh"):
        self.webhook_url = webhook_url
        self.language = language

    async def send(self, papers: list[AnalyzedPaper], topic_stats: dict) -> bool:
        """Send tiered paper digest to Feishu as interactive cards."""
        if not self.webhook_url:
            logger.warning("Feishu webhook URL not configured, skipping notification")
            return False

        if not papers:
            return await self._send_no_papers(topic_stats)

        messages = self._build_messages(papers, topic_stats)
        all_ok = True

        async with httpx.AsyncClient() as client:
            for i, content in enumerate(messages):
                ok = await self._post_message(client, content)
                if not ok:
                    all_ok = False
                    logger.error(f"Failed to send message {i+1}/{len(messages)}")

        return all_ok

    # ── Card builders ──────────────────────────────────────────────

    def _build_messages(
        self, papers: list[AnalyzedPaper], topic_stats: dict
    ) -> list[dict]:
        """Build interactive cards — one card per topic, HIGH only."""
        # Filter: only push HIGH papers
        relevant = [ap for ap in papers if ap.analysis.tier == RelevanceTier.HIGH]

        if not relevant:
            return []

        # Group by topic
        by_topic: dict[str, list[AnalyzedPaper]] = defaultdict(list)
        for ap in relevant:
            by_topic[ap.topic_name].append(ap)

        cards: list[dict] = []
        for topic_name, topic_papers in by_topic.items():
            topic_high = sum(1 for ap in topic_papers if ap.analysis.tier == RelevanceTier.HIGH)
            topic_medium = len(topic_papers) - topic_high

            if self.language == "zh":
                title = f"📚 {topic_name}（{topic_high} 高 + {topic_medium} 中）"
            else:
                title = f"📚 {topic_name} ({topic_high} high + {topic_medium} med)"

            header = {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            }

            sorted_papers = sorted(
                topic_papers,
                key=lambda p: (p.analysis.relevance_score, 0 if p.analysis.tier == RelevanceTier.HIGH else 1),
                reverse=True,
            )

            elements = []
            for ap in sorted_papers:
                elements.extend(self._build_paper_elements(ap))

            # Split into multiple cards if this topic exceeds size limit
            cards.extend(self._split_cards(header, elements))

        return cards

    def _build_paper_elements(self, ap: AnalyzedPaper) -> list[dict]:
        """Build card elements for one paper based on tier."""
        elements: list[dict] = []
        tier = ap.analysis.tier
        score = ap.analysis.relevance_score
        paper = ap.paper

        # Escape lark_md special chars in title
        title = paper.title.replace("[", "［").replace("]", "］")

        # Tier icon
        if tier == RelevanceTier.HIGH:
            icon = "🔥"
        elif tier == RelevanceTier.MEDIUM:
            icon = "📄"
        else:
            icon = "📌"

        # Title line
        if paper.source_url:
            title_md = f'{icon} **[{score}/10] [{title}]({paper.source_url})**'
        else:
            title_md = f"{icon} **[{score}/10] {title}**"
        elements.append(self._card_div(title_md))

        if tier == RelevanceTier.HIGH:
            elements.extend(self._build_high_details(ap))
        elif tier == RelevanceTier.MEDIUM:
            elements.extend(self._build_medium_details(ap))

        # Button for HIGH/MEDIUM
        if tier in (RelevanceTier.HIGH, RelevanceTier.MEDIUM) and paper.source_url:
            btn_text = "查看论文" if self.language == "zh" else "View Paper"
            elements.append(self._card_button(btn_text, paper.source_url))

        elements.append(self._card_hr())
        return elements

    def _build_high_details(self, ap: AnalyzedPaper) -> list[dict]:
        """Build detailed elements for HIGH-relevance papers."""
        elements: list[dict] = []
        paper = ap.paper
        zh = self.language == "zh"

        # Authors
        if paper.authors:
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += f" +{len(paper.authors)-3}"
            label = "👤 **作者**" if zh else "👤 **Authors**"
            elements.append(self._card_div(f"{label}：{authors_str}"))

        # Summary
        if ap.analysis.summary:
            label = "📝 **摘要**" if zh else "📝 **Summary**"
            summary = ap.analysis.summary[:500].replace("\n", " ")
            elements.append(self._card_div(f"{label}：{summary}"))

        # Key contributions
        if ap.analysis.key_contributions:
            label = "💡 **核心贡献**" if zh else "💡 **Key Contributions**"
            contribs = "\n".join(f"  • {c}" for c in ap.analysis.key_contributions[:3])
            elements.append(self._card_div(f"{label}：\n{contribs}"))

        # Applications
        if ap.analysis.potential_applications:
            label = "🔧 **潜在应用**" if zh else "🔧 **Applications**"
            apps = "、".join(ap.analysis.potential_applications[:3])
            elements.append(self._card_div(f"{label}：{apps}"))

        # Methodology Evaluation (Stage 2b)
        if ap.analysis.methodology_evaluation:
            label = "🔬 **方法论评估**" if zh else "🔬 **Methodology**"
            content = ap.analysis.methodology_evaluation[:500].replace("\n", " ")
            elements.append(self._card_div(f"{label}：\n{content}"))

        # Limitations (Stage 2b)
        if ap.analysis.limitations:
            label = "⚠️ **局限性分析**" if zh else "⚠️ **Limitations**"
            items = "\n".join(f"  • {l}" for l in ap.analysis.limitations[:5])
            elements.append(self._card_div(f"{label}：\n{items}"))

        # Future Directions (Stage 2b)
        if ap.analysis.future_directions:
            label = "🚀 **未来研究方向**" if zh else "🚀 **Future Directions**"
            items = "\n".join(f"  • {d}" for d in ap.analysis.future_directions[:5])
            elements.append(self._card_div(f"{label}：\n{items}"))

        # Comparative Analysis (Stage 3)
        if ap.analysis.comparative_analysis:
            label = "📊 **对比分析**" if zh else "📊 **Comparative Analysis**"
            content = ap.analysis.comparative_analysis[:500].replace("\n", " ")
            if ap.analysis.compared_with:
                if zh:
                    content += f"\n（与 {len(ap.analysis.compared_with)} 篇相关论文对比）"
                else:
                    content += f"\n(Compared with {len(ap.analysis.compared_with)} related papers)"
            elements.append(self._card_div(f"{label}：\n{content}"))

        return elements

    def _build_medium_details(self, ap: AnalyzedPaper) -> list[dict]:
        """Build compact elements for MEDIUM-relevance papers."""
        elements: list[dict] = []
        paper = ap.paper
        zh = self.language == "zh"

        # Authors (compact)
        if paper.authors:
            authors_str = ", ".join(paper.authors[:3])
            label = "👤" if zh else "👤"
            elements.append(self._card_div(f"{label} {authors_str}"))

        # Summary (truncated)
        if ap.analysis.summary:
            summary = ap.analysis.summary[:300].replace("\n", " ")
            elements.append(self._card_div(f"📝 {summary}"))

        # Contributions (inline)
        if ap.analysis.key_contributions:
            contribs = "、".join(ap.analysis.key_contributions[:3])
            label = "💡" if zh else "💡"
            elements.append(self._card_div(f"{label} {contribs}"))

        return elements

    # ── Card splitting ─────────────────────────────────────────────

    def _split_cards(self, header: dict, all_elements: list[dict]) -> list[dict]:
        """Split elements into multiple cards if content exceeds size limit."""
        cards: list[dict] = []
        current_elements: list[dict] = []
        current_size = 0

        # Pre-compute header size
        header_size = len(json.dumps({"header": header}, ensure_ascii=False).encode("utf-8"))

        for element in all_elements:
            elem_json = len(json.dumps(element, ensure_ascii=False).encode("utf-8"))

            if current_size + elem_json + header_size > MAX_CONTENT_BYTES and current_elements:
                cards.append(self._make_card(header, current_elements))
                current_elements = []
                current_size = 0

            current_elements.append(element)
            current_size += elem_json

        if current_elements:
            cards.append(self._make_card(header, current_elements))

        return cards

    def _make_card(self, header: dict, elements: list[dict]) -> dict:
        """Build a complete Feishu interactive card message."""
        return {
            "msg_type": "interactive",
            "card": {
                "header": header,
                "elements": elements,
            },
        }

    # ── HTTP ───────────────────────────────────────────────────────

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
            if result.get("code") == 0:
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
        if self.language == "zh":
            title = "📚 每日文献速递"
            text = "今日没有发现新的相关论文。"
        else:
            title = "📚 Daily Literature Digest"
            text = "No new relevant papers found today."

        message = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "blue",
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": text}},
                ],
            },
        }
        async with httpx.AsyncClient() as client:
            return await self._post_message(client, message)

    # ── Card element helpers ───────────────────────────────────────

    @staticmethod
    def _card_div(content: str) -> dict:
        """Build a div element with lark_md markdown text."""
        return {"tag": "div", "text": {"tag": "lark_md", "content": content}}

    @staticmethod
    def _card_hr() -> dict:
        """Build a horizontal rule divider."""
        return {"tag": "hr"}

    @staticmethod
    def _card_button(text: str, url: str, button_type: str = "primary") -> dict:
        """Build an action block with a link button."""
        return {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": text},
                    "url": url,
                    "type": button_type,
                }
            ],
        }

    @staticmethod
    def _card_note(content: str) -> dict:
        """Build a note element (small gray text)."""
        return {"tag": "note", "elements": [{"tag": "plain_text", "content": content}]}
