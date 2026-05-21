#!/bin/bash
# End of day routine - Create changelog for handoff
# Lab Tech Portal - Daily Summary Script

set -e  # Exit on error

APPEND_MODE=false
CHAT_FROM_CLIPBOARD=false
CHAT_SUMMARY_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --append)
            APPEND_MODE=true
            shift
            ;;
        --chat-from-clipboard)
            CHAT_FROM_CLIPBOARD=true
            shift
            ;;
        --chat-file)
            CHAT_SUMMARY_FILE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--append] [--chat-from-clipboard] [--chat-file <path>]"
            echo ""
            echo "  --append              Append a new update section if today's changelog exists"
            echo "  --chat-from-clipboard  Include a Copilot/chat summary from clipboard (macOS: pbpaste)"
            echo "  --chat-file <path>     Include a Copilot/chat summary from a file"
            echo ""
            echo "Examples:"
            echo "  ./end_day.sh                        # Create new changelog"
            echo "  ./end_day.sh --append               # Add update to existing changelog"
            echo "  ./end_day.sh --chat-from-clipboard  # Include AI chat summary"
            exit 0
            ;;
        *)
            echo -e "\033[0;31m❌ Unknown argument: $1\033[0m"
            echo "Run with --help for usage."
            exit 2
            ;;
    esac
done

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}🌙 Lab Tech Portal - End of Day${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Get contributor name from git config
CONTRIBUTOR=$(git config user.name | tr ' ' '_')
if [ -z "$CONTRIBUTOR" ]; then
    echo -e "${RED}❌ Error: Could not get user name from git config${NC}"
    echo -e "${YELLOW}💡 Set it with: git config user.name \"Your Name\"${NC}"
    exit 1
fi

DATE=$(date +%Y-%m-%d)
CHANGELOG_FILE="changelogs/CHANGELOG_${DATE}_${CONTRIBUTOR}.md"
CURRENT_BRANCH=$(git branch --show-current)

if [ -z "$CURRENT_BRANCH" ]; then
    echo -e "${RED}❌ Error: Could not determine current branch${NC}"
    echo -e "${YELLOW}💡 You may be in detached HEAD state${NC}"
    exit 1
fi

# Check if changelog already exists
if [ -f "$CHANGELOG_FILE" ]; then
    if [ "$APPEND_MODE" = true ]; then
        echo -e "${GREEN}Appending an update section to existing changelog...${NC}"
    else
        echo -e "${YELLOW}⚠️  Changelog already exists for today: $CHANGELOG_FILE${NC}"
        echo -e "${CYAN}Choose an action:${NC}"
        echo "  [a] Append update section"
        echo "  [e] Edit existing changelog"
        echo "  [o] Overwrite from template"
        echo "  [q] Quit"
        read -p "Choice (a/e/o/q): " ACTION

        case "$ACTION" in
            a|A)
                APPEND_MODE=true
                ;;
            e|E)
                echo -e "${GREEN}Opening existing changelog for editing...${NC}"
                ${EDITOR:-code} "$CHANGELOG_FILE"
                exit 0
                ;;
            o|O)
                echo -e "${YELLOW}Overwriting changelog from template...${NC}"
                ;;
            q|Q)
                echo "Aborted."
                exit 0
                ;;
            *)
                echo "Invalid choice. Aborted."
                exit 2
                ;;
        esac
    fi
fi

mkdir -p changelogs

if [ -f "$CHANGELOG_FILE" ] && [ "$APPEND_MODE" = true ]; then
    NOW="$(date +%H:%M)"

    {
        echo ""
        echo "---"
        echo ""
        echo "## Update - ${DATE} ${NOW}"
        echo ""
        echo "**Quick Summary**: [One sentence describing this update]"
        echo ""
        if [ -n "$CHAT_SUMMARY_FILE" ] || [ "$CHAT_FROM_CLIPBOARD" = true ]; then
            echo "### Copilot/Chat Summary"
            echo ""
            if [ -n "$CHAT_SUMMARY_FILE" ]; then
                if [ -f "$CHAT_SUMMARY_FILE" ]; then
                    cat "$CHAT_SUMMARY_FILE"
                else
                    echo "(Chat summary file not found: $CHAT_SUMMARY_FILE)"
                fi
            elif [ "$CHAT_FROM_CLIPBOARD" = true ]; then
                if command -v pbpaste >/dev/null 2>&1; then
                    pbpaste
                else
                    echo "(Clipboard summary requested but 'pbpaste' not available.)"
                fi
            fi
            echo ""
        else
            echo "### Notes"
            echo "- [ ] [Add notes here]"
            echo ""
        fi

        echo "### Commits Since Midnight"
        echo ""
        git log --since="midnight" --oneline --author="$(git config user.email)" | sed 's/^/- /' || true
        echo ""
        echo "### Working Tree Status"
        echo ""
        git status --porcelain | sed 's/^/- /' || true
        echo ""
    } >> "$CHANGELOG_FILE"
else
    # Create changelog from template
    cp changelogs/CHANGELOG_TEMPLATE.md "$CHANGELOG_FILE"

    # Replace placeholders
    sed -i.bak "s/\\[DATE\\]/$DATE/g" "$CHANGELOG_FILE"
    sed -i.bak "s/\\[CONTRIBUTOR\\]/$CONTRIBUTOR/g" "$CHANGELOG_FILE"
    rm "${CHANGELOG_FILE}.bak"

    # Get commit range for today
    COMMITS_TODAY=$(git log --since="midnight" --oneline --author="$(git config user.email)" | wc -l | xargs)
    if [ "$COMMITS_TODAY" -gt 0 ]; then
        echo -e "${GREEN}Found $COMMITS_TODAY commits from you today${NC}"
        FIRST_COMMIT=$(git log --since="midnight" --author="$(git config user.email)" --reverse --format="%h" | head -1)
        LAST_COMMIT=$(git log --since="midnight" --author="$(git config user.email)" --format="%h" | head -1)

        # Update commit range in changelog
        sed -i.bak "s/\\[commit hash\\] to \\[commit hash\\]/$FIRST_COMMIT to $LAST_COMMIT/g" "$CHANGELOG_FILE"
        rm "${CHANGELOG_FILE}.bak"
    fi

    sed -i.bak "s/\\[branch name\\]/$CURRENT_BRANCH/g" "$CHANGELOG_FILE"
    rm "${CHANGELOG_FILE}.bak"

    echo -e "${CYAN}========================================${NC}"
    echo -e "${GREEN}✅ Changelog template created!${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}Opening changelog for you to fill in: $CHANGELOG_FILE${NC}"
    echo ""
    echo -e "${CYAN}Tips for writing a good changelog:${NC}"
    echo -e "  • Be specific: 'Fixed login timeout' not 'Fixed bug'"
    echo -e "  • Explain WHY not just WHAT"
    echo -e "  • Include commands to reproduce your work"
    echo -e "  • Call out breaking changes"
    echo -e "  • List open questions for the team"
    echo ""
    echo -e "${YELLOW}⚠️  ARCHITECTURE CHECK:${NC}"
    echo -e "  Did you change how the pipeline works (new phases, changed data flow)?"
    echo -e "  If YES → Update ${CYAN}docs/ARCHITECTURE.md${NC} and set 'Last Verified' date"
    echo ""
fi

echo -e "${YELLOW}🧾 ISSUE / PROJECT BOARD CHECK:${NC}"
echo -e "  Before you finish for the day, close/update any GitHub Issues you worked on and confirm project-board status."
echo -e "  Suggested commands:"
echo -e "    - ${YELLOW}gh issue list --assignee @me --state open${NC}"
echo -e "    - ${YELLOW}gh project item-list 23 --owner adc-quality${NC}  (view project board)"
echo -e "    - ${YELLOW}gh issue close <number> -c \"Completed\"${NC}  (close issue)"
echo ""
echo -e "${GREEN}💡 CREATE ISSUE FOR TOMORROW:${NC}"
echo -e "  If you have a clear next task, create it and add to Project #23:"
echo -e "    ${YELLOW}gh issue create --title \"[Your Task]\" --body \"Description\" --repo adc-quality/lab-tech-portal${NC}"
echo -e "  Or save your notes to a file and create the issue in the morning."
echo ""
echo -e "${CYAN}When done:${NC}"
echo -e "  1. Save and close the changelog"
echo -e "  2. Commit it: ${YELLOW}git add $CHANGELOG_FILE && git commit -m \"docs: add changelog for $DATE\"${NC}"
echo -e "  3. Push: ${YELLOW}git push origin $CURRENT_BRANCH${NC}"
echo ""

# Open in editor
${EDITOR:-code} "$CHANGELOG_FILE"
