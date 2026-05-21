#!/usr/bin/env python3
"""
Morning startup routine for Lab Tech Portal
This script automates daily handoff and project status checks
Cross-platform: Windows, macOS, Linux
"""

import sys
import os
import subprocess
import platform
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

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
# CONFIGURATION
# =============================================================================

def load_config() -> dict:
    """Load configuration from .daily-routine-config or use defaults"""
    script_dir = Path(__file__).parent
    config_file = script_dir / ".daily-routine-config"
    
    # Default configuration based on OS
    is_windows = platform.system() == "Windows"
    
    config = {
        "PROJECT_NAME": "Lab Tech Portal",
        "DEFAULT_BRANCH": "master",
        "CHANGELOG_DIR": "changelogs",
        "PYTHON_CMD": "python" if is_windows else "python3",
        "REQUIREMENTS_FILE": "requirements.txt",
        "VENV_DIR": ".venv",
        "ENABLE_CONNECTIVITY_CHECKS": "false",
        "RECENT_COMMITS": "5",
        "CHANGELOG_DAYS": "3",
        "SKIP_CHANGELOG_CHECK": "false",
        "SKIP_BRANCH_CHECK": "false",
        "SKIP_CONNECTIVITY": "false"
    }
    
    # Try to load from config file (bash format)
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    original_line = line
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Skip if no = sign
                    if '=' not in line:
                        continue
                    
                    # Split on first = only
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove outer quotes first
                    if (value.startswith('"') and '"' in value[1:]):
                        # Find the closing quote
                        end_quote = value.index('"', 1)
                        value = value[1:end_quote]
                    elif (value.startswith("'") and "'" in value[1:]):
                        # Find the closing quote
                        end_quote = value.index("'", 1)
                        value = value[1:end_quote]
                    else:
                        # No quotes, remove inline comments
                        if '#' in value:
                            value = value.split('#')[0].strip()
                    
                    # Now handle ${VAR:-default} syntax
                    if '${' in value and ':-' in value and '}' in value:
                        # Extract default value: ${VAR:-default} -> default
                        start = value.index('${')
                        end = value.index('}', start)
                        var_expr = value[start:end+1]
                        if ':-' in var_expr:
                            default_val = var_expr.split(':-', 1)[1].rstrip('}')
                            value = value.replace(var_expr, default_val)
                    
                    # Clean up any remaining whitespace
                    value = value.strip()
                    
                    # Only update if value is not empty
                    if value:
                        config[key] = value
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️  Could not parse config file: {e}{Style.RESET_ALL}")
    
    # Override PYTHON_CMD based on OS if it's still the default
    if config["PYTHON_CMD"] == "python3" and is_windows:
        config["PYTHON_CMD"] = "python"
    
    return config


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def run_command(cmd: List[str], check: bool = True, capture: bool = True) -> Tuple[int, str]:
    """Run a command and return exit code and output"""
    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check)
            return result.returncode, result.stdout.strip()
        else:
            result = subprocess.run(cmd, check=check)
            return result.returncode, ""
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout.strip() if capture else ""
    except FileNotFoundError:
        return 127, ""


def command_exists(command: str) -> bool:
    """Check if a command exists"""
    return subprocess.run(
        ["which", command] if platform.system() != "Windows" else ["where", command],
        capture_output=True
    ).returncode == 0


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


def get_user_input(prompt: str) -> str:
    """Get user input with a prompt"""
    return input(f"{prompt} ").strip().lower()


# =============================================================================
# MAIN ROUTINE STEPS
# =============================================================================

def step_git_pull(config: dict):
    """Step 1: Pull latest changes"""
    print_header("📥 Step 1: Pulling latest changes...")
    
    # Fetch from origin
    exit_code, _ = run_command(["git", "fetch", "origin"])
    if exit_code != 0:
        print_error("❌ Error: Could not fetch from origin")
        return False
    
    # Get current branch
    exit_code, current_branch = run_command(["git", "branch", "--show-current"])
    if exit_code != 0 or not current_branch:
        print_error("❌ Error: Could not determine current branch")
        print_warning("💡 You may be in detached HEAD state. Check: git status")
        return False
    
    # Check how many commits behind
    exit_code, behind = run_command(
        ["git", "rev-list", f"HEAD..origin/{current_branch}", "--count"]
    )
    
    if exit_code == 0 and behind and int(behind) > 0:
        print_warning(f"⚠️  You are {behind} commits behind origin/{current_branch}")
        print_header("Pulling changes...")
        
        exit_code, _ = run_command(
            ["git", "pull", "--rebase", "origin", current_branch],
            check=False
        )
        
        if exit_code == 0:
            print_success("✅ Changes pulled successfully")
        else:
            print_error("❌ Error: Git pull failed")
            print_warning("💡 Try resolving conflicts or run: git pull --no-rebase")
            return False
    else:
        print_success("✅ Already up to date")
    
    print()
    return True


def step_recent_commits(config: dict):
    """Step 2: Show recent commits"""
    recent = int(config["RECENT_COMMITS"])
    print_header(f"📝 Step 2: Recent commits (last {recent})")
    
    # Run git log with color if in terminal
    exit_code, _ = run_command(
        ["git", "log", f"--oneline", f"-{recent}", "--decorate", "--color=always"],
        capture=False
    )
    
    print()


def step_recent_changelogs(config: dict):
    """Step 3: Find and display recent changelogs"""
    if config.get("SKIP_CHANGELOG_CHECK") == "true":
        print_header("Step 3: Changelogs - Skipped (not configured)")
        print()
        return
    
    print_header("📋 Step 3: Recent changelogs")
    
    changelog_dir = Path(config["CHANGELOG_DIR"])
    if not changelog_dir.exists():
        print_warning(f"No changelogs directory found ({config['CHANGELOG_DIR']})")
        print()
        return
    
    # Find changelogs modified in the last N days
    days = int(config["CHANGELOG_DAYS"])
    cutoff_time = datetime.now() - timedelta(days=days)
    
    recent_changelogs = []
    for changelog in changelog_dir.glob("CHANGELOG_*.md"):
        if "TEMPLATE" not in changelog.name:
            mtime = datetime.fromtimestamp(changelog.stat().st_mtime)
            if mtime >= cutoff_time:
                recent_changelogs.append((mtime, changelog))
    
    if recent_changelogs:
        print_success(f"Found recent changelogs (last {days} days):")
        for mtime, changelog in sorted(recent_changelogs, reverse=True)[:3]:
            print(f"  📄 {Fore.YELLOW}{changelog.name}{Style.RESET_ALL}")
    else:
        print_warning("No recent changelogs found")
    
    print()


def step_python_environment(config: dict):
    """Step 4: Check Python environment"""
    print_header("🐍 Step 4: Python environment check")
    
    python_cmd = config["PYTHON_CMD"]
    
    # Check if Python is installed
    if not command_exists(python_cmd):
        print_error(f"❌ Python not installed (looking for: {python_cmd})")
        print_warning("💡 Install Python from: https://www.python.org/")
        print_warning("   Recommended version: 3.9 or higher")
        return False
    
    # Get Python version
    exit_code, version = run_command([python_cmd, "--version"])
    if exit_code == 0:
        print_success(f"✅ {version}")
    
    # Check pip
    exit_code, pip_version = run_command([python_cmd, "-m", "pip", "--version"])
    if exit_code == 0:
        pip_ver = pip_version.split()[1] if pip_version else "unknown"
        print_success(f"✅ pip {pip_ver}")
    else:
        print_error("❌ pip not found")
        print_warning(f"💡 Install pip: {python_cmd} -m ensurepip --upgrade")
    
    # Check requirements.txt
    requirements_file = Path(config["REQUIREMENTS_FILE"])
    if not requirements_file.exists():
        print_warning(f"⚠️  {config['REQUIREMENTS_FILE']} not found")
        print()
        return True
    
    print_header("📦 Checking Python dependencies...")
    
    # Check virtual environment
    venv_dir = Path(config["VENV_DIR"])
    if venv_dir.exists():
        print_success(f"✅ Virtual environment found: {config['VENV_DIR']}")
        if platform.system() == "Windows":
            print_warning(f"💡 Remember to activate: {venv_dir}\\Scripts\\activate")
        else:
            print_warning(f"💡 Remember to activate: source {venv_dir}/bin/activate")
    else:
        print_warning(f"⚠️  No virtual environment found at {config['VENV_DIR']}")
        choice = get_user_input(f"{Fore.CYAN}Create virtual environment?{Style.RESET_ALL} (y/n)")
        
        if choice == 'y':
            exit_code, _ = run_command([python_cmd, "-m", "venv", str(venv_dir)])
            if exit_code == 0:
                print_success("✅ Virtual environment created")
                if platform.system() == "Windows":
                    print_header(f"Activate with: {venv_dir}\\Scripts\\activate")
                else:
                    print_header(f"Activate with: source {venv_dir}/bin/activate")
            else:
                print_error("❌ Failed to create virtual environment")
    
    # Ask to update dependencies
    choice = get_user_input(
        f"{Fore.CYAN}Update dependencies from {config['REQUIREMENTS_FILE']}?{Style.RESET_ALL} (y/n)"
    )
    
    if choice == 'y':
        print_warning("Installing dependencies...")
        exit_code, _ = run_command(
            [python_cmd, "-m", "pip", "install", "-r", str(requirements_file)],
            check=False,
            capture=False
        )
        
        if exit_code == 0:
            print_success("✅ Dependencies updated")
        else:
            print_error("❌ Error: pip install failed")
            print_warning(f"💡 Try: {python_cmd} -m pip install --upgrade pip")
    else:
        print_warning("Skipping dependency update")
    
    print()
    return True


def step_branch_check(config: dict):
    """Step 5: Check current branch"""
    if config.get("SKIP_BRANCH_CHECK") == "true":
        print_header("Step 5: Branch check - Skipped")
        print()
        return
    
    print_header("🌿 Step 5: Current branch")
    
    exit_code, current_branch = run_command(["git", "branch", "--show-current"])
    if exit_code != 0:
        print_error("❌ Could not determine current branch")
        print()
        return
    
    print(f"  You are on: {Fore.GREEN}{current_branch}{Style.RESET_ALL}")
    
    # Check if default branch exists
    default_branch = config["DEFAULT_BRANCH"]
    exit_code, _ = run_command(
        ["git", "show-ref", "--verify", f"refs/heads/{default_branch}"],
        check=False
    )
    
    if exit_code == 0:
        if current_branch != default_branch:
            print_warning(f"⚠️  You're not on '{default_branch}' branch")
            choice = get_user_input(
                f"{Fore.CYAN}Switch to {default_branch}?{Style.RESET_ALL} (y/n)"
            )
            
            if choice == 'y':
                run_command(["git", "checkout", default_branch], capture=False)
                print_success(f"✅ Switched to {default_branch}")
        else:
            print_success(f"✅ On default branch ({default_branch})")
    else:
        print_warning(f"Default branch '{default_branch}' not found, staying on {current_branch}")
    
    print()


def print_summary(config: dict):
    """Print summary and next steps"""
    print_header("=" * 40)
    print_success("✅ Morning startup complete!")
    print_header("=" * 40)
    print()
    
    if config.get("SKIP_CHANGELOG_CHECK") != "true":
        print_header("Next steps:")
        print("  1. Review changelogs above (if any)")
    else:
        print_header("Ready to start:")
    
    print(f"  2. Your open issues: {Fore.YELLOW}gh issue list --assignee @me --state open{Style.RESET_ALL}")
    print(f"  3. At end of day: {Fore.YELLOW}python daily\\ routine\\ scripts/end_day.py{Style.RESET_ALL}")
    print()
    
    print_header("Useful commands:")
    print(f"  • {Fore.YELLOW}gh issue view <number>{Style.RESET_ALL} - View issue details")
    python_cmd = config["PYTHON_CMD"]
    print(f"  • {Fore.YELLOW}{python_cmd} -m pytest{Style.RESET_ALL} - Run tests")
    print(f"  • {Fore.YELLOW}{python_cmd} app.py{Style.RESET_ALL} - Run Flask app")
    print()


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point"""
    # Load configuration
    config = load_config()
    
    # Print banner
    print_header("=" * 40)
    print_header(f"🌅 {config['PROJECT_NAME']} - Daily Start")
    print_header("=" * 40)
    print()
    
    # Run steps
    try:
        if not step_git_pull(config):
            sys.exit(1)
        
        step_recent_commits(config)
        step_recent_changelogs(config)
        
        if not step_python_environment(config):
            sys.exit(1)
        
        step_branch_check(config)
        
        print_summary(config)
        
    except KeyboardInterrupt:
        print()
        print_warning("\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
