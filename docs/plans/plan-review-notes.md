# Plan Review Notes — 2026-03-01

## Critical Issues Found

### 1. Fix 1 Gap B approach was wrong
**Original plan:** Intercept `variable_declarator` in `_extract_ts_nodes` recursion logic.
**Problem:** Adds complexity to the recursion control flow.
**Resolution:** Modify `_extract_ts_function` itself to walk up `.parent` to `variable_declarator` for the name when no direct identifier found. Same pattern as `_get_pair_property_name`. Self-contained fix.

### 2. `_get_assignment_name` does NOT handle `const foo = () => {}`
**Verified:** It only handles CommonJS `exports.foo = function(){}` patterns (looks for `assignment_expression → member_expression`). The `const foo` pattern is `lexical_declaration → variable_declarator`, completely different tree structure. Plan diagnosis confirmed correct.

### 3. Package structure: keep flat
**Original plan:** New `tldr/resolvers/` package.
**Resolution:** `tldr/tsconfig_resolver.py` — consistent with flat codebase structure.

### 4. Smoke test target gap
**Problem:** ed-predictor has `@/*` alias configured but unused — all imports are relative. Can't validate tsconfig resolver with ed-predictor alone.
**Resolution:** Create a synthetic test fixture (`tests/fixtures/test-monorepo/`) with path aliases for resolver validation.

## Risks

- **tree-sitter `.parent` availability:** Verify that tree-sitter Python bindings expose `.parent` on nodes. If not, need to pass parent context manually. (Low risk — modern tree-sitter-python does expose it.)

## No Issues Found With
- Fix 1 Gap A (collect_ts_definitions) — straightforward, mirrors existing pattern in cross_file_calls.py
- Fix 2 (tsconfig resolver) — design is solid, edge cases covered
- Execution order — correct dependencies
- Scope boundaries — appropriate for first pass
