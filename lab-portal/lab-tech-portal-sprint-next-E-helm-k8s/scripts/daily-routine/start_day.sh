#!/bin/bash
# Morning startup routine for Lab Tech Portal
# This script automates daily handoff and project status checks

set -e  # Exit on error

# =============================================================================
# CONFIGURATION - Load from .daily-routine-config or use defaults
# =============================================================================

# Try to load configuration file from the parent directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/.daily-routine-config"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# Default configuration values (override in .daily-routine-config)
PROJECT_NAME="${PROJECT_NAME:-Lab Tech Portal}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-master}"
CHANGELOG_DIR="${CHANGELOG_DIR:-changelogs}"
SCRIPTS_DIR="${SCRIPTS_DIR:-scripts}"
PYTHON_CMD="${PYTHON_CMD:-python3}"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-requirements.txt}"
VENV_DIR="${VENV_DIR:-.venv}"
ENABLE_CONNECTIVITY_CHECKS="${ENABLE_CONNECTIVITY_CHECKS:-false}"
TEST_CONNECTIONS_SCRIPT="${TEST_CONNECTIONS_SCRIPT:-scripts/test-connections.py}"
RECENT_COMMITS="${RECENT_COMMITS:-5}"
CHANGELOG_DAYS="${CHANGELOG_DAYS:-3}"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

is_windows() {
    case "$OSTYPE" in
        msys*|cygwin*|win32*) return 0 ;;
        *) return 1 ;;
    esac
}

command_exists() {
    command -v "$1" &> /dev/null
}

# =============================================================================
# COLORS
# =============================================================================

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# =============================================================================
# STARTUP BANNER
# =============================================================================

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}🌅 ${PROJECT_NAME} - Daily Start${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# 1. Git Pull
echo -e "${CYAN}📥 Step 1: Pulling latest changes...${NC}"
git fetch origin
CURRENT_BRANCH=$(git branch --show-current)

if [ -z "$CURRENT_BRANCH" ]; then
    echo -e "${RED}❌ Error: Could not determine current branch${NC}"
    echo -e "${YELLOW}💡 You may be in detached HEAD state. Check: git status${NC}"
    exit 1
fi

BEHIND=$(git rev-list HEAD..origin/$CURRENT_BRANCH --count 2>/dev/null || echo "0")

if [ "$BEHIND" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  You are $BEHIND commits behind origin/$CURRENT_BRANCH${NC}"
    echo -e "${CYAN}Pulling changes...${NC}"
    if git pull --rebase origin $CURRENT_BRANCH; then
        echo -e "${GREEN}✅ Changes pulled successfully${NC}"
    else
        echo -e "${RED}❌ Error: Git pull failed${NC}"
        echo -e "${YELLOW}💡 Try resolving conflicts or run: git pull --no-rebase${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Already up to date${NC}"
fi
echo ""

# 2. Show Recent Commits
echo -e "${CYAN}📝 Step 2: Recent commits (last ${RECENT_COMMITS})${NC}"
git log --oneline -${RECENT_COMMITS} --decorate --color=always
echo ""

# 3. Find and Display Recent Changelogs (if configured)
if [ "${SKIP_CHANGELOG_CHECK}" != "true" ] && [ -n "$CHANGELOG_DIR" ]; then
    echo -e "${CYAN}📋 Step 3: Recent changelogs${NC}"
    if [ -d "$CHANGELOG_DIR" ]; then
        RECENT_CHANGELOGS=$(find "$CHANGELOG_DIR" -name "CHANGELOG_*.md" -not -name "*TEMPLATE*" -mtime -${CHANGELOG_DAYS} 2>/dev/null | sort -r | head -3 || echo "")

        if [ -n "$RECENT_CHANGELOGS" ]; then
            echo -e "${GREEN}Found recent changelogs (last 3 days):${NC}"
            echo "$RECENT_CHANGELOGS" | while read -r file; do
                echo -e "  📄 ${YELLOW}$(basename "$file")${NC}"
            done
        else
            echo -e "${YELLOW}No recent changelogs found${NC}"
        fi
    else
        echo -e "${YELLOW}No changelogs directory found ($CHANGELOG_DIR)${NC}"
    fi
    echo ""
else
    echo -e "${CYAN}Step 3: Changelogs${NC} - ${YELLOW}Skipped (not configured)${NC}"
    echo ""
fi

# 4. Check Python Environment
echo -e "${CYAN}🐍 Step 4: Python environment check${NC}"

# Check if Python is installed
if command_exists "$PYTHON_CMD"; then
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
    echo -e "${GREEN}✅ $PYTHON_VERSION${NC}"
    
    # Check pip
    if $PYTHON_CMD -m pip --version &> /dev/null; then
        PIP_VERSION=$($PYTHON_CMD -m pip --version | awk '{print $2}')
        echo -e "${GREEN}✅ pip $PIP_VERSION${NC}"
    else
        echo -e "${RED}❌ pip not found${NC}"
        echo -e "${YELLOW}💡 Install pip: $PYTHON_CMD -m ensurepip --upgrade${NC}"
    fi

    # Check if requirements.txt exists
    if [ -f "$REQUIREMENTS_FILE" ]; then
        echo -e "${CYAN}📦 Checking Python dependencies...${NC}"
        
        # Check if virtual environment exists
        if [ -d "$VENV_DIR" ]; then
            echo -e "${GREEN}✅ Virtual environment found: $VENV_DIR${NC}"
            echo -e "${YELLOW}💡 Remember to activate: source $VENV_DIR/bin/activate${NC}"
        else
            echo -e "${YELLOW}⚠️  No virtual environment found at $VENV_DIR${NC}"
            echo -e "${CYAN}Create virtual environment?${NC} (y/n)"
            read -p "Choice: " CREATE_VENV
            if [ "$CREATE_VENV" = "y" ]; then
                if $PYTHON_CMD -m venv "$VENV_DIR"; then
                    echo -e "${GREEN}✅ Virtual environment created${NC}"
                    echo -e "${CYAN}Activate with: source $VENV_DIR/bin/activate${NC}"
                else
                    echo -e "${RED}❌ Failed to create virtual environment${NC}"
                fi
            fi
        fi
        
        # Try to install/update dependencies if pip-tools or just pip
        echo -e "${CYAN}Update dependencies from $REQUIREMENTS_FILE?${NC} (y/n)"
        read -p "Choice: " UPDATE_DEPS
        if [ "$UPDATE_DEPS" = "y" ]; then
            if [ -d "$VENV_DIR" ]; then
                echo -e "${YELLOW}Installing in virtual environment...${NC}"
                source "$VENV_DIR/bin/activate"
            fi
            
            if $PYTHON_CMD -m pip install -r "$REQUIREMENTS_FILE"; then
                echo -e "${GREEN}✅ Dependencies updated${NC}"
            else
                echo -e "${RED}❌ Error: pip install failed${NC}"
                echo -e "${YELLOW}💡 Try: $PYTHON_CMD -m pip install --upgrade pip${NC}"
                echo -e "${YELLOW}💡 Or check your network connection${NC}"
            fi
        else
            echo -e "${YELLOW}Skipping dependency update${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  $REQUIREMENTS_FILE not found${NC}"
    fi
else
    echo -e "${RED}❌ Python not installed (looking for: $PYTHON_CMD)${NC}"
    echo -e "${YELLOW}💡 Install Python from: https://www.python.org/${NC}"
    echo -e "${YELLOW}   Recommended version: 3.9 or higher${NC}"
    echo -e "${YELLOW}   Or update PYTHON_CMD in .daily-routine-config${NC}"
    exit 1
fi
echo ""

# 4a. Check Connectivity (Jira, Confluence, etc.) - Optional
if [ "${ENABLE_CONNECTIVITY_CHECKS}" = "true" ] && [ "${SKIP_CONNECTIVITY}" != "true" ]; then
    echo -e "${CYAN}🔌 Step 4a: Checking service connectivity${NC}"

    # Check if test script exists
    if [ -f "$TEST_CONNECTIONS_SCRIPT" ]; then
        echo -e "${CYAN}  Running connectivity tests...${NC}"
        if $PYTHON_CMD "$TEST_CONNECTIONS_SCRIPT" > /dev/null 2>&1; then
            echo -e "${GREEN}  ✅ Connectivity checks passed${NC}"
        else
            echo -e "${YELLOW}  ⚠️  Some connectivity checks failed${NC}"
            echo -e "${YELLOW}     💡 Check .env configuration (API tokens)${NC}"
            echo -e "${YELLOW}     💡 Verify network/VPN connection${NC}"
            echo -e "${YELLOW}     💡 Run manually: $PYTHON_CMD $TEST_CONNECTIONS_SCRIPT${NC}"
        fi
    else
        echo -e "${YELLOW}  ⚠️  Connectivity test script not found: $TEST_CONNECTIONS_SCRIPT${NC}"
        echo -e "${YELLOW}     💡 Create this script or disable checks with:${NC}"
        echo -e "${YELLOW}        ENABLE_CONNECTIVITY_CHECKS=\"false\" in .daily-routine-config${NC}"
    fi

    echo ""
else
    echo -e "${CYAN}Step 4a: Connectivity checks${NC} - ${YELLOW}Skipped (disabled)${NC}"
    echo ""
fi


# 5. Show Current Branch
if [ "${SKIP_BRANCH_CHECK}" != "true" ]; then
    echo -e "${CYAN}🌿 Step 5: Current branch${NC}"
    CURRENT_BRANCH=$(git branch --show-current)
    echo -e "  You are on: ${GREEN}$CURRENT_BRANCH${NC}"

    # Check if we should be on default branch
    if git show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH"; then
        if [ "$CURRENT_BRANCH" != "$DEFAULT_BRANCH" ]; then
            echo -e "${YELLOW}⚠️  You're not on '$DEFAULT_BRANCH' branch${NC}"
            echo -e "${CYAN}Switch to $DEFAULT_BRANCH?${NC} (y/n)"
            read -p "Choice: " SWITCH_BRANCH
            if [ "$SWITCH_BRANCH" = "y" ]; then
                git checkout "$DEFAULT_BRANCH"
                echo -e "${GREEN}✅ Switched to $DEFAULT_BRANCH${NC}"
            fi
        else
            echo -e "${GREEN}✅ On default branch ($DEFAULT_BRANCH)${NC}"
        fi
    else
        echo -e "${YELLOW}Default branch '$DEFAULT_BRANCH' not found, staying on $CURRENT_BRANCH${NC}"
    fi
    echo ""
else
    echo -e "${CYAN}Step 5: Branch check${NC} - ${YELLOW}Skipped${NC}"
    echo ""
fi

# 7. Summary
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}✅ Morning startup complete!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

if [ "${SKIP_CHANGELOG_CHECK}" != "true" ] && [ -n "$CHANGELOG_DIR" ]; then
    echo -e "${CYAN}Next steps:${NC}"
    echo -e "  1. Review changelogs above (if any)"
else
    echo -e "${CYAN}Ready to start:${NC}"
fi

echo -e "  2. Your open issues: ${YELLOW}gh issue list --assignee @me --state open${NC}"
echo -e "  3. At end of day: ${YELLOW}./daily\\ routine\\ scripts/end_day.sh${NC}"
echo ""

echo -e "${CYAN}Useful commands:${NC}"
echo -e "  • ${YELLOW}gh issue view <number>${NC} - View issue details"
echo -e "  • ${YELLOW}$PYTHON_CMD -m pytest${NC} - Run tests"
echo -e "  • ${YELLOW}$PYTHON_CMD app.py${NC} - Run Flask app"
echo ""
