---
name: unit-testing
description: "Generate test scaffolding, write assertions, create mocks and stubs, and update existing test suites for any language. Use when writing or updating unit tests, test cases, specs, test coverage, TDD workflows, or working with testing frameworks like pytest, Jest, JUnit, or Go testing."
---

## Workflow

1. **Identify** the public behavior to test — read the function/module under test, note its inputs, outputs, and side effects.
2. **Name the test** descriptively (e.g., `test_returns_empty_list_when_no_items_match`).
3. **Write using AAA** — Arrange inputs, Act by calling the function, Assert expected outputs.
4. **Run the suite** — execute with the project's test command (`pytest .`, `npm test`, `go test ./...`) and verify all pass.
5. **Check coverage gaps** — look for untested error paths, boundary conditions, and edge cases.

## Non-Negotiable Rules

1. **Test Behavior, Not Implementation**
   - Assert only public API outputs and observable side effects.
   - Do not test:
     - Private fields or state
     - Private methods
     - Internal functions or Python dunder methods (test only via public APIs as needed)
     - Internal call sequences
     - Intermediate steps outside the public contract
   - Tests must stay valid after refactoring if behavior is unchanged.
2. **Apply AAA (Arrange, Act, Assert) Pattern**
   - Each test must include:
     - Arrange: set up inputs, fixtures, mocks, or stubs
     - Act: invoke the code under test
     - Assert: verify expected behavior
   - Visually separate these sections with blank lines (or comments, if necessary).
3. **Total Isolation**
   - Unit tests must be:
     - Order-independent
     - Runnable individually
     - Free from shared mutable state
   - Avoid external systems (database, network, filesystem, environment, system clock).
   - Mock or stub all external dependencies, including time.
4. **No Logic in Test Code**
   - For multiple cases, use parameterized features in your test framework.
   - Test code should be declarative. Avoid:
     - if/else statements
     - Loops (use parameterized tests instead)
     - Complex calculations
     - Branching assertions
5. **Hardcode Expected Values**
   - Do not compute expected values in tests (except trivial helpers).
   - Use explicit literals in assertions for clarity.
   - Magic numbers/strings are allowed if they improve readability.

## Examples

**Python (pytest):**

```python
def test_discount_applied_for_bulk_order():
    # Arrange
    cart = Cart(items=[Item("widget", qty=100, price=5.00)])

    # Act
    total = cart.calculate_total()

    # Assert
    assert total == 450.00  # 10% bulk discount applied
```

**JavaScript (Jest):**

```javascript
test("returns filtered users matching the query", () => {
  // Arrange
  const users = [{ name: "Alice" }, { name: "Bob" }, { name: "Alana" }];

  // Act
  const result = filterUsers(users, "Al");

  // Assert
  expect(result).toEqual([{ name: "Alice" }, { name: "Alana" }]);
});
```

## General Advice

- Inject clocks, randomness, and I/O boundaries as dependencies. Use explicit seeding for deterministic randomness testing.
- Ensure the full test suite runs with a single command. Separate integration or performance suites from unit tests.
- Code under test must not detect it is being tested; tests should not depend on debug/test hooks.
- For filter logic, classify representative input sets for inclusion/exclusion testing.
- Cover error cases: null/missing inputs, invalid formats, boundaries, empty collections, negatives, exceptions, and failures (with mocks).
- Treat flaky tests as bugs. Unit tests must complete in seconds.
