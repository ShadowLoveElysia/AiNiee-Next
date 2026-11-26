"""Discover API contracts from source without importing the application runtime."""
from __future__ import annotations

import ast
import copy
import importlib.util
from pathlib import Path
import re
import sys
from typing import Any


_API_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _API_ROOT.parents[1]
_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
_INJECTED = {"Request", "Response", "BackgroundTasks", "WebSocket"}
_PRIMITIVES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "StrictBool": "boolean"}
_MISSING = object()


def _literal(node: ast.AST | None, fallback: Any = None) -> Any:
    try:
        return ast.literal_eval(node) if node is not None else fallback
    except (ValueError, TypeError):
        return fallback


def _name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _keywords(node: ast.Call) -> dict[str, ast.AST]:
    return {item.arg: item.value for item in node.keywords if item.arg}


def _contract_models() -> dict[str, type]:
    # This module contains DTOs only. Never replace it with an application import.
    from pydantic import BaseModel
    from Tools.APIServer import contracts, responses
    namespaces = [vars(contracts), vars(responses)]
    source = _PROJECT_ROOT / "ModuleFolders/MangaCore/api/schemas.py"
    if source.is_file():
        # Loading the pure DTO file directly avoids the api package's router imports.
        module_name = "_ainiee_manga_api_contracts"
        module = sys.modules.get(module_name)
        if module is None:
            spec = importlib.util.spec_from_file_location(module_name, source)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(module_name, None)
                raise
        namespaces.append(vars(module))
    return {
        name: value for namespace in namespaces for name, value in namespace.items()
        if isinstance(value, type) and issubclass(value, BaseModel) and value is not BaseModel
    }


def _annotation(node: ast.AST | None, models: dict[str, type], *, output: bool = False) -> tuple[dict, bool]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            node = ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return {"x-schema-unavailable": node.value}, False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        parts = [_annotation(part, models, output=output) for part in (node.left, node.right)]
        return {"anyOf": [item[0] for item in parts]}, all(item[1] for item in parts)
    if isinstance(node, ast.Constant) and node.value is None:
        return {"type": "null"}, True
    name = _name(node)
    if name in _PRIMITIVES:
        return {"type": _PRIMITIVES[name]}, True
    if name == "UUID":
        return {"type": "string", "format": "uuid"}, True
    if name in {"Any", "object"}:
        return {}, True
    if name in {"dict", "Dict"}:
        return {"type": "object", "additionalProperties": True}, True
    if name in {"list", "List"}:
        return {"type": "array", "items": {}}, True
    if name in models:
        return models[name].model_json_schema(mode="serialization" if output else "validation"), True
    if isinstance(node, ast.Subscript):
        outer = _name(node.value)
        args = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
        if outer == "Annotated":
            return _annotation(args[0], models, output=output)
        if outer in {"Optional", "Union"}:
            parts = [_annotation(arg, models, output=output) for arg in args]
            if outer == "Optional":
                parts.append(({"type": "null"}, True))
            return {"anyOf": [item[0] for item in parts]}, all(item[1] for item in parts)
        if outer in {"List", "list", "Sequence", "set", "Set"}:
            item, known = _annotation(args[0], models, output=output)
            return {"type": "array", "items": item}, known
        if outer in {"Dict", "dict", "Mapping"} and len(args) == 2:
            item, known = _annotation(args[1], models, output=output)
            return {"type": "object", "additionalProperties": item}, known
        if outer == "Literal":
            values = [_literal(arg, _MISSING) for arg in args]
            if all(value is not _MISSING for value in values):
                return {"enum": values}, True
    return {"x-schema-unavailable": ast.unparse(node) if node is not None else "undeclared"}, False


def _metadata(annotation: ast.AST | None, default: ast.AST | None):
    if isinstance(annotation, ast.Subscript) and _name(annotation.value) == "Annotated":
        parts = list(annotation.slice.elts) if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        for item in parts[1:]:
            if isinstance(item, ast.Call):
                return item
    return default if isinstance(default, ast.Call) else None


def _scalar(schema: dict) -> bool:
    if "anyOf" in schema:
        return all(_scalar(part) for part in schema["anyOf"])
    if "enum" in schema:
        return True
    return schema.get("type") in {"string", "number", "integer", "boolean", "null"}


def _hoist_definitions(schema: dict) -> dict:
    """Keep model references valid when a Pydantic schema is nested in a collection."""
    result = copy.deepcopy(schema)
    definitions = {}

    def visit(value):
        if isinstance(value, dict):
            for name, definition in value.pop("$defs", {}).items():
                if name in definitions and definitions[name] != definition:
                    raise ValueError(f"Conflicting contract schema definition: {name}")
                definitions[name] = definition
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(result)
    if definitions:
        result["$defs"] = definitions
    return result


def _field_schema(schema: dict, metadata: ast.Call | None, default: ast.AST | None):
    result = copy.deepcopy(schema)
    kwargs = _keywords(metadata) if metadata else {}
    for source, target in {
        "ge": "minimum", "gt": "exclusiveMinimum", "le": "maximum", "lt": "exclusiveMaximum",
        "min_length": "minLength", "max_length": "maxLength", "pattern": "pattern", "description": "description",
    }.items():
        value = _literal(kwargs.get(source), _MISSING)
        if value is not _MISSING:
            result[target] = value
    selected = default
    if metadata is not None and metadata is default:
        selected = metadata.args[0] if metadata.args else kwargs.get("default")
    value = _literal(selected, _MISSING)
    required = value is _MISSING or value is Ellipsis
    if not required:
        result["default"] = value
    return result, required, kwargs


def _request_contract(node: ast.FunctionDef | ast.AsyncFunctionDef, path: str, models: dict[str, type]):
    positional = [*node.args.posonlyargs, *node.args.args]
    defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    arguments = list(zip(positional, defaults)) + list(zip(node.args.kwonlyargs, node.args.kw_defaults))
    path_names = set(re.findall(r"{([^}:]+)(?::[^}]+)?}", path))
    parameters, bodies = [], []
    complete = True
    for argument, default in arguments:
        annotation = argument.annotation
        if _name(annotation) in _INJECTED:
            continue
        metadata = _metadata(annotation, default)
        marker = _name(metadata.func) if metadata else ""
        if marker == "Depends":
            complete = False
            continue
        schema, known = _annotation(annotation, models)
        schema, required, kwargs = _field_schema(schema, metadata, default)
        key = _literal(kwargs.get("alias"), argument.arg)
        if argument.arg in path_names or marker == "Path":
            location, required = "path", True
        elif marker in {"Query", "Header", "Cookie"}:
            location = marker.lower()
            if location == "header" and "alias" not in kwargs and _literal(kwargs.get("convert_underscores"), True):
                key = argument.arg.replace("_", "-")
        elif marker in {"File", "Form", "Body"} or not _scalar(schema):
            location = "body"
        else:
            location = "query"
        if marker == "File":
            schema, known = {"type": "string", "format": "binary"}, True
        complete = complete and known
        if location == "body":
            bodies.append((key, schema, required, marker, _literal(kwargs.get("embed"), False)))
        else:
            parameters.append({"name": key, "in": location, "required": required, "schema": _hoist_definitions(schema)})
    body = None
    if bodies:
        multipart = any(item[3] in {"File", "Form"} for item in bodies)
        if len(bodies) == 1 and not bodies[0][4] and not multipart:
            schema = bodies[0][1]
        else:
            schema = {"type": "object", "properties": {item[0]: item[1] for item in bodies}}
            required_fields = [item[0] for item in bodies if item[2]]
            if required_fields:
                schema["required"] = required_fields
        media_type = "multipart/form-data" if multipart else "application/json"
        body = {"required": any(item[2] for item in bodies), "content": {media_type: {"schema": _hoist_definitions(schema)}}}
    return parameters, body, complete


def _category(path: str, tags: list) -> str:
    if tags and isinstance(tags[0], str):
        return tags[0]
    parts = [part for part in path.strip("/").split("/") if part]
    if parts and parts[0] == "api":
        parts.pop(0)
    if parts and re.fullmatch(r"v\d+", parts[0]):
        parts.pop(0)
    return parts[0] if parts else "system"


def _router_metadata(tree: ast.Module) -> dict[str, tuple[str, list]]:
    routers = {"app": ("", [])}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if _name(node.value.func) != "APIRouter":
            continue
        kwargs = _keywords(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                routers[target.id] = (_literal(kwargs.get("prefix"), ""), _literal(kwargs.get("tags"), []))
    return routers


def _error_responses(node: ast.AST | None, models: dict[str, type]) -> dict:
    from pydantic import TypeAdapter
    from Tools.APIServer import responses

    declared = getattr(responses, _name(node), None)
    if isinstance(declared, dict):
        return {
            str(status): {
                "description": item["description"],
                "content": {"application/json": {"schema": TypeAdapter(item["model"]).json_schema(mode="serialization")}},
            }
            for status, item in declared.items()
        }
    if not isinstance(node, ast.Dict):
        return {}
    result = {}
    for key, value in zip(node.keys, node.values):
        if not isinstance(value, ast.Dict):
            continue
        fields = {_literal(k): v for k, v in zip(value.keys, value.values)}
        entry = {name: _literal(item) for name, item in fields.items() if name != "model"}
        if "model" in fields:
            schema, known = _annotation(fields["model"], models, output=True)
            entry["content"] = {"application/json": {"schema": _hoist_definitions(schema)}}
        result[str(_literal(key))] = entry
    return result


def _has_open_fields(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    if schema.get("x-contract-scope") == "partial":
        return True
    if schema.get("type") == "object" and not schema.get("properties"):
        return schema.get("additionalProperties") is not False
    if schema.get("type") == "array" and not schema.get("items"):
        return True
    properties = schema.get("properties", {})
    if any(not any(k in value for k in ("type", "$ref", "anyOf", "allOf", "oneOf", "enum", "const")) for value in properties.values()):
        return True
    return any(_has_open_fields(value) for value in properties.values()) or any(
        _has_open_fields(value) for key in ("$defs",) for value in schema.get(key, {}).values()
    ) or _has_open_fields(schema.get("items")) or any(
        _has_open_fields(value) for key in ("anyOf", "allOf", "oneOf") for value in schema.get(key, [])
    )


def _routes_from_source(source: Path, models: dict[str, type], *, optional: bool = False) -> list[dict]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    routers = _router_metadata(tree)
    result = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            router = routers.get(_name(decorator.func.value))
            if router is None or decorator.func.attr not in _METHODS or not decorator.args:
                continue
            suffix = _literal(decorator.args[0])
            if not isinstance(suffix, str):
                continue
            path = router[0] + suffix
            if not path.startswith("/api/") or path.startswith("/api/internal/") or path == "/api/internal":
                continue
            kwargs = _keywords(decorator)
            method = decorator.func.attr.upper()
            parameters, body, request_known = _request_contract(node, path, models)
            status = str(_literal(kwargs.get("status_code"), 200))
            response_node = kwargs.get("response_model", node.returns)
            schema, response_known = _annotation(response_node, models, output=True)
            response = {"description": "Declared response" if response_known else "Response schema is not declared"}
            returns_file = _name(response_node) == "FileResponse" or any(
                isinstance(item, ast.Return) and isinstance(item.value, ast.Call)
                and _name(item.value.func) == "FileResponse" for item in ast.walk(node)
            )
            transport = _literal(kwargs.get("openapi_extra"), {})
            if returns_file:
                response_known = True
                schema = {"type": "string", "format": "binary"}
                response["content"] = {"application/octet-stream": {"schema": schema}}
                transport["response_kind"] = "file"
            elif status not in {"204", "304"}:
                response["content"] = {"application/json": {"schema": _hoist_definitions(schema)}}
            else:
                response_known = True
            responses = _error_responses(kwargs.get("responses"), models)
            responses[status] = response
            detailed = response_known and not _has_open_fields(schema)
            request_detailed = request_known and not any(
                _has_open_fields(parameter["schema"]) for parameter in parameters
            ) and not any(
                _has_open_fields(content["schema"]) for content in (body or {}).get("content", {}).values()
            )
            result.append({
                "method": method, "path": path,
                "category": _category(path, _literal(kwargs.get("tags"), router[1])),
                "operation_id": _literal(kwargs.get("operation_id"), node.name),
                "parameters": parameters, "request_body": body, "responses": responses,
                "schema_complete": request_detailed and detailed,
                "request_fields_complete": request_detailed,
                "response_fields_complete": detailed,
                "schema_status": {
                    "request": "declared" if request_known else "partial",
                    "response": "declared" if response_known else "undeclared",
                },
                "availability": "unverified",
                "optional_module": "manga" if optional else None,
                "transport_metadata": transport,
                "validation_note": "Schemas describe declared transport types; domain validation and runtime capability checks still apply.",
            })
    return result


def load_api_catalog() -> list[dict]:
    """Return source-declared routes without starting the API or importing optional engines."""
    models = _contract_models()
    sources = [_API_ROOT / "application.py", *sorted((_API_ROOT / "routers").glob("*.py"))]
    manga = sorted((_PROJECT_ROOT / "ModuleFolders/MangaCore/api").glob("routes*.py"))
    routes = {}
    for source in [*sources, *manga]:
        for route in _routes_from_source(source, models, optional=source in manga):
            routes[(route["method"], route["path"])] = route
    return sorted(routes.values(), key=lambda route: (route["path"], route["method"]))
