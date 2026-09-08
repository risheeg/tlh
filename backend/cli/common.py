"""Shared helpers for the tlh CLI (config, DB session, API link discovery)."""

from __future__ import annotations

import argparse
import ast
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# backend/ (package lives at backend/cli/)
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Config helpers  (~/.tlh_config.json  stores the active user UUID)
# ---------------------------------------------------------------------------

CONFIG_PATH = Path.home() / ".tlh_config.json"

DEFAULT_LINK_TARGET = "main"
LINK_BASE_URL_ALIASES = {
    "main": "http://127.0.0.1:8001",
    "devbox": "http://localhost:8000",
}

SECTION_LABELS = {
    "api-docs": "API Documentation",
    "health": "Health",
    "accounts": "Accounts",
    "ingest": "Ingest",
    "portfolio": "Portfolio",
    "prices": "Prices",
    "corporate-actions": "Corporate Actions",
}

SECTION_ORDER = {section: index for index, section in enumerate(SECTION_LABELS)}

HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put"}


@dataclass(frozen=True)
class ApiLink:
    section: str
    methods: tuple[str, ...]
    path: str
    label: str


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _get_user_id() -> uuid.UUID:
    """Return the active user UUID or exit with a helpful message."""
    cfg = _load_config()
    raw = cfg.get("user_id")
    if not raw:
        sys.exit(
            "Error: no user set.\n"
            "Run:  uv run python scripts/cli.py auth set-user --uuid <UUID>\n"
            "  or  uv run python scripts/cli.py auth set-user --new"
        )
    try:
        return uuid.UUID(raw)
    except ValueError:
        sys.exit(f"Error: stored user_id '{raw}' is not a valid UUID. "
                 "Re-run `auth set-user` to fix it.")


# ---------------------------------------------------------------------------
# API link discovery helpers
# ---------------------------------------------------------------------------

def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _literal_string(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_strings(node: ast.expr | None) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    values: list[str] = []
    for item in node.elts:
        value = _literal_string(item)
        if value is not None:
            values.append(value)
    return values


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _route_source_files() -> list[Path]:
    backend_root = BACKEND_ROOT
    routers_dir = backend_root / "routers"
    preferred_files = [
        backend_root / "main.py",
        routers_dir / "accounts.py",
        routers_dir / "ingest.py",
        routers_dir / "portfolio.py",
        routers_dir / "prices.py",
        routers_dir / "corporate_actions.py",
    ]
    preferred = [path for path in preferred_files if path.exists()]
    preferred_resolved = {path.resolve() for path in preferred}
    extra = sorted(
        path
        for path in routers_dir.glob("*.py")
        if path.name != "__init__.py" and path.resolve() not in preferred_resolved
    )
    return preferred + extra


def _router_metadata(tree: ast.AST) -> dict[str, tuple[str, list[str]]]:
    metadata: dict[str, tuple[str, list[str]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        if _call_name(node.value) != "APIRouter":
            continue

        prefix = _literal_string(_keyword(node.value, "prefix")) or ""
        tags = _literal_strings(_keyword(node.value, "tags"))
        for target in node.targets:
            if isinstance(target, ast.Name):
                metadata[target.id] = (prefix, tags)
    return metadata


def _section_for_route(tags: list[str], prefix: str) -> str:
    if tags:
        return tags[0]
    path_section = prefix.strip("/").split("/", maxsplit=1)[0]
    return path_section or "api"


def _route_path(prefix: str, path: str) -> str:
    if not path:
        joined = prefix or "/"
    elif not prefix:
        joined = path
    else:
        joined = f"{prefix.rstrip('/')}/{path.lstrip('/')}"
    return joined if joined.startswith("/") else f"/{joined}"


def _route_methods(method_name: str, call: ast.Call) -> tuple[str, ...]:
    if method_name == "api_route":
        methods = _literal_strings(_keyword(call, "methods"))
        return tuple(method.upper() for method in methods) or ("GET",)
    return (method_name.upper(),)


def _route_label(function_node: ast.FunctionDef | ast.AsyncFunctionDef, call: ast.Call) -> str:
    summary = _literal_string(_keyword(call, "summary"))
    if summary:
        return summary.rstrip(".")

    docstring = ast.get_docstring(function_node)
    if docstring:
        return docstring.strip().splitlines()[0].rstrip(".")

    return function_node.name.replace("_", " ").capitalize()


def _extract_links_from_file(path: Path) -> list[ApiLink]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        sys.exit(f"Error: could not parse routes from {path}: {exc}")

    routers = _router_metadata(tree)
    links: list[ApiLink] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue

            method_name = decorator.func.attr.lower()
            if method_name not in HTTP_METHODS and method_name != "api_route":
                continue
            owner = decorator.func.value
            if not isinstance(owner, ast.Name):
                continue

            if owner.id == "app":
                prefix, router_tags = "", []
            elif owner.id in routers:
                prefix, router_tags = routers[owner.id]
            else:
                continue

            route_path = None
            if decorator.args:
                route_path = _literal_string(decorator.args[0])
            route_path = route_path if route_path is not None else _literal_string(
                _keyword(decorator, "path")
            )
            if route_path is None:
                continue

            route_tags = _literal_strings(_keyword(decorator, "tags")) or router_tags
            links.append(
                ApiLink(
                    section=_section_for_route(route_tags, prefix),
                    methods=_route_methods(method_name, decorator),
                    path=_route_path(prefix, route_path),
                    label=_route_label(node, decorator),
                )
            )
    return links


def _api_links() -> list[ApiLink]:
    links: list[ApiLink] = [
        ApiLink("api-docs", ("GET",), "/docs", "Swagger UI"),
        ApiLink("api-docs", ("GET",), "/redoc", "ReDoc"),
        ApiLink("api-docs", ("GET",), "/openapi.json", "OpenAPI schema"),
    ]
    for route_file in _route_source_files():
        links.extend(_extract_links_from_file(route_file))
    return links


def _normalize_base_url(raw: str) -> str:
    raw = raw.strip()
    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        sys.exit(f"Error: invalid base URL '{raw}'.")
    return raw.rstrip("/")


def _base_url(args: argparse.Namespace) -> str:
    if args.base_url:
        return _normalize_base_url(args.base_url)

    if args.host is not None or args.port is not None:
        host = args.host or "127.0.0.1"
        port = args.port or 8001
        return _normalize_base_url(f"{host}:{port}")

    target = args.target or DEFAULT_LINK_TARGET
    return _normalize_base_url(LINK_BASE_URL_ALIASES.get(target, target))


def _path_with_values(path: str, values: dict[str, str]) -> str:
    for name, value in values.items():
        path = path.replace(f"{{{name}}}", value)
    return path


def _print_api_links(base_url: str, links: list[ApiLink], values: dict[str, str]) -> None:
    method_width = max(6, *(len(", ".join(link.methods)) for link in links))
    url_width = max(len(f"{base_url}{_path_with_values(link.path, values)}") for link in links)

    print(f"API links for {base_url}\n")
    for section in sorted(
        {link.section for link in links},
        key=lambda section: (SECTION_ORDER.get(section, len(SECTION_ORDER)), section),
    ):
        print(f"{SECTION_LABELS.get(section, section.replace('-', ' ').title())}:")
        for link in [item for item in links if item.section == section]:
            methods = ", ".join(link.methods)
            url = f"{base_url}{_path_with_values(link.path, values)}"
            print(f"  {methods:<{method_width}}  {url:<{url_width}}  {link.label}")
        print()


# ---------------------------------------------------------------------------
# DB / session helpers (identical path-setup as seed.py)
# ---------------------------------------------------------------------------

def _get_db_session():
    """Return a live SQLAlchemy Session (caller must close it)."""
    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))

    from sqlalchemy.orm import Session  # noqa: E402 (local import)
    from db.constraints import ensure_db_constraints  # noqa: E402
    from db.session import engine  # noqa: E402
    from models.portfolio import StockSplit  # noqa: E402

    StockSplit.__table__.create(bind=engine, checkfirst=True)
    ensure_db_constraints(engine)

    return Session(engine)
