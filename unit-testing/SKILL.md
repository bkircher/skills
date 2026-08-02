---
name: unit-testing
description: Use when writing or updating unit tests (in any language).
---

Create maintainable, readable, deterministic, and refactor-resilient unit tests.

## Rules

1. **Test Behavior, Not Implementation**
   - Assert only public API outputs and observable side effects
   - Do not test:
     - Private fields or state
     - Private methods
     - Internal functions or Python dunder methods (test only via public APIs as needed)
     - Internal call sequences
     - Intermediate steps outside the public contract
   - Tests must stay valid after refactoring if behavior is unchanged
2. **Apply AAA (Arrange, Act, Assert) Pattern**
   - Each test must include:
     - Arrange: set up inputs, fixtures, mocks, or stubs
     - Act: invoke the code under test
     - Assert: verify expected behavior
   - Visually separate these sections with blank lines (or comments, if necessary)
3. **Total Isolation**
   - Unit tests must be:
     - Order-independent
     - Runnable individually
     - Free from shared mutable state
   - Avoid external systems (database, network, filesystem, environment, system clock)
   - Mock or stub all external dependencies, including time
4. **No Logic in Test Code**
   - For multiple cases, use parameterized features in your test framework
   - Test code should be declarative. Avoid:
     - if/else statements
     - Loops (use parameterized tests instead)
     - Complex calculations
     - Branching assertions
5. **Hardcode Expected Values**
   - Do not compute expected values in tests (except trivial helpers)
   - Use explicit literals in assertions for clarity
   - Magic numbers and strings are allowed if they improve readability

## General advice

- Never modify the code under test just to adapt to new or changed tests
- Inject clocks, randomness, and I/O boundaries as dependencies. Avoid reliance on real time or external systems. Use explicit seeding and deterministic sources for randomness testing
- Assert only outputs, not domain logic within tests
- Prefer built-in fixtures/utilities from test libraries
- Code under test must not detect it is being tested; tests should not depend on debug/test hooks
- Use descriptive names reflecting test intent
- Each test should verify a single logical behavior. Multiple assertions are fine if for one behavior; otherwise, split tests
- Cover error cases, including null or missing inputs, invalid formats, boundaries, empty collections, negative values, exceptions, and failures (with mocks)
- Unit tests must complete in seconds and avoid dependencies on time or external state; treat flaky tests as bugs
