"""Archive service for Feishu 'Interested' button.

Supports two modes:
  1. URL-based (recommended): Cards use open_url buttons → browser opens this server → archives to Zotero
  2. Callback-based: Feishu App sends card action callbacks → server archives to Zotero

Mode 1 works with the existing webhook bot (no Feishu App registration needed).
Mode 2 requires a registered Feishu App with card callback subscription.

Usage:
    # Local testing
    uvicorn src.callback_server:app --host 0.0.0.0 --port 8080

    # Deploy to Railway / Render / any cloud
    uvicorn src.callback_server:app --host 0.0.0.0 --port $PORT
"""

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

load_dotenv()

from src.config.loader import load_config
from src.config.models import AppConfig
from src.integrations.zotero import ZoteroArchiver
from src.search.models import Paper, AnalysisResult, AnalyzedPaper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("archive-server")

app = FastAPI(title="Literature Archive Service")

# Global state — loaded on startup, refreshed periodically
config: Optional[AppConfig] = None
zotero_archiver: Optional[ZoteroArchiver] = None
papers_store: dict[str, AnalyzedPaper] = {}


def _load_papers():
    """Load papers from state file saved by the pipeline."""
    global papers_store
    if not config:
        return

    state_file = Path(config.state_dir) / "papers_for_callback.json"
    if not state_file.exists():
        logger.info("No papers_for_callback.json found")
        return

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        loaded = {}
        for entry in data.get("papers", []):
            try:
                ap = AnalyzedPaper(
                    paper=Paper(**entry["paper"]),
                    analysis=AnalysisResult(**entry["analysis"]),
                    topic_name=entry["topic_name"],
                )
                loaded[ap.paper.paper_id] = ap
            except Exception as e:
                logger.warning(f"Failed to parse paper entry: {e}")
        papers_store = loaded
        logger.info(f"Loaded {len(papers_store)} papers for callback handling")
    except Exception as e:
        logger.error(f"Failed to load papers: {e}")


@app.on_event("startup")
async def startup():
    """Initialize config, Zotero client, and paper data on server start."""
    global config, zotero_archiver

    try:
        config = load_config("config.yaml")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    if config.zotero and config.zotero.enabled:
        zotero_archiver = ZoteroArchiver(config.zotero)

    _load_papers()


# ── Mode 1: URL-based archive (open_url button) ─────────────────────


def _verify_signature(paper_id: str, doi: str, sig: str) -> bool:
    """Verify HMAC-SHA256 signature for URL-based archive requests."""
    secret = ""
    if config and config.feishu_app:
        secret = os.environ.get(config.feishu_app.verification_token_env, "")
    if not secret:
        return False
    msg = f"{paper_id}:{doi}"
    expected = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]
    return hmac.compare_digest(sig, expected)


def _fetch_crossref_metadata(doi: str) -> dict:
    """Fetch paper metadata from CrossRef API using DOI."""
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    req = urllib.request.Request(url, headers={"User-Agent": "LiteraturePush/1.0 (mailto:research)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("message", {})
    except Exception as e:
        logger.warning(f"CrossRef lookup failed for {doi}: {e}")
        return {}


def _create_zotero_item_direct(doi: str, keywords: list[str], analysis_summary: str, contributions: list[str]) -> dict:
    """Create a Zotero item using CrossRef metadata + analysis data.

    This is used when the full paper data isn't in papers_store
    (e.g., papers_for_callback.json expired or not synced).
    Falls back to CrossRef for metadata.
    """
    if not zotero_archiver:
        return {"success": False, "error": "Zotero not configured"}

    # Fetch metadata from CrossRef
    metadata = _fetch_crossref_metadata(doi)

    # Build paper + analysis objects for ZoteroArchiver
    title = ""
    if metadata.get("title"):
        t = metadata["title"]
        title = t[0] if isinstance(t, list) else t

    authors = []
    for author in metadata.get("author", []):
        given = author.get("given", "")
        family = author.get("family", "")
        authors.append(f"{given} {family}".strip())

    abstract = metadata.get("abstract", "")

    # Parse publication date
    published = metadata.get("published-print", metadata.get("published-online", {}))
    pub_date = None
    date_parts = published.get("date-parts", [[""]])[0]
    if date_parts and date_parts[0]:
        try:
            from datetime import date
            parts = [int(x) for x in date_parts if x]
            pub_date = date(*parts)
        except (ValueError, TypeError):
            pass

    paper = Paper(
        paper_id=f"doi:{doi}",
        title=title or f"DOI:{doi}",
        authors=authors,
        abstract=abstract,
        doi=doi,
        source="crossref",
        source_url=f"https://doi.org/{doi}",
        published_date=pub_date,
    )

    analysis = AnalysisResult(
        relevance_score=9,
        extracted_keywords=keywords,
        summary=analysis_summary,
        key_contributions=contributions,
    )

    ap = AnalyzedPaper(paper=paper, analysis=analysis, topic_name="Interested")

    try:
        # Check for existing item
        existing = zotero_archiver._find_existing_item(paper)
        if existing:
            return {"success": True, "item_key": existing, "existed": True}

        result = zotero_archiver.archive_single(ap)
        return {
            "success": result.get("archived", False),
            "item_key": result.get("item_key"),
            "error": result.get("error"),
            "existed": False,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _html_page(title: str, message: str, success: bool, extra: str = "") -> str:
    """Mobile-friendly HTML result page."""
    icon = "✅" if success else "❌"
    color = "#10b981" if success else "#ef4444"
    return f"""<!DOCTYPE html>
<html lang="zh"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 420px; margin: 60px auto; padding: 0 20px; text-align: center; }}
  .icon {{ font-size: 52px; margin-bottom: 20px; }}
  .title {{ font-size: 20px; font-weight: 600; color: {color}; margin-bottom: 12px; }}
  .message {{ font-size: 14px; color: #555; line-height: 1.6; }}
  .extra {{ margin-top: 16px; font-size: 12px; color: #999; }}
  .back {{ margin-top: 24px; }}
  .back a {{ color: #3b82f6; text-decoration: none; font-size: 14px; }}
</style>
</head><body>
  <div class="icon">{icon}</div>
  <div class="title">{title}</div>
  <div class="message">{message}</div>
  {f'<div class="extra">{extra}</div>' if extra else ''}
  <div class="back"><a href="javascript:history.back()">← 返回飞书</a></div>
</body></html>"""


@app.get("/api/archive", response_class=HTMLResponse)
async def archive_by_url(
    pid: str = "",
    doi: str = "",
    sig: str = "",
    kw: str = "",
    s: str = "",
    c: str = "",
):
    """Handle 'Interested' button click from Feishu card (open_url mode).

    Query params:
        pid: paper_id
        doi: DOI of the paper
        sig: HMAC signature for verification
        kw: comma-separated keywords (for Zotero tags)
        s: short summary (for Zotero note)
        c: pipe-separated contributions (for Zotero note)
    """
    # Verify signature
    if not _verify_signature(pid, doi, sig):
        return _html_page("验证失败", "链接签名无效或已过期，请重新运行管线获取新链接。", False)

    if not doi:
        return _html_page("缺少 DOI", "该论文没有 DOI，无法自动归档。", False)

    if not zotero_archiver:
        return _html_page("Zotero 未配置", "归档服务未连接 Zotero，请联系管理员。", False)

    # Try loading from papers_store first (has full analysis data)
    ap = papers_store.get(pid)
    if ap:
        try:
            result = await zotero_archiver.archive_single(ap)
            if result.get("skipped"):
                return _html_page("已存在", f"《{ap.paper.title[:50]}》已在 Zotero 中。", True)
            elif result.get("archived"):
                logger.info(f"Archived via URL: {ap.paper.title[:60]}")
                return _html_page(
                    "已归档到 Zotero ✓",
                    f"《{ap.paper.title[:50]}》已成功归档，含 AI 标签和分析笔记。",
                    True,
                )
            else:
                return _html_page("归档失败", f"错误：{result.get('error', '未知')}", False)
        except Exception as e:
            return _html_page("归档失败", f"错误：{e}", False)

    # Fallback: create item from CrossRef + URL params
    keywords = [k.strip() for k in kw.split(",") if k.strip()] if kw else []
    summary = urllib.parse.unquote(s) if s else ""
    contributions = [c.strip() for c in c.split("|") if c.strip()] if c else ""

    result = _create_zotero_item_direct(doi, keywords, summary, contributions)

    if result.get("existed"):
        return _html_page("已存在", f"DOI:{doi} 已在 Zotero 中。", True)
    elif result.get("success"):
        return _html_page("已归档到 Zotero ✓", f"DOI:{doi} 已归档（元数据来自 CrossRef）。", True)
    else:
        return _html_page("归档失败", f"错误：{result.get('error', '未知')}", False)


# ── Mode 2: Feishu App callback (original) ──────────────────────────


@app.post("/feishu/callback")
async def handle_callback(request: Request):
    """Handle Feishu card action callback (requires Feishu App registration)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid JSON"}, status_code=400)

    logger.info(f"Received callback: {json.dumps(body, ensure_ascii=False)[:200]}")

    if not config or not config.feishu_app:
        return JSONResponse(content={"error": "Server not configured"}, status_code=500)

    verification_token = os.environ.get(config.feishu_app.verification_token_env, "")
    if verification_token and body.get("token") != verification_token:
        logger.warning("Invalid verification token")
        return JSONResponse(content={"error": "Invalid token"}, status_code=403)

    action = body.get("action", {})
    value = action.get("value", {})
    paper_id = value.get("paper_id")
    action_type = value.get("action")

    if not paper_id or action_type != "archive_to_zotero":
        return JSONResponse(content={"error": "Invalid action"}, status_code=400)

    if paper_id not in papers_store:
        _load_papers()

    ap = papers_store.get(paper_id)
    if not ap:
        return {"toast": {"type": "warning", "content": f"论文未找到（{paper_id}），请重新运行管线"}}

    if not zotero_archiver:
        return {"toast": {"type": "error", "content": "Zotero 未配置"}}

    try:
        result = await zotero_archiver.archive_single(ap)
        if result.get("skipped"):
            return {"toast": {"type": "info", "content": f"已存在于 Zotero 中：{ap.paper.title[:40]}"}}
        elif result.get("archived"):
            logger.info(f"Archived via button: {ap.paper.title[:60]}")
            return {"toast": {"type": "success", "content": f"已归档到 Zotero：{ap.paper.title[:40]}"}}
        else:
            return {"toast": {"type": "error", "content": f"归档失败：{result.get('error', 'unknown')}"}}
    except Exception as e:
        logger.error(f"Archive error: {e}")
        return {"toast": {"type": "error", "content": f"归档失败：{e}"}}


# ── Health check ─────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "papers_loaded": len(papers_store),
        "zotero_configured": zotero_archiver is not None,
    }
