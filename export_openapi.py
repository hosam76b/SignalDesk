"""Export the FastAPI OpenAPI document for frontend consumers."""

import argparse
import json
from pathlib import Path

from main import app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export the SignalDesk OpenAPI document.")
    parser.add_argument("-o", "--output", default="openapi.json", help="Output JSON file path.")
    parser.add_argument("--compact", action="store_true", help="Write compact JSON without indentation.")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    indent = None if args.compact else 2
    output.write_text(json.dumps(app.openapi(), indent=indent, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {output.resolve()}")
