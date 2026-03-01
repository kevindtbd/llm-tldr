"""Resolves TypeScript path aliases from tsconfig.json for cross-package import tracing."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TSConfigResolver:
    """Loads tsconfig.json path aliases and resolves aliased imports to absolute paths.

    All resolved paths are absolute and containment-checked against the project root
    to prevent path traversal attacks via malicious tsconfig entries.
    """

    # Extensions to try when resolving a bare import path to a file
    _FILE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", "")
    _INDEX_FILES = ("index.ts", "index.tsx", "index.js", "index.jsx")

    def __init__(self, project_root: str) -> None:
        self.project_root: Path = Path(project_root).resolve()
        self.path_mappings: list[tuple[str, str]] = []  # (prefix, resolved_target_dir)
        self._tsconfig_cache: dict[str, dict] = {}
        self._load_all_tsconfigs()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all_tsconfigs(self) -> None:
        """Load root tsconfig.json and tsconfig.base.json, extract path mappings."""
        for name in ("tsconfig.json", "tsconfig.base.json"):
            cfg_path = self.project_root / name
            if cfg_path.is_file():
                config = self._load_tsconfig(cfg_path)
                if config:
                    self._extract_paths(config, cfg_path.parent)

    def _load_tsconfig(self, path: Path, _seen: set | None = None) -> dict | None:
        """Load a tsconfig file, following ``extends`` chains.

        Security:
        - Tracks visited paths in *_seen* to break circular extends.
        - Depth-limited to 10 levels.
        - Containment-checked: refuses to follow extends outside project root.
        """
        resolved = path.resolve()

        if _seen is None:
            _seen = set()

        # Cycle / depth guard
        if str(resolved) in _seen:
            return None
        if len(_seen) > 10:
            return None
        _seen.add(str(resolved))

        # Cache hit
        cache_key = str(resolved)
        if cache_key in self._tsconfig_cache:
            return self._tsconfig_cache[cache_key]

        # Read & parse
        try:
            raw = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Could not read tsconfig %s: %s", resolved, exc)
            return None

        try:
            cleaned = self._strip_json_comments(raw)
            config: dict = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not parse tsconfig %s: %s", resolved, exc)
            return None

        # Follow extends
        extends_value = config.pop("extends", None)
        if extends_value:
            parent_config = self._resolve_extends(extends_value, resolved.parent, _seen)
            if parent_config is not None:
                # Merge: parent first, child overrides
                merged_compiler = {
                    **parent_config.get("compilerOptions", {}),
                    **config.get("compilerOptions", {}),
                }
                merged = {**parent_config, **config}
                merged["compilerOptions"] = merged_compiler
                config = merged

        self._tsconfig_cache[cache_key] = config
        return config

    def _resolve_extends(
        self, extends_value: str, config_dir: Path, _seen: set
    ) -> dict | None:
        """Resolve a tsconfig ``extends`` value to a loaded config dict."""
        candidates: list[Path] = []

        if extends_value.startswith("."):
            # Relative path
            base = (config_dir / extends_value).resolve()
            candidates.append(base)
            if not extends_value.endswith(".json"):
                candidates.append(base.with_suffix(".json"))
                candidates.append(base / "tsconfig.json")
        else:
            # npm-package style (e.g. "@tsconfig/node18/tsconfig.json")
            nm = config_dir / "node_modules" / extends_value
            candidates.append(nm.resolve())
            if not extends_value.endswith(".json"):
                candidates.append((nm.with_suffix(".json")).resolve())
                candidates.append((nm / "tsconfig.json").resolve())
            # Also try from project root node_modules
            nm_root = self.project_root / "node_modules" / extends_value
            candidates.append(nm_root.resolve())
            if not extends_value.endswith(".json"):
                candidates.append((nm_root.with_suffix(".json")).resolve())
                candidates.append((nm_root / "tsconfig.json").resolve())

        for candidate in candidates:
            # Containment check
            try:
                if not candidate.is_relative_to(self.project_root):
                    continue
            except (TypeError, ValueError):
                continue

            if candidate.is_file():
                return self._load_tsconfig(candidate, _seen)

        logger.warning(
            "Could not resolve tsconfig extends '%s' from %s", extends_value, config_dir
        )
        return None

    # ------------------------------------------------------------------
    # Path extraction
    # ------------------------------------------------------------------

    def _extract_paths(self, config: dict, config_dir: Path) -> None:
        """Extract compilerOptions.paths into self.path_mappings."""
        compiler_options = config.get("compilerOptions", {})
        base_url = compiler_options.get("baseUrl", ".")
        paths = compiler_options.get("paths")
        if not paths:
            return

        base_dir = (config_dir / base_url).resolve()

        for alias_pattern, targets in paths.items():
            if not isinstance(targets, list) or not targets:
                continue

            # Use first target (standard TS behaviour)
            target = targets[0]

            if alias_pattern.endswith("/*") and target.endswith("/*"):
                # Wildcard: @features/* -> src/features/*
                prefix = alias_pattern[:-2]  # strip /*
                target_dir = (base_dir / target[:-2]).resolve()  # strip /*
                self.path_mappings.append((prefix, str(target_dir)))
            else:
                # Exact match: @shared -> src/shared
                resolved_target = (base_dir / target).resolve()
                self.path_mappings.append((alias_pattern, str(resolved_target)))

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, import_path: str) -> Optional[str]:
        """Resolve an aliased import path to an absolute file path.

        Returns None for relative imports, unresolvable aliases, or paths
        that escape the project root.
        """
        # Skip relative imports
        if import_path.startswith("."):
            return None

        if not self.path_mappings:
            return None

        # Try exact match first
        for prefix, target in self.path_mappings:
            if import_path == prefix:
                result = self._try_resolve_file(target)
                if result:
                    return result

        # Try wildcard prefix match
        for prefix, target_dir in self.path_mappings:
            if import_path.startswith(prefix + "/"):
                rest = import_path[len(prefix) + 1 :]
                candidate = os.path.join(target_dir, rest)
                result = self._try_resolve_file(candidate)
                if result:
                    return result

        return None

    def _try_resolve_file(self, base_path: str) -> Optional[str]:
        """Try to resolve *base_path* to an actual file on disk.

        Tries bare path with extensions, then as directory with index files,
        then package.json main/module/types fields.

        Every candidate is containment-checked against project_root.
        """
        base = Path(base_path)

        # 1. Try as file (with extensions)
        for ext in self._FILE_EXTENSIONS:
            candidate = base.parent / (base.name + ext) if ext else base
            resolved = candidate.resolve()
            if self._is_safe(resolved) and resolved.is_file():
                return str(resolved)

        # 2. Try as directory with index files
        if base.resolve().is_dir():
            for index_name in self._INDEX_FILES:
                candidate = (base / index_name).resolve()
                if self._is_safe(candidate) and candidate.is_file():
                    return str(candidate)

        # 3. Try package.json main/module/types
        pkg_json = (base / "package.json").resolve()
        if self._is_safe(pkg_json) and pkg_json.is_file():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
                for field in ("types", "module", "main"):
                    entry = pkg.get(field)
                    if entry:
                        entry_path = (base / entry).resolve()
                        if self._is_safe(entry_path) and entry_path.is_file():
                            return str(entry_path)
            except (OSError, json.JSONDecodeError, ValueError):
                pass

        return None

    def _is_safe(self, resolved: Path) -> bool:
        """Return True if *resolved* is inside the project root."""
        try:
            return resolved.is_relative_to(self.project_root)
        except (TypeError, ValueError):
            return False

    # ------------------------------------------------------------------
    # JSON comment stripping
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_json_comments(text: str) -> str:
        """Strip ``//`` and ``/* */`` comments from JSON text.

        Uses a character-by-character state machine so that comment
        delimiters inside string literals are left untouched.
        """
        result: list[str] = []
        i = 0
        length = len(text)
        in_string = False
        in_line_comment = False
        in_block_comment = False

        while i < length:
            c = text[i]

            # --- Inside a line comment ---
            if in_line_comment:
                if c == "\n":
                    in_line_comment = False
                    result.append(c)
                i += 1
                continue

            # --- Inside a block comment ---
            if in_block_comment:
                if c == "*" and i + 1 < length and text[i + 1] == "/":
                    in_block_comment = False
                    i += 2
                else:
                    i += 1
                continue

            # --- Inside a string literal ---
            if in_string:
                result.append(c)
                if c == "\\" and i + 1 < length:
                    # Escaped character — emit it and skip
                    result.append(text[i + 1])
                    i += 2
                    continue
                if c == '"':
                    in_string = False
                i += 1
                continue

            # --- Normal mode ---
            if c == '"':
                in_string = True
                result.append(c)
                i += 1
                continue

            if c == "/" and i + 1 < length:
                next_c = text[i + 1]
                if next_c == "/":
                    in_line_comment = True
                    i += 2
                    continue
                if next_c == "*":
                    in_block_comment = True
                    i += 2
                    continue

            result.append(c)
            i += 1

        return "".join(result)
