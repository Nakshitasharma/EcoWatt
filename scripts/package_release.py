"""Create a clean, portable EcoWatt source archive without local secrets or DB state."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "EcoWatt.zip"
SOURCE_DIRS = ("backend", "frontend", "integrations", "scripts", "tests")
ROOT_FILES = ("README.md", "requirements.txt", ".env.example", ".gitignore")
DATA_FILES = ("data/BDG2_ATTRIBUTION.md", "data/bdg2_education_sample.csv")
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}


def main() -> None:
    entries: set[Path] = set()
    for directory in SOURCE_DIRS:
        for path in (ROOT / directory).rglob("*"):
            if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            if path.name == ".env" or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pyc"}:
                continue
            entries.add(path)
    entries.update(ROOT / name for name in ROOT_FILES if (ROOT / name).is_file())
    entries.update(ROOT / name for name in DATA_FILES if (ROOT / name).is_file())

    with ZipFile(DESTINATION, "w", compression=ZIP_DEFLATED, compresslevel=8) as archive:
        for path in sorted(entries):
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(f"Created {DESTINATION} with {len(entries)} files")


if __name__ == "__main__":
    main()
