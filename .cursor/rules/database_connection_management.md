# Database Connection Management - GUIDELINES

## Context Manager Pattern

All extractor classes that use database connections should implement the context manager protocol and **must** be used with `with` statements. Never use explicit `close()` calls or `try...finally` blocks for extractor cleanup.

## Required Pattern

**Always use context managers:**

```python
with ExtractorClass(...) as extractor:
    # Use extractor here
    result = extractor.extract_data(...)
```

**Never use explicit close() calls:**

```python
# ❌ WRONG - Do not do this
extractor = ExtractorClass(...)
try:
    result = extractor.extract_data(...)
finally:
    extractor.close()
```

## Why Context Managers?

1. **Automatic Cleanup**: Context managers guarantee that cleanup is called even if exceptions occur
2. **Exception Safety**: Resources are properly released regardless of how the block exits
3. **Pythonic**: Follows Python best practices for resource management
4. **Less Boilerplate**: Cleaner, more readable code without explicit try/finally blocks
5. **Consistency**: Single pattern throughout the codebase

## Implementation Requirements

When creating extractor classes that use database connections:

1. Implement `__enter__()` method that returns `self`
2. Implement `__exit__()` method that calls cleanup (closes database connections)
3. Implement a `close()` method that cleans up resources (especially database connections)
4. Document in the class docstring that it should be used as a context manager
5. Always use `with` statements when instantiating the extractor in code

## Best Practices

- Use context managers for any class that manages resources (database connections, file handles, network connections)
- Ensure cleanup happens even when exceptions occur
- Document resource management requirements in class docstrings
- Test that resources are properly cleaned up even on exceptions

---

**Status**: GUIDELINE - Follow this pattern for all resource-managing classes
