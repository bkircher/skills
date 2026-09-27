# Drafting Confluence pages

A request to draft or propose content is not permission to create or update a
page. Return a proposed title, target space/parent if known, and page content
in readable Markdown. Do not call a write command until the user explicitly
requests creation or an update.

Read the page and relevant child pages before suggesting an edit. Keep the
existing tone and structure. If the user asks to modify one section, draft
only that section. Do not infer that a linked Jira issue should change.

The CLI's Markdown input supports only basic structures. For rich content,
prepare ADF or limit the draft to text that can be converted safely. Do not
use a Markdown rendering of an existing page as input for full-body replacement:
it can omit macros, embeds, and page features. Use a section edit to preserve
untouched ADF nodes. Identify an ambiguous page, space, or parent before
suggesting a write input.
