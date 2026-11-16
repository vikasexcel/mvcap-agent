"""Loads the dataset for a call: Supabase first, then last-good copies.

Order of preference, so a Supabase outage or a bad edit never stops a call:
  1. a copy loaded within the last CACHE_TTL_SECONDS (no database round trip)
  2. a fresh, validated read from Supabase
  3. the last good dataset from this process, then from disk
  4. the snapshot bundled with the code (data/snapshot.json)
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path

from dataset import TABLES, Dataset

logger = logging.getLogger("store")

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "snapshot.json"
DISK_CACHE_PATH = (
    Path(os.environ.get("MVCAP_CACHE_DIR", tempfile.gettempdir()))
    / "mvcap_last_good.json"
)
CACHE_TTL_SECONDS = 60
FETCH_TIMEOUT_SECONDS = 4
RETRY_AFTER_FAILURE_SECONDS = 30  # skip a known-down database so calls don't wait on it

_lock = asyncio.Lock()
_last_good: tuple[float, Dataset] | None = None
_failed_at: float | None = None


def fetch_tables() -> dict[str, list[dict]]:
    from supabase_client import get_supabase

    client = get_supabase()
    return {name: client.table(name).select("*").execute().data for name in TABLES}


def _read_json(path: Path) -> dict[str, list[dict]]:
    return json.loads(path.read_text())


def _write_cache(tables: dict[str, list[dict]]) -> None:
    try:
        tmp = DISK_CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(tables))
        tmp.replace(DISK_CACHE_PATH)
    except OSError:
        logger.warning("could not write the dataset cache", exc_info=True)


def _validated(tables: dict[str, list[dict]], source: str) -> Dataset:
    ds = Dataset.from_tables(tables)
    errors, warnings = ds.problems()
    for w in warnings:
        logger.warning("dataset (%s): %s", source, w)
    if errors:
        raise ValueError(
            f"dataset from {source} failed validation: " + "; ".join(errors[:10])
        )
    return ds


def load_snapshot() -> Dataset:
    return _validated(_read_json(SNAPSHOT_PATH), "bundled snapshot")


async def load_dataset() -> Dataset:
    global _last_good, _failed_at
    async with _lock:
        now = time.monotonic()
        if _last_good and now - _last_good[0] < CACHE_TTL_SECONDS:
            return _last_good[1]
        recently_failed = (
            _failed_at is not None and now - _failed_at < RETRY_AFTER_FAILURE_SECONDS
        )
        if not recently_failed:
            try:
                tables = await asyncio.wait_for(
                    asyncio.to_thread(fetch_tables), FETCH_TIMEOUT_SECONDS
                )
                ds = _validated(tables, "supabase")
                _last_good, _failed_at = (now, ds), None
                _write_cache(tables)
                return ds
            except Exception:
                _failed_at = now
                logger.exception(
                    "could not load a valid dataset from Supabase; using a fallback copy"
                )
        if _last_good:
            return _last_good[1]
        for source, path in (
            ("disk cache", DISK_CACHE_PATH),
            ("bundled snapshot", SNAPSHOT_PATH),
        ):
            try:
                ds = _validated(_read_json(path), source)
                logger.warning("serving the dataset from the %s", source)
                return ds
            except Exception:
                logger.exception("fallback %s is unusable", source)
        raise RuntimeError(
            "no usable dataset: Supabase, disk cache and bundled snapshot all failed"
        )
