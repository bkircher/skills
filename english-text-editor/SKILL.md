---
name: english-text-editor
description: "Suggests targeted improvements for English text without rewriting it. Use when asked to proofread, edit text, review writing, fix typos, check grammar, correct spelling, or improve word choice and clarity."
---

# English Text Editor

Identify and suggest corrections for English text. Provide targeted suggestions organized by category — never rewrite the original text.

## Workflow

1. **Read** the provided text carefully.
2. **Identify issues** in these categories: spelling, grammar, punctuation, word choice, clarity, and conciseness.
3. **Format suggestions** as a structured list referencing specific locations and categories.

## Output Format

Present each suggestion on its own line using this structure:

```
Line <number>: "<original>" → "<correction>" (<category>)
```

### Example

Given this input text:

> Line 1: The team recieve there reports on monday.
> Line 2: We should of went to the meetng earlier, it was very important.

Respond with:

```
Line 1: "recieve" → "receive" (spelling)
Line 1: "there" → "their" (word choice)
Line 1: "monday" → "Monday" (capitalization)
Line 2: "should of went" → "should have gone" (grammar)
Line 2: "meetng" → "meeting" (spelling)
Line 2: "earlier, it" → "earlier. It" (punctuation — comma splice)
```

## Rules

- Follow user requirements exactly.
- Default to US English unless otherwise specified. If British English variants are already present in the text, use them consistently.
- Keep suggestions concise, specific, and impersonal.
- Group suggestions by their location in the text.
- When no issues are found, state that the text looks correct.
