# TypeScript Optimization Plan — llm-tldr

## Context

Stacking: parcadei/llm-tldr (original) → GrigoryEvko/llm-tldr (Qwen3 + usearch) → kevindtbd/llm-tldr (our fixes).

Smoke test targets:
- `~/ed-predictor` — arrow function extraction (React/TS components)
- `tests/fixtures/test-monorepo/` — tsconfig path alias resolution (synthetic)

---

## Fix 1: Arrow Function Extraction (hybrid_extractor.py)

### Gap A: `_collect_ts_definitions` (line 407)
**Problem:** Only collects `function_declaration` names. Arrow functions in `const foo = () => {}` are invisible to the intra-file call graph.

**Fix:** Add `lexical_declaration → variable_declarator` AND `variable_declaration → variable_declarator` check (same pattern as cross_file_calls.py:1996). Handle both `const/let` and `var` for completeness:
```python
elif child.type in ("lexical_declaration", "variable_declaration"):
    for vc_child in child.children:
        if vc_child.type == "variable_declarator":
            name = None
            has_arrow = False
            for vcc in vc_child.children:
                if vcc.type == "identifier":
                    name = self._safe_decode(source[vcc.start_byte:vcc.end_byte])
                elif vcc.type == "arrow_function":
                    has_arrow = True
            if name and has_arrow:
                names.add(name)
```

Also add `"lexical_declaration", "variable_declaration"` to the recursion set at line 429.

### Gap B: `_extract_ts_function` name resolution (line 637)
**Problem:** Returns `None` for arrow functions (no `identifier` child). Fallbacks (`_get_pair_property_name`, `_get_assignment_name`) don't handle `variable_declarator`.

**Fix:** Modify `_extract_ts_function` to walk up `.parent` to `variable_declarator` when no direct name found:
```python
# After line 657 (if not name:), before returning None:
if not name and node.type in ("arrow_function", "function_expression"):
    current = node.parent
    while current:
        if current.type == "variable_declarator":
            for c in current.children:
                if c.type == "identifier":
                    name = self._safe_decode(source[c.start_byte:c.end_byte])
                    break
            break
        current = current.parent
```

Note: Also handles unnamed `function_expression` in `const foo = function() {}` (architect review finding B).

### Files changed:
- `tldr/hybrid_extractor.py` — `_collect_ts_definitions`, `_extract_ts_function`

---

## Fix 2: tsconfig Path Alias Resolution

### New file: `tldr/tsconfig_resolver.py`

`TSConfigResolver` class (flat, consistent with codebase):
- `__init__(project_root)` — loads tsconfig.json + tsconfig.base.json
- `_load_tsconfig(path, _seen=None)` — follows `extends` chains, caches results
- `_extract_paths(config, config_dir)` — parses `compilerOptions.paths` with `baseUrl`
- `_strip_json_comments(text)` — state-machine approach (handles strings correctly)
- `resolve(import_path)` → `Optional[str]` — returns **absolute path** or None
- `_try_resolve_file(base_path)` → `Optional[str]` — tries extensions + index files

**Security hardening (from security review):**
1. **Path containment:** `_try_resolve_file` checks `resolved.is_relative_to(project_root)` before returning. Rejects paths escaping project root.
2. **Circular extends:** `_load_tsconfig` tracks visited paths in `_seen: set`. Breaks cycles silently.
3. **Extends depth limit:** Cap at 10 levels.
4. **Extends containment:** Containment check on extends paths before loading.
5. **npm-package extends:** Handle `"extends": "@tsconfig/node18/tsconfig.json"` by resolving from `node_modules/` or skipping gracefully.

### Integration: `cross_file_calls.py`

**Correct function name:** `_build_typescript_call_graph` (not `_build_ts_call_graph`)

In the import resolution section (~line 3414-3419):
```python
# BEFORE
if module.startswith('.'):
    module_path = _resolve_ts_import(rel_path, module)
else:
    module_path = module

# AFTER
if module.startswith('.'):
    module_path = _resolve_ts_import(rel_path, module)
else:
    resolved = tsconfig_resolver.resolve(module)
    if resolved:
        module_path = str(Path(resolved).relative_to(root))
    else:
        module_path = module
```

Initialize `tsconfig_resolver = TSConfigResolver(str(root))` at the top of `_build_typescript_call_graph`.

### Files changed:
- `tldr/tsconfig_resolver.py` (new)
- `tldr/cross_file_calls.py` — `_build_typescript_call_graph`

---

## Smoke Test Plan

### Test 1: Arrow functions (ed-predictor)
1. `pip install -e .` in llm-tldr dir
2. `tldr structure ~/ed-predictor/frontend/src/components/Dashboard.tsx --lang typescript`
3. **Expected:** Arrow functions in useQuery callbacks should appear
4. `tldr calls ~/ed-predictor/frontend/` — verify cross-file edges for TS

### Test 2: tsconfig resolver (synthetic fixture)
1. Create `tests/fixtures/test-monorepo/` with:
   - `tsconfig.json` with `@shared/*` alias
   - `packages/shared/src/helper.ts` (exports `helper`)
   - `packages/feature-a/src/handler.ts` (imports `helper` from `@shared`)
2. `tldr calls tests/fixtures/test-monorepo/`
3. **Expected:** handler.ts → helper.ts edge exists in call graph

### Test 3: Existing tests pass
1. `python -m pytest tests/` — no regressions

---

## Execution Order

1. Fix 1 (arrow functions) — hybrid_extractor.py only
2. Fix 2 (tsconfig resolver) — new file + cross_file_calls.py integration
3. Create synthetic test fixture
4. Run smoke tests (ed-predictor + fixture + existing tests)
5. Push to kevindtbd/llm-tldr

## Review Findings Incorporated
- [Architect] Function name corrected to `_build_typescript_call_graph`
- [Architect] Resolver returns absolute paths (required by `relative_to(root)`)
- [Architect] Also handle `variable_declaration` (var) in `_collect_ts_definitions`
- [Architect] Also handle `function_expression` in parent walk (not just arrow_function)
- [Architect] Handle npm-package extends or skip gracefully
- [Security] Path containment check in resolver (is_relative_to)
- [Security] Circular extends detection (visited set)
- [Security] Extends depth limit (cap at 10)
- [Security] Extends path containment (no escaping project root)

## NOT in scope
- Barrel file re-export chain following
- workspace:* protocol resolution
- Per-package tsconfig overrides
- Embedding model swaps
- Decorator pattern handling
