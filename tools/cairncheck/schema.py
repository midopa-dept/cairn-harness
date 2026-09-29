"""core.yaml `schemas`가 쓰는 JSON Schema draft-07 공통 부분집합 검사기.

지원: $ref(문서 내부), type, enum, const, required, properties, additionalProperties,
items, minItems, uniqueItems, minLength, pattern, minimum, oneOf.
지원하지 않는 keyword를 만나면 조용히 통과하지 않고 오류로 보고한다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

SUPPORTED = {
    "$ref", "type", "enum", "const", "required", "properties", "additionalProperties",
    "items", "minItems", "uniqueItems", "minLength", "pattern", "minimum", "oneOf",
    "description", "default",
}


@dataclass(frozen=True)
class SchemaError:
    path: str
    code: str
    message: str


def _type_ok(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    raise ValueError(f"지원하지 않는 type: {name}")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


class Validator:
    def __init__(self, root: dict):
        self.root = root

    def resolve(self, ref: str) -> dict:
        if not ref.startswith("#/"):
            raise ValueError(f"외부 $ref는 지원하지 않는다: {ref}")
        node: Any = self.root
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def validate(self, value: Any, schema: dict, path: str = "") -> list[SchemaError]:
        errors: list[SchemaError] = []
        unknown = set(schema) - SUPPORTED
        if unknown:
            return [SchemaError(path, "unsupported_keyword", f"검사기 미지원 keyword: {sorted(unknown)}")]
        if "$ref" in schema:
            return self.validate(value, self.resolve(schema["$ref"]), path)
        if "oneOf" in schema:
            branches = [self.validate(value, branch, path) for branch in schema["oneOf"]]
            passed = [b for b in branches if not b]
            if len(passed) == 1:
                return []
            if len(passed) > 1:
                return [SchemaError(path, "oneOf_multiple", "oneOf 둘 이상과 일치")]
            best = min(branches, key=len)
            return best if best else [SchemaError(path, "oneOf_none", "oneOf 어느 것과도 불일치")]
        if "type" in schema:
            names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(_type_ok(value, name) for name in names):
                return [SchemaError(path, "type", f"type {names} 기대, 실제 {type(value).__name__}")]
        if "const" in schema and value != schema["const"]:
            errors.append(SchemaError(path, "const", f"const {schema['const']!r} 기대, 실제 {value!r}"))
        if "enum" in schema and value not in schema["enum"]:
            errors.append(SchemaError(path, "enum", f"허용 값 {schema['enum']} 밖: {value!r}"))
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append(SchemaError(path, "minLength", "문자열이 너무 짧다"))
            if "pattern" in schema and not re.search(schema["pattern"], value):
                errors.append(SchemaError(path, "pattern", f"pattern 불일치: {value!r}"))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(SchemaError(path, "minimum", f"최솟값 {schema['minimum']} 미만"))
        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(SchemaError(path, "minItems", f"항목 {schema['minItems']}개 이상 필요"))
            if schema.get("uniqueItems"):
                seen = [_canonical(v) for v in value]
                if len(seen) != len(set(seen)):
                    errors.append(SchemaError(path, "uniqueItems", "중복 항목"))
            if "items" in schema:
                for index, item in enumerate(value):
                    errors.extend(self.validate(item, schema["items"], f"{path}/{index}"))
        if isinstance(value, dict):
            properties = schema.get("properties", {})
            for key in schema.get("required", []):
                if key not in value:
                    errors.append(SchemaError(f"{path}/{key}", "required", f"필수 key 없음: {key}"))
            additional = schema.get("additionalProperties", True)
            for key, item in value.items():
                child = f"{path}/{key}"
                if key in properties:
                    errors.extend(self.validate(item, properties[key], child))
                elif additional is False:
                    errors.append(SchemaError(child, "additionalProperties", f"허용되지 않은 key: {key}"))
                elif isinstance(additional, dict):
                    errors.extend(self.validate(item, additional, child))
        return errors


def definitions(contract: dict) -> dict:
    """contract(core.yaml)의 schemas.document를 root로 쓰는 validator 입력."""
    return contract["schemas"]["document"]


def validate_definition(contract: dict, name: str, value: Any) -> list[SchemaError]:
    root = definitions(contract)
    if name not in root.get("definitions", {}):
        return [SchemaError("", "definition_missing", f"계약에 {name} 정의가 없다")]
    return Validator(root).validate(value, {"$ref": f"#/definitions/{name}"})
