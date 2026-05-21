"""Write description to file."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.jira_service import JiraService


jira = JiraService()
issue = jira.get_issue("IAT-5063")
description = issue["fields"]["description"]

with open("description.txt", "w", encoding="utf-8") as f:
    f.write(description)

print("Description written to description.txt")
print(f"Length: {len(description)} characters")
