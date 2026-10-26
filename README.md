# logger-kotlin

Identifies loggers created during import or test runs that are no longer attached to handlers, returning candidates for removal.

```python
from logger_kotlin import LoggerHierarchyPruner

candidates = LoggerHierarchyPruner.scan()
for c in candidates:
    print(c.name, c.parent, c.level)

if candidates:
    LoggerHierarchyPruner.remove(candidates[0].name)
```

## Why

Python's `logging` module keeps every named logger ever instantiated in a process-global dict (`logging.Logger.manager.loggerDict`). Nothing ever evicts entries from that dict. In long-lived services and large test suites, import-time loggers accumulate: modules that were imported once, created a logger for namespacing, and are never used again still sit in memory with handlers they lost during teardown.

This library scans that dict and returns the loggers that are inert: no handlers attached and no explicit level set — meaning their behaviour is fully inherited and their existence changes nothing. Removing them is safe; keeping them is noise.

The trade-off is conservatism. A logger that was deliberately given a level but no handlers (a common pattern for silencing a noisy third-party library) is **not** flagged, because the explicit level is a signal that someone configured it on purpose. We would rather miss a pruneable logger than delete one that was intentionally tuned.

## Edge cases

- **Placeholders**: `logging` inserts `PlaceHolder` objects for intermediate namespace segments that have no real logger (e.g. `a.b` when only `a.b.c` was created). These are skipped — they have no state and deleting them breaks child resolution.
- **Effective level**: we check the logger's own `level` attribute, not `getEffectiveLevel()`. A logger whose parent was assigned a level will report that inherited level via `getEffectiveLevel()`, but the logger itself is still inert if its own level is `NOTSET` and it has no handlers. This is the distinction that makes the scan useful.
- **Mutating the live registry**: `remove()` operates on the real global dict. Call it only for candidates you have confirmed, and be aware that concurrently-created loggers in other threads may appear between `scan()` and `remove()`.
