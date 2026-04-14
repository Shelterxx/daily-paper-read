"""Notification delivery channels."""

from src.delivery.base import Notifier

__all__ = ["Notifier"]

# Lazy import to avoid circular dependency during module load
def __getattr__(name: str):
    if name == "FeishuNotifier":
        from src.delivery.feishu import FeishuNotifier
        return FeishuNotifier
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
