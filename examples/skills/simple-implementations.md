---
name: simple-implementations
description: Use when writing solutions for straightforward problems - prefer direct implementations over premature abstractions
---

# Simple Implementations

Ship working code first. Abstractions emerge from patterns, not predictions.

## Core Principle

**Three lines of duplication is better than one early abstraction.**

Don't write helper functions, factories, or base classes until you've solved the same problem three times.

## When to Apply

- Building utilities or libraries
- Solving well-defined problems with clear requirements
- When the problem is smaller than the "solution"

## When NOT to Apply

- Architectural layers (MVC, layering, domains)
- Established design patterns for your domain
- Code that's mandated by your framework

## Pattern

### Problem: Premature Abstraction
```python
# Over-engineered: generic parameter processing before we know what we need
class ParameterProcessor:
    def process(self, params: dict, schema: dict) -> dict:
        result = {}
        for key, rule in schema.items():
            if key in params:
                result[key] = self._apply_transformations(params[key], rule.get('transforms'))
        return result
```

### Solution: Direct Implementation
```python
# Direct: Do what's needed, nothing more
def validate_api_request(headers: dict, body: dict) -> tuple[bool, str]:
    if 'authorization' not in headers:
        return False, "Missing auth header"
    if 'email' not in body:
        return False, "Missing email"
    return True, ""
```

## Trade-offs

**Direct code is harder to extend** - but extending is free (copy-paste 5 lines takes 10 seconds).

**Abstractions are easy to misuse** - but building them takes hours. Write direct code, extract patterns when they emerge.

## Common Mistakes

- Writing base classes for one implementation
- Creating helper utilities before you repeat code
- Building configuration systems for one use case
- Parameterizing everything "just in case"

**Cost:** Abstractions that never get used, code that's harder to understand than the problem it solves.
