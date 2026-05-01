from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_detection.bom_service import analyze_plan_image, parse_symbol_catalog_json
from ai_detection.claude_client import ClaudeVisionClient


CLAUDE_SONNET_INPUT_USD_PER_MILLION_TOKENS = 3.0
CLAUDE_SONNET_OUTPUT_USD_PER_MILLION_TOKENS = 15.0


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def load_symbol_images(symbols_dir: Path, catalog_json_text: str) -> list[tuple[str, bytes]]:
    entries = parse_symbol_catalog_json(catalog_json_text)
    seen_materials: set[str] = set()
    images: list[tuple[str, bytes]] = []

    for entry in entries:
        material = entry.component_name.strip()
        if not entry.filename or not material:
            raise ValueError("Each catalog entry must include filename and component_name.")
        if material in seen_materials:
            raise ValueError(
                f"Duplicate material in catalog: {material}. This flow requires exactly one symbol image per material."
            )
        seen_materials.add(material)

        image_path = symbols_dir / entry.filename
        if not image_path.exists():
            raise FileNotFoundError(f"Symbol image not found: {image_path}")
        images.append((entry.filename, read_bytes(image_path)))

    if not images:
        raise ValueError("The symbol catalog is empty.")

    return images


def normalize_bom_payload(payload: dict[str, Any]) -> dict[str, Any]:
    bom = []
    for item in payload.get("bom", []):
        if not isinstance(item, dict):
            continue
        material = str(item.get("material", "")).strip()
        if not material:
            continue
        bom.append(
            {
                "material": material,
                "cantidad": int(item.get("cantidad", 0)),
            }
        )

    unidentified = payload.get("simbolos_no_identificados", [])
    if not isinstance(unidentified, list):
        unidentified = []

    return {
        "bom": bom,
        "simbolos_no_identificados": unidentified,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_bom_csv(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["material", "cantidad"])
        writer.writeheader()
        for item in payload.get("bom", []):
            writer.writerow(
                {
                    "material": item.get("material", ""),
                    "cantidad": item.get("cantidad", ""),
                }
            )


def build_usage_report(model: str, usage: dict[str, Any], prompt_metadata: dict[str, Any]) -> dict[str, Any]:
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    input_cost = input_tokens / 1_000_000 * CLAUDE_SONNET_INPUT_USD_PER_MILLION_TOKENS
    output_cost = output_tokens / 1_000_000 * CLAUDE_SONNET_OUTPUT_USD_PER_MILLION_TOKENS

    return {
        "model": model,
        "prompts": prompt_metadata,
        "usage": usage,
        "pricing_usd_per_million_tokens": {
            "input": CLAUDE_SONNET_INPUT_USD_PER_MILLION_TOKENS,
            "output": CLAUDE_SONNET_OUTPUT_USD_PER_MILLION_TOKENS,
        },
        "estimated_cost_usd": {
            "input": round(input_cost, 8),
            "output": round(output_cost, 8),
            "total": round(input_cost + output_cost, 8),
        },
    }


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_prompt_files(args: argparse.Namespace) -> dict[str, Path]:
    prompt_dir = Path(args.prompt_dir)
    files = {
        "plan_system": Path(args.plan_system_prompt_file) if args.plan_system_prompt_file else prompt_dir / "plan_system.md",
        "plan_user": Path(args.plan_user_prompt_file) if args.plan_user_prompt_file else prompt_dir / "plan_user.md",
        "reference_system": Path(args.reference_system_prompt_file) if args.reference_system_prompt_file else prompt_dir / "reference_system.md",
        "reference_user": Path(args.reference_user_prompt_file) if args.reference_user_prompt_file else prompt_dir / "reference_user.md",
    }

    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Prompt file(s) not found: " + ", ".join(missing))

    return files


def load_prompt_set(prompt_files: dict[str, Path]) -> tuple[dict[str, str], dict[str, Any]]:
    prompts = {name: read_text_file(path) for name, path in prompt_files.items()}
    metadata = {
        name: {
            "path": str(path),
            "sha256": file_sha256(path),
        }
        for name, path in prompt_files.items()
    }
    return prompts, metadata


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    data_dir = script_dir / "test_data"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    parser = argparse.ArgumentParser(
        description="Generate a symbol-count BOM JSON and CSV from an electrical diagram image."
    )
    parser.add_argument("--diagram-image", required=True, help="Electrical diagram image to analyze.")
    parser.add_argument("--symbols-dir", default=str(data_dir / "symbols"), help="Folder containing catalog symbol images.")
    parser.add_argument("--catalog-json", default=str(data_dir / "symbol_catalog.json"), help="Symbol catalog JSON path.")
    parser.add_argument("--output-json", default=str(data_dir / "outputs" / f"bom_{timestamp}.json"))
    parser.add_argument("--output-csv", default=str(data_dir / "outputs" / f"bom_{timestamp}.csv"))
    parser.add_argument("--raw-output", default=str(data_dir / "outputs" / f"bom_raw_{timestamp}.txt"))
    parser.add_argument("--usage-output", default=str(data_dir / "outputs" / f"bom_usage_{timestamp}.json"))
    parser.add_argument("--prompt-dir", default=str(script_dir / "prompts" / "bom_symbol_count" / "v1"))
    parser.add_argument("--plan-system-prompt-file", default=None)
    parser.add_argument("--plan-user-prompt-file", default=None)
    parser.add_argument("--reference-system-prompt-file", default=None)
    parser.add_argument("--reference-user-prompt-file", default=None)
    parser.add_argument("--env-file", default=str(script_dir.parent / ".env"), help="Optional .env file with ANTHROPIC_API_KEY.")
    parser.add_argument("--model", default=None, help="Claude model. Defaults to ANTHROPIC_MODEL or the client default.")
    parser.add_argument("--api-key", default=None, help="Claude API key. Defaults to ANTHROPIC_API_KEY or CLAUDE_API_KEY.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    diagram_image = Path(args.diagram_image)
    symbols_dir = Path(args.symbols_dir)
    catalog_json_path = Path(args.catalog_json)
    load_env_file(Path(args.env_file))

    for required_path in [diagram_image, symbols_dir, catalog_json_path]:
        if not required_path.exists():
            raise FileNotFoundError(f"Required path not found: {required_path}")

    catalog_json_text = catalog_json_path.read_text(encoding="utf-8")
    catalog_entries = parse_symbol_catalog_json(catalog_json_text)
    symbol_images = load_symbol_images(symbols_dir, catalog_json_text)
    prompts, prompt_metadata = load_prompt_set(resolve_prompt_files(args))
    client = ClaudeVisionClient.from_env(api_key=args.api_key, model=args.model)

    payload, raw_text, usage = analyze_plan_image(
        client,
        plan_images=[(diagram_image.name, read_bytes(diagram_image))],
        symbol_images=symbol_images,
        symbol_catalog_entries=catalog_entries,
        reference_payload={},
        plan_system_prompt=prompts["plan_system"],
        plan_user_prompt=prompts["plan_user"],
    )
    normalized_payload = normalize_bom_payload(payload)

    output_json = Path(args.output_json)
    output_csv = Path(args.output_csv)
    raw_output = Path(args.raw_output)
    usage_output = Path(args.usage_output)
    write_json(output_json, normalized_payload)
    write_bom_csv(output_csv, normalized_payload)
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text(raw_text, encoding="utf-8")
    write_json(usage_output, build_usage_report(client.model, usage, prompt_metadata))

    print(f"BOM JSON: {output_json}")
    print(f"BOM CSV: {output_csv}")
    print(f"Raw Claude output: {raw_output}")
    print(f"Usage/cost JSON: {usage_output}")


if __name__ == "__main__":
    main()
