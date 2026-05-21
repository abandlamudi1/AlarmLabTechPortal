#!/usr/bin/env python3
"""
Display GitHub Project Board in a rich table format
Usage: python3 display_project_board.py [--org ORG] [--project-id ID]
"""

import json
import subprocess
import sys
from typing import List, Dict, Any

try:
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("⚠️  'rich' library not installed. Install with: pip install rich", file=sys.stderr)
    sys.exit(1)


def get_project_items(org: str, project_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch project items using gh CLI"""
    try:
        result = subprocess.run(
            ["gh", "project", "item-list", str(project_id), "--owner", org, "--format", "json", "--limit", str(limit)],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(result.stdout)
        return data.get("items", [])
    except subprocess.CalledProcessError as e:
        print(f"❌ Error fetching project board: {e.stderr}", file=sys.stderr)
        return []
    except json.JSONDecodeError:
        print("❌ Error parsing project data", file=sys.stderr)
        return []


def get_status_emoji(status: str) -> str:
    """Get emoji for status"""
    status_map = {
        "Todo": "📋",
        "In Progress": "🔄",
        "Done": "✅",
        "Backlog": "📦",
        "Blocked": "🚫",
    }
    return status_map.get(status, "❓")


def get_priority_text(labels: List[str]) -> Text:
    """Extract and format priority from labels"""
    for label in labels:
        if label.startswith("priority:"):
            priority = label.split(":")[1]
            if priority == "high":
                return Text("High", style="bold red")
            elif priority == "medium":
                return Text("Medium", style="bold yellow")
            elif priority == "low":
                return Text("Low", style="bold green")
    return Text("-", style="dim")


def display_project_board(org: str, project_id: int):
    """Display project board in a rich table"""
    console = Console()
    
    # Fetch items
    items = get_project_items(org, project_id)
    
    if not items:
        console.print("[yellow]⚠️  No items found in project board[/yellow]")
        return
    
    # Group by status
    todo_items = [item for item in items if item.get("status") == "Todo"]
    in_progress_items = [item for item in items if item.get("status") == "In Progress"]
    done_items = [item for item in items if item.get("status") == "Done"]
    
    # Summary
    console.print(f"\n[bold cyan]📊 Project Board #{project_id} Summary[/bold cyan]")
    console.print(f"  [yellow]📋 Todo: {len(todo_items)}[/yellow]")
    console.print(f"  [cyan]🔄 In Progress: {len(in_progress_items)}[/cyan]")
    console.print(f"  [green]✅ Done: {len(done_items)}[/green]")
    console.print()
    
    # Display Todo items in a table
    if todo_items:
        table = Table(title="📋 Todo Items", show_header=True, header_style="bold cyan")
        table.add_column("#", style="cyan", width=8)
        table.add_column("Title", style="white", no_wrap=False)
        table.add_column("Priority", justify="center", width=10)
        table.add_column("Labels", style="dim", width=20)
        
        for item in todo_items:
            content = item.get("content", {})
            issue_number = str(content.get("number", ""))
            title = content.get("title", "")
            labels_data = item.get("labels", [])
            
            # Handle both label formats (string or dict)
            label_names = []
            if isinstance(labels_data, list):
                for label in labels_data:
                    if isinstance(label, str):
                        label_names.append(label)
                    elif isinstance(label, dict):
                        label_names.append(label.get("name", ""))
            
            # Get priority from labels
            priority = get_priority_text(label_names)
            
            # Format labels (exclude priority labels)
            other_labels = [l for l in label_names if not l.startswith("priority:")]
            labels_str = ", ".join(other_labels[:3]) if other_labels else "-"
            if len(other_labels) > 3:
                labels_str += "..."
            
            table.add_row(
                f"#{issue_number}",
                title,
                priority,
                labels_str
            )
        
        console.print(table)
        console.print()
    
    # Display In Progress items
    if in_progress_items:
        table = Table(title="🔄 In Progress", show_header=True, header_style="bold yellow")
        table.add_column("#", style="cyan", width=8)
        table.add_column("Title", style="white", no_wrap=False)
        table.add_column("Assignees", style="green", width=20)
        
        for item in in_progress_items:
            content = item.get("content", {})
            issue_number = str(content.get("number", ""))
            title = content.get("title", "")
            assignees = item.get("assignees", [])
            assignee_names = ", ".join([a.get("login", "") for a in assignees]) if assignees else "-"
            
            table.add_row(
                f"#{issue_number}",
                title,
                assignee_names
            )
        
        console.print(table)
        console.print()


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Display GitHub Project Board in rich table format")
    parser.add_argument("--org", default="adc-quality", help="GitHub organization")
    parser.add_argument("--project-id", type=int, default=23, help="GitHub project number")
    
    args = parser.parse_args()
    
    # Check if gh CLI is available
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ GitHub CLI (gh) not installed. Install from: https://cli.github.com/", file=sys.stderr)
        sys.exit(1)
    
    display_project_board(args.org, args.project_id)


if __name__ == "__main__":
    main()
