"""订单存储（SQLite）。

订单 = 平台的"任务单"：商品 SKU + 提交 payload + 状态机 + 进度 + 结果。
SQLite(WAL) 起步即可支撑多 Worker（写串行、认领用单条 UPDATE 原子完成）；
未来跨机共享时把 OrderStore 换成 PostgreSQL 实现，接口不变。

状态机：
  PENDING_PAYMENT → QUEUED → ASSIGNED → RUNNING ─┬→ SUCCEEDED
                                                  └→ FAILED
  用户取消：未执行前 CANCELLED；执行中置 cancel_requested，Worker 协作停止
  失联回收：heartbeat 超时（Phase 2 实现，本版单 Worker 不触发）
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.order')

# 订单状态
STATUS_PENDING_PAYMENT = "PENDING_PAYMENT"
STATUS_QUEUED = "QUEUED"
STATUS_ASSIGNED = "ASSIGNED"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"
STATUS_CANCELLED = "CANCELLED"

# 执行中可取消的状态集合
_CANCELLABLE_BEFORE_RUN = {STATUS_PENDING_PAYMENT, STATUS_QUEUED}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id       TEXT PRIMARY KEY,
    product_id     TEXT NOT NULL,
    user_email     TEXT DEFAULT '',
    title          TEXT DEFAULT '',
    scenario       TEXT DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'PENDING_PAYMENT',
    priority       INTEGER NOT NULL DEFAULT 0,
    worker_id      TEXT,
    payload        TEXT DEFAULT '{}',
    files          TEXT DEFAULT '[]',
    progress       INTEGER DEFAULT 0,
    stage_detail   TEXT DEFAULT '{}',
    result         TEXT,
    error          TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    heartbeat_at   TEXT,
    created_at     TEXT,
    updated_at     TEXT,
    started_at     TEXT,
    finished_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_claim
    ON orders(status, priority DESC, created_at);
"""


def _now() -> str:
    return datetime.now().isoformat()


class OrderStore:
    """订单的 SQLite 存取（线程安全；跨进程依赖 SQLite 写串行）。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(
            Config.UPLOAD_FOLDER, 'orders', 'orders.db'
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _ensure_schema(self) -> None:
        with self._init_lock:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)

    # ── 基础 CRUD ─────────────────────────────────────────────

    def create(
        self,
        order_id: str,
        product_id: str,
        scenario: str,
        title: str = "",
        user_email: str = "",
        priority: int = 0,
        payload: Optional[Dict[str, Any]] = None,
        files: Optional[List[Dict[str, str]]] = None,
        paid: bool = False,
    ) -> Dict[str, Any]:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO orders (order_id, product_id, user_email, title, scenario, "
                "status, priority, payload, files, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order_id, product_id, user_email, title, scenario,
                    STATUS_QUEUED if paid else STATUS_PENDING_PAYMENT,
                    priority,
                    json.dumps(payload or {}, ensure_ascii=False),
                    json.dumps(files or [], ensure_ascii=False),
                    now, now,
                ),
            )
        return self.get(order_id)  # type: ignore[return-value]

    def get(self, order_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_orders(
        self,
        *,
        user_email: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM orders"
        conditions, params = [], []
        if user_email:
            conditions.append("user_email = ?")
            params.append(user_email)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.get("payload") or "{}")
        data["files"] = json.loads(data.get("files") or "[]")
        data["stage_detail"] = json.loads(data.get("stage_detail") or "{}")
        data["result"] = json.loads(data["result"]) if data.get("result") else None
        data["cancel_requested"] = bool(data.get("cancel_requested"))
        return data

    # ── 支付 / 队列流转 ───────────────────────────────────────

    def mark_paid(self, order_id: str) -> bool:
        """支付完成 → 入队。仅 PENDING_PAYMENT 状态可流转。"""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? "
                "WHERE order_id = ? AND status = ?",
                (STATUS_QUEUED, _now(), order_id, STATUS_PENDING_PAYMENT),
            )
            return cursor.rowcount > 0

    def claim_next(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """原子认领一个已支付的排队订单（SQLite 写串行保证不重复认领）。"""
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT order_id FROM orders WHERE status = ? "
                "ORDER BY priority DESC, created_at ASC LIMIT 1",
                (STATUS_QUEUED,),
            ).fetchone()
            if row is None:
                return None
            cursor = conn.execute(
                "UPDATE orders SET status = ?, worker_id = ?, started_at = ?, "
                "heartbeat_at = ?, updated_at = ? WHERE order_id = ? AND status = ?",
                (STATUS_ASSIGNED, worker_id, now, now, now, row["order_id"],
                 STATUS_QUEUED),
            )
            if cursor.rowcount != 1:
                return None
            order_id = row["order_id"]
        # 事务已提交后再读取（否则新连接会读到提交前的旧状态）
        claimed = self.get(order_id)
        logger.info(f"Worker {worker_id} 认领订单 {order_id}")
        return claimed

    def mark_running(self, order_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
                (STATUS_RUNNING, _now(), order_id),
            )

    _EXECUTING_STATUSES = (STATUS_ASSIGNED, STATUS_RUNNING)

    def update_progress(
        self, order_id: str, progress: int, stage: str = "", detail: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新执行进度。仅 ASSIGNED/RUNNING 状态可写（防僵尸进程覆写终态）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT stage_detail FROM orders WHERE order_id = ? AND status IN (?, ?)",
                (order_id, *self._EXECUTING_STATUSES),
            ).fetchone()
            if row is None:
                return False
            stages = json.loads(row["stage_detail"]) if row else {}
            if stage:
                stages[stage] = detail if detail is not None else _now()
            conn.execute(
                "UPDATE orders SET progress = ?, stage_detail = ?, updated_at = ? "
                "WHERE order_id = ? AND status IN (?, ?)",
                (max(0, min(100, int(progress))), json.dumps(stages, ensure_ascii=False),
                 _now(), order_id, *self._EXECUTING_STATUSES),
            )
        return True

    # ── 终态 ──────────────────────────────────────────────────

    def set_result(self, order_id: str, result: Dict[str, Any]) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE orders SET status = ?, result = ?, progress = 100, "
                "finished_at = ?, updated_at = ? "
                "WHERE order_id = ? AND status IN (?, ?)",
                (STATUS_SUCCEEDED, json.dumps(result, ensure_ascii=False),
                 _now(), _now(), order_id, *self._EXECUTING_STATUSES),
            )
        return cursor.rowcount > 0

    def set_failed(self, order_id: str, error: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE orders SET status = ?, error = ?, finished_at = ?, updated_at = ? "
                "WHERE order_id = ? AND status IN (?, ?)",
                (STATUS_FAILED, error[:2000], _now(), _now(), order_id,
                 *self._EXECUTING_STATUSES),
            )
        return cursor.rowcount > 0

    def requeue(self, order_id: str) -> None:
        """失败重试入队（Phase 2 的重试策略入口）。"""
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status = ?, worker_id = NULL, error = NULL, "
                "updated_at = ? WHERE order_id = ?",
                (STATUS_QUEUED, _now(), order_id),
            )

    # ── 取消 ──────────────────────────────────────────────────

    def request_cancel(self, order_id: str) -> bool:
        """取消订单。已进入执行的置 cancel_requested 由 Worker 协作停止。"""
        order = self.get(order_id)
        if order is None:
            return False
        status = order["status"]
        if status in _CANCELLABLE_BEFORE_RUN:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE orders SET status = ?, finished_at = ?, updated_at = ? "
                    "WHERE order_id = ?",
                    (STATUS_CANCELLED, _now(), _now(), order_id),
                )
            return True
        if status in (STATUS_ASSIGNED, STATUS_RUNNING):
            with self._connect() as conn:
                conn.execute(
                    "UPDATE orders SET cancel_requested = 1, updated_at = ? "
                    "WHERE order_id = ?",
                    (_now(), order_id),
                )
            return True
        return False

    def is_cancel_requested(self, order_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def mark_cancelled(self, order_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE orders SET status = ?, finished_at = ?, updated_at = ? "
                "WHERE order_id = ? AND cancel_requested = 1",
                (STATUS_CANCELLED, _now(), _now(), order_id),
            )
        return cursor.rowcount > 0

    # ── 心跳（Phase 2 失联回收的依据） ─────────────────────────

    def heartbeat(self, order_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET heartbeat_at = ?, updated_at = ? WHERE order_id = ?",
                (_now(), _now(), order_id),
            )

    def find_stale_running(self, timeout_minutes: int = 10) -> List[Dict[str, Any]]:
        """心跳超时的执行中订单（Phase 2：worker 崩溃后重回队列）。"""
        threshold = (datetime.now() - timedelta(minutes=timeout_minutes)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE status IN (?, ?) AND "
                "(heartbeat_at IS NULL OR heartbeat_at < ?)",
                (STATUS_ASSIGNED, STATUS_RUNNING, threshold),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]
