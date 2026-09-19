from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path

EXT_LANG = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".rb": "ruby", ".php": "php",
    ".md": "markdown", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml", ".json": "json",
}
IGNORE = {".git", ".continuity", "node_modules", ".venv", "venv", "dist", "build", "target", "__pycache__", ".next", ".cache"}
SYMBOL_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|interface|type|struct|enum|fn)\s+([A-Za-z_$][\w$]*)", re.M)
IMPORT_RE = re.compile(r"(?:from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\)|^\s*import\s+([\w./-]+)|^\s*use\s+([\w:]+))", re.M)


def _iter_files(root: Path):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE and not d.startswith(".continuity")]
        b = Path(base)
        for name in files:
            p = b / name
            if p.suffix.lower() not in EXT_LANG:
                continue
            try:
                if p.stat().st_size > 1_500_000:
                    continue
            except OSError:
                continue
            yield p


def build_index(root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    files, symbols, edges = [], [], []
    for p in _iter_files(root):
        rel = p.relative_to(root).as_posix()
        try:
            raw = p.read_bytes(); text = raw.decode("utf-8"); st = p.stat()
        except (OSError, UnicodeDecodeError):
            continue
        lang = EXT_LANG[p.suffix.lower()]
        files.append({"path": rel, "lang": lang, "digest": hashlib.sha256(raw).hexdigest()[:16], "mtime_ns": st.st_mtime_ns, "summary": text[:500].replace("\x00", "")})
        if lang == "python":
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        symbols.append({"path": rel, "symbol": node.name, "kind": node.__class__.__name__.lower(), "line": node.lineno})
                    elif isinstance(node, ast.Import):
                        for n in node.names:
                            edges.append({"src": rel, "dst": n.name, "kind": "imports", "evidence": f"{rel}:{node.lineno}"})
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        edges.append({"src": rel, "dst": node.module, "kind": "imports", "evidence": f"{rel}:{node.lineno}"})
            except SyntaxError:
                pass
        else:
            for m in SYMBOL_RE.finditer(text):
                symbols.append({"path": rel, "symbol": m.group(1), "kind": "symbol", "line": text.count("\n", 0, m.start()) + 1})
            for m in IMPORT_RE.finditer(text):
                dst = next((g for g in m.groups() if g), None)
                if dst:
                    edges.append({"src": rel, "dst": dst, "kind": "imports", "evidence": f"{rel}:{text.count(chr(10), 0, m.start()) + 1}"})
    return files, symbols, edges
