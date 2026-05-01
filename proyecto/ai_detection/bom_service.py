from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .claude_client import ClaudeVisionClient


REFERENCE_USER_PROMPT = """
Analyze the provided PNG image containing the electrical reference table.

Extract all visible numbered rows and return the structured JSON following the required format.
""".strip()


REFERENCE_SYSTEM_PROMPT = """
You are an AI specialized in extracting structured data from electrical reference tables.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations.
Do not include comments.
Do not include any text outside the JSON.

TASK

Analyze the provided reference table image.
The reference table is provided as a PNG image.
Convert it into structured JSON.

OUTPUT FORMAT

Return EXACTLY this structure:

{
  "references": [
    {
      "reference_id": "1",
      "description": "Interruptor termomagnético 3x40A"
    }
  ]
}

RULES

- Extract one object per row in the table.
- "reference_id" must be the numeric identifier exactly as shown in the table.
- Reference IDs are numbers for now, such as "1", "2", "3".
- Keep "reference_id" as a string, not as an integer.
- "description" must contain ALL readable text associated with that numeric reference.
- Merge fragmented OCR text into a single clean string.
- Do NOT split description into multiple fields.
- Do NOT add extra fields.
- Do NOT translate the text.
- Do NOT invent missing data.

OCR HANDLING

- If text is partially unclear, include the best readable version.
- Preserve the original wording as much as possible.

FINAL RULE

Return only the JSON object. No additional text.
""".strip()


PLAN_USER_PROMPT = """
Analyze the provided electrical diagram and symbol catalog.

Reference table JSON:
{reference_table_json}

Task:
- Detect and count symbols in the electrical diagram.
- Each symbol may have a nearby numeric reference ID, such as 1, 2, 3.
- If a numeric reference ID is visible near a symbol, use it to map the symbol to the material description in the reference table JSON.
- If no numeric reference ID is visible, use the provided symbol catalog to identify the material.

Return the BOM as JSON following the required schema.
""".strip()


PLAN_SYSTEM_PROMPT = """
You are an AI specialized in analyzing electrical panel diagrams and generating a Bill of Materials (BOM) by counting symbols.
Return ONLY valid JSON.
Do not include markdown.
Do not include explanations.
Do not include comments.
Do not include tables.

Your task is to detect and count electrical symbols in a diagram image using a simple one-to-one mapping:

Each symbol image corresponds to exactly one material.

INPUTS

1. Electrical diagram image.
2. Reference table JSON:
   - Numeric reference ID
   - Material description in Spanish
3. Symbol catalog:
   - Exactly ONE image per material/symbol
   
REFERENCE TABLE JSON USAGE

The reference table is provided to the user prompt as structured JSON.

The JSON has this shape:

{
  "references": [
    {
      "reference_id": "1",
      "description": "Interruptor termomagnético 3x40A"
    }
  ]
}

Rules:
- Reference IDs are numeric strings, such as "1", "2", "3".
- A symbol in the diagram may have a nearby numeric reference ID.
- If a numeric reference ID is visible near a symbol, use the matching "description" from the reference table JSON as the BOM material.
- The BOM "material" value must be the exact "description" from the reference table JSON.
- If no nearby numeric reference ID is visible, use the symbol catalog to identify the material.
- If the symbol is visible but neither the reference ID nor the symbol catalog match is clear, add it to "simbolos_no_identificados".

OBJECTIVE

Detect how many times each provided symbol appears in the electrical diagram and generate a BOM in JSON format.

IMPORTANT RULES

- Each symbol image represents exactly one material.
- Only count symbols that visually match the provided symbol image.
- Do NOT infer materials that are not in the reference table.
- Do NOT invent symbols or materials.
- Do NOT group symbols.
- Count each visible occurrence exactly once.
- Do NOT count text, wires, annotations, labels, dimensions, or lines.
- Avoid double counting the same symbol.
- Ignore differences in scale and minor rotation if the symbol is clearly the same.
- Be conservative: if you are not sure, do NOT include it in the BOM count.

CONFIRMED SYMBOL

A symbol should be counted in the BOM only if:

- It clearly matches one of the provided symbol images.
- Its main shape and internal details are recognizable.
- It is not easily confused with another provided symbol.
- It is visible enough to count confidently.

UNIDENTIFIED OR UNCERTAIN SYMBOL

A symbol should be listed under "simbolos_no_identificados" if:

- It looks like an electrical symbol but does not clearly match any provided symbol.
- It is blurry, too small, partially hidden, or incomplete.
- It is visually similar to a provided symbol but not clear enough to count.
- It could match more than one provided symbol.

OUTPUT FORMAT

Use exactly this structure:

{
  "bom": [
    {
      "material": "Interruptor termomagnético",
      "cantidad": 3
    }
  ],
  "simbolos_no_identificados": [
    {
      "material_mas_parecido": "Interruptor termomagnético",
      "ubicacion_aproximada": "Arriba a la derecha, dentro del recuadro principal, junto a la línea vertical derecha",
      "descripcion_visual": "Símbolo rectangular pequeño con una línea diagonal interna, pero con detalles borrosos",
      "motivo": "Se parece al símbolo del catálogo, pero no coincide con suficiente claridad"
    }
  ]
}

OUTPUT RULES

- Include in "bom" only confirmed symbols.
- Do NOT include uncertain symbols in the BOM count.
- If a provided material does not appear in the diagram, omit it from "bom".
- List each unidentified or uncertain symbol individually.
- If there are no unidentified or uncertain symbols, return an empty array:
  "simbolos_no_identificados": []
- "material" must use the exact material name from the reference table.
- "cantidad" must be an integer.
- "material_mas_parecido" must be the closest material name from the reference table, or null if there is no clear closest match.
- "ubicacion_aproximada" must be specific.
- "descripcion_visual" must briefly describe the symbol shape.
- "motivo" must explain why it was not counted as confirmed.

LOCATION RULES

When describing approximate location, be as specific as possible.

Good location examples:

- "Arriba a la derecha, dentro del recuadro principal, junto a la línea vertical derecha"
- "Zona central, debajo del interruptor principal y a la izquierda del bloque de salidas"
- "Abajo a la izquierda, cerca del borde inferior del plano"
- "Centro-derecha, conectado a una línea horizontal que sale hacia la derecha"
- "Parte superior central, justo debajo del título del tablero"

Avoid vague locations like:

- "Arriba"
- "Abajo"
- "En el medio"
- "A la derecha"

ANALYSIS METHOD

1. First, inspect the reference table and symbol catalog.
2. Memorize the visual shape of each provided symbol.
3. Divide the diagram into zones:
   - top-left
   - top-center
   - top-right
   - center-left
   - center
   - center-right
   - bottom-left
   - bottom-center
   - bottom-right
4. Scan the diagram systematically from top-left to bottom-right.
5. For every visible symbol-like shape:
   - Compare it against all provided symbol images.
   - Count it only if there is a clear match.
   - If uncertain, add it to "simbolos_no_identificados".
6. Group confirmed counts by material.
7. Return only the final JSON.

FINAL RULE

Do not guess.

If a symbol is not clearly identifiable, do not count it in the BOM. Add it to "simbolos_no_identificados" instead.
""".strip()


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
    client: ClaudeVisionClient,
    *,
    image_bytes: bytes,
    filename: str,
    user_prompt: str = "",
    reference_system_prompt: str = REFERENCE_SYSTEM_PROMPT,
    reference_user_prompt: str = REFERENCE_USER_PROMPT,
) -> tuple[dict[str, Any], str]:
    content = [
        {"type": "text", "text": reference_user_prompt + ("\n\nExtra instructions:\n" + user_prompt.strip() if user_prompt.strip() else "")},
        client.build_image_block(image_bytes, filename),
    ]
    response = client.create_message(system_prompt=reference_system_prompt, user_content=content)
    raw_text = client.extract_text(response)
    return normalize_reference_payload(parse_json_response(raw_text)), raw_text


def analyze_plan_image(
    client: ClaudeVisionClient,
    *,
    plan_images: list[tuple[str, bytes]],
    symbol_images: list[tuple[str, bytes]],
    symbol_catalog_entries: list[SymbolCatalogEntry],
    reference_payload: dict[str, Any],
    user_prompt: str = "",
    cache_static_prefix: bool = False,
    cache_ttl: str = "5m",
    plan_system_prompt: str = PLAN_SYSTEM_PROMPT,
    plan_user_prompt: str = PLAN_USER_PROMPT,
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
