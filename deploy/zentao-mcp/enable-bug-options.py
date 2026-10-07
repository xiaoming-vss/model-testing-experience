"""Generate a schema overlay for paging, assignment and native file reads; no credentials."""

import argparse
import json
from pathlib import Path
import subprocess


def patch_schema(schema):
    paths = schema["paths"]
    for path, method in (("/bugs", "post"), ("/bugs/:bugID", "put")):
        properties = paths[path][method]["requestBody"]["content"]["application/json"][
            "schema"
        ]["properties"]
        properties["assignedTo"] = {
            "type": "string",
            "description": "指派人，使用禅道用户 account",
        }
    # OpenAPI path parameters require brace notation. The generated MCP tool
    # name stays get_executions_executionID_builds for both path spellings.
    legacy_path = "/executions/:executionID/builds"
    normalized_path = "/executions/{executionID}/builds"
    if legacy_path in paths:
        paths[normalized_path] = paths.pop(legacy_path)
    operation = paths[normalized_path]["get"]
    parameters = operation.setdefault("parameters", [])
    for name, location in (
        ("executionID", "path"),
        ("pageID", "query"),
        ("recPerPage", "query"),
    ):
        if not any(
            p.get("name") == name and p.get("in") == location for p in parameters
        ):
            parameters.append(
                {
                    "name": name,
                    "in": location,
                    "required": location == "path",
                    "schema": {"type": "integer", "minimum": 1},
                }
            )
    # Inline images may be omitted from Bug.files; metadata remains readable by file ID.
    legacy_file = paths.get("/files/:fileID", {})
    operation = paths.setdefault("/files/{fileID}", {}).setdefault("get", legacy_file.pop("get", {
        "summary": "Read native file ownership and metadata",
        "responses": {"200": {"description": "Native file metadata",
            "content": {"application/json": {"schema": {"type": "object"}}}}},
    }))
    parameters = operation.setdefault("parameters", [])
    if not any(p.get("name") == "fileID" and p.get("in") == "path" for p in parameters):
        parameters.append({"name": "fileID", "in": "path", "required": True,
                           "schema": {"type": "integer", "minimum": 1}})
    return schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", help="Default: image resolved from compose.yaml")
    parser.add_argument(
        "--output", type=Path, default=Path("config/bug-options-openapi.json")
    )
    args = parser.parse_args()
    image = args.image
    if not image:
        config = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "compose",
                    "-f",
                    "compose.yaml",
                    "config",
                    "--format",
                    "json",
                ]
            )
        )
        image = config["services"]["zentao-mcp"]["image"]
    raw = subprocess.check_output(
        [
            "docker",
            "run",
            "--rm",
            "--pull=missing",
            "--entrypoint",
            "cat",
            image,
            "/config/zentao-openapi.json",
        ]
    )
    schema = patch_schema(json.loads(raw))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
    temporary.chmod(0o644)
    temporary.replace(args.output)
    print(f"已生成 {args.output}；使用 compose.bug-options.yaml 重新创建 MCP 后生效。")


if __name__ == "__main__":
    main()
