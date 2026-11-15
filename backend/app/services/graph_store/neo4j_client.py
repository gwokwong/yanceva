"""Shared Neo4j bolt driver for the Graphiti-backed graph store."""

from __future__ import annotations

import atexit
import threading
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, TransientError

from ...config import Config
from ...utils.logger import get_logger

logger = get_logger("mirofish.neo4j")

_driver = None
_driver_lock = threading.Lock()

# Neo4j transient errors that are safe to retry for reads.
_RETRYABLE_STATUS_CODES = {
    "Neo.TransientError.DatabaseUnavailable",
    "Neo.TransientError.General.ReadOnly",
    "Neo.TransientError.Network.CommunicationError",
    "Neo.TransientError.Request.Timeout",
    "Neo.ClientError.Security.Unauthorized",
}


class Neo4jNotConfiguredError(RuntimeError):
    """Raised when NEO4J_* configuration is missing."""


def validate_neo4j_config() -> list[str]:
    """Return human-readable errors for missing Neo4j configuration."""

    errors: list[str] = []
    if not Config.NEO4J_URI:
        errors.append("NEO4J_URI 未配置")
    if not Config.NEO4J_USER:
        errors.append("NEO4J_USER 未配置")
    if Config.NEO4J_PASSWORD is None:
        errors.append("NEO4J_PASSWORD 未配置")
    return errors


def get_driver():
    """Return the process-shared Neo4j driver, creating it lazily."""

    global _driver
    if _driver is not None:
        return _driver

    with _driver_lock:
        if _driver is not None:
            return _driver
        errors = validate_neo4j_config()
        if errors:
            raise Neo4jNotConfiguredError("；".join(errors))
        _driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
            connection_timeout=30,
            max_connection_pool_size=50,
        )
        logger.info("Neo4j driver created for %s", Config.NEO4J_URI)
        return _driver


def close_driver() -> None:
    """Close the shared driver. Intended for tests and shutdown."""

    global _driver
    with _driver_lock:
        if _driver is not None:
            try:
                _driver.close()
            finally:
                _driver = None


atexit.register(close_driver)


def is_retryable_neo4j_error(error: BaseException) -> bool:
    """Return whether a failed Neo4j read is safe and useful to retry."""

    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return True
    if isinstance(error, TransientError):
        return True
    if isinstance(error, Neo4jError):
        code = getattr(error, "code", "") or ""
        if code in _RETRYABLE_STATUS_CODES:
            return True
        # Treat transient-like codes by prefix as retryable.
        return code.startswith("Neo.TransientError")
    return False


def call_read_with_retry(
    operation,
    *,
    operation_name: str,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
):
    """Retry a safe Neo4j read for transient errors (simple exponential backoff)."""

    import time

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt == max_attempts or not is_retryable_neo4j_error(error):
                raise
            delay = initial_delay * (2 ** (attempt - 1))
            logger.warning(
                "Neo4j %s attempt %s/%s failed (%s); retrying in %.1fs",
                operation_name,
                attempt,
                max_attempts,
                type(error).__name__,
                delay,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


def run_query(
    cypher: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    database: Optional[str] = None,
    operation_name: str = "query",
) -> List[Dict[str, Any]]:
    """Run a read query and return records as plain dicts of node/edge data."""

    driver = get_driver()

    def _execute() -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        with driver.session(database=database) as session:
            result = session.run(cypher, params or {})
            for record in result:
                records.append(dict(record))
        return records

    return call_read_with_retry(_execute, operation_name=operation_name)
