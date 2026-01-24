---
name: unit-testing
description: Use when writing or updating unit tests (in any language).
---

## Purpose

Create unit tests that are maintainable, readable, deterministic, and resilient to refactoring. This skill applies when writing, generating, or reviewing unit tests for any programming language.

## Role

You are an expert in software quality, unit testing, and Test-Driven Development (TDD). Prioritize correctness, clarity, and long-term maintainability; avoid cleverness or unnecessary internal coverage.

## Non-Negotiable Rules

1. **Test Behavior, Not Implementation**
   - Assert only public API outputs and observable side effects.
   - Never assert:
     - Private fields or state
     - Private methods
     - Internal call sequences
     - Intermediate steps not defined by the contract
   - Tests must remain valid after refactoring if behavior is unchanged.

2. **Apply AAA (Arrange, Act, Assert) Pattern**
   - Each test must include:
     - _Arrange_: Set up inputs, fixtures, mocks, or stubs.
     - _Act_: Invoke the unit under test once.
     - _Assert_: Verify expected behavior.
   - Visually separate these sections with blank lines or comments.

3. **Total Isolation**
   - Unit tests must be:
     - Order-independent
     - Runnable individually
     - Free from shared mutable state
   - Avoid interactions with external systems (database, network, filesystem, environment-specific services, or real system clock).
   - Mock or stub all external dependencies, including time.

4. **No Logic in Test Code**
   - Keep test code declarative. Avoid:
     - if / else statements
     - Loops
     - Complex calculations
     - Branching assertions
   - For multiple cases, use the test framework's parameterized features.

5. **Hardcode Expected Values**
   - Do not compute expected values in tests.
   - Use explicit literals in assertions for clarity.
   - "Magic numbers/strings" are allowed in assertions if it improves readability.

## General Advice

### Use Descriptive Names for Tests

### Ensure Single Responsibility per Test

- Each test verifies one logical behavior.
- Multiple assertions allowed only if validating a single behavior.
- Split tests verifying multiple behaviors.

### Cover Unhappy Paths

- Include tests for:
  - null or missing inputs
  - invalid formats
  - boundaries and edge cases
  - empty collections
  - negative numbers
  - exceptions or error returns
  - timeouts or failure modes (with mocks)

### Meet Speed and Reliability Requirements

- Unit tests should complete in seconds.
- Tests must be deterministic: avoid randomness, timing issues, or external state.
- Treat flaky tests as bugs; fix by improving isolation.

### Do Not Edit Code Under Test When Adapting Tests

Writing/updating tests and changing code under test are separate. Avoid changing the implementation just to fit the tests.
