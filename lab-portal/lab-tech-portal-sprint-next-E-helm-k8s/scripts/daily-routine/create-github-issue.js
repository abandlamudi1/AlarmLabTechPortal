#!/usr/bin/env node
/**
 * Create GitHub issue and automatically add to project board
 *
 * Node.js version for system-quality-quarterly-linking
 *
 * Usage:
 *   node "scripts/daily-routine/create-github-issue.js" --title "My Issue" --body "Description"
 *   node "scripts/daily-routine/create-github-issue.js" --title "My Issue" --body-file issue.md
 *   node "scripts/daily-routine/create-github-issue.js" --title "My Issue" --body-file issue.md --labels "bug,enhancement"
 *   node "scripts/daily-routine/create-github-issue.js" --batch issues.json
 */

const { execSync, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Configuration
const REPO_OWNER = 'adc-quality';
const REPO_NAME = 'jira-config';
const PROJECT_NUMBER = 15;

// Colors for terminal output
const colors = {
  cyan: '\x1b[36m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
  reset: '\x1b[0m',
};

/**
 * Run gh CLI command and return output
 */
function runGh(args, returnJson = false) {
  try {
    const result = execFileSync('gh', args, { encoding: 'utf8' });
    return returnJson ? JSON.parse(result) : result;
  } catch (error) {
    console.error(`${colors.red}❌ Command failed: gh ${args.join(' ')}${colors.reset}`);
    console.error(`${colors.red}${error.message}${colors.reset}`);
    throw error;
  }
}

/**
 * Execute GraphQL query via gh CLI
 */
function ghGraphql(query, variables = {}) {
  // Remove extra whitespace and newlines from query
  const cleanQuery = query.replace(/\s+/g, ' ').trim();
  
  const args = ['api', 'graphql', '-f', `query=${cleanQuery}`];

  for (const [key, value] of Object.entries(variables)) {
    if (typeof value === 'string') {
      args.push('-f', `${key}=${value}`);
    } else {
      args.push('-F', `${key}=${value}`);
    }
  }

  return runGh(args, true);
}

/**
 * Get repository node ID
 */
function getRepoId() {
  const query = `
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        id
      }
    }
  `;
  const data = ghGraphql(query, { owner: REPO_OWNER, name: REPO_NAME });
  return data.data.repository.id;
}

/**
 * Get project node ID
 */
function getProjectId() {
  const query = `
    query($org: String!, $num: Int!) {
      organization(login: $org) {
        projectV2(number: $num) {
          id
        }
      }
    }
  `;
  const data = ghGraphql(query, { org: REPO_OWNER, num: PROJECT_NUMBER });
  return data.data.organization.projectV2.id;
}

/**
 * Find existing issue by title
 */
function findIssueByTitle(title) {
  const queryStr = `repo:${REPO_OWNER}/${REPO_NAME} in:title "${title}" type:issue`;
  const query = `
    query($q: String!) {
      search(type: ISSUE, query: $q, first: 10) {
        nodes {
          ... on Issue {
            id
            number
            title
            url
          }
        }
      }
    }
  `;
  const data = ghGraphql(query, { q: queryStr });
  const nodes = data.data.search.nodes;

  for (const node of nodes) {
    if (node.title === title) {
      return node;
    }
  }
  return null;
}

/**
 * Create a new GitHub issue
 */
function createIssue(repoId, title, body) {
  const query = `
    mutation($repo: ID!, $title: String!, $body: String!) {
      createIssue(input: {repositoryId: $repo, title: $title, body: $body}) {
        issue {
          id
          number
          title
          url
        }
      }
    }
  `;
  const data = ghGraphql(query, { repo: repoId, title, body });
  return data.data.createIssue.issue;
}

/**
 * Add labels to an issue
 */
function addLabels(issueNumber, labels) {
  if (!labels || labels.length === 0) return;

  for (const label of labels) {
    try {
      runGh(`issue edit ${issueNumber} --repo ${REPO_OWNER}/${REPO_NAME} --add-label "${label}"`);
    } catch (error) {
      console.log(
        `${colors.yellow}⚠️  Label '${label}' not found or couldn't be added${colors.reset}`
      );
    }
  }
}

/**
 * Add issue to project
 */
function addIssueToProject(projectId, issueId) {
  const query = `
    mutation($project: ID!, $content: ID!) {
      addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
        item {
          id
        }
      }
    }
  `;
  const data = ghGraphql(query, { project: projectId, content: issueId });
  return data.data.addProjectV2ItemById.item.id;
}

/**
 * Create a single issue with all options
 */
function createSingleIssue(options) {
  const { title, body, labels = [], skipProject = false, checkExisting = true } = options;

  // Check for existing issue
  if (checkExisting) {
    const existing = findIssueByTitle(title);
    if (existing) {
      console.log(
        `${colors.yellow}⚠️  Issue already exists: #${existing.number} - ${title}${colors.reset}`
      );
      console.log(`   ${existing.url}`);
      return null;
    }
  }

  // Get repo ID and create issue
  const repoId = getRepoId();
  const issue = createIssue(repoId, title, body);
  console.log(`${colors.green}✅ Created #${issue.number}: ${title}${colors.reset}`);
  console.log(`   ${issue.url}`);

  // Add labels
  if (labels.length > 0) {
    addLabels(issue.number, labels);
    console.log(`   🏷️  Labels: ${labels.join(', ')}`);
  }

  // Add to project
  if (!skipProject) {
    try {
      const projectId = getProjectId();
      addIssueToProject(projectId, issue.id);
      console.log(`   📌 Added to Project #${PROJECT_NUMBER}`);
    } catch (error) {
      console.log(`${colors.yellow}⚠️  Could not add to project: ${error.message}${colors.reset}`);
    }
  }

  return issue;
}

/**
 * Batch create issues from JSON file
 */
function batchCreateIssues(batchFile, checkExisting = true) {
  const data = JSON.parse(fs.readFileSync(batchFile, 'utf8'));
  const issues = Array.isArray(data) ? data : [data];

  console.log(`${colors.cyan}📦 Batch creating ${issues.length} issue(s)...${colors.reset}\n`);

  let created = 0;
  let skipped = 0;

  for (const issueData of issues) {
    const { title, body = '', labels = [] } = issueData;

    if (!title) {
      console.log(`${colors.red}❌ Issue missing title, skipping${colors.reset}`);
      continue;
    }

    const result = createSingleIssue({ title, body, labels, checkExisting });
    if (result) {
      created++;
    } else {
      skipped++;
    }
    console.log();
  }

  console.log(`\n${colors.green}🎉 Done! Created: ${created}, Skipped: ${skipped}${colors.reset}`);
}

/**
 * Parse command line arguments
 */
function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    title: null,
    body: null,
    bodyFile: null,
    labels: [],
    batch: null,
    skipProject: false,
    noCheck: false,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    const next = args[i + 1];

    switch (arg) {
      case '--title':
        options.title = next;
        i++;
        break;
      case '--body':
        options.body = next;
        i++;
        break;
      case '--body-file':
        options.bodyFile = next;
        i++;
        break;
      case '--labels':
        options.labels = next.split(',').map((l) => l.trim());
        i++;
        break;
      case '--batch':
        options.batch = next;
        i++;
        break;
      case '--skip-project':
        options.skipProject = true;
        break;
      case '--no-check':
        options.noCheck = true;
        break;
      case '--help':
      case '-h':
        showHelp();
        process.exit(0);
    }
  }

  return options;
}

/**
 * Show help message
 */
function showHelp() {
  console.log(`
Create GitHub issue and add to project board

Usage:
  node "scripts/daily-routine/create-github-issue.js" --title "Issue Title" --body "Description"
  node "scripts/daily-routine/create-github-issue.js" --title "Issue Title" --body-file issue.md
  node "scripts/daily-routine/create-github-issue.js" --batch issues.json

Options:
  --title <text>        Issue title
  --body <text>         Issue body text
  --body-file <path>    Read body from file
  --labels <list>       Comma-separated labels (e.g., "bug,enhancement")
  --batch <file>        Batch create from JSON file
  --skip-project        Don't add to project board
  --no-check            Don't check for existing issues
  --help, -h            Show this help message

Examples:
  # Create simple issue
  node "scripts/daily-routine/create-github-issue.js" --title "Fix bug" --body "Description here"
  
  # With labels
  node "scripts/daily-routine/create-github-issue.js" --title "New feature" --body-file feature.md --labels "enhancement,priority:high"
  
  # Batch create
  node "scripts/daily-routine/create-github-issue.js" --batch issues.json
`);
}

/**
 * Main function
 */
function main() {
  const options = parseArgs();

  // Batch mode
  if (options.batch) {
    if (!fs.existsSync(options.batch)) {
      console.error(`${colors.red}❌ Batch file not found: ${options.batch}${colors.reset}`);
      process.exit(1);
    }
    batchCreateIssues(options.batch, !options.noCheck);
    return;
  }

  // Single issue mode
  if (!options.title) {
    console.error(`${colors.red}❌ Title is required. Use --help for usage.${colors.reset}`);
    process.exit(1);
  }

  let body = options.body;
  if (options.bodyFile) {
    if (!fs.existsSync(options.bodyFile)) {
      console.error(`${colors.red}❌ Body file not found: ${options.bodyFile}${colors.reset}`);
      process.exit(1);
    }
    body = fs.readFileSync(options.bodyFile, 'utf8');
  }

  createSingleIssue({
    title: options.title,
    body: body || '',
    labels: options.labels,
    skipProject: options.skipProject,
    checkExisting: !options.noCheck,
  });
}

// Run if executed directly
if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(`${colors.red}❌ Error: ${error.message}${colors.reset}`);
    process.exit(1);
  }
}

module.exports = { createSingleIssue, batchCreateIssues };
