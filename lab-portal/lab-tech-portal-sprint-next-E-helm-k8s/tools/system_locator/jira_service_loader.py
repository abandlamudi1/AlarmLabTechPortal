"""JiraService-based implementation of LabRequestLoader protocol."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from services.jira_service import JiraService, JiraServiceError

logger = logging.getLogger(__name__)


class JiraServiceLoader:
    """Loads Lab Request issues using the JiraService REST API client."""

    _LAB_REQUEST_ISSUE_TYPE = "Lab Request"
    _DEFAULT_PROJECT = "QENG"

    def __init__(self, jira_service: JiraService) -> None:
        """Initialize loader with a configured JiraService instance.
        
        Args:
            jira_service: Configured JiraService instance for making API calls
        """
        self._jira = jira_service

    def load_lab_requests(
        self,
        *,
        project_keys: Optional[Iterable[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        issue_keys: Optional[Iterable[str]] = None,
        fields: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Load Lab Request issues from Jira using JQL search.
        
        Args:
            project_keys: List of project keys to search (e.g., ['QENG'])
            start_date: Filter issues created on or after this date
            end_date: Filter issues created on or before this date
            issue_keys: Specific issue keys to fetch (e.g., ['QENG-12345'])
            fields: Specific fields to retrieve (defaults to all)
            
        Returns:
            List of issue dictionaries with 'key', 'summary', 'description', 'status', 'fields'
        """
        jql = self._build_jql(
            project_keys=project_keys,
            start_date=start_date,
            end_date=end_date,
            issue_keys=issue_keys,
        )

        try:
            result = self._jira.search_issues(
                jql=jql,
                fields="*all" if not fields else ",".join(fields),
                max_results=500,  # Higher limit for bulk imports
            )
        except JiraServiceError as exc:
            logger.error("Failed to search Jira issues: %s", exc)
            raise RuntimeError(f"Failed to search Jira issues: {exc}") from exc

        issues = result.get("issues", [])
        if not isinstance(issues, list):
            logger.error("Jira search returned non-list 'issues' field")
            return []

        return [self._transform_issue(issue) for issue in issues]

    def _build_jql(
        self,
        *,
        project_keys: Optional[Iterable[str]],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        issue_keys: Optional[Iterable[str]],
    ) -> str:
        """Build JQL query from filter parameters.
        
        Args:
            project_keys: Project keys to filter by
            start_date: Created date >= this value
            end_date: Created date <= this value
            issue_keys: Specific issue keys to include
            
        Returns:
            JQL query string
        """
        clauses: List[str] = []

        # Specific issue keys take precedence
        if issue_keys:
            keys_list = list(issue_keys)
            if len(keys_list) == 1:
                clauses.append(f'key = {keys_list[0]}')
            else:
                keys_str = ", ".join(keys_list)
                clauses.append(f'key in ({keys_str})')
        else:
            # Project filter (default to QENG if not specified)
            if project_keys:
                projects = list(project_keys)
                if len(projects) == 1:
                    clauses.append(f'project = {projects[0]}')
                else:
                    projects_str = ", ".join(projects)
                    clauses.append(f'project in ({projects_str})')
            else:
                clauses.append(f'project = {self._DEFAULT_PROJECT}')

            # Issue type filter
            clauses.append(f'issuetype = "{self._LAB_REQUEST_ISSUE_TYPE}"')

            # Date range filters
            if start_date:
                date_str = start_date.strftime("%Y-%m-%d")
                clauses.append(f'created >= "{date_str}"')
            
            if end_date:
                date_str = end_date.strftime("%Y-%m-%d")
                clauses.append(f'created <= "{date_str}"')

        # Order by created date (newest first)
        jql = " AND ".join(clauses) + " ORDER BY created DESC"
        logger.info("Built JQL query: %s", jql)
        return jql

    def _transform_issue(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Jira API issue format to LabRequestLoader format.
        
        Args:
            issue: Raw issue dictionary from Jira API
            
        Returns:
            Transformed issue dictionary with normalized fields
        """
        fields = issue.get("fields", {})
        
        # Extract status - handle both string and object formats
        status_field = fields.get("status", {})
        if isinstance(status_field, dict):
            status = status_field.get("name", "Unknown")
        else:
            status = str(status_field) if status_field else "Unknown"

        return {
            "key": issue.get("key", ""),
            "summary": fields.get("summary", ""),
            "description": fields.get("description", ""),
            "status": status,
            "fields": fields,
            "created": fields.get("created"),
            "updated": fields.get("updated"),
        }
