from __future__ import annotations

import json
from pathlib import Path

from custerion_collection.config import data_dir
from custerion_collection.models import deep_dive_artifact_json_schema


def export_deep_dive_schema(output_path: str | None = None) -> Path:
    """Write the DeepDiveArtifact JSON schema to disk and return the file path."""
    if output_path:
        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path = data_dir() / "schemas" / "deep_dive_artifact.schema.json"
        path.parent.mkdir(parents=True, exist_ok=True)

    schema = deep_dive_artifact_json_schema()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")
    return path
