import base64
import logging
import os
import threading
import time
from pathlib import Path
from datetime import date, datetime
from typing import Any, Dict, Iterable, Mapping, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Slice B, Issue #32: top-level import. prometheus_client uses a process-global
# registry that does not require a Flask app context, so this import is safe at
# module load time and does not create a circular-import risk.
from services import metrics as _metrics

logger = logging.getLogger(__name__)


class JiraServiceError(RuntimeError):
    """Base exception for Jira service failures."""


class JiraAuthError(JiraServiceError):
    """Raised when authentication with Jira fails."""


class JiraIssueCreationError(JiraServiceError):
    """Raised when Jira issue creation fails."""


class JiraIssueUpdateError(JiraServiceError):
    """Raised when Jira issue updates fail."""


class JiraIssueTransitionError(JiraServiceError):
    """Raised when Jira issue transitions fail."""


class JiraMetadataError(JiraServiceError):
    """Raised when Jira metadata lookup fails."""


class JiraAttachmentUploadError(JiraServiceError):
    """Raised when uploading an attachment to Jira fails."""


class JiraNotFoundError(JiraServiceError):
    """Raised when a requested Jira resource is not found."""


class JiraRateLimitError(JiraServiceError):
    """Raised when the in-process rate limiter rejects a call (distinct from
    Retry exhaustion on a 429 response from the server)."""


class _TokenBucket:
    """Thread-safe token-bucket rate limiter.

    Args:
        rate: Number of tokens added per second.
        capacity: Maximum token capacity (burst ceiling).
        block_timeout: Maximum seconds to wait for a token before raising
            JiraRateLimitError.  0 = fail immediately when empty.
    """

    def __init__(
        self,
        rate: float = 10.0,
        capacity: float = 10.0,
        block_timeout: float = 5.0,
    ) -> None:
        if rate <= 0:
            raise ValueError(f"rate must be positive, got {rate!r}")
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity!r}")
        if block_timeout < 0:
            raise ValueError(f"block_timeout must be non-negative, got {block_timeout!r}")
        self._rate = rate
        self._capacity = capacity
        self._block_timeout = block_timeout
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self) -> None:
        """Acquire one token, blocking up to *block_timeout* seconds.

        Raises:
            JiraRateLimitError: if no token becomes available within the
                configured timeout.
        """
        deadline = time.monotonic() + self._block_timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            # Release lock during sleep so other threads can refill concurrently.
            remaining = deadline - time.monotonic()
            if remaining <= 0 or wait > remaining:
                raise JiraRateLimitError(
                    "Jira rate limiter: request rejected (token bucket exhausted)"
                )
            time.sleep(min(wait, remaining))


class JiraService:
    """Client for interacting with Jira REST API in a reusable, deterministic way.

    Slice C hardening (Issue #72):
    - HTTPAdapter with urllib3.Retry (3 retries, back-off, 429/5xx retry list)
    - Thread-safe token-bucket rate limiter applied before every HTTP call
    - All custom field IDs and transition IDs read from env vars (no hardcoded IDs)
    """

    _DEFAULT_PROJECT_KEY = "QENG"  # fallback when JIRA_LAB_REQUEST_PROJECT_KEY is unset

    def __init__(self, *, timeout: int = 15) -> None:
        self._timeout = timeout
        self._base_url = self._get_env("JIRA_URL").rstrip("/")
        pat = self._get_env("JIRA_PAT")

        # Support Bearer token auth for Jira PATs (no username needed)
        self._base_headers = {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/json",
        }
        self._json_headers = {**self._base_headers, "Content-Type": "application/json"}
        self._attachment_headers = {**self._base_headers, "X-Atlassian-Token": "no-check"}

        # --- Slice C: HTTPAdapter with retry on transient failures ---
        retry_policy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)

        self._session = requests.Session()
        self._session.headers.update(self._base_headers)
        self._session.mount("https://", adapter)

        # --- Slice C: in-process token-bucket rate limiter ---
        # 10 req/s sustained, burst up to 10, wait at most 5s before raising.
        self._rate_limiter = _TokenBucket(rate=10.0, capacity=10.0, block_timeout=5.0)

        # --- Slice C: field/transition IDs from env vars ---
        # All Jira custom field IDs and the issue type ID are read from env vars
        # at call time via _field_id().  Set these in .env (see .env.example
        # §Slice C) before running.  Missing vars raise JiraServiceError on
        # first use rather than at construction time, so existing tests that
        # skip on missing JIRA_URL/JIRA_PAT are not broken by missing field vars.
        self._transition_done_id: Optional[str] = os.getenv("JIRA_TRANSITION_DONE_ID")
        self._transition_cancel_id: Optional[str] = os.getenv("JIRA_TRANSITION_CANCEL_ID")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_env(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise JiraServiceError(f"Missing required environment variable: {key}")
        return value

    # Mapping from logical field name → env var name (Slice C, Issue #72).
    # Values are read at call time so construction does not require all vars.
    _FIELD_ENV: Dict[str, str] = {
        "lab_request_type": "JIRA_CUSTOMFIELD_LAB_REQUEST_TYPE",
        "lead_qe_team": "JIRA_CUSTOMFIELD_LEAD_QE_TEAM",
        "lead_rd_team": "JIRA_CUSTOMFIELD_LEAD_RD_TEAM",
        "deadline": "JIRA_CUSTOMFIELD_DEADLINE",
        "planned_end_date": "JIRA_CUSTOMFIELD_PLANNED_END_DATE",
        "high_level_estimate": "JIRA_CUSTOMFIELD_HIGH_LEVEL_ESTIMATE",
        "issue_type_id": "JIRA_LAB_REQUEST_ISSUE_TYPE_ID",
    }

    @classmethod
    def _field_id(cls, name: str) -> str:
        """Return the Jira field ID for *name* from the environment.

        Raises:
            JiraServiceError: if *name* is not a known field, or if the
                corresponding env var is not set.
        """
        if name not in cls._FIELD_ENV:
            valid = ", ".join(sorted(cls._FIELD_ENV))
            raise JiraServiceError(
                f"Unknown Jira field name {name!r}. Valid names: {valid}"
            )
        env_var = cls._FIELD_ENV[name]
        return cls._get_env(env_var)

    def _throttle(self) -> None:
        """Acquire a rate-limiter token before issuing an HTTP request."""
        self._rate_limiter.acquire()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_connectivity(self) -> None:
        """Cheap authenticated round-trip to verify Jira credentials and reachability.

        Calls ``/rest/api/2/myself`` — a lightweight read-only endpoint that
        returns the current user.  Uses the existing session/auth configured in
        ``__init__`` so no second auth path is introduced.

        Raises:
            JiraAuthError: if Jira responds with 401 or 403 (bad/expired token).
            JiraServiceError: if the request fails at the network level, or Jira
                returns any non-2xx status other than 401/403.
        """
        self._throttle()
        try:
            resp = self._session.get(
                f"{self._base_url}/rest/api/2/myself",
                timeout=5,
            )
        except requests.RequestException as exc:
            logger.error("Error reaching Jira during connectivity check: %s", exc)
            raise JiraServiceError("Could not reach Jira — check network connectivity and JIRA_URL.") from exc
        if resp.status_code in (401, 403):
            raise JiraAuthError("Jira authentication failed")
        if not resp.ok:
            raise JiraServiceError(f"Jira returned {resp.status_code}")

    def create_lab_request(
        self,
        *,
        summary: str,
        description: str,
        assignee: Optional[object] = None,
        priority: object,
        lab_request_type: object,
        lead_qe_team: object = "Support Team",
        lead_rd_team: object = "Quality Engineering",
        deadline: object,
        custom_fields: Optional[Dict[str, object]] = None,
        attachments: Optional[Iterable[str]] = None,
        project_key: Optional[str] = None,
        issue_type_id: Optional[str] = None,
    ) -> str:
        effective_project_key = (
            project_key
            if project_key is not None
            else os.getenv("JIRA_LAB_REQUEST_PROJECT_KEY", self._DEFAULT_PROJECT_KEY)
        )
        effective_issue_type_id = issue_type_id if issue_type_id is not None else self._field_id("issue_type_id")
        fields = self._build_lab_request_fields(
            summary=summary,
            description=description,
            assignee=assignee,
            priority=priority,
            lab_request_type=lab_request_type,
            lead_qe_team=lead_qe_team,
            lead_rd_team=lead_rd_team,
            deadline=deadline,
            custom_fields=custom_fields,
            project_key=effective_project_key,
            issue_type_id=effective_issue_type_id,
        )
        payload = {"fields": fields}
        issue_key = self._create_issue(payload)

        if attachments:
            self._upload_attachments(issue_key, attachments)

        return issue_key

    def get_issue(self, issue_key: str, *, fields: str = "*all") -> Dict[str, object]:
        """Get full details of a Jira issue.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            fields: Comma-separated field names or '*all' for all fields

        Returns:
            Dictionary containing issue data with 'key', 'fields', etc.
        """
        url = f"{self._base_url}/rest/api/2/issue/{issue_key}"
        params = {"fields": fields}
        self._throttle()
        try:
            response = self._session.get(url, params=params, headers=self._json_headers, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.error("Error communicating with Jira while fetching issue: %s", exc)
            raise JiraServiceError("Failed to communicate with Jira while fetching issue") from exc

        if response.status_code in (401, 403):
            logger.error("Jira authentication failed during issue fetch: %s", response.text)
            raise JiraAuthError("Authentication with Jira failed while fetching issue")

        if response.status_code == 404:
            raise JiraNotFoundError(f"Issue not found: {issue_key}")

        if response.status_code >= 300:
            logger.error(
                "Jira issue fetch failed (status %s): %s",
                response.status_code,
                response.text,
            )
            raise JiraServiceError(
                f"Failed to fetch Jira issue (status {response.status_code})"
            )

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Jira returned invalid issue payload: %s", response.text)
            raise JiraServiceError("Jira issue response was not valid JSON") from exc

    def search_issues(
        self,
        jql: str,
        *,
        fields: str = "*all",
        max_results: int = 100,
        start_at: int = 0
    ) -> Dict[str, object]:
        """Execute JQL search and return matching issues.

        Args:
            jql: JQL query string (e.g., 'project = QENG AND issuetype = "Lab Request"')
            fields: Comma-separated field names or '*all' for all fields
            max_results: Maximum number of results to return (default: 100)
            start_at: Starting index for pagination (default: 0)

        Returns:
            Dictionary containing search results with 'issues', 'total', etc.
        """
        url = f"{self._base_url}/rest/api/2/search"
        params = {
            "jql": jql,
            "fields": fields,
            "maxResults": max_results,
            "startAt": start_at,
        }
        self._throttle()
        try:
            response = self._session.get(url, params=params, headers=self._json_headers, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.error("Error communicating with Jira while searching issues: %s", exc)
            raise JiraServiceError("Failed to communicate with Jira while searching issues") from exc

        if response.status_code in (401, 403):
            logger.error("Jira authentication failed during issue search: %s", response.text)
            raise JiraAuthError("Authentication with Jira failed while searching issues")

        if response.status_code >= 300:
            logger.error(
                "Jira issue search failed (status %s): %s",
                response.status_code,
                response.text,
            )
            raise JiraServiceError(
                f"Failed to search Jira issues (status {response.status_code})"
            )

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Jira returned invalid search payload: %s", response.text)
            raise JiraServiceError("Jira search response was not valid JSON") from exc

    def get_transitions(self, issue_key: str) -> Dict[str, object]:
        url = f"{self._base_url}/rest/api/2/issue/{issue_key}/transitions"
        self._throttle()
        try:
            response = self._session.get(url, headers=self._json_headers, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.error("Error communicating with Jira while fetching transitions: %s", exc)
            raise JiraIssueTransitionError("Failed to communicate with Jira while fetching transitions") from exc

        if response.status_code in (401, 403):
            logger.error("Jira authentication failed during transition fetch: %s", response.text)
            raise JiraAuthError("Authentication with Jira failed while fetching transitions")

        if response.status_code >= 300:
            logger.error(
                "Jira transition lookup failed (status %s): %s",
                response.status_code,
                response.text,
            )
            raise JiraIssueTransitionError(
                f"Failed to fetch Jira transitions (status {response.status_code})"
            )

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Jira returned invalid transitions payload: %s", response.text)
            raise JiraIssueTransitionError("Jira transitions response was not valid JSON") from exc

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        *,
        fields: Optional[Dict[str, object]] = None,
        comment: Optional[str] = None,
    ) -> None:
        url = f"{self._base_url}/rest/api/2/issue/{issue_key}/transitions"
        payload: Dict[str, object] = {"transition": {"id": transition_id}}
        if fields:
            payload["fields"] = fields
        if comment:
            payload["update"] = {"comment": [{"add": {"body": comment}}]}

        self._throttle()
        try:
            response = self._session.post(url, json=payload, headers=self._json_headers, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.error("Error communicating with Jira while transitioning issue: %s", exc)
            _metrics.jira_task_failure_total.labels(operation="transition_issue").inc()
            raise JiraIssueTransitionError("Failed to communicate with Jira while transitioning issue") from exc

        if response.status_code in (401, 403):
            logger.error("Jira authentication failed during transition: %s", response.text)
            _metrics.jira_task_failure_total.labels(operation="transition_issue").inc()
            raise JiraAuthError("Authentication with Jira failed while transitioning issue")

        if response.status_code >= 300:
            logger.error(
                "Jira transition failed (status %s): %s",
                response.status_code,
                response.text,
            )
            _metrics.jira_task_failure_total.labels(operation="transition_issue").inc()
            raise JiraIssueTransitionError(
                f"Failed to transition Jira issue (status {response.status_code})"
            )
        _metrics.jira_task_success_total.labels(operation="transition_issue").inc()

    def transition_issue_by_name(
        self,
        issue_key: str,
        transition_name: str,
        *,
        fields: Optional[Dict[str, object]] = None,
        comment: Optional[str] = None,
    ) -> None:
        transitions = self.get_transitions(issue_key).get("transitions", [])
        if not isinstance(transitions, list):
            raise JiraIssueTransitionError("Jira transitions response did not include a list")
        for transition in transitions:
            name = str(transition.get("name", ""))
            if name.strip().lower() == transition_name.strip().lower():
                transition_id = str(transition.get("id"))
                return self.transition_issue(
                    issue_key,
                    transition_id,
                    fields=fields,
                    comment=comment,
                )
        raise JiraIssueTransitionError(f"Transition not found: {transition_name}")

    def update_issue_fields(self, issue_key: str, fields: Dict[str, object]) -> None:
        url = f"{self._base_url}/rest/api/2/issue/{issue_key}"
        payload = {"fields": fields}
        self._throttle()
        try:
            response = self._session.put(url, json=payload, headers=self._json_headers, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.error("Error communicating with Jira while updating issue: %s", exc)
            _metrics.jira_task_failure_total.labels(operation="update_issue").inc()
            raise JiraIssueUpdateError("Failed to communicate with Jira while updating issue") from exc

        if response.status_code in (401, 403):
            logger.error("Jira authentication failed during issue update: %s", response.text)
            _metrics.jira_task_failure_total.labels(operation="update_issue").inc()
            raise JiraAuthError("Authentication with Jira failed while updating issue")

        if response.status_code >= 300:
            logger.error(
                "Jira issue update failed (status %s): %s",
                response.status_code,
                response.text,
            )
            _metrics.jira_task_failure_total.labels(operation="update_issue").inc()
            raise JiraIssueUpdateError(
                f"Failed to update Jira issue (status {response.status_code})"
            )
        _metrics.jira_task_success_total.labels(operation="update_issue").inc()

    def update_assignee(self, issue_key: str, assignee: object) -> None:
        """Update the assignee of a Jira issue.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            assignee: Username, email, or None to unassign
        """
        if assignee is None or assignee == "unassigned":
            fields = {"assignee": None}
        else:
            fields = {"assignee": self._normalize_assignee(assignee)}
        self.update_issue_fields(issue_key, fields)

    def update_description(self, issue_key: str, description: str) -> None:
        """Update the description of a Jira issue.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            description: New description text
        """
        self.update_issue_fields(issue_key, {"description": description})

    def update_lab_request_type(self, issue_key: str, lab_request_type: object) -> None:
        """Update the Lab Request Type custom field.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            lab_request_type: New lab request type value
        """
        field_id = self._field_id("lab_request_type")
        fields = {field_id: self._normalize_select(lab_request_type)}
        self.update_issue_fields(issue_key, fields)

    def update_priority(self, issue_key: str, priority: object) -> None:
        """Update the priority of a Jira issue.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            priority: Priority name (e.g., 'P1: Critical', 'P5: Nice to Have')
        """
        fields = {"priority": self._normalize_named_item(priority, "priority")}
        self.update_issue_fields(issue_key, fields)

    def update_deadline(self, issue_key: str, deadline: object) -> None:
        """Update the Deadline custom field.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            deadline: Date string (YYYY-MM-DD) or date object
        """
        field_id = self._field_id("deadline")
        fields = {field_id: self._normalize_date(deadline)}
        self.update_issue_fields(issue_key, fields)

    def update_planned_end_date(self, issue_key: str, planned_end_date: object) -> None:
        """Update the Planned End Date custom field.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            planned_end_date: Date string (YYYY-MM-DD format) or date object
        """
        field_id = self._field_id("planned_end_date")
        # Use standard YYYY-MM-DD format for date picker
        fields = {field_id: self._normalize_date(planned_end_date)}
        self.update_issue_fields(issue_key, fields)

    def update_high_level_estimate(self, issue_key: str, estimate: str) -> None:
        """Update the High Level Estimate custom field.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            estimate: One of: 'None', 'X-Small', 'Small', 'Medium', 'Large', 'X-Large'
        """
        field_id = self._field_id("high_level_estimate")
        fields = {field_id: {"value": estimate}}
        self.update_issue_fields(issue_key, fields)

    def update_resolution(self, issue_key: str, resolution: str) -> None:
        """Update the resolution field.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            resolution: Resolution name (e.g., 'Done', 'Cancelled', etc.)
        """
        fields = {"resolution": {"name": resolution}}
        self.update_issue_fields(issue_key, fields)

    # Workflow transition convenience methods

    def transition_to_on_hold(self, issue_key: str, comment: Optional[str] = None) -> None:
        """Transition a Lab Request to 'On Hold' status.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            comment: Optional comment for the transition
        """
        self.transition_issue_by_name(issue_key, "On Hold", comment=comment)

    def transition_to_defining_requirements(self, issue_key: str, comment: Optional[str] = None) -> None:
        """Transition a Lab Request to 'Defining Requirements' status.

        Works from: On Hold, Cancelled (via 'Reopen' transition)

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            comment: Optional comment for the transition
        """
        self.transition_issue_by_name(issue_key, "Reopen", comment=comment)

    def transition_to_cancelled(self, issue_key: str, comment: Optional[str] = None) -> None:
        """Transition a Lab Request to 'Cancelled' status.

        Automatically sets resolution to 'Cancelled'.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            comment: Optional comment for the transition
        """
        # Set resolution first
        self.update_resolution(issue_key, "Cancelled")
        # Then transition
        self.transition_issue_by_name(issue_key, "Cancelled", comment=comment)

    def transition_to_pending_staff(self, issue_key: str, comment: Optional[str] = None) -> None:
        """Transition a Lab Request to 'Pending Staff' status.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            comment: Optional comment for the transition
        """
        self.transition_issue_by_name(issue_key, "Request Help", comment=comment)

    def transition_to_in_progress(
        self,
        issue_key: str,
        planned_end_date: object,
        high_level_estimate: str,
        comment: Optional[str] = None
    ) -> None:
        """Transition a Lab Request to 'In Progress' status.

        Requires: Planned End Date and High Level Estimate

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            planned_end_date: Date in YYYY-MM-DD format (e.g., '2026-02-20') or date object
            high_level_estimate: One of: 'None', 'X-Small', 'Small', 'Medium', 'Large', 'X-Large'
            comment: Optional comment for the transition
        """
        # Set required fields first
        self.update_planned_end_date(issue_key, planned_end_date)
        self.update_high_level_estimate(issue_key, high_level_estimate)
        # Then transition
        self.transition_issue_by_name(issue_key, "Start Progress", comment=comment)

    def transition_to_testing(self, issue_key: str, comment: Optional[str] = None) -> None:
        """Transition a Lab Request to 'Testing' status.

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            comment: Optional comment for the transition
        """
        self.transition_issue_by_name(issue_key, "Ready for Testing", comment=comment)

    def transition_to_closed(self, issue_key: str, resolution: str = "Done", comment: Optional[str] = None) -> None:
        """Transition a Lab Request to 'Closed' status.

        Requires: Resolution

        Args:
            issue_key: The issue key (e.g., 'QENG-12345')
            resolution: Resolution name (default: 'Done')
            comment: Optional comment for the transition
        """
        # Transition with resolution in the transition payload
        transitions_result = self.get_transitions(issue_key)
        transitions = transitions_result.get("transitions", [])

        closed_transition = None
        for t in transitions:
            if t["name"] == "Closed":
                closed_transition = t
                break

        if not closed_transition:
            raise JiraIssueTransitionError("Transition not found: Closed")

        # Transition with resolution field
        self.transition_issue(
            issue_key,
            closed_transition["id"],
            fields={"resolution": {"name": resolution}},
            comment=comment
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_lab_request_fields(
        self,
        *,
        summary: str,
        description: str,
        assignee: Optional[object],
        priority: object,
        lab_request_type: object,
        lead_qe_team: object,
        lead_rd_team: object,
        deadline: object,
        custom_fields: Optional[Dict[str, object]],
        project_key: str,
        issue_type_id: str,
    ) -> Dict[str, object]:
        self._require("summary", summary)
        self._require("description", description)
        self._require("priority", priority)
        self._require("lab_request_type", lab_request_type)
        self._require("lead_qe_team", lead_qe_team)
        self._require("lead_rd_team", lead_rd_team)
        self._require("deadline", deadline)

        fields: Dict[str, object] = {
            "project": {"key": project_key},
            "issuetype": {"id": issue_type_id},
            "summary": summary,
            "description": description,
            "priority": self._normalize_named_item(priority, "priority"),
            self._field_id("lab_request_type"): self._normalize_select(lab_request_type),
            self._field_id("lead_qe_team"): self._normalize_select(lead_qe_team),
            self._field_id("lead_rd_team"): self._normalize_select(lead_rd_team),
            self._field_id("deadline"): self._normalize_date(deadline),
        }
        # Add assignee only if provided
        if assignee is not None and assignee != "unassigned":
            fields["assignee"] = self._normalize_assignee(assignee)
        if custom_fields:
            fields.update(custom_fields)
        return fields

    @staticmethod
    def _require(name: str, value: object) -> None:
        if value is None or value == "":
            raise JiraIssueCreationError(f"Missing required field: {name}")

    @staticmethod
    def _normalize_named_item(value: object, label: str) -> Dict[str, str]:
        if isinstance(value, dict):
            return value  # Assume already in Jira format
        if isinstance(value, str):
            return {"name": value}
        raise JiraIssueCreationError(f"Invalid {label} value type: {type(value).__name__}")

    @staticmethod
    def _normalize_select(value: object) -> Dict[str, str]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"value": value}
        raise JiraIssueCreationError(f"Invalid select value type: {type(value).__name__}")

    @staticmethod
    def _normalize_assignee(value: object) -> Dict[str, str]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"name": value}
        raise JiraIssueCreationError(f"Invalid assignee value type: {type(value).__name__}")

    @staticmethod
    def _normalize_date(value: object) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            return value
        raise JiraIssueCreationError("Invalid deadline value type; expected YYYY-MM-DD string")

    def _create_issue(self, payload: Mapping[str, Any]) -> str:
        url = f"{self._base_url}/rest/api/2/issue"
        self._throttle()
        try:
            response = self._session.post(url, json=payload, headers=self._json_headers, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.error("Error communicating with Jira while creating issue: %s", exc)
            _metrics.jira_task_failure_total.labels(operation="create_issue").inc()
            raise JiraIssueCreationError("Failed to communicate with Jira while creating issue") from exc

        if response.status_code in (401, 403):
            logger.error("Jira authentication failed during issue creation: %s", response.text)
            _metrics.jira_task_failure_total.labels(operation="create_issue").inc()
            raise JiraAuthError("Authentication with Jira failed while creating issue")

        if response.status_code != 201:
            detail = response.text.strip()
            if len(detail) > 800:
                detail = f"{detail[:800]}..."
            logger.error(
                "Jira issue creation failed (status %s): %s",
                response.status_code,
                detail or response.text,
            )
            message = f"Failed to create Jira issue (status {response.status_code})"
            if detail:
                message = f"{message}: {detail}"
            _metrics.jira_task_failure_total.labels(operation="create_issue").inc()
            raise JiraIssueCreationError(message)

        try:
            issue_key = response.json()["key"]
        except (ValueError, KeyError) as exc:
            logger.error("Jira responded with invalid payload: %s", response.text)
            _metrics.jira_task_failure_total.labels(operation="create_issue").inc()
            raise JiraIssueCreationError("Jira response missing issue key") from exc

        _metrics.jira_task_success_total.labels(operation="create_issue").inc()
        return issue_key

    def _upload_attachments(self, issue_key: str, attachments: Iterable[str]) -> None:
        url = f"{self._base_url}/rest/api/2/issue/{issue_key}/attachments"
        for attachment_path in attachments:
            path = Path(attachment_path)
            if not path.is_file():
                raise JiraAttachmentUploadError(f"Attachment not found: {attachment_path}")

            self._throttle()
            try:
                with path.open("rb") as file_handle:
                    files = {"file": (path.name, file_handle, "application/octet-stream")}
                    response = self._session.post(
                        url,
                        files=files,
                        headers=self._attachment_headers,
                        timeout=self._timeout,
                    )
            except requests.RequestException as exc:
                logger.error(
                    "Error communicating with Jira while uploading attachment %s: %s",
                    path,
                    exc,
                )
                raise JiraAttachmentUploadError(
                    f"Failed to communicate with Jira while uploading attachment {path.name}"
                ) from exc

            if response.status_code in (401, 403):
                logger.error(
                    "Jira authentication failed during attachment upload %s: %s",
                    path,
                    response.text,
                )
                raise JiraAuthError(
                    f"Authentication with Jira failed while uploading attachment {path.name}"
                )

            if response.status_code >= 300:
                logger.error(
                    "Attachment upload failed for %s (status %s): %s",
                    path,
                    response.status_code,
                    response.text,
                )
                raise JiraAttachmentUploadError(
                    f"Failed to upload attachment {path.name} (status {response.status_code})"
                )
