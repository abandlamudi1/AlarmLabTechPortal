# Daily Routine Scripts

**Daily workflow automation scripts for Lab Tech Portal**

These scripts help you maintain consistent daily workflows, keep your environment updated, and create structured changelogs for team handoffs.

## ⚠️ IMPORTANT: Daily Workflow Requirements

**Before suggesting ANY code changes, ensure the developer has:**
1. ✅ Run the start_day script this morning
2. 📋 Read recent changelogs (last 2-3 days)
3. 📊 Checked the GitHub Project Board for context

**When work is complete, remind developer to:**
1. 🌙 Run the end_day script to create changelog
2. 📝 Document technical decisions in changelog
3. 💾 Commit and push the changelog

## 🖥️ Cross-Platform Support

These scripts now work on **Windows, macOS, and Linux**!

### Running on Windows
```powershell
# PowerShell
python "scripts/daily-routine/start_day.py"
python "scripts/daily-routine/end_day.py"

# Or use batch files
"scripts/daily-routine\start_day.bat"
"scripts/daily-routine\end_day.bat"
```

### Running on macOS/Linux
```bash
# Using Python directly
python3 "scripts/daily-routine/start_day.py"
python3 "scripts/daily-routine/end_day.py"

# Or use bash scripts (legacy - calls Python versions)
./daily\ routine\ scripts/start_day.sh
./daily\ routine\ scripts/end_day.sh
```

### Optional: Copilot/Chat Summary → Changelog

This repo's scripts cannot directly read VS Code Copilot chat history.

Recommended lightweight workflow:
- Ask Copilot to generate a short changelog-ready summary (5–10 bullets + key decisions + commands).
- Copy that summary to your clipboard, then run:
  - **Windows**: `python "scripts/daily-routine/end_day.py" --chat-from-clipboard`
  - **macOS/Linux**: `python3 "scripts/daily-routine/end_day.py" --chat-from-clipboard`

Alternative:
- Save the summary to a file (e.g. `notes/chat_summary.md`) and run:
  - `python "scripts/daily-routine/end_day.py" --chat-file notes/chat_summary.md`

## 📋 Overview

These scripts handle:
- Pulling latest code
- Checking Python environment and dependencies
- Displaying recent commits and changelogs
- Showing GitHub project board status
- Creating structured end-of-day changelogs
- Managing daily workflow

## 🚀 Quick Start

### 1. Configuration Already Set Up

The `.daily-routine-config` file has been created with settings for this project:
- Project: Lab Tech Portal
- GitHub Project: #23
- Python environment checks
- Changelog directory: `changelogs/`

### 2. Install Dependencies

```bash
# Install colorama for cross-platform colored output
pip install colorama

# Or install all requirements
pip install -r requirements.txt
```

### 3. Run Daily Routines

**Windows (PowerShell)**:
```powershell
python "scripts/daily-routine/start_day.py"
python "scripts/daily-routine/end_day.py"
```

**macOS/Linux**:
```bash
python3 "scripts/daily-routine/start_day.py"
python3 "scripts/daily-routine/end_day.py"
```

**Legacy bash scripts** (macOS/Linux - still work but call Python versions):
```bash
chmod +x "scripts/daily-routine"/*.sh
./daily\ routine\ scripts/start_day.sh
./daily\ routine\ scripts/end_day.sh
```

## 📝 Script Descriptions

### start_day.py (Cross-Platform)
**Purpose**: Morning startup routine

**Available scripts**:
- `start_day.py` - Main Python script (works everywhere)
- `start_day.bat` - Windows batch wrapper
- `start_day.sh` - Bash script (legacy, calls Python version)

**What it does**:
1. **Git Pull**: Fetches latest code
2. **Recent Commits**: Shows recent activity (last 5 commits)
3. **Changelogs**: Displays recent changelogs (last 3 days)
4. **Python Environment Check**: 
   - Verifies Python installation
   - Checks pip availability
   - Checks for virtual environment
   - Offers to install/update dependencies from requirements.txt
5. **Connectivity**: Tests service connections (if configured)
6. **Project Board**: Shows GitHub project #23 status
   - **Rich Table Display**: If `rich` library is installed, displays issues in a formatted table with:
     - Issue number in the first column
     - Issue description/title in the second column  
     - Priorpy (Cross-Platform)
**Purpose**: End of day summary and changelog creation

**Available scripts**:
- `end_day.py` - Main Python script (works everywhere)
- `end_day.bat` - Windows batch wrapper  
- `end_day.sh` - Bash script (legacy, calls Python version)
   - **Fallback**: Uses simple text display with `jq` if `rich` is not available
7. **Branch Check**: Verifies you're on the correct branch

### end_day.sh
**Purpose**: End of day summary and changelog creation

**What it does**:
- Creates or appends to daily changelog
- Can include Copilot chat summaries (via clipboard or file)
- Lists commits from today
- Shows working tree status
- Guides you through committing the changelog
- Reminds you to update GitHub issues and project board

**Options**:
- `--append`: Add an update section to existing changelog
- `--chat-from-clipboard`: Include Copilot summary from clipboard
- `--chat-file <path>`: Include Copilot summary from a file

## ⚙️ Configuration

Configuration is stored in `.daily-routine-config`:

```bash
# Project Configuration
PROJECT_NAME="Lab Tech Portal"
GITHUB_ORG="adc-quality"
GITHUB_PROJECT_ID="23"
CHANGELOG_DIR="changelogs"

# Python Environment Settings
PYTHON_CMD="python3"  # or "python"
REQUIREMENTS_FILE="requirements.txt"
VENV_DIR=".venv"

# Optional: Custom scripts
TEST_CONNECTIONS_SCRIPT="scripts/test-connections.py"
```

### Customization Options

You can customize behavior by editing `.daily-routine-config`:

1. **Python Command**: Change `PYTHON_CMD="python"` if needed
2. **Virtual Environment**: Set `VENV_DIR` to your venv location
3. **Connectivity Checks**: Set `ENABLE_CONNECTIVITY_CHECKS="true"` if you have test scripts
4. **Skip Checks**: Add `SKIP_CHANGELOG_CHECK="true"` to skip certain steps

## 🔧 Prerequisites

### Required
- **Git**: Version control
- **Python 3.9+**: Python runtime
- **pip**: Package manager

### Optional (for full functionality)
- **GitHub CLI (gh)**: For project board integration
  ```bash
  # Install via Homebrew (macOS)
  brew install gh
  
  # Authenticate
  gh auth login
  ```
- **rich**: Python library for beautiful table formatting of issues
  ```bash
  pip install rich
  # Or it's included in requirements.txt
  ```
- **jq**: JSON processor (fallback if rich is not installed)
  ```bash
  # macOS
  brew install jq
  ```

## 💡 Best Practices

### Daily Workflow

1. **Start of Day**
   - Run `start_day.sh` first thing in the morning
   - Review the project board priorities shown
   - Check any recent changelogs from team members
   - Activate your virtual environment if prompted

2. **During the Day**
   - Make small, focused commits with descriptive messages
   - Reference issue numbers in commits (e.g., `Fix #123: Description`)
   - Update your working branch regularly

3. **End of Day**
   - Run `end_day.sh` to create your changelog
   - Document what you did and why (technical decisions)
   - Include any commands or steps for reproducing your work
   - Update GitHub issues and project board
   - Push your changes before signing off

### Changelog Best Practices

When filling out your changelog:
- **Be specific**: "Fixed Flask route timeout in /api/inventory" not "Fixed bug"
- **Explain WHY not just WHAT**: Include context for your decisions
- **Include commands**: How to reproduce or test your work
- **Call out breaking changes**: Anything that affects other developers
- **List open questions**: Things you're unsure about or need team input on

### Using Virtual Environments

It's recommended to use Python virtual environments:

```bash
# Create virtual environment
python3 -m venv .venv

# Activate it (macOS/Linux)
source .venv/bin/activate

# Activate it (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

The `start_day.sh` script will detect if you don't have a venv and offer to create one.

## 🐛 Troubleshooting

### Common Issues

#### "Python not found"
**Solution**: 
- Install Python from https://www.python.org/
- Or update `PYTHON_CMD` in `.daily-routine-config` (e.g., to `python` instead of `python3`)

#### "Permission denied"
**Solution**:
```bash
chmod +x "scripts/daily-routine"/*.sh
```

#### "GitHub CLI not authenticated"
**Solution**:
```bash
gh auth login
# Follow the interactive prompts
```

#### "Dependencies installation fails"
**Solution**:
- Check your network connection
- Try upgrading pip: `python3 -m pip install --upgrade pip`
- Activate virtual environment first: `source .venv/bin/activate`

#### "Can't find recent changelogs"
**Solution**:
- Create the changelogs directory: `mkdir changelogs`
- Copy the template: `cp "scripts/daily-routine/CHANGELOG_TEMPLATE.md" changelogs/`

### Debug Mode

Run scripts with debug output:
```bash
bash -x "scripts/daily-routine/start_day.sh"
```

## 📂 File Structure

```
lab-tech-portal/
├── scripts/daily-routine/
│   ├── .daily-routine-config      # Configuration file
│   ├── DAILYROUTE_README.md       # This file
│   ├── start_day.sh               # Morning routine
│   ├── end_day.sh                 # Evening routine
│   └── CHANGELOG_TEMPLATE.md      # Template for changelogs
├── changelogs/                     # Daily changelogs stored here
│   └── CHANGELOG_2026-02-06_username.md
├── requirements.txt                # Python dependencies
├── app.py                          # Main Flask app
└── ...
```

## 🔗 Related Documentation

- [GitHub Project Board #23](https://github.com/orgs/adc-quality/projects/23)
- [Repository Issues](https://github.com/adc-quality/lab-tech-portal/issues)

## 🔐 Security Best Practices

### API Tokens and Credentials

**NEVER commit tokens to version control!**

Store tokens in environment variables or a `.env` file:

```bash
# .env (add to .gitignore!)
JIRA_API_TOKEN=your-token-here
GITHUB_TOKEN=ghp_your-token-here
```

Load in Python:
```python
from dotenv import load_dotenv
load_dotenv()
```

### Recommended .gitignore entries

```gitignore
# Sensitive configuration
.env
.env.local

# Virtual environments
.venv/
venv/
ENV/

# Backup files created by scripts
*.backup
```

## 📊 GitHub Project Board Integration

The scripts integrate with GitHub Project #23:
- View project: https://github.com/orgs/adc-quality/projects/23
- `start_day.sh` shows board status (Todo, In Progress, Done counts)
- `end_day.sh` reminds you to update issues and board

Useful commands:
```bash
# View project board
gh project item-list 23 --owner adc-quality

# List your open issues
gh issue list --assignee @me --state open

# Create new issue
gh issue create --title "Bug: Description" --body "Details"

# Close issue
gh issue close 123 -c "Completed in commit abc123"
```

## 🤝 Contributing

Found a bug or have an improvement? Submit an issue or PR to the repository!

## 🎨 Rich Table Display Feature

The scripts/daily-routine support enhanced visual display of GitHub issues using the `rich` Python library.

### What You Get

When `rich` is installed, the project board display shows a beautiful formatted table:

**Column Layout:**
1. **Issue #** - The GitHub issue number (e.g., #1, #42)
2. **Title** - Full description of the issue
3. **Priority** - Color-coded priority (High/Medium/Low) extracted from labels
4. **Labels** - Other labels assigned to the issue

**Color Coding:**
- 🔴 **High Priority** - Bold red text
- 🟡 **Medium Priority** - Bold yellow text
- 🟢 **Low Priority** - Bold green text

### Setup

```bash
# Install rich (already in requirements.txt)
pip install rich

# Or activate venv and update
source .venv/bin/activate
pip install -r requirements.txt
```

### Usage

The rich display is automatically used when available. You can also run it manually:

```bash
# Display project board in rich table format
python3 "scripts/daily-routine/display_project_board.py" --org adc-quality --project-id 23
```

### Priority Labels

To take advantage of priority display, label your issues with:
- `priority:high` - Shows as red
- `priority:medium` - Shows as yellow  
- `priority:low` - Shows as green

**Example:**
```bash
gh issue create --title "Critical bug fix" --body "Details" --label "bug,priority:high"
```

## 💡 Tips for Copilot Integration

When working with GitHub Copilot:

1. **At start of day**: After running `start_day.sh`, tell Copilot:
   - "I just ran the morning startup script"
   - "Here are the recent changelogs: [paste relevant ones]"
   - "My focus today is: [your task from project board]"

2. **During development**: Ask Copilot for help:
   - "Generate a changelog summary for today's work"
   - "What are the key decisions I should document?"
   - "Summarize the changes we made in bullet points"

3. **End of day**: Ask Copilot:
   - "Create a 5-10 bullet changelog of today's work including technical decisions and key commands"
   - Copy the response and use `--chat-from-clipboard` option

This creates a feedback loop where Copilot helps you document your work consistently!


