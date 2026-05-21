"""Jira → System Locator import orchestration."""
from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import db
from .description_parser import parse_ticket_for_system
from .lab_request_ingestion import LabRequestIngestionClient, LabRequestRecord

_REQUIRED_LOCATION_FIELDS = ("location_number", "location_name")
_IDENTIFIER_LABELS = (
    ("CID", "cid"),
    ("Login", "login"),
    ("IMEI", "imei"),
    ("MAC", "mac"),
    ("Camera Serial", "camera_serial"),
    ("Board Serial", "board_serial"),
)
_DEFAULT_STATUS = "Active"
_FALLBACK_DESCRIPTION = """Imported from Jira Lab Request {issue_key}."""


@dataclass(frozen=True)
class IdentifierValue:
    label: str
    value: str
    source: str = "jira"


@dataclass(frozen=True)
class IdentifierConflict:
    label: str
    value: str
    conflicting_system_id: int
    conflicting_system_name: str


@dataclass(frozen=True)
class ImportCandidate:
    issue_key: str
    system_name: str
    notes: str
    jira_status: str
    mapped_status: str
    location: Dict[str, Optional[str]]
    location_complete: bool
    missing_location_fields: List[str]
    identifiers: List[IdentifierValue]
    identifier_conflicts: List[IdentifierConflict]
    applied_identifiers: List[IdentifierValue]
    existing_system: Optional[Dict[str, Any]]
    action: str  # "create" or "update"


@dataclass
class ImportResult:
    candidates: List[ImportCandidate]
    created: int = 0
    updated: int = 0
    skipped: int = 0


class JiraImportError(RuntimeError):
    """Base exception for Jira import failures."""


class JiraPermissionError(JiraImportError):
    """Raised when the MCP transport reports a permission failure."""


class JiraFieldMapping:
    """Maps logical field names to Jira field identifiers."""

    _DEFAULT_CANDIDATES: Mapping[str, Tuple[str, ...]] = {
        "cid": ("cid", "CID", "customfield_cid"),
        "login": ("login", "Login", "customfield_login"),
        "imei": ("imei", "IMEI", "customfield_imei"),
        "mac": ("mac", "MAC", "customfield_mac"),
        "camera_serial": (
            "camera_serial",
            "Camera Serial",
            "customfield_cameraSerial",
            "customfield_camera_serial",
        ),
        "board_serial": (
            "board_serial",
            "Board Serial",
            "customfield_boardSerial",
            "customfield_board_serial",
        ),
        "location_number": ("location_number", "Location Number", "customfield_location_number"),
        "location_name": ("location_name", "Location Name", "customfield_location_name"),
    }

    def __init__(self, field_map: Mapping[str, Sequence[str]]) -> None:
        self._field_map: Dict[str, Tuple[str, ...]] = {
            key: tuple(values) for key, values in field_map.items()
        }

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "JiraFieldMapping":
        raw_map: Dict[str, Tuple[str, ...]] = {}
        configured = config.get("SYSTEM_LOCATOR_JIRA_FIELD_MAP", {})
        if isinstance(configured, Mapping):
            for name, value in configured.items():
                tokens = _split_field_tokens(value)
                if tokens:
                    raw_map[name.lower()] = tokens

        for logical in cls._DEFAULT_CANDIDATES.keys():
            env_key = f"SYSTEM_LOCATOR_JIRA_FIELD_{logical.upper()}"
            override = config.get(env_key) or os.environ.get(env_key)
            if override:
                raw_map[logical] = _split_field_tokens(override)
            elif logical not in raw_map:
                raw_map[logical] = cls._DEFAULT_CANDIDATES[logical]
        return cls(raw_map)

    def pick(self, issue_fields: Mapping[str, Any], logical_name: str) -> Optional[Any]:
        for key in self._field_map.get(logical_name, ()):  # type: ignore[arg-type]
            value = _extract_field(issue_fields, key)
            if _is_meaningful(value):
                return value
        return None


class JiraImportService:
    """Coordinates loading Lab Request data and translating it into systems."""

    def __init__(
        self,
        client: LabRequestIngestionClient,
        field_mapping: JiraFieldMapping,
        *,
        status_mapping: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._client = client
        self._field_mapping = field_mapping
        self._status_mapping = {
            (key or "").strip().lower(): value
            for key, value in (status_mapping or {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }

    def build_preview(
        self,
        *,
        project_keys: Optional[Iterable[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        issue_keys: Optional[Iterable[str]] = None,
    ) -> List[ImportCandidate]:
        issues = self._fetch_issues(
            project_keys=project_keys,
            start_date=start_date,
            end_date=end_date,
            issue_keys=issue_keys,
        )
        return [self._issue_to_candidate(issue) for issue in issues]

    def apply(
        self,
        *,
        project_keys: Optional[Iterable[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        issue_keys: Optional[Iterable[str]] = None,
    ) -> ImportResult:
        candidates = self.build_preview(
            project_keys=project_keys,
            start_date=start_date,
            end_date=end_date,
            issue_keys=issue_keys,
        )
        result = ImportResult(candidates=candidates)
        for candidate in candidates:
            payload = self._build_payload(candidate)
            identifier_pairs = [(item.label, item.value) for item in candidate.applied_identifiers]
            if candidate.existing_system:
                db.update_system(candidate.existing_system["id"], payload, identifier_pairs)
                result.updated += 1
            else:
                db.create_system(payload, identifier_pairs)
                result.created += 1
        return result

    def _fetch_issues(
        self,
        *,
        project_keys: Optional[Iterable[str]],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        issue_keys: Optional[Iterable[str]],
    ) -> List[LabRequestRecord]:
        try:
            return self._client.fetch_lab_requests(
                project_keys=project_keys,
                start_date=start_date,
                end_date=end_date,
                issue_keys=issue_keys,
            )
        except PermissionError as exc:  # pragma: no cover - depends on transport implementation
            raise JiraPermissionError(str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive catch around MCP client
            raise JiraImportError(f"Failed to fetch Lab Request issues: {exc}") from exc

    def _issue_to_candidate(self, issue: LabRequestRecord) -> ImportCandidate:
        # Parse description for auto-population
        parsed_data = None
        if issue.description:
            try:
                # parse_ticket_for_system expects Jira issue format
                # Convert LabRequestRecord to that format
                jira_issue = {
                    "key": issue.key,
                    "fields": {
                        "summary": issue.summary,
                        "description": issue.description,
                        **issue.fields
                    }
                }
                parsed_data = parse_ticket_for_system(jira_issue)
            except Exception:
                # If parsing fails, continue without parsed data
                # Silent fallback - user will still see original fields from Jira custom fields
                parsed_data = None
        
        # System name: use parsed name if available, else summary, else default
        system_name = (parsed_data.get("system_name") if parsed_data else None) \
                      or issue.summary \
                      or f"Lab Request {issue.key}"
        
        # Description/Notes: use parsed notes if available, else normalized description
        description = _normalize_description(issue.description) or _FALLBACK_DESCRIPTION.format(issue_key=issue.key)
        if parsed_data and parsed_data.get("notes"):
            description = parsed_data["notes"]
        
        # Location: use parsed data primarily (converted from location_number/location_name)
        location_fields = {
            "location_number": (parsed_data.get("location_number") if parsed_data else None)
                             or _to_string(self._field_mapping.pick(issue.fields, "location_number")),
            "location_name": (parsed_data.get("location_name") if parsed_data else None)
                           or _to_string(self._field_mapping.pick(issue.fields, "location_name")),
        }
        missing_fields = [key for key in _REQUIRED_LOCATION_FIELDS if not location_fields.get(key)]

        # Identifiers: collect from custom fields first, then add parsed ones
        identifiers = self._collect_identifiers(issue, parsed_data)
        existing_system = db.get_system_by_jira_key(issue.key)
        if not existing_system:
            existing_system = self._match_by_identifiers(identifiers)

        conflicts = self._identify_conflicts(identifiers, existing_system)
        applied_identifiers = self._filter_identifiers(identifiers, conflicts, existing_system, issue.key)

        mapped_status = self._map_status(issue.status)
        if missing_fields:
            mapped_status = "Incomplete"

        action = "update" if existing_system else "create"

        return ImportCandidate(
            issue_key=issue.key,
            system_name=system_name,
            notes=description,
            jira_status=issue.status,
            mapped_status=mapped_status,
            location=location_fields,
            location_complete=not missing_fields,
            missing_location_fields=missing_fields,
            identifiers=identifiers,
            identifier_conflicts=conflicts,
            applied_identifiers=applied_identifiers,
            existing_system=existing_system,
            action=action,
        )

    def _collect_identifiers(self, issue: LabRequestRecord, parsed_data: Optional[Dict[str, Any]] = None) -> List[IdentifierValue]:
        identifiers: List[IdentifierValue] = [IdentifierValue(label="Jira", value=issue.key)]
        seen: set = {issue.key.lower()}
        
        # Collect from custom fields first
        for label, logical in _IDENTIFIER_LABELS:
            raw_value = self._field_mapping.pick(issue.fields, logical)
            for normalized in _expand_identifier_values(raw_value):
                lowered = normalized.lower()
                if lowered in seen:
                    continue
                identifiers.append(IdentifierValue(label=label, value=normalized))
                seen.add(lowered)
        
        # Add identifiers from parsed description if available
        if parsed_data:
            for parsed_id in parsed_data.get("identifiers", []):
                lowered = parsed_id["value"].lower()
                if lowered in seen:
                    continue
                identifiers.append(IdentifierValue(
                    label=parsed_id["label"],
                    value=parsed_id["value"],
                    source="description_parser"
                ))
                seen.add(lowered)
        return identifiers

    def _match_by_identifiers(self, identifiers: Sequence[IdentifierValue]) -> Optional[Dict[str, Any]]:
        for identifier in identifiers:
            if identifier.label == "Jira":
                continue
            system = db.find_system_by_identifier(identifier.value)
            if system:
                return system
        return None

    def _identify_conflicts(
        self,
        identifiers: Sequence[IdentifierValue],
        existing_system: Optional[Dict[str, Any]],
    ) -> List[IdentifierConflict]:
        values = [item.value for item in identifiers if item.label != "Jira"]
        conflicts: List[IdentifierConflict] = []
        for entry in db.find_identifier_conflicts(values, exclude_system_id=(existing_system or {}).get("id")):
            conflicts.append(
                IdentifierConflict(
                    label=entry.get("label", "Identifier"),
                    value=entry.get("value", ""),
                    conflicting_system_id=entry.get("system_id"),
                    conflicting_system_name=entry.get("system_name", "Unknown"),
                )
            )
        return conflicts

    def _filter_identifiers(
        self,
        identifiers: Sequence[IdentifierValue],
        conflicts: Sequence[IdentifierConflict],
        existing_system: Optional[Dict[str, Any]],
        issue_key: str,
    ) -> List[IdentifierValue]:
        conflict_values = {conflict.value.lower() for conflict in conflicts}
        applied: List[IdentifierValue] = []
        existing_pairs = set()
        if existing_system:
            for identifier in existing_system.get("identifiers", []):
                normalized_label = identifier["label"].strip().lower()
                normalized_value = identifier["value"].strip().lower()
                if normalized_label == "jira" and normalized_value != issue_key.strip().lower():
                    continue
                pair = (normalized_label, normalized_value)
                existing_pairs.add(pair)
                applied.append(IdentifierValue(label=identifier["label"], value=identifier["value"], source="existing"))

        for identifier in identifiers:
            key = (identifier.label.strip().lower(), identifier.value.strip().lower())
            if key in existing_pairs:
                continue
            if identifier.label != "Jira" and identifier.value.strip().lower() in conflict_values:
                continue
            applied.append(identifier)
            existing_pairs.add(key)
        return applied

    def _map_status(self, jira_status: str) -> str:
        lowered = (jira_status or "").strip().lower()
        if lowered in self._status_mapping:
            return self._status_mapping[lowered]
        if not lowered:
            return _DEFAULT_STATUS
        if any(token in lowered for token in ("maint", "service", "hold", "progress")):
            return "Maintenance"
        if any(token in lowered for token in ("block", "fail", "break", "repair")):
            return "Broken"
        if any(token in lowered for token in ("decom", "retire", "archive")):
            return "Decommissioned"
        return _DEFAULT_STATUS

    def _build_payload(self, candidate: ImportCandidate) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": candidate.system_name,
            "location_number": candidate.location.get("location_number"),
            "location_name": candidate.location.get("location_name"),
            "status": candidate.mapped_status,
            "notes": candidate.notes,
            "jira_issue_key": candidate.issue_key,
        }
        tickets = {candidate.issue_key}
        if candidate.existing_system:
            for ticket in candidate.existing_system.get("jira_tickets", []):
                tickets.add(ticket)
        payload["jira_tickets"] = "\n".join(sorted(tickets)) or None
        return payload


def _split_field_tokens(value: Any) -> Tuple[str, ...]:
    if value is None:
        return tuple()
    if isinstance(value, (list, tuple, set)):
        tokens = [str(item).strip() for item in value if str(item).strip()]
        return tuple(tokens)
    text = str(value)
    return tuple(token.strip() for token in text.replace(";", ",").split(",") if token.strip())


def _extract_field(fields: Mapping[str, Any], dotted_key: str) -> Any:
    current: Any = fields
    for chunk in dotted_key.split("."):
        if isinstance(current, Mapping):
            current = current.get(chunk)
        else:
            return None
    return current


def _is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(_is_meaningful(item) for item in value)
    if isinstance(value, Mapping):
        return any(_is_meaningful(item) for item in value.values())
    return True


def _expand_identifier_values(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = []
        for entry in value:
            items.extend(_expand_identifier_values(entry))
        return items
    if isinstance(value, Mapping):
        for key in ("value", "name", "displayName", "display_value"):
            if key in value and _is_meaningful(value[key]):
                return _expand_identifier_values(value[key])
        return [_to_string(value)] if _is_meaningful(value) else []
    text = _to_string(value)
    if "\n" in text:
        return [segment.strip() for segment in text.splitlines() if segment.strip()]
    if ";" in text:
        return [segment.strip() for segment in text.split(";") if segment.strip()]
    return [text] if text else []


def _to_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("text", "value", "name", "displayName", "display_value"):
            if key in value and value[key]:
                return _to_string(value[key])
        return str(value)
    if isinstance(value, (list, tuple, set)):
        flattened = [_to_string(item) for item in value if _to_string(item)]
        return ", ".join(flattened)
    return str(value).strip()


def _normalize_description(raw: Any) -> str:
    text = _to_string(raw)
    if not text:
        return ""
    return textwrap.dedent(text).strip()
