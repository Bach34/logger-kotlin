"""logger-kotlin: identifies detached loggers for pruning."""

from .core import LoggerHierarchyPruner, PruneCandidate

__all__ = ["LoggerHierarchyPruner", "PruneCandidate"]
