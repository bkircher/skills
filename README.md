# Skills

Forget about MCP; use command-line tools and tailor context to the task at hand.
Use with Codex or Claude Code.

## Install

    $ git clone git@github.com:bkircher/skills.git ~/.codex/skills

… or something like this. You can also clone somewhere else and symlink from the
agent-specific directories.

## Test

Start codex like

    $ codex --enable skills -m gpt-5.2

Then, when prompted

    > list skills

Shout output something like:

```raw
• Explored
  └ List ls -1

─ Worked for 7s ──────────────────────────────────────────────────────────────────────────────────────────

• - git-commit-message — Formulate a git commit message
  - github-code-review — Conduct a thorough GitHub PR code review
```

## Use with Codex

Skills are still work-in-progress it seems (as of codex 0.72.0). Run codex with

    $ codex --enable skills -m gpt-5.1-codex-max -s workspace-write -a on-request

Tested with

    $ codex --version
    codex-cli 0.72.0

## Use with Claude Code

TODO

## Create your own skills

    $ mkdir -p ~/.codex/skills/<my-name>
    $ curl -fsSL \
        https://raw.githubusercontent.com/anthropics/skills/refs/heads/main/template/SKILL.md \
        -o ~/.codex/skills/<my-name>/SKILL.md

## Links

- <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview>
- <https://simonwillison.net/2025/Dec/12/openai-skills/>
- <https://github.com/anthropics/skills>
- <https://github.com/anthropics/claude-cookbooks/tree/main/skills>
