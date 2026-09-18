"""Audit backend architecture size, coupling and dependency cycles.

The script is intentionally dependency-free so it can run in CI before the
application environment is installed.
"""
from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"


def _module_name(path: Path) -> str:
    relative = path.relative_to(BACKEND_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_relative(module: str, level: int, imported: str | None) -> str:
    package = module.split(".")[:-1]
    if level > 0:
        keep = max(0, len(package) - level + 1)
        base = package[:keep]
    else:
        base = []
    suffix = [part for part in (imported or "").split(".") if part]
    return ".".join([*base, *suffix])


def _extract_imports(module: str, tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_relative(module, node.level, node.module)
            if target:
                imports.add(target)
                imports.update(f"{target}.{alias.name}" for alias in node.names)
    return imports


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for target in graph.get(node, set()):
            if target not in graph:
                continue
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])

        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            item = stack.pop()
            on_stack.remove(item)
            component.append(item)
            if item == node:
                break
        if len(component) > 1:
            components.append(sorted(component))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return sorted(components, key=lambda item: (-len(item), item))


def _top_target(target: str, known: set[str]) -> str | None:
    candidate = target
    while candidate and candidate not in known:
        candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
    return candidate or None


def build_report(*, god_lines: int = 800, fan_in_limit: int = 20, fan_out_limit: int = 20) -> dict:
    modules: dict[str, Path] = {}
    line_counts: dict[str, int] = {}
    raw_imports: dict[str, set[str]] = {}

    for path in sorted(APP_ROOT.rglob("*.py")):
        module = _module_name(path)
        modules[module] = path
        text = path.read_text(encoding="utf-8")
        line_counts[module] = len(text.splitlines())
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            raw_imports[module] = set()
            continue
        raw_imports[module] = _extract_imports(module, tree)

    known = set(modules)
    graph: dict[str, set[str]] = {}
    for module, imports in raw_imports.items():
        targets = {
            resolved
            for item in imports
            if (resolved := _top_target(item, known)) is not None
            and resolved != module
        }
        graph[module] = targets

    fan_in = Counter(target for targets in graph.values() for target in targets)
    god_files = [
        {
            "module": module,
            "lines": line_counts[module],
            "path": modules[module].relative_to(BACKEND_ROOT).as_posix(),
        }
        for module in modules
        if line_counts[module] > god_lines
    ]
    god_files.sort(key=lambda item: (-item["lines"], item["module"]))

    high_fan_in = [
        {"module": module, "fan_in": count}
        for module, count in fan_in.most_common()
        if count >= fan_in_limit
    ]
    high_fan_out = [
        {"module": module, "fan_out": len(targets)}
        for module, targets in sorted(graph.items(), key=lambda item: (-len(item[1]), item[0]))
        if len(targets) >= fan_out_limit
    ]
    cycles = _strongly_connected_components(graph)

    package_counts = Counter(module.split(".")[1] if "." in module else module for module in modules)
    package_lines = Counter()
    for module, lines in line_counts.items():
        package = module.split(".")[1] if "." in module else module
        package_lines[package] += lines

    critical = bool(cycles or high_fan_out or any(item["lines"] > 1500 for item in god_files))
    return {
        "root": APP_ROOT.relative_to(BACKEND_ROOT.parent).as_posix(),
        "thresholds": {
            "god_lines": god_lines,
            "fan_in": fan_in_limit,
            "fan_out": fan_out_limit,
        },
        "summary": {
            "modules": len(modules),
            "total_lines": sum(line_counts.values()),
            "god_files": len(god_files),
            "cycles": len(cycles),
            "high_fan_in_modules": len(high_fan_in),
            "high_fan_out_modules": len(high_fan_out),
        },
        "packages": [
            {"package": package, "modules": package_counts[package], "lines": package_lines[package]}
            for package in sorted(package_counts)
        ],
        "god_files": god_files,
        "high_fan_in": high_fan_in,
        "high_fan_out": high_fan_out,
        "cycles": cycles,
        "critical": critical,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--god-lines", type=int, default=800)
    parser.add_argument("--fan-in", type=int, default=20)
    parser.add_argument("--fan-out", type=int, default=20)
    parser.add_argument("--output", default="")
    parser.add_argument("--fail-on-critical", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_report(
        god_lines=args.god_lines,
        fan_in_limit=args.fan_in,
        fan_out_limit=args.fan_out,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    if args.fail_on_critical and report["critical"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
