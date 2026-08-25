"""Export the FastAPI OpenAPI document for frontend consumers."""

import json
from pathlib import Path

from main import app


if __name__ == "__main__":
    output = Path("openapi.json")
    output.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {output.resolve()}")
