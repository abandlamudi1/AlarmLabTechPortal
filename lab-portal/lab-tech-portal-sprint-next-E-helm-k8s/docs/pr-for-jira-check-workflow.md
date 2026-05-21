# PR Runbook: Add Jira Status Check Workflow

This runbook covers creating a pull request for adding [.github/workflows/jira-check.yml](.github/workflows/jira-check.yml).

## 1. Start-of-day project workflow checks

Run these first if you have not done them yet today.

./daily\ routine\ scripts/start_day.sh

Then review:
- recent files in [changelogs](changelogs)
- project board: https://github.com/orgs/adc-quality/projects/23

## 2. Sync local master and create a feature branch

git checkout master
git pull origin master
git checkout -b chore/add-jira-status-check-workflow

## 3. Verify the workflow file is present

ls .github/workflows/jira-check.yml

## 4. Validate YAML syntax

Ensure PyYAML is installed in the active project virtual environment first:

python -m pip install PyYAML

python -c "import yaml, pathlib; p=pathlib.Path('.github/workflows/jira-check.yml'); yaml.safe_load(p.read_text()); print('YAML parse OK:', p)"

## 5. Inspect change and stage only this file

git status
git diff -- .github/workflows/jira-check.yml
git add .github/workflows/jira-check.yml
git status

## 6. Commit

git commit -m "ci: add Jira status check workflow for pull requests"

## 7. Push branch

git push -u origin chore/add-jira-status-check-workflow

## 8. Create PR with GitHub CLI

gh pr create \
  --base master \
  --head chore/add-jira-status-check-workflow \
  --title "ci: add Jira status check workflow" \
  --body-file - <<'EOF'
## Summary
- Add [.github/workflows/jira-check.yml](.github/workflows/jira-check.yml)
- Trigger on opened, synchronize, reopened, edited pull request events
- Reuse adc-quality reusable Jira status workflow
- Pass JIRA_TOKEN from repository secrets

## Why
- Ensure Jira status validation runs automatically on PR changes.

## Validation
- YAML parsed locally
- File path and trigger checked

## Checklist
- [ ] JIRA_TOKEN exists in repository Actions secrets
- [ ] Check appears in PR status checks
EOF

Confirm it was created:

gh pr view --web

## 9. Optional: open PR in browser and edit body manually

gh pr create --web --base master --head chore/add-jira-status-check-workflow

## 10. Verify checks and repository secret

- In PR checks, confirm Jira Status Check is running.
- In repository settings, confirm Actions secret JIRA_TOKEN exists.

## 11. After merge

- Confirm file exists on master: [.github/workflows/jira-check.yml](.github/workflows/jira-check.yml)
- Watch the next PR event to confirm this check runs normally.

## 12. End-of-day workflow

./daily\ routine\ scripts/end_day.sh

Then:
- document technical decisions in [changelogs](changelogs)
- commit and push changelog with message format: docs: add changelog for YYYY-MM-DD
- update linked issues and Project Board #23
