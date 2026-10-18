import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "code_rules_baseline.txt"
MAX_LINES = 300
ALLOWED_PY_COMMENT = re.compile(r"#\s*(noqa|type:\s*ignore|pragma)\b")
TEST_PART = re.compile(r"(\.test\.|\.spec\.|/__tests__/|/test/setup)")


def python_files() -> list[Path]:
    return sorted((ROOT / "backend" / "app").rglob("*.py"))


def typescript_files() -> list[Path]:
    files = [*(ROOT / "frontend" / "src").rglob("*.ts"), *(ROOT / "frontend" / "src").rglob("*.tsx")]
    return sorted(p for p in files if not TEST_PART.search(p.as_posix()) and not p.name.endswith(".d.ts"))


def has_python_comment(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        if token.start[0] == 1 and token.string.startswith("#!"):
            continue
        if not ALLOWED_PY_COMMENT.match(token.string):
            return True
    return False


def typescript_files_with_comments(files: list[Path]) -> set[Path]:
    script = ROOT / "frontend" / "scripts" / "find-comments.mjs"
    result = subprocess.run(
        ["node", str(script), *map(str, files)],
        cwd=ROOT / "frontend",
        capture_output=True,
        text=True,
        check=True,
    )
    return {Path(line.rsplit(":", 1)[0]) for line in result.stdout.splitlines()}


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def entry(rule: str, path: Path) -> str:
    return f"{rule}\t{path.relative_to(ROOT).as_posix()}"


def current_violations() -> set[str]:
    py_files = python_files()
    ts_files = typescript_files()
    violations = {entry("too-long", p) for p in [*py_files, *ts_files] if line_count(p) > MAX_LINES}
    violations |= {entry("comments", p) for p in py_files if has_python_comment(p)}
    violations |= {entry("comments", p) for p in typescript_files_with_comments(ts_files)}
    return violations


def main() -> int:
    baseline = set(BASELINE.read_text(encoding="utf-8").splitlines()) if BASELINE.exists() else set()
    current = current_violations()
    new = sorted(current - baseline)
    resolved = sorted(baseline - current)
    for line in new:
        print(f"violation\t{line}")
    for line in resolved:
        print(f"resolved, remove from {BASELINE.name}\t{line}")
    return 1 if new or resolved else 0


if __name__ == "__main__":
    sys.exit(main())
