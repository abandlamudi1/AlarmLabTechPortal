#!/usr/bin/env python3
"""
End of day routine - Create changelog for handoff
Lab Tech Portal - Daily Summary Script
Cross-platform: Windows, macOS, Linux
"""

import sys
import os
import subprocess
import platform
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

# Try to import colorama for cross-platform color support
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    # Fallback - no colors
    class Fore:
        CYAN = GREEN = YELLOW = RED = ""
    class Style:
        RESET_ALL = ""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def run_command(cmd: list, check: bool = True) -> Tuple[int, str]:
    """Run a command and return exit code and output"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result.returncode, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout.strip()
    except FileNotFoundError:
        return 127, ""


def print_header(text: str):
    """Print a colored header"""
    print(f"{Fore.CYAN}{text}{Style.RESET_ALL}")


def print_success(text: str):
    """Print a success message"""
    print(f"{Fore.GREEN}{text}{Style.RESET_ALL}")


def print_warning(text: str):
    """Print a warning message"""
    print(f"{Fore.YELLOW}{text}{Style.RESET_ALL}")


def print_error(text: str):
    """Print an error message"""
    print(f"{Fore.RED}{text}{Style.RESET_ALL}")


def get_clipboard_content() -> Optional[str]:
    """Get clipboard content (cross-platform)"""
    try:
        if platform.system() == "Darwin":  # macOS
            result = subprocess.run(["pbpaste"], capture_output=True, text=True)
            return result.stdout if result.returncode == 0 else None
        elif platform.system() == "Windows":
            result = subprocess.run(["powershell", "-command", "Get-Clipboard"], 
                                  capture_output=True, text=True)
            return result.stdout if result.returncode == 0 else None
        elif platform.system() == "Linux":
            # Try xclip first, then xsel
            for cmd in [["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard"]]:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout
        return None
    except:
        return None


def open_in_editor(filepath: Path):
    """Open file in default editor (cross-platform)"""
    try:
        if platform.system() == "Windows":
            os.startfile(str(filepath))
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(["open", str(filepath)])
        else:  # Linux
            # Try various editors
            for editor in ["code", "$EDITOR", "xdg-open", "nano", "vim"]:
                if editor == "$EDITOR":
                    editor = os.environ.get("EDITOR", "nano")
                try:
                    subprocess.run([editor, str(filepath)])
                    return
                except:
                    continue
    except Exception as e:
        print_warning(f"Could not open editor automatically: {e}")
        print(f"Please open manually: {filepath}")


# =============================================================================
# MAIN LOGIC
# =============================================================================

def create_changelog(append_mode: bool = False, 
                     chat_from_clipboard: bool = False,
                     chat_file: Optional[str] = None):
    """Create or append to today's changelog"""
    
    # Get contributor name from git config
    exit_code, contributor = run_command(["git", "config", "user.name"])
    if exit_code != 0 or not contributor:
        print_error("❌ Error: Could not get user name from git config")
        print_warning("💡 Set it with: git config user.name \"Your Name\"")
        return False
    
    contributor = contributor.replace(' ', '_')
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # Create changelogs directory if it doesn't exist
    changelog_dir = Path("changelogs")
    changelog_dir.mkdir(exist_ok=True)
    
    changelog_file = changelog_dir / f"CHANGELOG_{date_str}_{contributor}.md"
    
    # Get current branch
    exit_code, current_branch = run_command(["git", "branch", "--show-current"])
    if exit_code != 0 or not current_branch:
        print_error("❌ Error: Could not determine current branch")
        print_warning("💡 You may be in detached HEAD state")
        return False
    
    # Check if changelog exists
    if changelog_file.exists():
        if append_mode:
            print_success("Appending an update section to existing changelog...")
        else:
            print_warning(f"⚠️  Changelog already exists for today: {changelog_file}")
            print_header("Choose an action:")
            print("  [a] Append update section")
            print("  [e] Edit existing changelog")
            print("  [o] Overwrite from template")
            print("  [q] Quit")
            
            choice = input("Choice (a/e/o/q): ").strip().lower()
            
            if choice == 'a':
                append_mode = True
            elif choice == 'e':
                print_success("Opening existing changelog for editing...")
                open_in_editor(changelog_file)
                return True
            elif choice == 'o':
                print_warning("Overwriting changelog from template...")
            elif choice == 'q':
                print("Aborted.")
                return True
            else:
                print("Invalid choice. Aborted.")
                return False
    
    # Append mode
    if changelog_file.exists() and append_mode:
        now = datetime.now().strftime("%H:%M")
        
        with open(changelog_file, 'a', encoding='utf-8') as f:
            f.write("\n")
            f.write("---\n")
            f.write("\n")
            f.write(f"## Update - {date_str} {now}\n")
            f.write("\n")
            f.write("**Quick Summary**: [One sentence describing this update]\n")
            f.write("\n")
            
            # Add chat summary if requested
            if chat_file or chat_from_clipboard:
                f.write("### Copilot/Chat Summary\n")
                f.write("\n")
                
                if chat_file:
                    chat_path = Path(chat_file)
                    if chat_path.exists():
                        f.write(chat_path.read_text(encoding='utf-8'))
                    else:
                        f.write(f"(Chat summary file not found: {chat_file})\n")
                elif chat_from_clipboard:
                    clipboard = get_clipboard_content()
                    if clipboard:
                        f.write(clipboard)
                    else:
                        f.write("(Clipboard summary requested but could not read clipboard.)\n")
                f.write("\n")
            else:
                f.write("### Notes\n")
                f.write("- [ ] [Add notes here]\n")
                f.write("\n")
            
            # Add commits since midnight
            f.write("### Commits Since Midnight\n")
            f.write("\n")
            exit_code, email = run_command(["git", "config", "user.email"])
            if exit_code == 0 and email:
                exit_code, commits = run_command(
                    ["git", "log", "--since=midnight", "--oneline", f"--author={email}"]
                )
                if exit_code == 0 and commits:
                    for line in commits.split('\n'):
                        if line:
                            f.write(f"- {line}\n")
            f.write("\n")
            
            # Add working tree status
            f.write("### Working Tree Status\n")
            f.write("\n")
            exit_code, status = run_command(["git", "status", "--porcelain"])
            if exit_code == 0 and status:
                for line in status.split('\n'):
                    if line:
                        f.write(f"- {line}\n")
            f.write("\n")
        
        print_success("✅ Update section appended to changelog")
        open_in_editor(changelog_file)
        return True
    
    # Create new changelog from template
    template_file = changelog_dir / "CHANGELOG_TEMPLATE.md"
    if not template_file.exists():
        print_error(f"❌ Template file not found: {template_file}")
        return False
    
    # Copy template
    template_content = template_file.read_text(encoding='utf-8')
    
    # Replace placeholders
    template_content = template_content.replace('[DATE]', date_str)
    template_content = template_content.replace('[CONTRIBUTOR]', contributor)
    template_content = template_content.replace('[branch name]', current_branch)
    
    # Get commit range for today
    exit_code, email = run_command(["git", "config", "user.email"])
    if exit_code == 0 and email:
        exit_code, commits_count = run_command([
            "git", "log", "--since=midnight", "--oneline", f"--author={email}",
            "--format=%h"
        ])
        
        if exit_code == 0 and commits_count:
            commits = commits_count.strip().split('\n')
            if commits and commits[0]:
                print_success(f"Found {len(commits)} commits from you today")
                first_commit = commits[-1]
                last_commit = commits[0]
                template_content = template_content.replace(
                    '[commit hash] to [commit hash]',
                    f'{first_commit} to {last_commit}'
                )
    
    # Write the changelog
    changelog_file.write_text(template_content, encoding='utf-8')
    
    # Print success
    print_header("=" * 40)
    print_success("✅ Changelog template created!")
    print_header("=" * 40)
    print()
    print_warning(f"Opening changelog for you to fill in: {changelog_file}")
    print()
    print_header("Tips for writing a good changelog:")
    print("  • Be specific: 'Fixed login timeout' not 'Fixed bug'")
    print("  • Explain WHY not just WHAT")
    print("  • Include commands to reproduce your work")
    print("  • Call out breaking changes")
    print("  • List open questions for the team")
    print()
    print_warning("⚠️  ARCHITECTURE CHECK:")
    print(f"  Did you change how the pipeline works (new phases, changed data flow)?")
    print(f"  If YES → Update {Fore.CYAN}docs/ARCHITECTURE.md{Style.RESET_ALL} and set 'Last Verified' date")
    print()
    
    print_warning("🧾 ISSUE / PROJECT BOARD CHECK:")
    print("  Before you finish for the day, close/update any GitHub Issues you worked on")
    print("  and confirm project-board status.")
    print("  Suggested commands:")
    print(f"    - {Fore.YELLOW}gh issue list --assignee @me --state open{Style.RESET_ALL}")
    print(f"    - {Fore.YELLOW}gh project item-list 23 --owner adc-quality{Style.RESET_ALL}  (view project board)")
    print(f"    - {Fore.YELLOW}gh issue close <number> -c \"Completed\"{Style.RESET_ALL}  (close issue)")
    print()
    print_success("💡 CREATE ISSUE FOR TOMORROW:")
    print("  If you have a clear next task, create it and add to Project #23:")
    print(f"    {Fore.YELLOW}gh issue create --title \"[Your Task]\" --body \"Description\" --repo adc-quality/lab-tech-portal{Style.RESET_ALL}")
    print("  Or save your notes to a file and create the issue in the morning.")
    print()
    print_header("When done:")
    print(f"  1. Save and close the changelog")
    print(f"  2. Commit it: {Fore.YELLOW}git add {changelog_file} && git commit -m \"docs: add changelog for {date_str}\"{Style.RESET_ALL}")
    print(f"  3. Push: {Fore.YELLOW}git push origin {current_branch}{Style.RESET_ALL}")
    print()
    
    # Open editor
    open_in_editor(changelog_file)
    
    return True


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="End of day routine - Create changelog for handoff"
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append a new update section if today's changelog exists"
    )
    parser.add_argument(
        "--chat-from-clipboard",
        action="store_true",
        help="Include a Copilot/chat summary from clipboard"
    )
    parser.add_argument(
        "--chat-file",
        type=str,
        help="Include a Copilot/chat summary from a file"
    )
    
    args = parser.parse_args()
    
    # Print banner
    print_header("=" * 40)
    print_header("🌙 Lab Tech Portal - End of Day")
    print_header("=" * 40)
    print()
    
    try:
        success = create_changelog(
            append_mode=args.append,
            chat_from_clipboard=args.chat_from_clipboard,
            chat_file=args.chat_file
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print()
        print_warning("\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
