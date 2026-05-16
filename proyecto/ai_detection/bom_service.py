from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .errors import AIProviderError
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
    if not cleaned:
        raise ValueError("The model response was empty; no JSON object could be parsed.")

    fenced_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", cleaned, flags=re.DOTALL)
    if fenced_match:
        cleaned = fenced_match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = extract_first_json_object(cleaned)

    if not isinstance(parsed, dict):
        raise ValueError("The model response must decode to a JSON object.")

    return parsed


def extract_first_json_object(text: str) -> dict[str, Any]:
    for start_index, char in enumerate(text):
        if char != "{":
            continue

        depth = 0
        in_string = False
        escape_next = False

        for end_index in range(start_index, len(text)):
            current = text[end_index]

            if in_string:
                if escape_next:
                    escape_next = False
                elif current == "\\":
                    escape_next = True
                elif current == '"':
                    in_string = False
                continue

            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start_index : end_index + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break

    raise json.JSONDecodeError("No valid JSON object found", text, 0)


def response_debug_summary(response_payload: dict[str, Any]) -> str:
    usage = response_payload.get("usageMetadata") or response_payload.get("usage") or {}
    finish_reason = None

    candidates = response_payload.get("candidates", [])
    if candidates and isinstance(candidates[0], dict):
        finish_reason = candidates[0].get("finishReason")

    choices = response_payload.get("choices", [])
    if choices and isinstance(choices[0], dict):
        finish_reason = choices[0].get("finish_reason") or finish_reason

    return json.dumps(
        {
            "finish_reason": finish_reason,
            "usage": usage,
        },
        ensure_ascii=False,
    )


def parse_json_response_from_model(raw_text: str, response_payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return parse_json_response(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        preview = raw_text.strip().replace("\n", "\\n")[:500] or "<empty>"
        raise AIProviderError(
            "Model response was not valid JSON. "
            f"Response preview: {preview}. "
            f"Response metadata: {response_debug_summary(response_payload)}"
        ) from exc


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


CATALOG_VISUAL_SCAN_SYSTEM_PROMPT = """You are an AI specialized in visual symbol catalog analysis for electrical plan recognition.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations.
Do not include comments.

You will receive:
1. A symbol catalog JSON.
2. One image for each catalog symbol.

Your task is to visually analyze each symbol image and produce visual-only disambiguation notes that will help another AI identify the same symbols later in electrical plans.

Rules:
- Describe only visible geometry, marks, relative placement, shapes, and distinctive visual features.
- Do NOT use electrical meaning.
- Do NOT infer function, behavior, protection type, or engineering purpose.
- Do NOT classify by component name meaning.
- Do NOT say what the component does.
- Focus on visual differences between symbols in this same catalog.
- If two or more symbols are visually similar, explicitly explain how to distinguish them.
- Include negative identification rules: when NOT to classify a plan symbol as this catalog symbol.
- Keep descriptions concise but specific.
- The actual symbol image remains the source of truth; notes are only visual aids.
- Do not rename component_name.
- Do not change filename.

Return exactly this JSON structure:

{
  "catalog_visual_analysis": [
    {
      "filename": "symbol_filename.png",
      "component_name": "Exact Component Name",
      "visual_signature": "Short visual-only description of the whole symbol.",
      "distinguishing_features": [
        "Distinctive visual feature 1",
        "Distinctive visual feature 2"
      ],
      "negative_identification_rules": [
        "Do not classify as this symbol if...",
        "Do not identify from this partial feature alone..."
      ],
      "likely_confusions_with_other_catalog_symbols": [
        {
          "component_name": "Other Exact Component Name",
          "distinction": "Visual-only difference between this symbol and the other symbol."
        }
      ],
      "notes": "One concise visual-only classification note."
    }
  ]
}
"""


def normalize_catalog_visual_analysis_payload(
    payload: dict[str, Any],
    catalog_entries: list[SymbolCatalogEntry],
) -> dict[str, Any]:
    entries_by_filename = {entry.filename: entry for entry in catalog_entries if entry.filename}
    normalized = []

    for item in payload.get("catalog_visual_analysis", []):
        if not isinstance(item, dict):
            continue

        filename = str(item.get("filename", "")).strip()
        if not filename or filename not in entries_by_filename:
            continue

        catalog_entry = entries_by_filename[filename]
        normalized.append(
            {
                "filename": filename,
                "component_name": catalog_entry.component_name,
                "visual_signature": str(item.get("visual_signature", "")).strip(),
                "distinguishing_features": normalize_string_list(item.get("distinguishing_features")),
                "negative_identification_rules": normalize_string_list(item.get("negative_identification_rules")),
                "likely_confusions_with_other_catalog_symbols": normalize_confusion_list(
                    item.get("likely_confusions_with_other_catalog_symbols")
                ),
                "notes": str(item.get("notes", "")).strip(),
            }
        )

    return {"catalog_visual_analysis": normalized}


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_confusion_list(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        component_name = str(item.get("component_name", "")).strip()
        distinction = str(item.get("distinction", item.get("reason", ""))).strip()
        if component_name or distinction:
            normalized.append(
                {
                    "component_name": component_name,
                    "distinction": distinction,
                }
            )
    return normalized


def generate_catalog_visual_analysis(
    client: AIProvider,
    *,
    symbol_images: list[tuple[str, bytes]],
    symbol_catalog_entries: list[SymbolCatalogEntry],
    catalog_visual_analysis_system_prompt: str = CATALOG_VISUAL_SCAN_SYSTEM_PROMPT,
    catalog_visual_analysis_user_prompt: str = "Symbol catalog JSON:\n{symbol_catalog_json}",
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    catalog_by_filename = {entry.filename: entry for entry in symbol_catalog_entries if entry.filename}
    minimal_catalog = [
        {
            "filename": entry.filename,
            "component_name": entry.component_name.strip(),
        }
        for entry in symbol_catalog_entries
        if entry.filename and entry.component_name.strip()
    ]

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": catalog_visual_analysis_user_prompt.replace(
                "{symbol_catalog_json}",
                json.dumps(minimal_catalog, ensure_ascii=False, indent=2),
            ),
        }
    ]

    for symbol_filename, symbol_bytes in symbol_images:
        entry = catalog_by_filename.get(symbol_filename, SymbolCatalogEntry(filename=symbol_filename))
        content.append(
            {
                "type": "text",
                "text": "Catalog symbol image:\n"
                + json.dumps(
                    {
                        "filename": symbol_filename,
                        "component_name": entry.component_name.strip(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        )
        content.append(client.build_image_block(symbol_bytes, symbol_filename))

    response = client.create_message(
        system_prompt=catalog_visual_analysis_system_prompt,
        user_content=content,
        max_tokens=8000,
    )
    raw_text = client.extract_text(response)
    parsed = parse_json_response_from_model(raw_text, response)
    return normalize_catalog_visual_analysis_payload(parsed, symbol_catalog_entries), raw_text, client.extract_usage(response)


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
    return normalize_reference_payload(parse_json_response_from_model(raw_text, response)), raw_text, client.extract_usage(response)


def analyze_plan_image(
    client: AIProvider,
    *,
    plan_images: list[tuple[str, bytes]],
    symbol_images: list[tuple[str, bytes]],
    symbol_catalog_entries: list[SymbolCatalogEntry],
    reference_payload: dict[str, Any],
    plan_system_prompt: str,
    plan_user_prompt: str,
    catalog_visual_analysis: dict[str, Any] | None = None,
    user_prompt: str = "",
    reference_table_has_standard: bool = False,
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

    if reference_table_has_standard:
        reference_context = {
            "references": [],
            "source": "standard_symbol_catalog",
            "notes": "No reference table image is provided. Use the symbol catalog JSON and symbol images as the source of material names.",
        }
        reference_instruction = (
            "\n\nStandard symbol catalog mode:\n"
            "- No separate reference table image was provided.\n"
            "- The symbol catalog JSON and the attached symbol images define the standard material names.\n"
            "- If a plan symbol matches a catalog image, use that catalog material name directly.\n"
        )
    else:
        reference_context = reference_payload
        reference_instruction = ""

    static_intro_block = {
        "type": "text",
        "text": plan_user_prompt.replace(
            "{reference_table_json}",
            json.dumps(reference_context, ensure_ascii=False, indent=2),
        )
        + ("\n\nExtra instructions:\n" + user_prompt.strip() if user_prompt.strip() else "")
        + reference_instruction
        + "\n\nSymbol catalog JSON:\n"
        + json.dumps({"materials": materials}, ensure_ascii=False, indent=2)
        + (
            "\n\nCatalog visual analysis from previous step:\n"
            + json.dumps(catalog_visual_analysis, ensure_ascii=False, indent=2)
            if catalog_visual_analysis
            else ""
        ),
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
    return parse_json_response_from_model(raw_text, response), raw_text, client.extract_usage(response)
