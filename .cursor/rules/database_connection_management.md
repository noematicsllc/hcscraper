# Database Connection Management

## Context Manager Pattern for Extractors

All extractor classes (`OrderExtractor`, `BillingDocumentExtractor`, `BulkOrderExtractor`, and any future extractors) implement the context manager protocol and **must** be used with `with` statements. Never use explicit `close()` calls or `try...finally` blocks for extractor cleanup.

## Required Pattern

**Always use context managers:**

```python
with OrderExtractor(
    api_client=api_client,
    output_directory=output_dir,
    save_json=True,
    update_mode=args.update,
    max_consecutive_failures=args.max_consecutive_failures
) as extractor:
    # Use extractor here
    stats = extractor.extract_orders(order_ids)
```

**Never use explicit close() calls:**

```python
# ❌ WRONG - Do not do this
extractor = OrderExtractor(...)
try:
    stats = extractor.extract_orders(order_ids)
finally:
    extractor.close()
```

## Why Context Managers?

1. **Automatic Cleanup**: Context managers guarantee that `close()` is called even if exceptions occur
2. **Exception Safety**: Resources are properly released regardless of how the block exits
3. **Pythonic**: Follows Python best practices for resource management
4. **Less Boilerplate**: Cleaner, more readable code without explicit try/finally blocks
5. **Consistency**: Single pattern throughout the codebase

## Implementation Details

All extractor classes implement:
- `__enter__()`: Returns `self` when entering the context
- `__exit__()`: Calls `close()` when exiting the context (even on exceptions)
- `close()`: Closes database connections and cleans up resources

The context manager pattern ensures that database connections are always properly closed, preventing connection leaks.

## When Adding New Extractors

When creating new extractor classes:
1. Implement `__enter__()` and `__exit__()` methods
2. Implement a `close()` method that cleans up resources (especially database connections)
3. Document in the class docstring that it should be used as a context manager
4. Always use `with` statements when instantiating the extractor in code

