"""Agent-run sync that pushes 3D print requests to Jira via Atlassian MCP."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Dict, Iterable

from tools.print_requests import db


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync 3D print requests to Jira")
    parser.add_argument("--limit", type=int, help="Maximum number of requests to sync this run")
    args = parser.parse_args()

    client = _build_jira_client()
    requests = db.pending_requests()
    if args.limit is not None:
        requests = requests[: args.limit]

    if not requests:
        print("No pending requests to sync.")
        return

    for record in requests:
        summary = _build_summary(record)
        description = _build_description(record)
        issue = client.create_lab_request(summary=summary, description=description)
        issue_key = _extract_issue_key(issue)
        if not issue_key:
            raise RuntimeError("Failed to obtain Jira issue key from response")

        file_path = record.get("uploaded_file_path")
        if file_path:
            _attach_file(client, issue_key, file_path)

        image_path = record.get("uploaded_image_path")
        if image_path:
            _attach_file(client, issue_key, image_path)

        db.mark_synced(record["id"], issue_key)
        print(f"Created {issue_key} for request {record['id']}")


def _build_summary(record: Dict[str, object]) -> str:
    base = str(record.get("description") or record.get("request_type") or "3D Print Request")
    if base:
        first_line = base.splitlines()[0].strip()
    else:
        first_line = "3D Print Request"
    if len(first_line) > 80:
        first_line = first_line[:77] + "..."
    return f"3D Print Request: {first_line}" if not first_line.lower().startswith("3d print request") else first_line


def _build_description(record: Dict[str, object]) -> str:
    sections = [
        "3D Print Request submitted via Lab Tech Portal",
        "",
        f"Requester: {record.get('requester')}",
        f"Team: {record.get('team') or 'Not specified'}",
        f"Request type: {record.get('request_type')}",
        f"Submitted at: {record.get('created_at')}",
        "",
    ]
    description = record.get("description") or "No additional notes were provided."
    sections.append(description)
    file_path = record.get("uploaded_file_path")
    if file_path:
        sections.extend([
            "",
            f"Attachment queued from portal: {file_path}",
        ])
    image_path = record.get("uploaded_image_path")
    if image_path:
        sections.extend([
            "",
            f"Design image queued from portal: {image_path}",
        ])
    return "\n".join(sections)


def _attach_file(client, issue_key: str, file_path: str) -> None:
    if not os.path.exists(file_path):
        print(f"Warning: file {file_path} missing; skipping attachment.", file=sys.stderr)
        return
    try:
        client.add_attachment(issue_key, file_path)
    except AttributeError:
        # Some SDKs expose attachment uploads as upload_attachments(issue_key, paths=[...]).
        try:
            client.upload_attachments(issue_key, [file_path])
        except Exception as exc:  # pragma: no cover - defensive path
            print(f"Failed to attach file for {issue_key}: {exc}", file=sys.stderr)
    except Exception as exc:  # pragma: no cover - defensive path
        print(f"Failed to attach file for {issue_key}: {exc}", file=sys.stderr)


def _extract_issue_key(issue: object) -> str:
    if isinstance(issue, dict):
        key = issue.get("key") or issue.get("issueKey")
        if key:
            return str(key)
    if hasattr(issue, "key"):
        return str(issue.key)
    if hasattr(issue, "issueKey"):
        return str(issue.issueKey)
    return ""


def _build_jira_client() -> object:
    try:
        from atlassian_mcp import JiraClient  # type: ignore
    except ImportError as exc:
        raise SystemExit("Install the atlassian-mcp package before running this sync") from exc

    base_url = os.environ.get("ATLASSIAN_MCP_BASE_URL")
    workspace = os.environ.get("ATLASSIAN_MCP_WORKSPACE")
    token = os.environ.get("ATLASSIAN_MCP_TOKEN")
    if not base_url or not workspace or not token:
        raise SystemExit("Set ATLASSIAN_MCP_BASE_URL, ATLASSIAN_MCP_WORKSPACE, and ATLASSIAN_MCP_TOKEN")

    return JiraClient(base_url=base_url, workspace=workspace, token=token)


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
