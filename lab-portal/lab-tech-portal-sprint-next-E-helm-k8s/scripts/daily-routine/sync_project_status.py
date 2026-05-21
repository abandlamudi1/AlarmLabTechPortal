#!/usr/bin/env python3
"""Sync GitHub Project status to local markdown and display open items.

This script queries the actual GitHub Project board and generates a summary
of open items, priorities, and task statuses. Use this daily to stay aligned
with the team's current work.

Usage:
    # View open items
    python scripts/sync_project_status.py

    # View all items (including Done)
    python scripts/sync_project_status.py --all

    # Update local GITHUB_PROJECT_TASKS.md
    python scripts/sync_project_status.py --update-local

    # Change status of an issue
    python scripts/sync_project_status.py --issue 45 --status "In Progress"
"""

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

# Try to import rich, but fall back to basic output if not available
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    # Fallback console that mimics rich's basic interface
    class FallbackConsole:
        def print(self, text="", **kwargs):
            # Remove rich markup like [cyan], [green], etc.
            import re
            clean_text = re.sub(r'\[/?[a-z]+\]', '', str(text))
            print(clean_text)
        
        def rule(self, text="", **kwargs):
            print(f"\n{'='*60}\n{text}\n{'='*60}")
    
    console = FallbackConsole()
    Table = None
    Panel = None
    box = None


def run_gh_command(cmd: List[str]) -> str:
    """Run a gh CLI command and return stdout."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running command: {' '.join(cmd)}[/red]")
        console.print(f"[red]{e.stderr}[/red]")
        sys.exit(1)


def get_project_items(org: str = "adc-quality", project_number: int = 15, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch all items from the GitHub Project."""
    console.print(f"[cyan]Querying GitHub Project #{project_number}...[/cyan]")

    cmd = [
        "gh", "project", "item-list", str(project_number),
        "--owner", org,
        "--format", "json",
        "--limit", str(limit)
    ]

    output = run_gh_command(cmd)
    data = json.loads(output)
    return data.get("items", [])


def group_by_status_and_priority(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Group items by status, then by priority."""
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for item in items:
        status = item.get("status", "Unknown")
        priority = item.get("priority", "None")
        grouped[status][priority].append(item)

    return grouped


def display_summary(items: List[Dict[str, Any]], show_all: bool = False) -> None:
    """Display a summary table of items."""
    grouped = group_by_status_and_priority(items)

    # Count by status
    status_counts = {status: sum(len(tasks) for tasks in priorities.values())
                    for status, priorities in grouped.items()}

    # Summary panel
    total = len(items)
    todo = status_counts.get("Todo", 0)
    in_progress = status_counts.get("In Progress", 0)
    done = status_counts.get("Done", 0)

    summary = (
        f"[bold]Total Items:[/bold] {total}\n"
        f"[yellow]📋 Todo:[/yellow] {todo}\n"
        f"[cyan]🔄 In Progress:[/cyan] {in_progress}\n"
        f"[green]✅ Done:[/green] {done}"
    )
    if HAS_RICH and Panel is not None:
        console.print(Panel(summary, title="Project Status", border_style="blue"))
    else:
        console.print("Project Status")
        console.print(summary)

    # Display items by status and priority
    for status in ["In Progress", "Todo", "Done"] if show_all else ["In Progress", "Todo"]:
        if status not in grouped:
            continue

        priorities = grouped[status]

        # Sort priorities: P0, P1, P2, None
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "None": 3}
        sorted_priorities = sorted(priorities.keys(), key=lambda p: priority_order.get(p, 99))

        for priority in sorted_priorities:
            tasks = priorities[priority]
            if not tasks:
                continue

            # Create table
            if HAS_RICH and Table is not None:
                table = Table(
                    title=f"{status} - Priority {priority}",
                    box=box.ROUNDED,
                    show_header=True,
                    header_style="bold magenta"
                )

                table.add_column("#", style="cyan", width=4)
                table.add_column("Title", style="white", max_width=50)
                table.add_column("Size", style="yellow", width=6)
                table.add_column("Assignee", style="green", width=15)
                table.add_column("Iteration", style="blue", width=12)

                for task in tasks:
                    content = task.get("content", {})
                    number = str(content.get("number", "?"))
                    title = content.get("title", "Untitled")
                    size = task.get("size", "-")
                    assignees = task.get("assignees", [])
                    assignee = assignees[0] if assignees else "-"
                    iteration_data = task.get("iteration", {})
                    iteration = iteration_data.get("title", "-") if iteration_data else "-"

                    # Truncate title if too long
                    if len(title) > 47:
                        title = title[:44] + "..."

                    table.add_row(number, title, size, assignee, iteration)

                console.print(table)
                console.print()
            else:
                console.print(f"{status} - Priority {priority}")
                for task in tasks:
                    content = task.get("content", {})
                    number = str(content.get("number", "?"))
                    title = content.get("title", "Untitled")
                    console.print(f"  #{number} - {title}")
                console.print()


def display_high_priority_focus(items: List[Dict[str, Any]]) -> None:
    """Display P0 items that are not Done."""
    p0_items = [
        item for item in items
        if item.get("priority") == "P0" and item.get("status") != "Done"
    ]

    if not p0_items:
        console.print("[green]🎉 All P0 items are complete![/green]\n")
        return

    if HAS_RICH and Panel is not None and Table is not None:
        console.print(Panel(
            f"[bold red]⚠️  {len(p0_items)} HIGH PRIORITY items need attention![/bold red]",
            border_style="red"
        ))

        table = Table(box=box.HEAVY, show_header=True, header_style="bold red")
        table.add_column("#", style="cyan", width=4)
        table.add_column("Title", style="white", max_width=60)
        table.add_column("Status", style="yellow", width=12)
        table.add_column("Assignee", style="green", width=15)

        for item in p0_items:
            content = item.get("content", {})
            number = str(content.get("number", "?"))
            title = content.get("title", "Untitled")
            status = item.get("status", "Unknown")
            assignees = item.get("assignees", [])
            assignee = assignees[0] if assignees else "Unassigned"

            table.add_row(number, title, status, assignee)

        console.print(table)
        console.print()
    else:
        console.print(f"⚠️  {len(p0_items)} HIGH PRIORITY items need attention!")
        for item in p0_items:
            content = item.get("content", {})
            number = str(content.get("number", "?"))
            title = content.get("title", "Untitled")
            status = item.get("status", "Unknown")
            console.print(f"  #{number} - {title} ({status})")
        console.print()


def display_suggested_next_steps(items: List[Dict[str, Any]]) -> None:
    """Suggest what to work on next based on status and priority."""
    # P0 Todo items
    p0_todo = [
        item for item in items
        if item.get("priority") == "P0" and item.get("status") == "Todo"
    ]

    # P0 In Progress items
    p0_in_progress = [
        item for item in items
        if item.get("priority") == "P0" and item.get("status") == "In Progress"
    ]

    suggestions = []

    if p0_in_progress:
        suggestions.append("[yellow]✋ Finish in-progress P0 items before starting new work[/yellow]")
        for item in p0_in_progress:
            content = item.get("content", {})
            suggestions.append(f"   → #{content.get('number')}: {content.get('title', 'Untitled')}")

    if p0_todo and not p0_in_progress:
        suggestions.append("[green]🚀 Pick a P0 Todo item to start:[/green]")
        for item in p0_todo[:3]:  # Show top 3
            content = item.get("content", {})
            suggestions.append(f"   → #{content.get('number')}: {content.get('title', 'Untitled')}")

    if not p0_todo and not p0_in_progress:
        # Look at P1 items
        p1_todo = [
            item for item in items
            if item.get("priority") == "P1" and item.get("status") == "Todo"
        ]
        if p1_todo:
            suggestions.append("[green]🎯 All P0 done! Consider P1 items:[/green]")
            for item in p1_todo[:3]:
                content = item.get("content", {})
                suggestions.append(f"   → #{content.get('number')}: {content.get('title', 'Untitled')}")

    if suggestions:
        if HAS_RICH and Panel is not None:
            console.print(Panel("\n".join(suggestions), title="💡 Suggested Next Steps", border_style="cyan"))
            console.print()
        else:
            console.print("Suggested Next Steps")
            console.print("\n".join(suggestions))
            console.print()


def update_local_markdown(items: List[Dict[str, Any]]) -> None:
    """Update GITHUB_PROJECT_TASKS.md with current status."""
    console.print("[cyan]Updating GITHUB_PROJECT_TASKS.md...[/cyan]")

    grouped = group_by_status_and_priority(items)

    def sanitize_cell(value: str) -> str:
        """Sanitize table cell content for Markdown tables."""
        return value.replace("|", "\\|").replace("\n", " ").strip()

    # Generate markdown content
    lines = [
        "# GitHub Project Tasks - System Quality Quarterly Linking",
        "",
        f"**Last Updated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Source**: GitHub Project #12 (live sync)",
        "",
        "---",
        ""
    ]

    # Add summary
    status_counts = {status: sum(len(tasks) for tasks in priorities.values())
                    for status, priorities in grouped.items()}

    lines.extend([
        "## Summary",
        "",
        f"- **Total Items**: {len(items)}",
        f"- **Todo**: {status_counts.get('Todo', 0)}",
        f"- **In Progress**: {status_counts.get('In Progress', 0)}",
        f"- **Done**: {status_counts.get('Done', 0)}",
        "",
        "---",
        ""
    ])

    # Open tasks table (Todo + In Progress)
    open_items = [
        item for item in items
        if item.get("status") in {"Todo", "In Progress"}
    ]

    priority_order = {"P0": 0, "P1": 1, "P2": 2, "None": 3}
    status_order = {"In Progress": 0, "Todo": 1}
    open_items.sort(
        key=lambda i: (
            priority_order.get(i.get("priority", "None"), 99),
            status_order.get(i.get("status", "Todo"), 99),
            i.get("content", {}).get("number", 0) or 0,
        )
    )

    lines.extend([
        "## Open Tasks (Table)",
        "",
        "| Task # | Summary | Priority |",
        "| --- | --- | --- |",
    ])

    if open_items:
        for item in open_items:
            content = item.get("content", {})
            number = content.get("number", "?")
            title = sanitize_cell(content.get("title", "Untitled"))
            priority = item.get("priority", "None")
            lines.append(f"| {number} | {title} | {priority} |")
    else:
        lines.append("| - | No open tasks found | - |")

    lines.extend([
        "",
        "---",
        ""
    ])

    # Add items by status and priority
    for status in ["In Progress", "Todo", "Done"]:
        if status not in grouped:
            continue

        lines.append(f"## {status}")
        lines.append("")

        priorities = grouped[status]
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "None": 3}
        sorted_priorities = sorted(priorities.keys(), key=lambda p: priority_order.get(p, 99))

        for priority in sorted_priorities:
            tasks = priorities[priority]
            if not tasks:
                continue

            lines.append(f"### Priority {priority}")
            lines.append("")

            for task in tasks:
                content = task.get("content", {})
                number = content.get("number", "?")
                title = content.get("title", "Untitled")
                url = content.get("url", "#")
                size = task.get("size", "-")
                assignees = task.get("assignees", [])
                assignee = assignees[0] if assignees else "Unassigned"

                lines.extend([
                    f"#### #{number} - {title}",
                    "",
                    f"**URL**: {url}",
                    f"**Size**: {size} | **Assignee**: {assignee}",
                    "",
                    f"{content.get('body', '').strip()}",
                    "",
                    "---",
                    ""
                ])

    # Write to file
    output_path = "GITHUB_PROJECT_TASKS.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    console.print(f"[green]✅ Updated {output_path}[/green]\n")


def main():
    parser = argparse.ArgumentParser(description="Sync GitHub Project status")
    parser.add_argument("--all", action="store_true", help="Show all items including Done")
    parser.add_argument("--update-local", action="store_true", help="Update GITHUB_PROJECT_TASKS.md")
    parser.add_argument("--org", default="adc-quality", help="GitHub organization")
    parser.add_argument("--project", type=int, default=12, help="Project number")
    parser.add_argument("--issue", type=int, help="Issue number to update")
    parser.add_argument("--status", help="New status for issue (Todo, In Progress, Done)")

    args = parser.parse_args()

    # Fetch items
    items = get_project_items(org=args.org, project_number=args.project)

    if args.issue and args.status:
        console.print(f"[yellow]Note: Updating issue status requires using gh CLI directly[/yellow]")
        console.print(f"[cyan]Run: gh issue edit {args.issue} --add-project adc-quality/{args.project}[/cyan]")
        return

    # Display summary
    console.print(f"\n[bold]GitHub Project #{args.project} Status Report[/bold]")
    console.print(f"[dim]Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n")

    # High priority focus
    display_high_priority_focus(items)

    # Suggested next steps
    display_suggested_next_steps(items)

    # Full summary
    display_summary(items, show_all=args.all)

    # Update local file if requested
    if args.update_local:
        update_local_markdown(items)
    else:
        console.print("[dim]Tip: Run with --update-local to sync GITHUB_PROJECT_TASKS.md[/dim]\n")


if __name__ == "__main__":
    main()
