Skills
======

Forget about MCP[^1]; use command-line tools and tailor context to the task at
hand.

> [!NOTE]
> Unsolicited advice: try to stay away from snake oil and cruft. The best skill
> is no skill. Seriously, only write skills to update or steer clankers if you
> want to adjust their “out-of-the-box” behavior. The models are good, they know
> what they are doing (in like 89% of the cases[^2]).

Use with Codex, Claude Code, Pi.

[^1]: for most of the time
[^2]: totally made up number


Install
-------

~~~~ sh
git clone git@github.com:bkircher/skills.git ~/src/skills
~~~~

… or something like this. You can also clone somewhere else and symlink to the
agent-specific directories.


Test
----

Start Codex as normal:

~~~~ sh
codex -m gpt-5.3
~~~~

(before Codex version 0.80.0, pass `--enable skills` feature flag):

~~~~ sh
codex --enable skills -m gpt-5.2
~~~~

Then, when prompted:

~~~~ text
> list skills
~~~~

Should output something like:

~~~~ text
• Available skills:

  - english-text-editor
  - gh-address-comments
  - gh-code-review
  - gh-run-failure
  - git-commit-message
  - jira-read-ticket
~~~~


Use with Codex
--------------

Skills are still a work in progress (as of Codex 0.72.0) [^3]. Run Codex with:
`codex --enable skills`. For example:

~~~~ sh
codex --enable skills -m gpt-5.2-codex -s workspace-write -a on-request
~~~~

Tested with:

~~~~ sh
codex --version
codex-cli 0.72.0
~~~~

[^3]: I believe Codex fully supports skills now; haven't used it in a while


Use with Claude Code
--------------------

Claude Code supports skills out of the box. Make sure the skills are installed,
e.g.,

~~~~ sh
cd ~/.claude
ln -s $HOME/src/skills skills
~~~~

Then in Claude CLI:

~~~~ text
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
~~~~


List of skills
--------------

List of skills:

| Skill               | Description                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------- |
| confluence-read     | Search Confluence pages and fetch page content                                                                        |
| english-text-editor | Suggests improvements for English language text (spelling, wording)                                                   |
| gh-address-comments | Address review/issue comments on open GitHub PR for current branch [Source]                                           |
| gh-code-review      | Conduct thorough code review for a GitHub PR                                                                          |
| gh-run-failure      | Analyze failures in GitHub pipelines or jobs                                                                          |
| git-commit-message  | Generate Git commit messages from staged changes when requested                                                       |
| jira-read-ticket    | Pull description, comments, or more from a Jira ticket                                                                |
| jira-write-ticket   | Write a Jira ticket                                                                                                   |
| playwright-cli      | Automate browser interactions, test web pages, and work with Playwright tests [Source] (added 2026-04-06, Apache-2.0) |
| snyk-cli            | Scan and triage Snyk security findings in local repositories and container images                                     |
| sonar-cli           | Access and understand SonarQube analysis results with the SonarQube CLI                                               |
| unit-testing        | Help when writing or updating unit tests                                                                              |

[Source]: https://github.com/microsoft/playwright-cli/tree/main/skills/playwright-cli


Create your own skills
----------------------

~~~~ sh
mkdir -p ~/src/skills/<my-name>
curl -fsSL \
    https://raw.githubusercontent.com/anthropics/skills/refs/heads/main/template/SKILL.md \
    -o ~/src/skills/<my-name>/SKILL.md
~~~~


Links
-----

General:

 -  <https://agentskills.io/home>
 -  <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview>
 -  <https://simonwillison.net/2025/Dec/12/openai-skills/>
 -  <https://github.com/anthropics/skills>
 -  <https://github.com/anthropics/claude-cookbooks/tree/main/skills>
 -  <https://developers.openai.com/codex/skills/>

Prompting:

 -  <https://cookbook.openai.com/examples/gpt-5/gpt-5-2_prompting_guide>
 -  Prompt optimizer:
    <https://platform.openai.com/chat/edit?models=gpt-5.2&optimize=true>

Other skills:

 -  [The Agent Skills Directory]
 -  [github.com/VoltAgent/awesome-claude-skills]
 -  OpenAI curated set of skills:
    [github.com/openai/skills]

[The Agent Skills Directory]: https://skills.sh/
[github.com/VoltAgent/awesome-claude-skills]: https://github.com/VoltAgent/awesome-claude-skills
[github.com/openai/skills]: https://github.com/openai/skills


License
-------

Unless otherwise noted, the license is MIT. Some skills are copied from
elsewhere and have their own licenses.
