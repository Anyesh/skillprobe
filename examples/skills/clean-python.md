---
name: clean-python
description: Use when writing Python code - enforce minimal function signatures, type hints, and avoid docstrings on simple functions
---

# Clean Python

Write minimal, focused Python functions that prioritize clarity over verbosity.

## Core Principles

1. **No docstrings on simple functions** - If a function's purpose is clear from its name and type hints, a docstring is noise
2. **Always use type hints** - Type hints are documentation that the compiler can verify
3. **Single-line definitions when possible** - Keep simple functions on one line with arrow notation

## When to Use

- Writing utility functions (less than 5 lines)
- Creating helper functions with clear names
- Building libraries where type hints aid discoverability

## When NOT to Use

- Complex business logic that genuinely needs explanation
- Public APIs with non-obvious behavior
- Functions with tricky edge cases

## Examples

### Good: Clean and clear
```python
def is_prime(n: int) -> bool:
    return n > 1 and all(n % i != 0 for i in range(2, int(n**0.5) + 1))

def parse_config(path: str) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)

def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
```

### Bad: Over-documented
```python
def is_prime(n):
    """Check if n is a prime number."""
    return n > 1 and all(n % i != 0 for i in range(2, int(n**0.5) + 1))

def parse_config(path):
    """
    Loads configuration from a JSON file at the given path.
    
    Args:
        path: The file path to load
    
    Returns:
        A dictionary containing the config
    """
    with open(path) as f:
        return json.load(f)
```

## Guidelines

**Keep it simple:** If the function name + type hints tell the story, stop writing.

**Type hints are mandatory:** Every parameter and return value needs a type annotation.

**Multi-line functions may need explanation:** If it's complex enough to need 5+ lines, consider whether a docstring helps or if you should refactor instead.
