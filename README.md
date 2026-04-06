# Skills

Forget about MCP; use command-line tools and tailor context to the task at hand.
Use with Codex or Claude Code.

## Install

    $ git clone git@github.com:bkircher/skills.git ~/.codex/skills

… or something like this. You can also clone somewhere else and symlink to the
agent-specific directories.

## Test

Start Codex like normal:

    $ codex -m gpt-5.3

(before Codex version 0.80.0, pass `--enable skills` feature flag):

    $ codex --enable skills -m gpt-5.2

Then, when prompted:

    > list skills

Should output something like:

```raw
• Available skills:

  - english-text-editor
  - gh-address-comments
  - gh-code-review
  - gh-run-failure
  - git-commit-message
  - jira-read-ticket
  - skill-creator
  - skill-installer
```

## Use with Codex

Skills are still a work in progress (as of Codex 0.72.0). Run Codex with:
`codex --enable skills`. For example:

    $ codex --enable skills -m gpt-5.2-codex -s workspace-write -a on-request

Tested with:

    $ codex --version
    codex-cli 0.72.0

## Use with Claude Code

Claude Code does skills out of the box. Make sure they are installed, e.g.,

    $ cd ~/.claude
    $ ln -s $HOME/.codex/skills skills

Then in Claude CLI:

```raw
> list skills

⏺ Here are the available skills:

  GitHub & Git:
  - gh-address-comments - Help address review/issue comments on the open GitHub PR for the current branch
  - gh-code-review - Conduct a thorough and in-depth code review for a PR on GitHub
  - gh-run-failure - Analyze failures in GitHub pipelines or jobs
  - git-commit-message - Formulate a git commit message

  Text & Documentation:
  - english-text-editor - Suggests improvements for English language text (spelling, wording)

  Project Management:
  - jira-read-ticket - Read Jira ticket description, comments, and details

  You can invoke any skill using the / prefix, for example: /gh-code-review or /git-commit-message
```

## List of skills

List of skills:

┌─────────────────────┬───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┐
│ Skill │ Description │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ english-text-editor │ Suggests improvements for English language text (spelling, wording) │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ gh-address-comments │ Address review/issue comments on open GitHub PR for current branch [Source](https://github.com/openai/skills/tree/main/skills/.curated/gh-address-comments) │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ gh-code-review │ Conduct thorough code review for a GitHub PR │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ gh-run-failure │ Analyze failures in GitHub pipelines or jobs │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ git-commit-message │ Formulate a git commit message │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ confluence-read │ Search Confluence pages and fetch page content │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ jira-read-ticket │ Pull description, comments, or more from a Jira ticket │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ jira-write-ticket │ Write a Jira ticket │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ postgresql-table-design │ Design and optimize PostgreSQL schemas │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ terraform │ Help when writing Terraform or OpenTofu [Source](https://github.com/antonbabenko/terraform-skill) │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ unit-testing │ Help when writing or updating unit tests │
├─────────────────────┼───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┤
│ playwright-cli │ Automate browser interactions, test web pages, and work with Playwright tests (added 2026-04-06, Apache-2.0) │
└─────────────────────┴───────────────────────────────────────────────────────────----------------------------------------------------------------------------------------──────────┘

## Create your own skills

    $ mkdir -p ~/.codex/skills/<my-name>
    $ curl -fsSL \
        https://raw.githubusercontent.com/anthropics/skills/refs/heads/main/template/SKILL.md \
        -o ~/.codex/skills/<my-name>/SKILL.md

## Links

General:

- <https://agentskills.io/home>
- <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview>
- <https://simonwillison.net/2025/Dec/12/openai-skills/>
- <https://github.com/anthropics/skills>
- <https://github.com/anthropics/claude-cookbooks/tree/main/skills>
- <https://developers.openai.com/codex/skills/>

Prompting:

- <https://cookbook.openai.com/examples/gpt-5/gpt-5-2_prompting_guide>
- Prompt optimizer:
  <https://platform.openai.com/chat/edit?models=gpt-5.2&optimize=true>

Other skills:

- [The Agent Skills Directory](https://skills.sh/)
- [github.com/VoltAgent/awesome-claude-skills](https://github.com/VoltAgent/awesome-claude-skills)
- OpenAI curated set of skills:
  [github.com/openai/skills](https://github.com/openai/skills)

## License

Unless otherwise noted, the license is MIT. Some skills copied from elsewhere
have their own licenses.
