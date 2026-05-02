from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .providers import AIProvider

@dataclass
class SymbolCatalogEntry:
    filename: str
    component_name: str = ""
    component_code: str = ""
    specification_hint: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SymbolCatalogEntry":
        return cls(
            filename=str(data.get("filename", "")),
            component_name=str(data.get("component_name", "")),
            component_code=str(data.get("component_code", "")),
            specification_hint=str(data.get("specification_hint", "")),
            notes=str(data.get("notes", "")),
        )


def parse_json_response(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", cleaned, flags=re.DOTALL)
    if fenced_match:
        cleaned = fenced_match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        json_match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
        if not json_match:
            raise
        parsed = json.loads(json_match.group(1))

    if not isinstance(parsed, dict):
        raise ValueError("The model response must decode to a JSON object.")

    return parsed


def normalize_reference_payload(payload: dict[str, Any]) -> dict[str, Any]:
    references = payload.get("references", [])
    normalized = []
    for item in references:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "reference_id": str(item.get("reference_id", "")).strip(),
                "description": str(item.get("description", "")).strip(),
                "specification": str(item.get("specification", "")).strip(),
                "notes": str(item.get("notes", "")).strip(),
            }
        )

    return {"references": [item for item in normalized if item["reference_id"] or item["description"]]}


def build_reference_lookup(reference_payload: dict[str, Any]) -> dict[str, str]:
    lookup = {}
    for item in reference_payload.get("references", []):
        ref_id = item.get("reference_id", "").strip()
        description = item.get("description", "").strip()
        specification = item.get("specification", "").strip()
        merged = " | ".join(part for part in [description, specification] if part)
        if ref_id and merged:
            lookup[ref_id] = merged
    return lookup


def parse_symbol_catalog_json(raw_text: str) -> list[SymbolCatalogEntry]:
    if not raw_text.strip():
        return []

    data = json.loads(raw_text)
    if not isinstance(data, list):
        raise ValueError("The symbol catalog metadata must be a JSON array.")

    return [SymbolCatalogEntry.from_dict(item) for item in data if isinstance(item, dict)]


def extract_reference_table_from_image(
    client: AIProvider,
    *,
    image_bytes: bytes,
    filename: str,
    reference_system_prompt: str,
    reference_user_prompt: str,
    user_prompt: str = "",
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    content = [
        {"type": "text", "text": reference_user_prompt + ("\n\nExtra instructions:\n" + user_prompt.strip() if user_prompt.strip() else "")},
        client.build_image_block(image_bytes, filename),
    ]
    response = client.create_message(system_prompt=reference_system_prompt, user_content=content)
    raw_text = client.extract_text(response)
    return normalize_reference_payload(parse_json_response(raw_text)), raw_text, client.extract_usage(response)


def analyze_plan_image(
    client: AIProvider,
    *,
    plan_images: list[tuple[str, bytes]],
    symbol_images: list[tuple[str, bytes]],
    symbol_catalog_entries: list[SymbolCatalogEntry],
    reference_payload: dict[str, Any],
    plan_system_prompt: str,
    plan_user_prompt: str,
    user_prompt: str = "",
    cache_static_prefix: bool = False,
    cache_ttl: str = "5m",
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    catalog_by_filename = {entry.filename: entry for entry in symbol_catalog_entries if entry.filename}
    materials = [
        {
            "material": entry.component_name.strip(),
            "symbol_filename": entry.filename,
        }
        for entry in symbol_catalog_entries
        if entry.filename and entry.component_name.strip()
    ]

    static_intro_block = {
        "type": "text",
        "text": plan_user_prompt.replace(
            "{reference_table_json}",
            json.dumps(reference_payload, ensure_ascii=False, indent=2),
        )
        + ("\n\nExtra instructions:\n" + user_prompt.strip() if user_prompt.strip() else "")
        + "\n\nReference table and symbol catalog JSON:\n"
        + json.dumps({"materials": materials}, ensure_ascii=False, indent=2),
    }

    content: list[dict[str, Any]] = [
        static_intro_block,
    ]

    for symbol_filename, symbol_bytes in symbol_images:
        entry = catalog_by_filename.get(symbol_filename, SymbolCatalogEntry(filename=symbol_filename))
        content.append(
            {
                "type": "text",
                "text": "Reference material and its single symbol image:\n"
                + json.dumps(
                    {
                        "material": entry.component_name.strip(),
                        "symbol_filename": symbol_filename,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        )
        content.append(client.build_image_block(symbol_bytes, symbol_filename))

    if cache_static_prefix and content:
        last_static_block = content[-1]
        last_static_block["cache_control"] = {
            "type": "ephemeral",
            "ttl": cache_ttl,
        }

    content.extend(
        [{"type": "text", "text": "Plan images to analyze for BOM:"}]
    )
    for index, (plan_filename, plan_bytes) in enumerate(plan_images, start=1):
        image_role = "full-plan context image"
        if index > 1:
            image_role = "zoomed/cropped plan image for reading local specs"
        content.append(
            {
                "type": "text",
                "text": f"Plan image {index}: {plan_filename} ({image_role})",
            }
        )
        content.append(client.build_image_block(plan_bytes, plan_filename))

    betas = ["extended-cache-ttl-2025-04-11"] if cache_static_prefix and cache_ttl == "1h" else None
    response = client.create_message(
        system_prompt=plan_system_prompt,
        user_content=content,
        betas=betas,
    )
    raw_text = client.extract_text(response)
    return parse_json_response(raw_text), raw_text, client.extract_usage(response)
