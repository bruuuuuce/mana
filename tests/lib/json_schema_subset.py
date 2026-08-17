#!/usr/bin/env python3
"""Offline evaluator for the JSON Schema keywords used by Scope v2 tests.

This is deliberately a test utility, not a production validator or the SS05
cross-artifact semantic governor. It keeps the contract acceptance suite free
from package downloads and provider calls.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any


class SchemaEvaluator:
    def __init__(self) -> None:
        self.documents: dict[Path, Any] = {}

    def load(self, path: Path) -> Any:
        resolved = path.resolve()
        if resolved not in self.documents:
            with resolved.open(encoding="utf-8") as handle:
                self.documents[resolved] = json.load(handle)
        return self.documents[resolved]

    @staticmethod
    def same_json(left: Any, right: Any) -> bool:
        return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
            right, sort_keys=True, separators=(",", ":")
        )

    @staticmethod
    def instance_type_matches(instance: Any, expected: str) -> bool:
        if expected == "null":
            return instance is None
        if expected == "boolean":
            return isinstance(instance, bool)
        if expected == "object":
            return isinstance(instance, dict)
        if expected == "array":
            return isinstance(instance, list)
        if expected == "string":
            return isinstance(instance, str)
        if expected == "integer":
            return isinstance(instance, int) and not isinstance(instance, bool)
        if expected == "number":
            return (
                isinstance(instance, (int, float))
                and not isinstance(instance, bool)
                and math.isfinite(instance)
            )
        raise ValueError(f"unsupported JSON Schema type: {expected}")

    def resolve_ref(self, ref: str, current_document: Path) -> tuple[Any, Path]:
        path_part, separator, fragment = ref.partition("#")
        target_path = (
            (current_document.parent / path_part).resolve()
            if path_part
            else current_document.resolve()
        )
        target = self.load(target_path)
        if separator and fragment:
            if not fragment.startswith("/"):
                raise ValueError(f"unsupported non-pointer fragment: {ref}")
            for raw_token in fragment[1:].split("/"):
                token = raw_token.replace("~1", "/").replace("~0", "~")
                if isinstance(target, list):
                    target = target[int(token)]
                else:
                    target = target[token]
        return target, target_path

    def evaluate(
        self,
        instance: Any,
        schema: Any,
        current_document: Path,
        location: str = "$",
    ) -> list[str]:
        if schema is True:
            return []
        if schema is False:
            return [f"{location}: false schema rejects the value"]
        if not isinstance(schema, dict):
            return [f"{location}: schema is not an object or boolean"]

        errors: list[str] = []

        if "$ref" in schema:
            try:
                referenced, referenced_document = self.resolve_ref(
                    schema["$ref"], current_document
                )
                errors.extend(
                    self.evaluate(instance, referenced, referenced_document, location)
                )
            except (KeyError, IndexError, OSError, ValueError) as exc:
                errors.append(f"{location}: cannot resolve {schema['$ref']}: {exc}")

        if "type" in schema:
            declared = schema["type"]
            expected_types = declared if isinstance(declared, list) else [declared]
            if not any(
                self.instance_type_matches(instance, expected)
                for expected in expected_types
            ):
                errors.append(
                    f"{location}: expected type {declared!r}, got "
                    f"{type(instance).__name__}"
                )
                return errors

        if "const" in schema and not self.same_json(instance, schema["const"]):
            errors.append(f"{location}: value does not match const {schema['const']!r}")

        if "enum" in schema and not any(
            self.same_json(instance, candidate) for candidate in schema["enum"]
        ):
            errors.append(f"{location}: value is not in enum {schema['enum']!r}")

        if isinstance(instance, str):
            if "minLength" in schema and len(instance) < schema["minLength"]:
                errors.append(f"{location}: string is shorter than minLength")
            if "maxLength" in schema and len(instance) > schema["maxLength"]:
                errors.append(f"{location}: string is longer than maxLength")
            if "pattern" in schema and re.search(schema["pattern"], instance) is None:
                errors.append(
                    f"{location}: string does not match pattern {schema['pattern']!r}"
                )

        if (
            isinstance(instance, (int, float))
            and not isinstance(instance, bool)
            and math.isfinite(instance)
        ):
            if "minimum" in schema and instance < schema["minimum"]:
                errors.append(f"{location}: number is below minimum {schema['minimum']}")
            if "maximum" in schema and instance > schema["maximum"]:
                errors.append(f"{location}: number is above maximum {schema['maximum']}")

        if isinstance(instance, list):
            if "minItems" in schema and len(instance) < schema["minItems"]:
                errors.append(f"{location}: array has fewer than minItems")
            if "maxItems" in schema and len(instance) > schema["maxItems"]:
                errors.append(f"{location}: array has more than maxItems")
            if schema.get("uniqueItems"):
                canonical = [
                    json.dumps(item, sort_keys=True, separators=(",", ":"))
                    for item in instance
                ]
                if len(canonical) != len(set(canonical)):
                    errors.append(f"{location}: array items are not unique")
            if "items" in schema:
                for index, item in enumerate(instance):
                    errors.extend(
                        self.evaluate(
                            item,
                            schema["items"],
                            current_document,
                            f"{location}[{index}]",
                        )
                    )

        if isinstance(instance, dict):
            required = schema.get("required", [])
            for name in required:
                if name not in instance:
                    errors.append(f"{location}: missing required property {name!r}")

            properties = schema.get("properties", {})
            for name, property_schema in properties.items():
                if name in instance:
                    errors.extend(
                        self.evaluate(
                            instance[name],
                            property_schema,
                            current_document,
                            f"{location}.{name}",
                        )
                    )

            if schema.get("additionalProperties") is False:
                for name in instance:
                    if name not in properties:
                        errors.append(
                            f"{location}: additional property {name!r} is not allowed"
                        )
            elif isinstance(schema.get("additionalProperties"), dict):
                for name in instance:
                    if name not in properties:
                        errors.extend(
                            self.evaluate(
                                instance[name],
                                schema["additionalProperties"],
                                current_document,
                                f"{location}.{name}",
                            )
                        )

        for child_schema in schema.get("allOf", []):
            errors.extend(
                self.evaluate(instance, child_schema, current_document, location)
            )

        if "anyOf" in schema:
            alternatives = [
                self.evaluate(instance, child, current_document, location)
                for child in schema["anyOf"]
            ]
            if not any(not alternative for alternative in alternatives):
                errors.append(f"{location}: no anyOf alternative matched")

        if "oneOf" in schema:
            alternatives = [
                self.evaluate(instance, child, current_document, location)
                for child in schema["oneOf"]
            ]
            matched = sum(not alternative for alternative in alternatives)
            if matched != 1:
                errors.append(
                    f"{location}: expected exactly one oneOf match, found {matched}"
                )

        if "if" in schema:
            condition_errors = self.evaluate(
                instance, schema["if"], current_document, location
            )
            selected = "then" if not condition_errors else "else"
            if selected in schema:
                errors.extend(
                    self.evaluate(
                        instance, schema[selected], current_document, location
                    )
                )

        return errors


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "Usage: tests/lib/json_schema_subset.py <schema.json> <instance.json>",
            file=sys.stderr,
        )
        return 2

    schema_path = Path(argv[1]).resolve()
    instance_path = Path(argv[2]).resolve()
    evaluator = SchemaEvaluator()
    try:
        schema = evaluator.load(schema_path)
        with instance_path.open(encoding="utf-8") as handle:
            instance = json.load(handle)
        errors = evaluator.evaluate(instance, schema, schema_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
