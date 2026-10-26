"""Core logic for identifying prune-eligible loggers.

The standard ``logging`` module holds every named logger ever created in a
single dict (``logging.Logger.manager.loggerDict``).  Loggers created during
import or test runs accumulate there forever.  The Python docs and source do
not provide a way to discover which of these loggers still serve a purpose.

A logger is a "prune candidate" when:
  * It exists in the global manager dict.
  * It has zero handlers directly attached.
  * Its effective level is inherited from a parent (i.e.
    ``logger.level == logging.NOTSET``) or is explicitly ``logging.NOTSET``.
  * It is NOT itself a placeholder node (placeholders mark empty intermediate
    namespace segments and have no state to prune).

We deliberately ignore propagation: a logger with zero local handlers but a
non-NOTSET level was deliberately configured and should be left alone.  This is
the conservative reading — false positives are more costly than false
negatives.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class PruneCandidate:
    """A logger that appears safe to remove.

    Attributes:
        name: dotted logger name, e.g. ``"project.imports.foo"``.
        level: numeric level on the logger (``logging.NOTSET`` if inherited).
        has_handlers: always False — candidates by definition have none.
        parent: name of the closest ancestor that exists in the dict,
            or ``None`` for the root namespace.
    """

    name: str
    level: int
    has_handlers: bool
    parent: Optional[str]


class LoggerHierarchyPruner:
    """Scan ``logging.Logger.manager.loggerDict`` for prune candidates.

    The class is stateless; calling :meth:`scan` snapshots the live logger
    manager at call time so the result reflects the logging registry exactly
    when invoked.
    """

    @staticmethod
    def _parent_of(name: str, known: Dict[str, object]) -> Optional[str]:
        """Return the closest existing ancestor of *name*.

        We walk up the dotted path rather than relying on the parent
        attribute of the logger object, because placeholder entries do not
        expose a usable parent and we want a deterministic textual answer.
        """
        parts = name.rsplit(".", 1)
        while len(parts) == 2:
            ancestor = parts[0]
            if ancestor in known:
                return ancestor
            parts = ancestor.rsplit(".", 1)
        return None

    @staticmethod
    def scan(
        registry: Optional[Dict[str, object]] = None,
    ) -> List[PruneCandidate]:
        """Return prune candidates in sorted, stable order.

        Args:
            registry: optional logger dict to inspect.  Defaults to the live
                ``logging.Logger.manager.loggerDict``.  Injecting a fake dict
                keeps tests deterministic without touching global state.
        """
        if registry is None:
            registry = logging.Logger.manager.loggerDict

        candidates: List[PruneCandidate] = []
        for name, node in registry.items():
            # Placeholders (instances of ``logging.PlaceHolder``) exist only to
            # keep namespace structure for child loggers; they have no level,
            # no handlers, and cannot be "removed" in any meaningful sense.
            if not isinstance(node, logging.Logger):
                continue

            if node.handlers:
                continue

            # A logger whose level was explicitly set (even if it currently
            # equals the root level) was intentionally configured.  Only
            # NOTSET loggers inherit their behaviour entirely from ancestors,
            # which is what makes them dead weight once they have no handlers.
            if node.level != logging.NOTSET:
                continue

            candidates.append(
                PruneCandidate(
                    name=name,
                    level=node.level,
                    has_handlers=False,
                    parent=LoggerHierarchyPruner._parent_of(name, registry),
                )
            )

        candidates.sort(key=lambda c: c.name)
        return candidates

    @staticmethod
    def remove(name: str) -> bool:
        """Delete *name* from the live logger manager.

        Returns ``True`` if a logger node was removed, ``False`` if the name
        was absent or was a placeholder (which we never remove).  This is a
        mutating convenience; :meth:`scan` is the safe, read-only entry point.
        """
        registry = logging.Logger.manager.loggerDict
        node = registry.get(name)
        if not isinstance(node, logging.Logger):
            return False
        del registry[name]
        return True


# Ensure the module's own logger does not register as a candidate during import
# of this package — it would be self-defeating noise in scan results.
_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())

# Re-export the stdlib module so consumers do not need a second import when
# they want ``logging.NOTSET`` alongside the pruner API.
stdlib_logging = sys.modules["logging"]
