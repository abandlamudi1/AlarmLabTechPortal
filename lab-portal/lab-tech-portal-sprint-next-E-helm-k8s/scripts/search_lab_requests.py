"""Search for Lab Request tickets to analyze description patterns."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.jira_service import JiraService, JiraServiceError


def search_lab_requests():
    """Search for recent Lab Request tickets."""
    try:
        jira = JiraService()
        
        # Search for Lab Requests in IAT project (where IAT-5063 came from)
        jql = 'project = IAT ORDER BY created DESC'
        
        result = jira.search_issues(jql, max_results=10)
        
        issues = result.get("issues", [])
        total = result.get("total", 0)
        
        print(f"\nFound {total} total issues in IAT project")
        print(f"Showing first {len(issues)} issues:\n")
        print("=" * 100)
        
        for issue in issues:
            key = issue.get("key", "")
            fields = issue.get("fields", {})
            summary = fields.get("summary", "")
            issue_type = fields.get("issuetype", {}).get("name", "")
            status = fields.get("status", {}).get("name", "")
            description = fields.get("description", "")
            
            has_table = "||" in description if description else False
            desc_length = len(description) if description else 0
            
            print(f"{key:15} | {issue_type:20} | {status:20} | Desc: {desc_length:4} chars | Table: {has_table}")
            print(f"  Summary: {summary[:80]}")
            print("-" * 100)
        
        return issues
        
    except JiraServiceError as e:
        print(f"Error searching tickets: {e}")
        return []


if __name__ == "__main__":
    search_lab_requests()
