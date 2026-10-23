"""可替换的会话存储接口。"""

from __future__ import annotations

import math
import threading
import time
from copy import deepcopy
from typing import Protocol

from skillforge.shared.errors import ConfigError
from skillforge.shared.types import SessionState


class SessionStore(Protocol):
    def get(self, session_id: str) -> SessionState | None: ...

    def save(self, session: SessionState) -> None: ...


class InMemorySessionStore:
    """单进程内存存储；多 worker/实例不共享，重启丢失。

    跨实例请替换为 Redis/SQLite 存储。TTL 从最后保存起算；满额淘汰
    最久未保存的会话。读写使用副本，锁保护存储操作；同一会话并发保存
    采用最后写入覆盖语义，客户端应串行续传。
    """

    def __init__(self, ttl_seconds: float = 3600, max_sessions: int = 1000) -> None:
        if not math.isfinite(ttl_seconds) or ttl_seconds <= 0 or max_sessions <= 0:
            raise ConfigError("会话 TTL 必须为有限正数，容量必须为正数")
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions
        self._entries: dict[str, tuple[float, SessionState]] = {}
        self._lock = threading.Lock()

    def _sweep(self, now: float) -> None:
        # 字典按保存时间排序，只需扫描过期前缀。
        while self._entries:
            key = next(iter(self._entries))
            if now - self._entries[key][0] < self.ttl:
                break
            del self._entries[key]

    def get(self, session_id: str) -> SessionState | None:
        with self._lock:
            self._sweep(time.monotonic())
            entry = self._entries.get(session_id)
            return deepcopy(entry[1]) if entry else None

    def save(self, session: SessionState) -> None:
        with self._lock:
            now = time.monotonic()
            self._sweep(now)
            self._entries.pop(session.session_id, None)
            if len(self._entries) >= self.max_sessions:
                del self._entries[next(iter(self._entries))]
            self._entries[session.session_id] = (now, deepcopy(session))
