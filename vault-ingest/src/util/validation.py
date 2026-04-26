"""JSON Schema validation for extraction output (subset of draft-7)."""

import re

from util.json_parse import is_json_null


_DATE_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _type_ok(value, t: str) -> bool:
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return _is_number(value)
    if t == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, float) and value == int(value):
            return True
        return False
    if t == "boolean":
        return isinstance(value, bool)
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "null":
        return is_json_null(value)
    return False


def _error_json_path(path_parts: list) -> str:
    s = "$"
    for part in path_parts:
        if isinstance(part, int):
            s += f"[{part}]"
        else:
            s += f".{part}"
    return s


def _format_ok_for_string(value, schema: dict) -> bool:
    if schema.get("format") != "date" or not isinstance(value, str):
        return True
    return bool(_DATE_RE.match(value))


def _iter_extraction_schema_errors(  # noqa: C901
    value,
    schema: dict,
    path: list,
) -> list[str]:
    """Subset of JSON Schema draft-7 used by taxonomy: type unions, object props,
    arrays, additionalProperties, required, enum, and format: date. No $ref/oneOf.
    """
    p = _error_json_path(path)
    if "enum" in schema and value not in schema["enum"]:
        return [f"{p}: {value!r} is not one of {schema['enum']!r}"]

    typ = schema.get("type")
    if typ is None:
        return []

    if isinstance(typ, list):
        for t in typ:
            if t == "null" and is_json_null(value):
                return []
        for t in typ:
            if t == "null":
                continue
            if not _type_ok(value, t):
                continue
            if t == "string" and not _format_ok_for_string(value, schema):
                return [f"{p}: {value!r} is not a valid date string (expected YYYY-MM-DD)"]
            return []
        return [f"{p}: {value!r} is not of type {typ!r}"]

    if not _type_ok(value, typ):
        return [f"{p}: {value!r} is not of type {typ!r}"]

    if typ == "string" and not _format_ok_for_string(value, schema):
        return [f"{p}: {value!r} is not a valid date string (expected YYYY-MM-DD)"]

    if typ == "object" and isinstance(value, dict):
        out: list[str] = []
        for key in schema.get("required") or ():
            if key not in value:
                p2 = path + [key]
                out.append(f"{_error_json_path(p2)}: {key!r} is a required property")
        add_ok = bool(schema.get("additionalProperties", True))
        props = schema.get("properties") or {}
        for key in value:
            if key in props or add_ok:
                continue
            p2 = path + [key]
            out.append(f"{_error_json_path(p2)}: additional property {key!r} is not allowed")
        for key, sub in props.items():
            if key in value:
                out.extend(
                    _iter_extraction_schema_errors(
                        value[key],
                        sub,
                        path + [key],
                    )
                )
        return out

    if typ == "array" and isinstance(value, list):
        out = []
        items = schema.get("items")
        if items is not None:
            for i, el in enumerate(value):
                out.extend(
                    _iter_extraction_schema_errors(
                        el,
                        items,
                        path + [i],
                    )
                )
        return out

    return []


def validate_extraction(payload, schema: dict, path: str = "$") -> list[str]:
    """Validate extraction output against a JSON object schema; return error strings."""
    del path
    if not isinstance(schema, dict):
        return ["$: schema must be a JSON object"]
    return _iter_extraction_schema_errors(
        payload,
        schema,
        [],
    )
