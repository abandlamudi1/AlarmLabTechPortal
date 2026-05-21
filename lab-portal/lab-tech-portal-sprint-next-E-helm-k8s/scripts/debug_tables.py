"""Debug table parsing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.jira_service import JiraService
from tools.system_locator.description_parser import DescriptionParser


def debug_table_parsing(issue_key: str):
    """Debug table parsing for a ticket."""
    jira = JiraService()
    issue = jira.get_issue(issue_key)
    
    fields = issue.get("fields", {})
    description = fields.get("description", "")
    
    print(f"\n{'='*80}")
    print("DESCRIPTION LENGTH:", len(description), "characters")
    print(f"{'='*80}\n")
    
    print(f"{'='*80}")
    print("PARSED TABLES:")
    print(f"{'='*80}\n")
    
    tables = DescriptionParser._parse_jira_table(description)
    
    print(f"Found {len(tables)} table rows\n")
    
    for i, row in enumerate(tables):
        print(f"Row {i+1} ({len(row)} columns):")
        for header, value in row.items():
            # Safely print value
            value_display = value.replace('\n', '\\n')[:80]
            print(f"  {header:35} : {value_display}")
        print()


if __name__ == "__main__":
    debug_table_parsing("IAT-5063")
