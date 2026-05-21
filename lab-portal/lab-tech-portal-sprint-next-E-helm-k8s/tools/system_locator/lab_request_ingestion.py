"""Lab Request data ingestion utilities.

This module keeps runtime code decoupled from the Atlassian MCP SDK by
consuming pre-fetched Lab Request payloads produced by an out-of-band agent
run or other ingestion mechanism.  Runtime callers only deal with structured
records and optional caching, independent of how the raw data was collected."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple, Union

_CACHE_DEFAULT_TTL_SECONDS = 300


class LabRequestLoader(Protocol):
    """Protocol describing the data ingestion hook."""

    def load_lab_requests(
        self,
        *,
        project_keys: Optional[Iterable[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        issue_keys: Optional[Iterable[str]] = None,
        fields: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return Lab Request issue dictionaries."""


@dataclass(frozen=True)
class LabRequestRecord:
    key: str
    summary: str
    description: str
    status: str
    fields: Dict[str, Any]


class LabRequestIngestionClient:
    """Fetch Lab Request issues via a loader with optional caching."""

    def __init__(
        self,
        loader: Optional[LabRequestLoader] = None,
        *,
        cache_ttl_seconds: int = _CACHE_DEFAULT_TTL_SECONDS,
    ) -> None:
        self._loader = loader or self._load_default_loader()
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[Tuple[Any, ...], Tuple[float, List[LabRequestRecord]]] = {}

    def fetch_lab_requests(
        self,
        *,
        project_keys: Optional[Iterable[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        issue_keys: Optional[Iterable[str]] = None,
        fields: Optional[Iterable[str]] = None,
        force_refresh: bool = False,
    ) -> List[LabRequestRecord]:
        cache_key = self._build_cache_key(project_keys, start_date, end_date, issue_keys, fields)
        now = time.time()
        cached = self._cache.get(cache_key)
        if not force_refresh and cached and cached[0] > now:
            return cached[1]

        raw_items = self._loader.load_lab_requests(
            project_keys=project_keys,
            start_date=start_date,
            end_date=end_date,
            issue_keys=issue_keys,
            fields=fields,
        )
        filtered_items = self._apply_filters(
            raw_items,
            project_keys=project_keys,
            start_date=start_date,
            end_date=end_date,
            issue_keys=issue_keys,
        )
        records = [
            LabRequestRecord(
                key=item.get("key", "").strip(),
                summary=item.get("summary", "").strip(),
                description=(item.get("description") or ""),
                status=item.get("status", "").strip(),
                fields=item.get("fields") or {},
            )
            for item in filtered_items
            if item.get("key")
        ]
        ttl_expires_at = now + max(self._cache_ttl_seconds, 1)
        self._cache[cache_key] = (ttl_expires_at, records)
        return records

    def clear_cache(self) -> None:
        self._cache.clear()

    @staticmethod
    def _build_cache_key(
        project_keys: Optional[Iterable[str]],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        issue_keys: Optional[Iterable[str]],
        fields: Optional[Iterable[str]],
    ) -> Tuple[Any, ...]:
        def _norm(iterable: Optional[Iterable[str]]) -> Tuple[str, ...]:
            if not iterable:
                return tuple()
            return tuple(sorted(str(value).strip() for value in iterable if str(value).strip()))

        return (
            _norm(project_keys),
            start_date.isoformat() if start_date else None,
            end_date.isoformat() if end_date else None,
            _norm(issue_keys),
            _norm(fields),
        )

    def _apply_filters(
        self,
        items: Iterable[Mapping[str, Any]],
        *,
        project_keys: Optional[Iterable[str]],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        issue_keys: Optional[Iterable[str]],
    ) -> List[Dict[str, Any]]:
        project_filter = {key.strip().lower() for key in project_keys or [] if str(key).strip()}
        issue_filter = {key.strip() for key in issue_keys or [] if str(key).strip()}
        start_ts = start_date.timestamp() if start_date else None
        end_ts = end_date.timestamp() if end_date else None

        filtered: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            if not key:
                continue
            project = key.split("-")[0].lower() if "-" in key else ""
            if project_filter and project not in project_filter:
                continue
            if issue_filter and key not in issue_filter:
                continue
            created_at = _coerce_datetime(item.get("created"))
            if start_ts and (created_at or datetime.min).timestamp() < start_ts:
                continue
            if end_ts and (created_at or datetime.min).timestamp() > end_ts:
                continue
            filtered.append(item)
        return filtered

    @staticmethod
    def _load_default_loader() -> LabRequestLoader:
        data_path = os.environ.get("SYSTEM_LOCATOR_LAB_REQUESTS_FILE")
        if not data_path:
            raise RuntimeError(
                "Set SYSTEM_LOCATOR_LAB_REQUESTS_FILE or provide a custom LabRequestLoader instance."
            )
        return _JSONFileLoader(Path(data_path))


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class _JSONFileLoader:
    """Loader that reads Lab Request issues from a JSON file produced by an agent."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    def load_lab_requests(
        self,
        *,
        project_keys: Optional[Iterable[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        issue_keys: Optional[Iterable[str]] = None,
        fields: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not self._file_path.exists():
            return []
        with self._file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            issues = payload.get("issues")
            if isinstance(issues, list):
                return [item for item in issues if isinstance(item, dict)]
        return []


def create_json_loader(path: Union[str, os.PathLike[str]]) -> LabRequestLoader:
    """Helper for wiring a JSON file loader from application configuration."""

    return _JSONFileLoader(Path(path))
