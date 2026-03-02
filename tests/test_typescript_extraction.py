"""Tests for TypeScript/JSX extraction bugs.

Bug 1: Object literal methods (async callbacks in configs) not extracted
Bug 2: Nested function declarations inside components not extracted
Bug 3: TSConfigResolver initialized with project root, misses nested tsconfig.json paths
Bug 4: `warm` defaults to python-only, should default to all languages
Bug 5: Module-level calls in test files not captured (describe/it callbacks)
Bug 6: JSX component usage (<SlotCard />) not treated as call edges
Bug 7: .tsx files parsed with typescript parser instead of tsx (JSX invisible)
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure tldr package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "test-nextjs-app"


# ---------------------------------------------------------------------------
# Bug 1: Object literal methods
# ---------------------------------------------------------------------------

class TestObjectLiteralMethods:
    """auth.ts has 4 async methods inside authOptions.callbacks object literal.
    They should be extracted as functions."""

    def test_extracts_object_methods(self):
        from tldr.hybrid_extractor import HybridExtractor

        extractor = HybridExtractor()
        filepath = str(FIXTURE_DIR / "lib" / "auth.ts")
        result = extractor.extract(filepath)

        assert result is not None, "Extraction returned None"
        func_names = {f.name for f in result.functions}

        # All 4 async methods in the callbacks object should be found
        assert "redirect" in func_names, f"Missing 'redirect' in {func_names}"
        assert "signIn" in func_names, f"Missing 'signIn' in {func_names}"
        assert "jwt" in func_names, f"Missing 'jwt' in {func_names}"
        assert "session" in func_names, f"Missing 'session' in {func_names}"

    def test_extracts_at_least_four_functions(self):
        from tldr.hybrid_extractor import HybridExtractor

        extractor = HybridExtractor()
        filepath = str(FIXTURE_DIR / "lib" / "auth.ts")
        result = extractor.extract(filepath)

        assert result is not None
        # At minimum the 4 callback methods
        assert len(result.functions) >= 4, f"Expected >=4 functions, got {len(result.functions)}"


# ---------------------------------------------------------------------------
# Bug 2: Nested function declarations
# ---------------------------------------------------------------------------

class TestNestedFunctionDeclarations:
    """Counter.tsx has handleIncrement, handleReset (function declarations)
    and handleDouble (arrow function) nested inside Counter component.
    All should be extracted."""

    def test_extracts_nested_functions(self):
        from tldr.hybrid_extractor import HybridExtractor

        extractor = HybridExtractor()
        filepath = str(FIXTURE_DIR / "components" / "Counter.tsx")
        result = extractor.extract(filepath)

        assert result is not None, "Extraction returned None"
        func_names = {f.name for f in result.functions}

        assert "Counter" in func_names, f"Missing 'Counter' in {func_names}"
        assert "handleIncrement" in func_names, f"Missing 'handleIncrement' in {func_names}"
        assert "handleReset" in func_names, f"Missing 'handleReset' in {func_names}"
        assert "handleDouble" in func_names, f"Missing 'handleDouble' in {func_names}"

    def test_extracts_all_five_items(self):
        from tldr.hybrid_extractor import HybridExtractor

        extractor = HybridExtractor()
        filepath = str(FIXTURE_DIR / "components" / "Counter.tsx")
        result = extractor.extract(filepath)

        assert result is not None
        # Counter + 3 nested handlers
        assert len(result.functions) >= 4, f"Expected >=4 functions, got {len(result.functions)}"


# ---------------------------------------------------------------------------
# Bug 3: TSConfig path alias resolution
# ---------------------------------------------------------------------------

class TestTSConfigPathAliasResolution:
    """route.ts imports from @/lib/helpers and @/lib/db.
    TSConfigResolver should find the tsconfig.json in the fixture dir
    and resolve @/* to ./* correctly."""

    def test_resolver_finds_nested_tsconfig(self):
        from tldr.tsconfig_resolver import TSConfigResolver

        resolver = TSConfigResolver(str(FIXTURE_DIR))
        assert len(resolver.path_mappings) > 0, "No path mappings loaded from fixture tsconfig"

    def test_resolver_resolves_alias(self):
        from tldr.tsconfig_resolver import TSConfigResolver

        resolver = TSConfigResolver(str(FIXTURE_DIR))
        resolved = resolver.resolve("@/lib/helpers")
        assert resolved is not None, "@/lib/helpers should resolve to a file"
        assert resolved.endswith("helpers.ts"), f"Expected helpers.ts, got {resolved}"

    def test_resolver_resolves_db_alias(self):
        from tldr.tsconfig_resolver import TSConfigResolver

        resolver = TSConfigResolver(str(FIXTURE_DIR))
        resolved = resolver.resolve("@/lib/db")
        assert resolved is not None, "@/lib/db should resolve to a file"
        assert resolved.endswith("db.ts"), f"Expected db.ts, got {resolved}"

    def test_call_graph_resolves_alias_imports(self):
        """End-to-end: scanning the fixture project should produce cross-file
        edges from route.ts to helpers.ts and db.ts via @/ alias."""
        from tldr.cross_file_calls import _build_typescript_call_graph, ProjectCallGraph, scan_project

        graph = ProjectCallGraph()
        # Build a func_index from fixture files
        from tldr.hybrid_extractor import HybridExtractor
        extractor = HybridExtractor()

        func_index = {}
        ts_files = []
        for root_dir, _dirs, files in os.walk(str(FIXTURE_DIR)):
            for f in files:
                if f.endswith((".ts", ".tsx")):
                    full = os.path.join(root_dir, f)
                    ts_files.append(full)
                    result = extractor.extract(full)
                    if result:
                        rel = str(Path(full).relative_to(FIXTURE_DIR))
                        for func in result.functions:
                            func_index[(Path(full).stem, func.name)] = rel

        _build_typescript_call_graph(
            FIXTURE_DIR,
            graph,
            func_index,
            file_list=ts_files,
        )

        # route.ts should have edges to helpers.ts functions
        all_edges = list(graph.edges)
        dst_files = {e[2] for e in all_edges}  # (src_file, src_func, dst_file, dst_func)
        dst_funcs = {e[3] for e in all_edges}

        # We expect at least requireAuth and apiError to be resolved
        assert "requireAuth" in dst_funcs or any(
            "helpers" in d for d in dst_files
        ), f"No edges to helpers.ts. All edges: {all_edges}"


# ---------------------------------------------------------------------------
# Bug 4: warm default language
# ---------------------------------------------------------------------------

class TestWarmDefaultLanguage:
    """The CLI `warm` command should default to all languages, not just python."""

    def test_warm_default_is_all(self):
        import subprocess
        result = subprocess.run(
            ["python3", "-m", "tldr.cli", "warm", "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        help_text = result.stdout + result.stderr
        # After fix, default should be 'all', not 'python'
        assert "(default: all)" in help_text or "default='all'" in help_text, (
            f"warm --help still shows python as default:\n{help_text}"
        )


# ---------------------------------------------------------------------------
# Bug 5: Module-level calls in test files
# ---------------------------------------------------------------------------

class TestModuleLevelCalls:
    """Test files have describe/it at module level, not inside functions.
    Imported symbols used inside callbacks should create call edges."""

    def _build_fixture_graph(self):
        from tldr.cross_file_calls import _build_typescript_call_graph, ProjectCallGraph
        from tldr.hybrid_extractor import HybridExtractor

        graph = ProjectCallGraph()
        extractor = HybridExtractor()

        func_index = {}
        ts_files = []
        for root_dir, _dirs, files in os.walk(str(FIXTURE_DIR)):
            for f in files:
                if f.endswith((".ts", ".tsx")):
                    full = os.path.join(root_dir, f)
                    ts_files.append(full)
                    result = extractor.extract(full)
                    if result:
                        rel = str(Path(full).relative_to(FIXTURE_DIR))
                        for func in result.functions:
                            func_index[(Path(full).stem, func.name)] = rel

        _build_typescript_call_graph(
            FIXTURE_DIR, graph, func_index, file_list=ts_files,
        )
        return graph

    def test_test_file_has_edges(self):
        """counter.test.tsx calls Counter() — should produce a call edge."""
        graph = self._build_fixture_graph()
        all_edges = list(graph.edges)

        # Find edges originating from the test file
        test_edges = [e for e in all_edges if "counter.test" in e[0]]
        assert len(test_edges) > 0, (
            f"No edges from counter.test.tsx. All edges: {all_edges}"
        )

    def test_test_file_calls_imported_function(self):
        """counter.test.tsx imports Counter and calls it — edge should resolve."""
        graph = self._build_fixture_graph()
        all_edges = list(graph.edges)

        # Should have edge from test file to Counter component
        dst_funcs = {e[3] for e in all_edges if "counter.test" in e[0]}
        assert "Counter" in dst_funcs, (
            f"No edge to Counter from test file. Edges from test: "
            f"{[e for e in all_edges if 'counter.test' in e[0]]}"
        )


# ---------------------------------------------------------------------------
# Bug 6: JSX component usage as call edges
# ---------------------------------------------------------------------------

class TestJSXComponentCalls:
    """<SlotCard /> and <Counter /> in TripView.tsx should create call edges."""

    def _build_fixture_graph(self):
        from tldr.cross_file_calls import _build_typescript_call_graph, ProjectCallGraph
        from tldr.hybrid_extractor import HybridExtractor

        graph = ProjectCallGraph()
        extractor = HybridExtractor()

        func_index = {}
        ts_files = []
        for root_dir, _dirs, files in os.walk(str(FIXTURE_DIR)):
            for f in files:
                if f.endswith((".ts", ".tsx")):
                    full = os.path.join(root_dir, f)
                    ts_files.append(full)
                    result = extractor.extract(full)
                    if result:
                        rel = str(Path(full).relative_to(FIXTURE_DIR))
                        for func in result.functions:
                            func_index[(Path(full).stem, func.name)] = rel

        _build_typescript_call_graph(
            FIXTURE_DIR, graph, func_index, file_list=ts_files,
        )
        return graph

    def test_jsx_creates_call_edges(self):
        """TripView.tsx renders <SlotCard /> and <Counter /> — should be edges."""
        graph = self._build_fixture_graph()
        all_edges = list(graph.edges)

        trip_view_edges = [e for e in all_edges if "TripView" in e[0]]
        dst_funcs = {e[3] for e in trip_view_edges}

        assert "SlotCard" in dst_funcs or "Counter" in dst_funcs, (
            f"No JSX component edges from TripView. "
            f"TripView edges: {trip_view_edges}"
        )
