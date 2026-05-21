"""Fetch Lab Request issues via Atlassian MCP and write them to JSON.

This script is meant for agent-run execution outside the Flask runtime. It
collects Lab Request issues and persists them to a JSON file that the
System Locator can ingest with the lab_request_ingestion module."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Lab Request issues to JSON")
    parser.add_argument("--output", required=True, help="Destination JSON file path")
    parser.add_argument("--project", action="append", dest="projects", help="Project key to query")
    parser.add_argument("--issue", action="append", dest="issues", help="Specific issue key to include")
    parser.add_argument("--start", dest="start", help="ISO8601 lower bound for created date")
    parser.add_argument("--end", dest="end", help="ISO8601 upper bound for created date")
    parser.add_argument("--fields", dest="fields", nargs="*", help="Additional Jira fields to request")
    args = parser.parse_args()

    client = _build_jira_client()
    params = {
        "project_keys": _clean_iterable(args.projects),
        "issue_keys": _clean_iterable(args.issues),
        "start_date": _parse_datetime(args.start),
        "end_date": _parse_datetime(args.end),
        "fields": _clean_iterable(args.fields),
    }
    issues = client.search_lab_requests(
        project_keys=params["project_keys"],
        issue_keys=params["issue_keys"],
        start_date=params["start_date"],
        end_date=params["end_date"],
        fields=params["fields"],
    )

    payload = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "issues": issues,
        "query": {key: _serialize_for_json(value) for key, value in params.items()},
    }

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _build_jira_client():
    try:
        from atlassian_mcp import JiraClient  # type: ignore
    except ImportError as exc:
        raise SystemExit("Install the atlassian-mcp package before running this script") from exc

    base_url = os.environ.get("ATLASSIAN_MCP_BASE_URL")
    workspace = os.environ.get("ATLASSIAN_MCP_WORKSPACE")
    token = os.environ.get("ATLASSIAN_MCP_TOKEN")
    if not base_url or not workspace or not token:
        raise SystemExit(
            "Set ATLASSIAN_MCP_BASE_URL, ATLASSIAN_MCP_WORKSPACE, and ATLASSIAN_MCP_TOKEN environment variables"
        )
    return JiraClient(base_url=base_url, workspace=workspace, token=token)


def _clean_iterable(values: Optional[Iterable[str]]) -> Optional[List[str]]:
    if not values:
        return None
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return cleaned or None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"Invalid datetime value: {value}") from exc


def _serialize_for_json(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return value
    return value


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
