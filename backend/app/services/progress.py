"""Context-local progress events for user-visible execution summaries."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Any


ProgressEmitter = Callable[[dict[str, Any]], Awaitable[None]]
_emitter: ContextVar[ProgressEmitter | None] = ContextVar("progress_emitter", default=None)
_events: ContextVar[list[dict[str, Any]] | None] = ContextVar("progress_events", default=None)


class ProgressScope:
    def __init__(self, emitter: ProgressEmitter | None = None):
        self._emitter = emitter
        self._events: list[dict[str, Any]] = []
        self._emitter_token: Token | None = None
        self._events_token: Token | None = None

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def __enter__(self) -> "ProgressScope":
        self._emitter_token = _emitter.set(self._emitter)
        self._events_token = _events.set(self._events)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._events_token is not None:
            _events.reset(self._events_token)
        if self._emitter_token is not None:
            _emitter.reset(self._emitter_token)


async def emit_progress(stage: str, label: str, detail: str | None = None) -> None:
    event = {"stage": stage, "label": label}
    if detail:
        event["detail"] = detail
    log = _events.get()
    if log is not None and len(log) < 24:
        log.append(event)
    current = _emitter.get()
    if current is not None:
        await current(event)
