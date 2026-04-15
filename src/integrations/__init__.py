"""Integrations package: Zotero archiving and Obsidian vault generation."""


def __getattr__(name: str):
    """Lazy import for integration modules to avoid importing
    optional dependencies when the integration is disabled."""
    if name == "ObsidianWriter":
        from src.integrations.obsidian import ObsidianWriter
        return ObsidianWriter
    if name == "ZoteroArchiver":
        from src.integrations.zotero import ZoteroArchiver
        return ZoteroArchiver
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
