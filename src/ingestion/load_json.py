from pathlib import Path
import json

RAW_PATH = Path("data/raw/placements.json")


def main() -> None:
    if not RAW_PATH.exists():
        print(f"Missing file: {RAW_PATH}")
        return

    with RAW_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded top-level object type: {type(data).__name__}")
    print(f"Top-level record count: {len(data) if isinstance(data, list) else 'N/A'}")


if __name__ == "__main__":
    main()
