"""Convert uploaded files (structured and unstructured) into plain text for analysis."""

import csv
import io
import json
from email import policy
from email.parser import BytesParser
from pathlib import PurePath

import yaml

MAX_FILE_BYTES = 10 * 1024 * 1024


class UnsupportedFileError(ValueError):
    pass


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(f"[Page {i}]\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages, 1))


def _docx(data: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        parts += [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
    return "\n".join(parts)


def _eml(data: bytes) -> str:
    msg = BytesParser(policy=policy.default).parsebytes(data)
    body = msg.get_body(preferencelist=("plain", "html"))
    header = "\n".join(f"{h}: {msg[h]}" for h in ("From", "To", "Cc", "Date", "Subject") if msg[h])
    return f"{header}\n\n{body.get_content() if body else ''}"


def _openapi_summary(spec: dict) -> str:
    lines = [f"API: {spec.get('info', {}).get('title', 'unnamed')} {spec.get('info', {}).get('version', '')}".strip()]
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            if isinstance(op, dict):
                lines.append(f"- {method.upper()} {path}: {op.get('summary') or op.get('description', '')}".rstrip(": "))
    schemas = spec.get("components", {}).get("schemas", {})
    for name, schema in schemas.items():
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        fields = ", ".join(f"{k}{'*' if k in required else ''} ({v.get('type', 'object')})" for k, v in props.items())
        lines.append(f"Schema {name}: {fields}")
    return "\n".join(lines)


def _structured(data: dict | list) -> str:
    if isinstance(data, dict) and ("openapi" in data or "swagger" in data):
        return _openapi_summary(data)
    # Questionnaire format: [{"question": ..., "answer": ...}] or {"answers": [...]}
    items = data.get("answers") if isinstance(data, dict) else data
    if isinstance(items, list) and items and all(isinstance(i, dict) and "question" in i for i in items):
        return "\n\n".join(f"Q: {i['question']}\nA: {i.get('answer', '')}" for i in items)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _csv(data: bytes) -> str:
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    if rows and "question" in rows[0]:
        return "\n\n".join(f"Q: {r['question']}\nA: {r.get('answer', '')}" for r in rows)
    return "\n".join("; ".join(f"{k}: {v}" for k, v in r.items()) for r in rows)


def extract_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise UnsupportedFileError("File exceeds 10 MB limit")
    ext = PurePath(filename).suffix.lower().lstrip(".")
    match ext:
        case "pdf":
            return _pdf(data)
        case "docx":
            return _docx(data)
        case "eml":
            return _eml(data)
        case "json":
            return _structured(json.loads(data))
        case "yaml" | "yml":
            return _structured(yaml.safe_load(data))
        case "csv":
            return _csv(data)
        case "txt" | "md" | "sql":
            return data.decode("utf-8", errors="replace")
        case _:
            raise UnsupportedFileError(f"Unsupported file type: .{ext}")
