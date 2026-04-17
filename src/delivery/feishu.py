"""Feishu notifier with App API support and collapsible panel cards.

Supports two sending modes:
  1. App API (recommended): Uses app_id/app_secret to send via /im/v1/messages.
     Supports collapsible_panel, interactive buttons, and all card features.
  2. Webhook (fallback): Simple webhook URL posting. Limited card components.
"""

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional

import httpx

from src.delivery.base import Notifier
from src.search.models import AnalyzedPaper, RelevanceTier

logger = logging.getLogger(__name__)

# Feishu card payload limit ~30KB; use 28KB conservatively
MAX_CONTENT_BYTES = 28000

# Feishu API endpoints
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


class FeishuNotifier(Notifier):
    """Feishu notifier using App API (preferred) or webhook fallback.

    Builds rich cards with collapsible panels for detailed analysis,
    sending via Feishu App API when configured.
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        language: str = "zh",
        compact_cards: bool = True,
        feishu_app_config=None,
    ):
        self.webhook_url = webhook_url
        self.language = language
        self.compact_cards = compact_cards
        self.feishu_app_config = feishu_app_config
        self._use_app_api = (
            feishu_app_config is not None
            and feishu_app_config.enabled
            and os.environ.get(feishu_app_config.app_id_env)
            and os.environ.get(feishu_app_config.app_secret_env)
        )
        self._cached_token: Optional[str] = None
        self._token_expires: float = 0

        if self._use_app_api:
            logger.info("Feishu: using App API mode (supports collapsible_panel)")
        elif webhook_url:
            logger.info("Feishu: using webhook mode (no collapsible_panel)")

    # ── Token management (App API) ──────────────────────────────────

    async def _get_tenant_token(self, client: httpx.AsyncClient) -> Optional[str]:
        """Get or refresh tenant_access_token for App API."""
        now = time.time()
        if self._cached_token and now < self._token_expires - 60:
            return self._cached_token

        app_id = os.environ.get(self.feishu_app_config.app_id_env, "")
        app_secret = os.environ.get(self.feishu_app_config.app_secret_env, "")

        try:
            resp = await client.post(
                FEISHU_TOKEN_URL,
                json={"app_id": app_id, "app_secret": app_secret},
                timeout=10,
            )
            data = resp.json()
            if data.get("code") == 0:
                self._cached_token = data["tenant_access_token"]
                self._token_expires = now + data.get("expire", 7200)
                logger.info("Feishu: obtained tenant_access_token")
                return self._cached_token
            else:
                logger.error(f"Feishu token error: {data}")
                return None
        except Exception as e:
            logger.error(f"Feishu token request failed: {e}")
            return None

    # ── Main send ───────────────────────────────────────────────────

    async def send(self, papers: list[AnalyzedPaper], topic_stats: dict) -> bool:
        """Send tiered paper digest to Feishu."""
        if not papers:
            return await self._send_no_papers(topic_stats)

        messages = self._build_messages(papers, topic_stats)
        if not messages:
            return await self._send_no_papers(topic_stats)

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
        relevant = [ap for ap in papers if ap.analysis.tier == RelevanceTier.HIGH]

        if not relevant:
            return []

        by_topic: dict[str, list[AnalyzedPaper]] = defaultdict(list)
        for ap in relevant:
            by_topic[ap.topic_name].append(ap)

        use_panels = self._use_app_api or self.compact_cards

        date_str = datetime.now(timezone.utc).strftime("%m-%d")
        cards: list[dict] = []
        for topic_name, topic_papers in by_topic.items():
            n = len(topic_papers)
            if self.language == "zh":
                title = f"📚 {topic_name}（{date_str}，推送 {n} 篇）"
            else:
                title = f"📚 {topic_name} ({date_str}, {n} papers)"

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
                elements.extend(self._build_paper_elements(ap, use_panels))

            cards.extend(self._split_cards(header, elements))

        return cards

    def _build_paper_elements(self, ap: AnalyzedPaper, use_panels: bool = False) -> list[dict]:
        """Build card elements for one paper based on tier."""
        elements: list[dict] = []
        tier = ap.analysis.tier
        score = ap.analysis.relevance_score
        paper = ap.paper
        zh = self.language == "zh"

        # Escape lark_md special chars in title
        title = paper.title.replace("[", "［").replace("]", "］")

        # Tier icon
        icon = "🔥" if tier == RelevanceTier.HIGH else ("📄" if tier == RelevanceTier.MEDIUM else "📌")

        # Title line
        if paper.source_url:
            title_md = f'{icon} **[{score}/10] [{title}]({paper.source_url})**'
        else:
            title_md = f"{icon} **[{score}/10] {title}**"
        elements.append(self._card_div(title_md))

        if tier == RelevanceTier.HIGH:
            if use_panels and self._use_app_api:
                elements.extend(self._build_high_collapsible(ap))
            elif use_panels:
                elements.extend(self._build_high_details_compact(ap))
            else:
                elements.extend(self._build_high_details(ap))
        elif tier == RelevanceTier.MEDIUM:
            elements.extend(self._build_medium_details(ap))

        # Buttons
        actions = []
        if tier in (RelevanceTier.HIGH, RelevanceTier.MEDIUM) and paper.source_url:
            btn_text = "查看论文" if zh else "View Paper"
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": btn_text},
                "url": paper.source_url,
                "type": "primary",
            })
        if paper.pdf_url:
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "PDF"},
                "url": paper.pdf_url,
                "type": "default",
            })

        # Interactive "interested" button for HIGH papers
        if tier == RelevanceTier.HIGH and self.feishu_app_config and self.feishu_app_config.callback_base_url:
            url = self._generate_archive_url(ap)
            if url:
                btn_text = "⭐ 感兴趣" if zh else "⭐ Interested"
                actions.append({
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": btn_text},
                    "url": url,
                    "type": "primary",
                })

        if actions:
            elements.append({"tag": "action", "actions": actions})

        elements.append(self._card_hr())
        return elements

    def _build_high_collapsible(self, ap: AnalyzedPaper) -> list[dict]:
        """Build HIGH details with collapsible panels (App API mode).

        Layout:
          Always visible: Authors+Date, short summary, key contributions
          Collapsible: applications, methodology, limitations, future, comparison
          Footer: DOI, keywords, PDF link
        """
        elements: list[dict] = []
        paper = ap.paper
        zh = self.language == "zh"

        # --- Always visible ---

        # Authors + Date
        parts = []
        if paper.authors:
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += f" +{len(paper.authors) - 3}"
            parts.append(f"👤 {authors_str}")
        if paper.published_date:
            parts.append(paper.published_date.strftime("%Y-%m-%d"))
        if parts:
            elements.append(self._card_div(" | ".join(parts)))

        # Short summary
        if ap.analysis.summary:
            summary = ap.analysis.summary[:200].replace("\n", " ")
            if len(ap.analysis.summary) > 200:
                summary += "..."
            elements.append(self._card_div(f"📝 {summary}"))

        # Key contributions (always shown)
        if ap.analysis.key_contributions:
            label = "💡 **核心贡献**" if zh else "💡 **Key Contributions**"
            contribs = "\n".join(f"  • {c}" for c in ap.analysis.key_contributions[:3])
            elements.append(self._card_div(f"{label}：\n{contribs}"))

        # --- Collapsible panels ---

        # Applications
        if ap.analysis.potential_applications:
            label = "🔧 **潜在应用**" if zh else "🔧 **Applications**"
            apps = "、".join(ap.analysis.potential_applications[:3])
            elements.append(self._collapsible_panel(label, apps))

        # Methodology
        if ap.analysis.methodology_evaluation:
            label = "🔬 **方法论评估**" if zh else "🔬 **Methodology**"
            content = ap.analysis.methodology_evaluation[:500].replace("\n", " ")
            elements.append(self._collapsible_panel(label, content))

        # Limitations
        if ap.analysis.limitations:
            label = "⚠️ **局限性**" if zh else "⚠️ **Limitations**"
            items = "\n".join(f"  • {l}" for l in ap.analysis.limitations[:5])
            elements.append(self._collapsible_panel(label, items))

        # Future directions
        if ap.analysis.future_directions:
            label = "🚀 **未来方向**" if zh else "🚀 **Future Directions**"
            items = "\n".join(f"  • {d}" for d in ap.analysis.future_directions[:5])
            elements.append(self._collapsible_panel(label, items))

        # Comparative analysis
        if ap.analysis.comparative_analysis:
            label = "📊 **对比分析**" if zh else "📊 **Comparative Analysis**"
            content = ap.analysis.comparative_analysis[:500].replace("\n", " ")
            if ap.analysis.compared_with:
                n = len(ap.analysis.compared_with)
                content += f"\n（与 {n} 篇相关论文对比）" if zh else f"\n(Compared with {n} papers)"
            elements.append(self._collapsible_panel(label, content))

        # --- Metadata footer ---
        meta_parts = []
        if paper.doi:
            meta_parts.append(f"DOI: [{paper.doi}](https://doi.org/{paper.doi})")
        if ap.analysis.extracted_keywords:
            kw_str = ", ".join(ap.analysis.extracted_keywords[:5])
            meta_parts.append(f"🏷 {kw_str}")
        if meta_parts:
            elements.append(self._card_note(" | ".join(meta_parts)))

        return elements

    def _build_high_details(self, ap: AnalyzedPaper) -> list[dict]:
        """Build flat detailed elements for HIGH-relevance papers (webhook fallback)."""
        elements: list[dict] = []
        paper = ap.paper
        zh = self.language == "zh"

        if paper.authors:
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += f" +{len(paper.authors)-3}"
            label = "👤 **作者**" if zh else "👤 **Authors**"
            elements.append(self._card_div(f"{label}：{authors_str}"))

        if ap.analysis.summary:
            label = "📝 **摘要**" if zh else "📝 **Summary**"
            summary = ap.analysis.summary[:500].replace("\n", " ")
            elements.append(self._card_div(f"{label}：{summary}"))

        if ap.analysis.key_contributions:
            label = "💡 **核心贡献**" if zh else "💡 **Key Contributions**"
            contribs = "\n".join(f"  • {c}" for c in ap.analysis.key_contributions[:3])
            elements.append(self._card_div(f"{label}：\n{contribs}"))

        if ap.analysis.potential_applications:
            label = "🔧 **潜在应用**" if zh else "🔧 **Applications**"
            apps = "、".join(ap.analysis.potential_applications[:3])
            elements.append(self._card_div(f"{label}：{apps}"))

        if ap.analysis.methodology_evaluation:
            label = "🔬 **方法论评估**" if zh else "🔬 **Methodology**"
            content = ap.analysis.methodology_evaluation[:500].replace("\n", " ")
            elements.append(self._card_div(f"{label}：\n{content}"))

        if ap.analysis.limitations:
            label = "⚠️ **局限性分析**" if zh else "⚠️ **Limitations**"
            items = "\n".join(f"  • {l}" for l in ap.analysis.limitations[:5])
            elements.append(self._card_div(f"{label}：\n{items}"))

        if ap.analysis.future_directions:
            label = "🚀 **未来研究方向**" if zh else "🚀 **Future Directions**"
            items = "\n".join(f"  • {d}" for d in ap.analysis.future_directions[:5])
            elements.append(self._card_div(f"{label}：\n{items}"))

        if ap.analysis.comparative_analysis:
            label = "📊 **对比分析**" if zh else "📊 **Comparative Analysis**"
            content = ap.analysis.comparative_analysis[:500].replace("\n", " ")
            if ap.analysis.compared_with:
                content += f"\n（与 {len(ap.analysis.compared_with)} 篇相关论文对比）" if zh else f"\n(Compared with {len(ap.analysis.compared_with)} papers)"
            elements.append(self._card_div(f"{label}：\n{content}"))

        return elements

    def _build_high_details_compact(self, ap: AnalyzedPaper) -> list[dict]:
        """Build compact elements for HIGH-relevance papers (webhook compact mode, no collapsible)."""
        elements: list[dict] = []
        paper = ap.paper
        zh = self.language == "zh"

        parts = []
        if paper.authors:
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += f" +{len(paper.authors) - 3}"
            parts.append(f"👤 {authors_str}")
        if paper.published_date:
            parts.append(paper.published_date.strftime("%Y-%m-%d"))
        if parts:
            elements.append(self._card_div(" | ".join(parts)))

        if ap.analysis.summary:
            summary = ap.analysis.summary[:150].replace("\n", " ")
            if len(ap.analysis.summary) > 150:
                summary += "..."
            elements.append(self._card_div(f"📝 {summary}"))

        if ap.analysis.key_contributions:
            label = "💡 **核心贡献**" if zh else "💡 **Key Contributions**"
            contribs = "\n".join(f"  • {c}" for c in ap.analysis.key_contributions[:3])
            elements.append(self._card_div(f"{label}：\n{contribs}"))

        # Grouped secondary info (flat, since no collapsible)
        secondary = []
        if ap.analysis.potential_applications:
            apps = "、".join(ap.analysis.potential_applications[:3])
            secondary.append(f"🔧 {apps}")
        if ap.analysis.methodology_evaluation:
            secondary.append(f"🔬 {ap.analysis.methodology_evaluation[:200]}")
        if secondary:
            elements.append(self._card_div("\n".join(secondary)))

        return elements

    def _build_medium_details(self, ap: AnalyzedPaper) -> list[dict]:
        """Build compact elements for MEDIUM-relevance papers."""
        elements: list[dict] = []
        paper = ap.paper

        if paper.authors:
            authors_str = ", ".join(paper.authors[:3])
            elements.append(self._card_div(f"👤 {authors_str}"))

        if ap.analysis.summary:
            summary = ap.analysis.summary[:300].replace("\n", " ")
            elements.append(self._card_div(f"📝 {summary}"))

        if ap.analysis.key_contributions:
            contribs = "、".join(ap.analysis.key_contributions[:3])
            elements.append(self._card_div(f"💡 {contribs}"))

        return elements

    # ── Archive URL generation ──────────────────────────────────────

    def _generate_archive_url(self, ap: AnalyzedPaper) -> str:
        """Generate a signed URL for the archive service."""
        if not self.feishu_app_config or not self.feishu_app_config.callback_base_url:
            return ""

        base = self.feishu_app_config.callback_base_url.rstrip("/")
        secret = os.environ.get(self.feishu_app_config.verification_token_env, "")

        paper_id = ap.paper.paper_id
        doi = ap.paper.doi or ""

        if not doi:
            return ""

        msg = f"{paper_id}:{doi}"
        sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]

        params = {"pid": paper_id, "doi": doi, "sig": sig}
        if ap.analysis.extracted_keywords:
            params["kw"] = ",".join(ap.analysis.extracted_keywords[:5])
        if ap.analysis.summary:
            params["s"] = ap.analysis.summary[:200]
        if ap.analysis.key_contributions:
            params["c"] = "|".join(ap.analysis.key_contributions[:3])

        return f"{base}/api/archive?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)

    # ── Card splitting ──────────────────────────────────────────────

    def _split_cards(self, header: dict, all_elements: list[dict]) -> list[dict]:
        """Split elements into multiple cards if content exceeds size limit."""
        cards: list[dict] = []
        current_elements: list[dict] = []
        current_size = 0

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

    # ── HTTP posting ────────────────────────────────────────────────

    async def _post_message(
        self, client: httpx.AsyncClient, message: dict
    ) -> bool:
        """Send a card message via App API or webhook."""
        if self._use_app_api:
            return await self._post_app_api(client, message)
        elif self.webhook_url:
            return await self._post_webhook(client, message)
        else:
            logger.warning("No Feishu sending method configured")
            return False

    async def _post_app_api(
        self, client: httpx.AsyncClient, message: dict
    ) -> bool:
        """Send via Feishu App API (/im/v1/messages)."""
        token = await self._get_tenant_token(client)
        if not token:
            logger.error("Failed to get Feishu token, falling back to webhook")
            if self.webhook_url:
                return await self._post_webhook(client, message)
            return False

        chat_id = os.environ.get(self.feishu_app_config.chat_id_env, "")
        if not chat_id:
            logger.error("FEISHU_CHAT_ID not set")
            return False

        # App API expects card JSON in the body, not wrapped in msg_type
        card_json = message.get("card", message)

        try:
            resp = await client.post(
                FEISHU_MESSAGE_URL,
                params={"receive_id": chat_id, "receive_id_type": "chat_id"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "receive_id": chat_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card_json, ensure_ascii=False),
                },
                timeout=15,
            )
            result = resp.json()
            if result.get("code") == 0:
                logger.info("Feishu App API: message sent successfully")
                return True
            else:
                logger.error(f"Feishu App API error: {result}")
                # Fall back to webhook if available
                if self.webhook_url:
                    logger.info("Falling back to webhook")
                    return await self._post_webhook(client, message)
                return False
        except Exception as e:
            logger.error(f"Feishu App API failed: {e}")
            if self.webhook_url:
                return await self._post_webhook(client, message)
            return False

    async def _post_webhook(
        self, client: httpx.AsyncClient, message: dict
    ) -> bool:
        """Send via webhook URL (fallback)."""
        try:
            response = await client.post(
                self.webhook_url,
                json=message,
                timeout=15,
            )
            result = response.json()
            if result.get("code") == 0:
                logger.info("Feishu webhook: message sent successfully")
                return True
            else:
                logger.error(f"Feishu webhook error: {result}")
                return False
        except Exception as e:
            logger.error(f"Feishu webhook failed: {e}")
            return False

    async def _send_no_papers(self, topic_stats: dict) -> bool:
        """Send notification when no new papers found."""
        date_str = datetime.now(timezone.utc).strftime("%m-%d")
        if self.language == "zh":
            title = f"📚 每日文献速递（{date_str}）"
            text = "今日没有发现新的相关论文。"
        else:
            title = f"📚 Daily Literature Digest ({date_str})"
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

    # ── Card element helpers ────────────────────────────────────────

    @staticmethod
    def _card_div(content: str) -> dict:
        return {"tag": "div", "text": {"tag": "lark_md", "content": content}}

    @staticmethod
    def _card_hr() -> dict:
        return {"tag": "hr"}

    @staticmethod
    def _card_note(content: str) -> dict:
        return {"tag": "note", "elements": [{"tag": "plain_text", "content": content}]}

    @staticmethod
    def _collapsible_panel(title: str, content_md: str, expanded: bool = False) -> dict:
        """Build a collapsible panel (requires App API sending mode).

        Structure per Feishu docs:
          header.title → panel title
          elements → panel content (markdown elements)
        """
        return {
            "tag": "collapsible_panel",
            "expanded": expanded,
            "header": {
                "title": {
                    "tag": "markdown",
                    "content": title,
                },
            },
            "elements": [
                {"tag": "markdown", "content": content_md}
            ],
        }
