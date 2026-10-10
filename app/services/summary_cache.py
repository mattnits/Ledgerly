"""Small process-local cache for immutable financial summary DTOs."""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Hashable, TypeVar

from sqlalchemy import event
from sqlalchemy.orm import Session


T = TypeVar("T")
_MAX_ENTRIES = 64
_cache: OrderedDict[Hashable, object] = OrderedDict()
_lock = RLock()


def get_cached_summary(key: Hashable) -> T | None:
    with _lock:
        value = _cache.get(key)
        if value is None:
            return None
        _cache.move_to_end(key)
        return value  # type: ignore[return-value]


def cache_summary(key: Hashable, value: T) -> T:
    with _lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)
    return value


def clear_summary_cache() -> None:
    with _lock:
        _cache.clear()


@event.listens_for(Session, "after_commit")
def _clear_after_commit(_session: Session) -> None:
    clear_summary_cache()
