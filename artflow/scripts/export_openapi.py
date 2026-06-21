from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def _schema_name(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "type" in schema:
        if schema["type"] == "array":
            return f"array[{_schema_name(schema.get('items', {}))}]"
        return str(schema["type"])
    if "anyOf" in schema:
        return " | ".join(_schema_name(item) for item in schema["anyOf"])
    return "object"


def _operation_title(method: str, path: str, operation: dict[str, Any]) -> str:
    summary = operation.get("summary")
    operation_id = operation.get("operationId")
    title = summary or operation_id or f"{method.upper()} {path}"
    return str(title).strip()


def _request_body_summary(operation: dict[str, Any]) -> str:
    request_body = operation.get("requestBody")
    if not request_body:
        return "none"
    content = request_body.get("content", {})
    if not content:
        return "present"
    parts: list[str] = []
    for content_type, body in content.items():
        schema = body.get("schema", {})
        parts.append(f"`{content_type}`: `{_schema_name(schema)}`")
    return ", ".join(parts)


def _parameters_table(operation: dict[str, Any]) -> list[str]:
    params = operation.get("parameters") or []
    if not params:
        return ["Parameters: none"]

    lines = [
        "Parameters:",
        "",
        "| Name | In | Required | Type |",
        "| --- | --- | --- | --- |",
    ]
    for param in params:
        schema = param.get("schema", {})
        required = "yes" if param.get("required") else "no"
        lines.append(
            f"| `{param.get('name', '')}` | `{param.get('in', '')}` | {required} | `{_schema_name(schema)}` |"
        )
    return lines


def _responses_summary(operation: dict[str, Any]) -> list[str]:
    responses = operation.get("responses") or {}
    if not responses:
        return ["Responses: none"]

    lines = ["Responses:"]
    for status, response in sorted(responses.items(), key=lambda item: str(item[0])):
        description = response.get("description") or ""
        content = response.get("content") or {}
        if content:
            content_types = ", ".join(f"`{key}`" for key in content.keys())
            lines.append(f"- `{status}`: {description} ({content_types})")
        else:
            lines.append(f"- `{status}`: {description}")
    return lines


def build_markdown(schema: dict[str, Any]) -> str:
    info = schema.get("info", {})
    title = info.get("title", "API")
    version = info.get("version", "")
    description = info.get("description", "")
    paths = schema.get("paths", {})

    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            tags = operation.get("tags") or ["default"]
            grouped[str(tags[0])].append((path, method.upper(), operation))

    lines = [
        f"# {title} OpenAPI",
        "",
        f"- Version: `{version or 'n/a'}`",
        f"- OpenAPI: `{schema.get('openapi', 'n/a')}`",
        f"- Paths: `{len(paths)}`",
        "",
    ]
    if description:
        lines.extend([str(description), ""])

    lines.extend(
        [
            "## Generated Artifacts",
            "",
            "- Machine-readable schema: `docs/openapi.json`",
            "- Human-readable summary: `docs/openapi.md`",
            "",
            "## Endpoints",
            "",
        ]
    )

    for tag in sorted(grouped):
        lines.extend([f"### {tag}", ""])
        for path, method, operation in sorted(grouped[tag], key=lambda item: (item[0], item[1])):
            title = _operation_title(method, path, operation)
            security = operation.get("security")
            auth = "yes" if security else "not declared"
            lines.extend(
                [
                    f"#### `{method} {path}`",
                    "",
                    f"- Summary: {title}",
                    f"- Operation ID: `{operation.get('operationId', 'n/a')}`",
                    f"- Auth: {auth}",
                    f"- Request body: {_request_body_summary(operation)}",
                    "",
                ]
            )
            description = operation.get("description")
            if description:
                lines.extend([str(description).strip(), ""])
            lines.extend(_parameters_table(operation))
            lines.append("")
            lines.extend(_responses_summary(operation))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI schema and Markdown summary.")
    parser.add_argument("--json", default="docs/openapi.json", help="Path for OpenAPI JSON output.")
    parser.add_argument("--markdown", default="docs/openapi.md", help="Path for Markdown summary output.")
    args = parser.parse_args()

    sys.path.insert(0, str(PROJECT_ROOT))
    from main import app

    schema = app.openapi()
    json_path = Path(args.json)
    markdown_path = Path(args.markdown)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(build_markdown(schema), encoding="utf-8")
    print(f"Wrote {json_path} and {markdown_path}")
    print(f"OpenAPI {schema.get('openapi')} with {len(schema.get('paths', {}))} paths")


if __name__ == "__main__":
    main()
