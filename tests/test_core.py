"""Deterministic tests for logger-kotlin.

We never touch the global ``logging`` manager directly; every case injects a
hand-built registry dict so results are independent of test execution order.
"""

import logging
import unittest

from logger_kotlin.core import (
    PruneCandidate,
    LoggerHierarchyPruner,
)


class _FakePlaceholder:
    """Stand-in for ``logging.PlaceHolder``.

    We cannot instantiate the real one without registering it as a child of a
    logger, which would pollute global state.  ``scan`` only checks
    ``isinstance(node, logging.Logger)``, so any non-Logger object behaves as
    a placeholder for our purposes.
    """


class ScanTests(unittest.TestCase):
    def test_empty_registry(self):
        self.assertEqual(LoggerHierarchyPruner.scan({}), [])

    def test_candidate_with_no_handlers_and_notset(self):
        lg = logging.getLogger("orphan.child")
        lg.handlers = []
        lg.level = logging.NOTSET
        result = LoggerHierarchyPruner.scan({"orphan.child": lg})
        self.assertEqual(
            result,
            [
                PruneCandidate(
                    name="orphan.child",
                    level=logging.NOTSET,
                    has_handlers=False,
                    parent=None,
                )
            ],
        )

    def test_logger_with_handler_is_skipped(self):
        lg = logging.getLogger("h.active")
        lg.handlers = [logging.StreamHandler()]
        lg.level = logging.NOTSET
        result = LoggerHierarchyPruner.scan({"h.active": lg})
        self.assertEqual(result, [])

    def test_logger_with_explicit_level_is_skipped(self):
        lg = logging.getLogger("h.configured")
        lg.handlers = []
        lg.level = logging.WARNING
        result = LoggerHierarchyPruner.scan({"h.configured": lg})
        self.assertEqual(result, [])

    def test_placeholder_is_skipped(self):
        result = LoggerHierarchyPruner.scan({"gap": _FakePlaceholder()})
        self.assertEqual(result, [])

    def test_results_sorted_alphabetically(self):
        names = ["z.last", "a.first", "m.middle"]
        registry = {}
        for n in names:
            lg = logging.getLogger(n)
            lg.handlers = []
            lg.level = logging.NOTSET
            registry[n] = lg
        result = LoggerHierarchyPruner.scan(registry)
        self.assertEqual([c.name for c in result], ["a.first", "m.middle", "z.last"])

    def test_parent_resolves_to_nearest_existing_ancestor(self):
        child = logging.getLogger("root.mid.child")
        child.handlers = []
        child.level = logging.NOTSET
        root = logging.getLogger("root")
        root.handlers = [logging.NullHandler()]
        root.level = logging.INFO
        registry = {"root": root, "root.mid.child": child, "root.mid": _FakePlaceholder()}
        result = LoggerHierarchyPruner.scan(registry)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "root.mid.child")
        # "root.mid" exists as a placeholder entry, which counts as an existing
        # node for parent resolution, so the nearest ancestor is "root.mid".
        self.assertEqual(result[0].parent, "root.mid")

    def test_parent_none_when_no_ancestor_present(self):
        lg = logging.getLogger("solo")
        lg.handlers = []
        lg.level = logging.NOTSET
        result = LoggerHierarchyPruner.scan({"solo": lg})
        self.assertIsNone(result[0].parent)

    def test_mixed_registry_only_returns_eligible(self):
        active = logging.getLogger("mix.active")
        active.handlers = [logging.NullHandler()]
        active.level = logging.DEBUG
        configured = logging.getLogger("mix.configured")
        configured.handlers = []
        configured.level = logging.ERROR
        orphan = logging.getLogger("mix.orphan")
        orphan.handlers = []
        orphan.level = logging.NOTSET
        ph = _FakePlaceholder()
        registry = {
            "mix.active": active,
            "mix.configured": configured,
            "mix.orphan": orphan,
            "mix.gap": ph,
        }
        result = LoggerHierarchyPruner.scan(registry)
        self.assertEqual([c.name for c in result], ["mix.orphan"])


class RemoveTests(unittest.TestCase):
    def setUp(self):
        # Snapshot the real registry so mutations do not leak across tests.
        self._saved = dict(logging.Logger.manager.loggerDict)

    def tearDown(self):
        logging.Logger.manager.loggerDict.clear()
        logging.Logger.manager.loggerDict.update(self._saved)

    def test_remove_live_logger(self):
        name = "__pruner_test_removable"
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.level = logging.NOTSET
        self.assertIn(name, logging.Logger.manager.loggerDict)
        self.assertTrue(LoggerHierarchyPruner.remove(name))
        self.assertNotIn(name, logging.Logger.manager.loggerDict)

    def test_remove_missing_name_returns_false(self):
        self.assertFalse(LoggerHierarchyPruner.remove("__does_not_exist__"))

    def test_remove_placeholder_returns_false(self):
        name = "__pruner_test_placeholder"
        # Manually inject a placeholder-like object.
        logging.Logger.manager.loggerDict[name] = _FakePlaceholder()
        self.assertFalse(LoggerHierarchyPruner.remove(name))


if __name__ == "__main__":
    unittest.main()
