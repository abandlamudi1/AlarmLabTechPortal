from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from services.audit_log import log_event as _audit
from services.jira_service import JiraAuthError, JiraService, JiraServiceError
from services.rbac import requires_role
from . import db
from tasks.system_locator_tasks import sync_jira_import as _sync_jira_import_task
from .jira_import_service import (
    ImportCandidate,
    ImportResult,
    JiraFieldMapping,
    JiraImportError,
    JiraImportService,
    JiraPermissionError,
)
from .jira_service_loader import JiraServiceLoader
from .lab_request_ingestion import LabRequestIngestionClient, LabRequestLoader, create_json_loader

systems_bp = Blueprint(
    "systems",
    __name__,
    template_folder="templates",
    static_folder="static",
)

# HQ Location Mapping (Source of Truth)
# All locations are implicitly at Alarm.com HQ
HQ_LOCATION_MAP: Dict[Optional[str], str] = {
    "10-640": "Automation Lab",
    "10-510": "QE Lab",
    "10-630": "Product Testing Lab",
    "10-070": "Hardware Test Framework Lab",
    "11-050": "DE Lab",
    "9-070": "International Lab",
    "7-370": "Commercial Team Lab",
    "6-430": "Mobile/CX Team Lab",
    "5-030": "Video Team Lab",
    None: "Panels Team Lab",  # Special case: Panels Team Lab has no location number
}

# Reverse mapping: Location Name -> Location Number
HQ_LOCATION_NAME_TO_NUMBER: Dict[str, Optional[str]] = {
    name: number for number, name in HQ_LOCATION_MAP.items()
}

STATUS_CHOICES: List[str] = [
    "Active",
    "Broken",
    "Maintenance",
    "Incomplete",
    "Decommissioned",
]

IDENTIFIER_TYPE_CHOICES: List[str] = [
    "CID",
    "Login",
    "IMEI",
    "MAC",
    "Asset Tag",
    "Linked Jira Ticket",
    "Other",
]

LAB_LOCATION_CHOICES: List[str] = [
    "Automation Lab",
    "QE Lab",
    "Product Testing Lab",
    "Hardware Test Framework Lab",
    "DE Lab",
    "International Lab",
    "Commercial Team Lab",
    "Mobile/CX Team Lab",
    "Video Team Lab",
    "Panels Team Lab",
]


def _get_location_name_from_number(location_number: Optional[str]) -> Optional[str]:
    """Get location name from location number using HQ location map."""
    if location_number is None:
        return HQ_LOCATION_MAP.get(None)
    normalized = (location_number or "").strip()
    return HQ_LOCATION_MAP.get(normalized) if normalized else HQ_LOCATION_MAP.get(None)


def _get_location_number_from_name(location_name: str) -> Optional[str]:
    """Get location number from location name using HQ location map."""
    normalized = (location_name or "").strip()
    return HQ_LOCATION_NAME_TO_NUMBER.get(normalized)


def _auto_populate_location_fields(form_data: Dict[str, str]) -> Dict[str, str]:
    """
    Auto-populate missing location field based on the provided one using HQ location map.
    Modifies and returns the form_data dictionary.
    """
    location_number = (form_data.get("location_number") or "").strip() or None
    location_name = (form_data.get("location_name") or "").strip() or None
    
    # If location number provided but name missing, auto-fill name
    if location_number and not location_name:
        auto_name = _get_location_name_from_number(location_number)
        if auto_name:
            form_data["location_name"] = auto_name
    
    # If location name provided but number missing, auto-fill number
    elif location_name and not location_number:
        auto_number = _get_location_number_from_name(location_name)
        if auto_number is not None:  # Could be empty string for Panels Team Lab
            form_data["location_number"] = auto_number if auto_number else ""
    
    return form_data


def _validate_location_pair(location_number: Optional[str], location_name: Optional[str]) -> Optional[str]:
    """
    Validate that location number and name match the HQ location map.
    Returns error message if invalid, None if valid.
    """
    # Normalize inputs
    norm_number = (location_number or "").strip() if location_number else None
    norm_name = (location_name or "").strip() if location_name else None
    
    # Both empty is an error (handled by required field validation)
    if not norm_number and not norm_name:
        return None
    
    # Special case: Panels Team Lab with no number
    if norm_name == "Panels Team Lab" and not norm_number:
        return None
    
    # If number provided, check if it's valid and name matches
    if norm_number:
        expected_name = HQ_LOCATION_MAP.get(norm_number)
        if expected_name is None:
            valid_numbers = [k for k in HQ_LOCATION_MAP.keys() if k is not None]
            return f"Invalid Location Number. Must be one of: {', '.join(sorted(valid_numbers))}, or leave empty for Panels Team Lab."
        if norm_name and norm_name != expected_name:
            return f"Location mismatch: {norm_number} should be '{expected_name}', not '{norm_name}'."
    
    # If name provided, check if it's valid and number matches
    if norm_name:
        expected_number = HQ_LOCATION_NAME_TO_NUMBER.get(norm_name)
        if expected_number is None and norm_name != "Panels Team Lab":
            valid_names = list(HQ_LOCATION_MAP.values())
            return f"Invalid Location Name. Must be one of: {', '.join(sorted(valid_names))}."
        if norm_number and norm_number != expected_number:
            if expected_number is None:
                return f"Panels Team Lab should not have a Location Number."
            else:
                return f"Location mismatch: '{norm_name}' should be {expected_number}, not {norm_number}."
    
    return None


def _collect_identifier_pairs(form) -> Iterable[Tuple[str, str]]:
    labels = form.getlist("identifier_label")
    values = form.getlist("identifier_value")
    return [(label, value) for label, value in zip(labels, values)]


def _summarize_location(system: Dict[str, object]) -> str:
    """Create a friendly location summary from location_number and location_name."""
    location_number = (system.get("location_number") or "").strip()
    location_name = (system.get("location_name") or "").strip()
    
    parts: List[str] = []
    if location_number:
        parts.append(location_number)
    if location_name:
        parts.append(location_name)
    
    return " · ".join(parts) if parts else "Location not specified"


def _build_form_payload(defaults: Dict[str, object]) -> Dict[str, object]:
    jira_list = defaults.get("jira_tickets", [])
    return {
        "name": defaults.get("name", ""),
        "location_number": defaults.get("location_number", ""),
        "location_name": defaults.get("location_name", ""),
        "status": defaults.get("status", STATUS_CHOICES[0]),
        "notes": defaults.get("notes", ""),
        "jira_tickets": "\n".join(jira_list) if isinstance(jira_list, list) else (jira_list or ""),
        "identifiers": defaults.get("identifiers", []),
        "jira_issue_key": defaults.get("jira_issue_key", ""),
    }


def _validate_form(form_data: Dict[str, str], identifiers: List[Tuple[str, str]], current_system_id: Optional[int] = None) -> Dict[str, str]:
    errors: Dict[str, str] = {}
    name = (form_data.get("name") or "").strip()
    location_number = (form_data.get("location_number") or "").strip() or None
    location_name = (form_data.get("location_name") or "").strip() or None
    status = (form_data.get("status") or "").strip()

    if not name:
        errors["name"] = "System Profile name is required."
    
    # Validate location fields
    if not location_number and not location_name:
        errors["location"] = "Either Location Number or Location Name is required."
    else:
        # Validate that the location number and name match the HQ location map
        location_error = _validate_location_pair(location_number, location_name)
        if location_error:
            errors["location"] = location_error
    
    if not status:
        errors["status"] = "Choose a status to show system profile availability."

    normalized_values: Dict[str, str] = {}
    duplicate_values: List[str] = []
    stripped_values: List[str] = []
    for _, raw_value in identifiers:
        normalized = (raw_value or "").strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        stripped_values.append(normalized)
        if lowered in normalized_values and normalized not in duplicate_values:
            duplicate_values.append(normalized)
        else:
            normalized_values[lowered] = normalized

    if duplicate_values:
        formatted = ", ".join(sorted(set(duplicate_values)))
        errors["identifiers"] = f"Duplicate identifier value(s) on form: {formatted}."

    conflicts = db.find_identifier_conflicts(stripped_values, exclude_system_id=current_system_id)
    if conflicts:
        conflict_descriptions = []
        for conflict in conflicts:
            conflict_descriptions.append(f"{conflict['value']} (System Profile: {conflict['system_name']})")
        message = "Already in use: " + ", ".join(conflict_descriptions)
        if "identifiers" in errors:
            errors["identifiers"] += f" {message}"
        else:
            errors["identifiers"] = message

    return errors


def _preload_identifiers(form) -> List[Dict[str, str]]:
    labels = form.getlist("identifier_label")
    values = form.getlist("identifier_value")
    preloaded: List[Dict[str, str]] = []
    for label, value in zip(labels, values):
        if label or value:
            preloaded.append({"label": label, "value": value})
    return preloaded


@systems_bp.route("/", methods=["GET"])
def dashboard():
    identifier_type = request.args.get("identifier_type", "").strip()
    identifier_value = request.args.get("identifier_value", "").strip()
    location_name = request.args.get("location_name", "").strip()
    message = request.args.get("message")
    status = request.args.get("status")

    identifier_ready = bool(identifier_type and identifier_value)
    location_ready = bool(location_name)
    identifier_incomplete = bool(identifier_type) ^ bool(identifier_value)

    systems: List[Dict[str, object]] = []
    if identifier_ready:
        if identifier_type == "Linked Jira Ticket":
            systems = db.search_systems_by_jira_ticket(identifier_value)
        else:
            systems = db.search_systems_by_identifier(identifier_type, identifier_value)

    if location_ready:
        location_systems = db.list_systems_by_location(location_name)
        if systems:
            location_ids = {system["id"] for system in location_systems}
            systems = [system for system in systems if system["id"] in location_ids]
        else:
            systems = location_systems

    filters_applied = identifier_ready or location_ready

    identifiers_map = db.get_identifiers_map(system["id"] for system in systems)
    results: List[Dict[str, object]] = []
    for system in systems:
        enriched = {
            **system,
            "identifiers": identifiers_map.get(system["id"], []),
        }
        enriched["location_summary"] = _summarize_location(enriched)
        enriched["location_complete"] = all(
            (enriched.get(field) or "").strip() for field in ("location_number", "location_name")
        )
        enriched["missing_location_fields"] = [
            field
            for field in ("location_number", "location_name")
            if not (enriched.get(field) or "").strip()
        ]
        results.append(enriched)

    single_result = results[0] if filters_applied and len(results) == 1 else None

    return render_template(
        "systems_dashboard.html",
        identifier_type=identifier_type,
        identifier_value=identifier_value,
        location_name=location_name,
        identifier_types=IDENTIFIER_TYPE_CHOICES,
        lab_locations=LAB_LOCATION_CHOICES,
        filters_applied=filters_applied,
        identifier_incomplete=identifier_incomplete,
        results=results,
        message=message,
        status=status,
        total=len(results),
        single_result=single_result,
    )


@systems_bp.route("/new", methods=["GET", "POST"])
def create_system():
    if request.method == "POST":
        form_data = request.form.to_dict()
        
        # Auto-populate missing location field before validation
        form_data = _auto_populate_location_fields(form_data)
        
        raw_identifiers = _collect_identifier_pairs(request.form)
        form_identifiers = _preload_identifiers(request.form)
        errors = _validate_form(form_data, raw_identifiers)
        if errors:
            form_defaults = _build_form_payload({**form_data, "identifiers": form_identifiers})
            return render_template(
                "system_form.html",
                form=form_defaults,
                status_choices=STATUS_CHOICES,
                action="create",
                errors=errors,
            ), 400
        system_id = db.create_system(form_data, raw_identifiers)
        actor = (session.get("user_identity") or {}).get("email", "<unknown>")
        _audit(
            actor=actor,
            action="system_locator.create",
            resource_type="system",
            resource_id=system_id,
            detail={"name": form_data.get("name")},
        )
        return redirect(
            url_for(
                "systems.dashboard",
                status="success",
                message="System Profile created successfully.",
            )
        )

    form_defaults = _build_form_payload({})
    return render_template(
        "system_form.html",
        form=form_defaults,
        status_choices=STATUS_CHOICES,
        action="create",
    )


@systems_bp.route("/<int:system_id>/edit", methods=["GET", "POST"])
def edit_system(system_id: int):
    record = db.get_system(system_id)
    if record is None:
        return redirect(
            url_for(
                "systems.dashboard",
                status="error",
                message="System Profile not found.",
            )
        )

    if request.method == "POST":
        form_data = request.form.to_dict()
        
        # Auto-populate missing location field before validation
        form_data = _auto_populate_location_fields(form_data)
        
        raw_identifiers = _collect_identifier_pairs(request.form)
        form_identifiers = _preload_identifiers(request.form)
        errors = _validate_form(form_data, raw_identifiers, current_system_id=system_id)
        if errors:
            form_defaults = _build_form_payload({**form_data, "identifiers": form_identifiers})
            return render_template(
                "system_form.html",
                form=form_defaults,
                status_choices=STATUS_CHOICES,
                action="edit",
                system_id=system_id,
                errors=errors,
            ), 400
        db.update_system(system_id, form_data, raw_identifiers)
        actor = (session.get("user_identity") or {}).get("email", "<unknown>")
        _audit(
            actor=actor,
            action="system_locator.edit",
            resource_type="system",
            resource_id=system_id,
            detail={"name": form_data.get("name")},
        )
        return redirect(
            url_for(
                "systems.dashboard",
                status="success",
                message="System Profile updated successfully.",
            )
        )

    form_defaults = _build_form_payload(record)
    if not form_defaults["identifiers"]:
        form_defaults["identifiers"] = []
    
    # Get status and message from query params (e.g., after incorrect PIN)
    status = request.args.get("status")
    message = request.args.get("message")
    
    return render_template(
        "system_form.html",
        form=form_defaults,
        status_choices=STATUS_CHOICES,
        action="edit",
        system_id=system_id,
        status=status,
        message=message,
    )


@systems_bp.post("/<int:system_id>/delete")
def delete_system(system_id: int):
    db.delete_system(system_id)
    actor = (session.get("user_identity") or {}).get("email", "<unknown>")
    _audit(actor=actor, action="system_locator.decommission",
           resource_type="system", resource_id=system_id, detail={})
    return redirect(
        url_for("systems.dashboard", status="success",
                message="System Profile decommissioned successfully.")
    )


@systems_bp.post("/<int:system_id>/recommission")
def recommission_system(system_id: int):
    db.recommission_system(system_id)
    actor = (session.get("user_identity") or {}).get("email", "<unknown>")
    _audit(actor=actor, action="system_locator.recommission",
           resource_type="system", resource_id=system_id, detail={})
    return redirect(
        url_for("systems.dashboard", status="success",
                message="System Profile recommissioned successfully.")
    )


@systems_bp.post("/<int:system_id>/hard-delete")
@requires_role("admin")
def hard_delete_system(system_id: int):
    """Permanently delete a system profile with PIN protection."""
    pin = request.form.get("pin", "").strip()
    
    # Validate PIN server-side — value read from SYSTEM_LOCATOR_DELETE_PIN env var (Slice A, Issue #6)
    expected_pin = current_app.config.get("SYSTEM_LOCATOR_DELETE_PIN", "")
    if not expected_pin or pin != expected_pin:
        return redirect(
            url_for(
                "systems.edit_system",
                system_id=system_id,
                status="error",
                message="Incorrect PIN. System Profile was not deleted.",
            )
        )
    
    # Get system name for success message before deletion
    system = db.get_system(system_id)
    system_name = system["name"] if system else "System Profile"
    
    # Perform hard delete
    db.hard_delete_system(system_id)
    actor = (session.get("user_identity") or {}).get("email", "<unknown>")
    _audit(
        actor=actor,
        action="system_locator.hard_delete",
        resource_type="system",
        resource_id=system_id,
        detail={"name": system_name},
    )

    return redirect(
        url_for(
            "systems.dashboard",
            status="success",
            message=f"{system_name} has been permanently deleted.",
        )
    )


@systems_bp.route("/jira-import", methods=["GET", "POST"])
def jira_import():
    service = _get_import_service()
    form_defaults = {
        "project_keys": request.form.get("project_keys", "").strip(),
        "start_date": request.form.get("start_date", "").strip(),
        "end_date": request.form.get("end_date", "").strip(),
        "issue_keys": request.form.get("issue_keys", "").strip(),
    }

    preview: List[ImportCandidate] = []
    result: Optional[ImportResult] = None
    errors: List[str] = []
    applied_message: Optional[str] = None
    import_task_id: Optional[str] = None

    if request.method == "POST":
        action = request.form.get("action", "preview")
        filters, parse_errors = _parse_import_filters(request.form)
        errors.extend(parse_errors)

        if not errors:
            try:
                if action == "confirm":
                    selected_keys = _parse_issue_keys(request.form.get("confirmed_issue_keys", ""))
                    if not selected_keys:
                        errors.append("No Jira issues selected for import.")
                    else:
                        # Pre-flight: verify Jira credentials before dispatching the
                        # Celery task (Issue #100).  After the async migration, auth
                        # errors no longer surface in the HTTP response; this cheap
                        # /myself round-trip re-surfaces them synchronously.
                        # Only run when the live JiraService loader is active; skip
                        # when a custom or file-based loader is configured so that
                        # non-Jira deployments are not blocked by credential checks.
                        _uses_live_jira = (
                            current_app.config.get("SYSTEM_LOCATOR_LAB_REQUEST_LOADER") is None
                            and not current_app.config.get("SYSTEM_LOCATOR_LAB_REQUESTS_FILE")
                        )
                        if _uses_live_jira:
                            try:
                                JiraService().validate_connectivity()
                            except JiraAuthError as exc:
                                errors.append(str(exc))
                            except JiraServiceError as exc:
                                errors.append(str(exc))

                        if not errors:
                            # Dispatch the import asynchronously (Wave 2, Issue #15).
                            # Capture the task ID for Wave 3 polling UI (Issue #18).
                            start_dt = filters.get("start_date")
                            end_dt = filters.get("end_date")
                            celery_result = _sync_jira_import_task.delay(
                                project_keys=filters.get("project_keys"),
                                start_date_iso=start_dt.isoformat() if start_dt else None,
                                end_date_iso=end_dt.isoformat() if end_dt else None,
                                issue_keys=selected_keys,
                            )
                            import_task_id = celery_result.id
                            applied_message = "Import in progress... Results will be available shortly."
                            form_defaults["issue_keys"] = "\n".join(selected_keys)
                else:
                    preview = service.build_preview(
                        project_keys=filters.get("project_keys"),
                        start_date=filters.get("start_date"),
                        end_date=filters.get("end_date"),
                        issue_keys=filters.get("issue_keys"),
                    )
            except JiraPermissionError as exc:
                errors.append(str(exc))
            except JiraImportError as exc:
                errors.append(str(exc))

    confirmed_issue_keys = [candidate.issue_key for candidate in preview]

    return render_template(
        "jira_import.html",
        form=form_defaults,
        preview=preview,
        errors=errors,
        applied_message=applied_message,
        import_task_id=import_task_id,
        confirmed_issue_keys="\n".join(confirmed_issue_keys),
    )


def build_import_service(config) -> JiraImportService:
    """Construct a JiraImportService from a Flask config mapping.

    Extracted as a standalone helper so both the route handler
    (_get_import_service, which wraps this with an app-level cache) and
    Celery tasks (which cannot share the request-scoped cache) call the same
    construction logic.  Keeping the two callers in sync is therefore automatic.

    Args:
        config: a dict-like mapping (typically ``current_app.config`` or an
                equivalent passed in by a Celery task).
    """
    cache_ttl = int(config.get("SYSTEM_LOCATOR_JIRA_CACHE_TTL", 300))

    # Check for custom loader first (for testing / overrides)
    loader: Optional[LabRequestLoader] = config.get("SYSTEM_LOCATOR_LAB_REQUEST_LOADER")
    if loader is None:
        # Check for JSON file loader (legacy / testing)
        loader_path = config.get("SYSTEM_LOCATOR_LAB_REQUESTS_FILE")
        if loader_path:
            loader = create_json_loader(loader_path)
        else:
            # Use live Jira API via JiraService (default)
            jira_service = JiraService()
            loader = JiraServiceLoader(jira_service)

    client = LabRequestIngestionClient(loader=loader, cache_ttl_seconds=cache_ttl)
    field_mapping = JiraFieldMapping.from_config(config)
    status_map = config.get("SYSTEM_LOCATOR_JIRA_STATUS_MAP", {})
    return JiraImportService(client, field_mapping, status_mapping=status_map)


def _get_import_service() -> JiraImportService:
    cache_key = "_jira_import_service"
    service: Optional[JiraImportService] = getattr(current_app, cache_key, None)
    if service:
        return service

    service = build_import_service(current_app.config)
    setattr(current_app, cache_key, service)
    return service


def _parse_import_filters(form) -> Tuple[Dict[str, object], List[str]]:
    errors: List[str] = []
    project_keys = _parse_project_keys(form.get("project_keys", ""))
    issue_keys = _parse_issue_keys(form.get("issue_keys", ""))

    start_date_raw = form.get("start_date", "").strip()
    end_date_raw = form.get("end_date", "").strip()
    start_date = _parse_date(start_date_raw, "Start date", errors)
    end_date = _parse_date(end_date_raw, "End date", errors)

    if start_date and end_date and start_date > end_date:
        errors.append("Start date must be on or before end date.")

    filters: Dict[str, object] = {}
    if project_keys:
        filters["project_keys"] = project_keys
    if issue_keys:
        filters["issue_keys"] = issue_keys
    if start_date:
        filters["start_date"] = start_date
    if end_date:
        filters["end_date"] = end_date

    return filters, errors


def _parse_project_keys(raw: str) -> List[str]:
    return _split_to_list(raw)


def _parse_issue_keys(raw: str) -> List[str]:
    return _split_to_list(raw)


def _split_to_list(raw: str) -> List[str]:
    tokens: List[str] = []
    text = (raw or "").replace(";", "\n")
    for chunk in text.splitlines():
        for piece in chunk.split(","):
            token = piece.strip()
            if token:
                tokens.append(token)
    return tokens


def _parse_date(value: str, label: str, errors: List[str]):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        errors.append(f"{label} must be YYYY-MM-DD.")
        return None


def _format_import_result(result: ImportResult) -> str:
    parts: List[str] = []
    if result.created:
        parts.append(f"Created {result.created}")
    if result.updated:
        parts.append(f"Updated {result.updated}")
    if result.skipped:
        parts.append(f"Skipped {result.skipped}")
    return ", ".join(parts) if parts else "No changes applied."
