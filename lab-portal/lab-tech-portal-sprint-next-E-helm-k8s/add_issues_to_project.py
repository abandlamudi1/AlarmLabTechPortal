"""Add all roadmap issues (#2-#40) to the Lab Tech Portal Tracker project board.

Prerequisites:
  Run this first to add the 'project' write scope to your token:
    gh auth refresh -s project

Then run:
    python add_issues_to_project.py
"""

import subprocess
import sys

REPO = "adc-quality/lab-tech-portal"
PROJECT_NUMBER = 23
ORG = "adc-quality"
ISSUE_RANGE = range(2, 41)  # Issues #2 through #40


def run_gh(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def main():
    # Verify project scope
    auth = run_gh(["auth", "status"])
    if auth and "project" not in auth:
        status = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True
        )
        scopes = status.stderr + status.stdout
        if "'project'" not in scopes:
            print("ERROR: Your token is missing the 'project' scope.")
            print("Run: gh auth refresh -s project")
            print("Then re-run this script.")
            sys.exit(1)

    added = 0
    failed = 0

    for issue_num in ISSUE_RANGE:
        url = f"https://github.com/{REPO}/issues/{issue_num}"
        print(f"Adding #{issue_num} to project...", end=" ")

        result = subprocess.run(
            ["gh", "project", "item-add", str(PROJECT_NUMBER),
             "--owner", ORG, "--url", url],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            print("OK")
            added += 1
        else:
            err = result.stderr.strip().split("\n")[0] if result.stderr else "unknown error"
            print(f"FAILED ({err})")
            failed += 1

    print(f"\nDone! Added: {added}, Failed: {failed}")


if __name__ == "__main__":
    main()
