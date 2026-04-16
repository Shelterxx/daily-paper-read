"""Obsidian vault integration: generate literature cards, daily summaries, and push to Git.

Generates per-paper markdown cards with YAML frontmatter and structured sections,
daily summary notes with statistics and wiki-links, and topic-based backlinks
between related papers. Commits and pushes to a Git vault repository via HTTPS + PAT.

Requirements: OBS-01 (paper cards), OBS-02 (daily summary),
              OBS-03 (backlinks), OBS-04 (Git push)
"""

import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.search.models import AnalyzedPaper, RelevanceTier
from src.config.models import ObsidianConfig

logger = logging.getLogger(__name__)


class ObsidianWriter:
    """Generates Obsidian-compatible markdown files and pushes to a Git vault repo."""

    def __init__(self, config: ObsidianConfig):
        self.config = config

    async def write_and_push(self, papers: list[AnalyzedPaper], topic_stats: dict) -> dict:
        """Main entry: generate cards + daily summary, then git commit + push.

        Returns: {cards_written: int, daily_written: bool, pushed: bool, errors: list[str]}
        """
        result = {
            "cards_written": 0,
            "daily_written": False,
            "pushed": False,
            "errors": [],
        }

        try:
            # Check if Obsidian integration is enabled
            if not self.config.enabled:
                logger.info("Obsidian disabled, skipping")
                return result

            # Check vault repo URL
            if not self.config.vault_repo_url:
                logger.warning("Obsidian vault_repo_url is empty, skipping")
                result["errors"].append("vault_repo_url not configured")
                return result

            # Read PAT from environment
            pat = os.environ.get(self.config.vault_pat_env, "")
            if not pat:
                logger.warning(
                    f"Obsidian PAT env var '{self.config.vault_pat_env}' not set, skipping"
                )
                result["errors"].append(
                    f"PAT not set: {self.config.vault_pat_env}"
                )
                return result

            # Get today's date in UTC
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Build topic peers map for backlinks
            topic_peers = self._get_topic_peers(papers)

            # Create temporary directory for generated files
            with tempfile.TemporaryDirectory() as tmpdir:
                papers_dir = Path(tmpdir) / "papers"
                daily_dir = Path(tmpdir) / "daily"
                papers_dir.mkdir()
                daily_dir.mkdir()

                # Generate paper cards
                for ap in papers:
                    try:
                        peers = topic_peers.get(ap.topic_name, [])
                        card_content = self._generate_paper_card(ap, peers)
                        filename = self._sanitize_filename(ap.paper) + ".md"
                        card_path = papers_dir / filename
                        card_path.write_text(card_content, encoding="utf-8")
                        result["cards_written"] += 1
                    except Exception as e:
                        error_msg = f"Failed to generate card for '{ap.paper.title[:40]}': {e}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)

                # Generate daily summary
                try:
                    summary_content = self._generate_daily_summary(
                        papers, topic_stats, date_str
                    )
                    summary_path = daily_dir / f"{date_str}-daily-summary.md"
                    summary_path.write_text(summary_content, encoding="utf-8")
                    result["daily_written"] = True
                except Exception as e:
                    error_msg = f"Failed to generate daily summary: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)

                # Git clone, copy files, commit and push
                if result["cards_written"] > 0 or result["daily_written"]:
                    pushed = self._git_clone_push(
                        Path(tmpdir), date_str, result["cards_written"]
                    )
                    result["pushed"] = pushed
                    if not pushed:
                        result["errors"].append("Git push failed")

        except Exception as e:
            logger.error(f"ObsidianWriter.write_and_push failed: {e}")
            result["errors"].append(str(e))

        return result

    def _sanitize_filename(self, paper) -> str:
        """Convert paper DOI or dedup_key to a safe filename.

        Replace '/' with '-', remove other special chars.
        E.g. '10.1234/abc' -> '10.1234-abc'
        """
        if paper.doi:
            base = paper.doi.replace("/", "-").replace("\\", "-")
        else:
            base = paper.dedup_key.replace(":", "-").replace("/", "-")

        # Remove characters invalid in filenames
        base = re.sub(r'[<>"|?*]', "", base)
        return base

    def _generate_paper_card(self, ap: AnalyzedPaper, topic_peers: list[str]) -> str:
        """Generate a single paper card in markdown with YAML frontmatter.

        OBS-01: Per-paper markdown cards with structured sections.
        OBS-03: Backlinks to same-topic papers via wiki-links.
        """
        paper = ap.paper
        analysis = ap.analysis
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # YAML frontmatter
        authors_str = ", ".join(paper.authors) if paper.authors else ""
        keywords_str = ", ".join(analysis.extracted_keywords) if analysis.extracted_keywords else ""

        lines = [
            "---",
            f'title: "{paper.title}"',
            f"authors: [{authors_str}]",
            f'doi: "{paper.doi or ""}"',
            f"score: {analysis.relevance_score}",
            f"date: {date_str}",
            f'topics: ["{ap.topic_name}"]',
            f"keywords: [{keywords_str}]",
            f"source: {paper.source}",
            "---",
            "",
        ]

        # Summary section
        lines.append("## Summary")
        lines.append(analysis.summary or "(No summary available)")
        lines.append("")

        # Key Contributions
        if analysis.key_contributions:
            lines.append("## Key Contributions")
            for contrib in analysis.key_contributions:
                lines.append(f"- {contrib}")
            lines.append("")

        # Methodology
        if analysis.methodology_evaluation:
            lines.append("## Methodology")
            lines.append(analysis.methodology_evaluation)
            lines.append("")

        # Limitations
        if analysis.limitations:
            lines.append("## Limitations")
            for lim in analysis.limitations:
                lines.append(f"- {lim}")
            lines.append("")

        # Future Directions
        if analysis.future_directions:
            lines.append("## Future Directions")
            for fd in analysis.future_directions:
                lines.append(f"- {fd}")
            lines.append("")

        # Related Papers (backlinks - OBS-03)
        self_filename = self._sanitize_filename(paper)
        peer_links = [
            f"[[{peer}]]"
            for peer in topic_peers
            if peer != self_filename
        ]
        # Add topic tag link
        topic_link = f"[[{ap.topic_name}]]"

        lines.append("## Related Papers")
        for link in peer_links:
            lines.append(link)
        lines.append(topic_link)
        lines.append("")

        return "\n".join(lines)

    def _generate_daily_summary(
        self, papers: list[AnalyzedPaper], topic_stats: dict, date_str: str
    ) -> str:
        """Generate the daily summary note listing all papers with stats and wiki-links.

        OBS-02: Daily summary with statistics and per-topic tables.
        """
        lines = [
            f"# Daily Literature Digest - {date_str}",
            "",
        ]

        # Statistics block
        total = len(papers)
        high_count = sum(1 for p in papers if p.analysis.tier == RelevanceTier.HIGH)
        medium_count = sum(1 for p in papers if p.analysis.tier == RelevanceTier.MEDIUM)
        low_count = sum(1 for p in papers if p.analysis.tier == RelevanceTier.LOW)

        lines.append("## Statistics")
        lines.append(f"- Total new papers: {total}")
        lines.append(f"- HIGH: {high_count}, MEDIUM: {medium_count}, LOW: {low_count}")
        lines.append("")

        # Group papers by topic, sorted by score descending
        papers_by_topic: dict[str, list[AnalyzedPaper]] = {}
        for ap in papers:
            if ap.topic_name not in papers_by_topic:
                papers_by_topic[ap.topic_name] = []
            papers_by_topic[ap.topic_name].append(ap)

        for topic_name, topic_papers in papers_by_topic.items():
            sorted_papers = sorted(
                topic_papers, key=lambda x: x.analysis.relevance_score, reverse=True
            )

            lines.append(f"## {topic_name}")
            lines.append("| Score | Title | Link |")
            lines.append("|-------|-------|------|")

            for ap in sorted_papers:
                card_filename = self._sanitize_filename(ap.paper)
                title = ap.paper.title
                wiki_link = f"[[{card_filename}|{title}]]"
                source_url = ap.paper.source_url or ""
                if source_url:
                    link = f"[source]({source_url})"
                else:
                    link = ""
                lines.append(
                    f"| {ap.analysis.relevance_score} | {wiki_link} | {link} |"
                )
            lines.append("")

        # All Papers section
        lines.append("## All Papers")
        for ap in papers:
            card_filename = self._sanitize_filename(ap.paper)
            lines.append(f"- [[{card_filename}]]")
        lines.append("")

        return "\n".join(lines)

    def _get_topic_peers(self, papers: list[AnalyzedPaper]) -> dict[str, list[str]]:
        """Build topic_name -> list of wiki-link filenames for backlinks.

        OBS-03: Papers within the same topic link to each other.
        """
        peers: dict[str, list[str]] = {}
        for ap in papers:
            if ap.topic_name not in peers:
                peers[ap.topic_name] = []
            filename = self._sanitize_filename(ap.paper)
            if filename not in peers[ap.topic_name]:
                peers[ap.topic_name].append(filename)
        return peers

    def _git_clone_push(self, local_dir: Path, date_str: str, paper_count: int) -> bool:
        """Clone vault repo, copy generated files, commit and push.

        OBS-04: Generated notes are committed and pushed to a Git vault repository via HTTPS + PAT.
        """
        pat = os.environ.get(self.config.vault_pat_env, "")
        repo_url = self.config.vault_repo_url

        # Construct authenticated URL
        auth_url = repo_url.replace("https://", f"https://{pat}@")

        vault_dir: Optional[Path] = None
        try:
            # Clone into a new temp directory
            vault_dir = Path(tempfile.mkdtemp())
            result = subprocess.run(
                ["git", "clone", auth_url, str(vault_dir)],
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.error(f"Git clone failed: {result.stderr.decode()}")
                return False

            # Set git identity (required in CI environments)
            subprocess.run(
                ["git", "config", "user.email", "bot@literature-push"],
                cwd=str(vault_dir), capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Literature Push Bot"],
                cwd=str(vault_dir), capture_output=True,
            )

            # Copy generated files to vault
            vault_papers = vault_dir / "papers"
            vault_daily = vault_dir / "daily"
            vault_papers.mkdir(exist_ok=True)
            vault_daily.mkdir(exist_ok=True)

            # Copy paper cards
            src_papers = local_dir / "papers"
            if src_papers.exists():
                for md_file in src_papers.glob("*.md"):
                    dest = vault_papers / md_file.name
                    shutil.copy2(str(md_file), str(dest))

            # Copy daily summary
            src_daily = local_dir / "daily"
            if src_daily.exists():
                for md_file in src_daily.glob("*.md"):
                    dest = vault_daily / md_file.name
                    shutil.copy2(str(md_file), str(dest))

            # Stage files
            subprocess.run(
                ["git", "add", "papers/", "daily/"],
                cwd=str(vault_dir),
                capture_output=True,
            )

            # Commit
            commit_msg = f"docs(daily): {date_str} -- {paper_count} papers archived"
            commit_result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=str(vault_dir),
                capture_output=True,
            )

            # Nothing to commit is OK (all files unchanged)
            if commit_result.returncode != 0:
                stderr = commit_result.stderr.decode()
                if "nothing to commit" in stderr or "no changes added" in stderr:
                    logger.info("No changes to commit to Obsidian vault")
                    return True
                logger.error(f"Git commit failed: {stderr}")
                return False

            # Push to main
            push_result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=str(vault_dir),
                capture_output=True,
                timeout=60,
            )

            if push_result.returncode != 0:
                # Conflict handling: try pull --rebase then push again
                logger.warning(
                    f"Git push failed, attempting rebase: {push_result.stderr.decode()}"
                )
                pull_result = subprocess.run(
                    ["git", "pull", "--rebase", "origin", "main"],
                    cwd=str(vault_dir),
                    capture_output=True,
                    timeout=60,
                )
                if pull_result.returncode == 0:
                    retry_result = subprocess.run(
                        ["git", "push", "origin", "main"],
                        cwd=str(vault_dir),
                        capture_output=True,
                        timeout=60,
                    )
                    if retry_result.returncode != 0:
                        logger.error(
                            f"Git push failed after rebase: {retry_result.stderr.decode()}"
                        )
                        return False
                else:
                    logger.error(
                        f"Git pull --rebase failed: {pull_result.stderr.decode()}"
                    )
                    return False

            logger.info(
                f"Obsidian vault updated: {date_str} -- {paper_count} papers"
            )
            return True

        except subprocess.TimeoutExpired:
            logger.error("Git operation timed out")
            return False
        except Exception as e:
            logger.error(f"Git clone+push failed: {e}")
            return False
        finally:
            # Clean up cloned vault directory
            if vault_dir and vault_dir.exists():
                try:
                    shutil.rmtree(str(vault_dir))
                except Exception:
                    logger.warning(f"Failed to clean up vault dir: {vault_dir}")
