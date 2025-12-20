# Skills

Forget about MCP; use command-line tools and tailor context to the task at hand.
Use with Codex or Claude Code.

## Install

    $ git clone git@github.com:bkircher/skills.git ~/.codex/skills

… or something like this. You can also clone somewhere else and symlink from the
agent-specific directories.

## Test

Start Codex like this:

    $ codex --enable skills -m gpt-5.2

Then, when prompted:

    > list skills

Should output something like:

```raw
• Explored
  └ List ls -1

─ Worked for 7s ──────────────────────────────────────────────────────────────────────────────────────────

• - git-commit-message — Formulate a git commit message
  - github-code-review — Conduct a thorough GitHub PR code review
```

## Use with Codex

Skills are still a work in progress (as of Codex 0.72.0). Run Codex with:
`codex --enable skills`. For example:

    $ codex --enable skills -m gpt-5.2-codex -s workspace-write -a on-request

Tested with:

    $ codex --version
    codex-cli 0.72.0

## Use with Claude Code

TODO

## List of skills

List of skills:

- english-text-editor — Suggests improvements for English language text but does
  not rewrite the original. Use when asked to correct spelling or wording and
  the text is English.
- git-commit-message — Formulate a git commit message. Use this skill whenever
  asked to create a commit message.
- github-code-review — Conduct a thorough and in-depth code review. Use this
  skill when conducting a code review for a PR on GitHub.
- github-run-failure — Use to analyze failures in GitHub pipelines or jobs.

## Create your own skills

    $ mkdir -p ~/.codex/skills/<my-name>
    $ curl -fsSL \
        https://raw.githubusercontent.com/anthropics/skills/refs/heads/main/template/SKILL.md \
        -o ~/.codex/skills/<my-name>/SKILL.md

## Links

General:

- <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview>
- <https://simonwillison.net/2025/Dec/12/openai-skills/>
- <https://github.com/anthropics/skills>
- <https://github.com/anthropics/claude-cookbooks/tree/main/skills>

Prompting:

- <https://cookbook.openai.com/examples/gpt-5/gpt-5-2_prompting_guide>
- Prompt optimizer:
  <https://platform.openai.com/chat/edit?models=gpt-5.2&optimize=true>

Other skills:

- [github.com/VoltAgent/awesome-claude-skills](https://github.com/VoltAgent/awesome-claude-skills)
