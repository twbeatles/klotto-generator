from __future__ import annotations

from pathlib import Path
import sys

TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".json",
    ".txt",
    ".spec",
    ".yml",
    ".yaml",
}
ALWAYS_INCLUDE = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "requirements.txt",
}
SKIP_DIRS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".pyright",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "venv",
}


def should_check(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in ALWAYS_INCLUDE


def iter_text_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and should_check(path))


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    issues: list[str] = []
    checked_files = 0

    for path in iter_text_files(repo_root):
        checked_files += 1
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            issues.append(f"{path.relative_to(repo_root)}: invalid UTF-8 ({exc})")
            continue

        if "\ufffd" in text:
            issues.append(f"{path.relative_to(repo_root)}: contains Unicode replacement characters")

    if issues:
        print("UTF-8 verification failed:")
        for issue in issues:
            print(f" - {issue}")
        return 1

    print(f"UTF-8 verification passed for {checked_files} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
