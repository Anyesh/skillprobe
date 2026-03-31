---
name: systematic-debugging
description: Use when a test is failing, code behavior is unexpected, or you're hunting a bug - trace execution systematically before guessing
---

# Systematic Debugging

Find the root cause before changing code.

## Three Rules

1. **Read the error message** - Start here. 99% of bugs are explained by the error.
2. **Verify your assumptions** - What you think is true might not be. Check the state.
3. **Trace execution** - Follow the code path from input to failure point.

## Pattern: Hypothesis Testing

```
1. What's the observed behavior? (test output, error, unexpected result)
2. What should happen? (expected behavior)
3. Where does it diverge? (add logging to narrow it down)
4. Why does it diverge? (root cause)
5. Fix the root cause, not the symptom
```

## When NOT to Use

- Code review (looking for style issues)
- Performance optimization (not debugging, different methodology)
- Learning new frameworks (read docs, not debugging)

## Common Mistakes

- Adding more logging without reading existing logs
- Changing code without understanding the failure
- Fixing the symptom instead of the root cause
- Using print statements instead of actual debugger

**Cost:** Hours wasted, multiple failed fixes, frustration.

## Tools

- **Debugger** - Breakpoints, step through execution
- **Logging** - Trace variable state
- **Assertions** - Verify assumptions
- **Reproducible test case** - Isolate the problem
