from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_detection.bom_service import (
    analyze_plan_image,
    extract_reference_table_from_image,
    parse_symbol_catalog_json,
)
from ai_detection.provider_resolvers import find_provider_resolver, supported_provider_choices


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


def pricing_for_model(provider: str, model: str) -> dict[str, float] | None:
    normalized_provider = provider.lower()
    normalized_model = model.lower()

    match normalized_provider, normalized_model:
        case "anthropic", model_name if "opus" in model_name:
            return {"input": 15.0, "output": 75.0}
        case "anthropic", model_name if "sonnet" in model_name:
            return {"input": 3.0, "output": 15.0}
        case "anthropic", model_name if "haiku" in model_name:
            return {"input": 0.8, "output": 4.0}
        case "openai", "gpt-5.5-pro":
            return {
                "input": 30.0,
                "output": 180.0,
                "input_long_context": 60.0,
                "output_long_context": 270.0,
            }
        case "openai", "gpt-5.5":
            return {
                "input": 5.0,
                "output": 30.0,
                "cached_input": 0.5,
                "input_long_context": 10.0,
                "cached_input_long_context": 1.0,
                "output_long_context": 45.0,
            }
        case "openai", "gpt-5.4-pro":
            return {
                "input": 30.0,
                "output": 180.0,
                "input_long_context": 60.0,
                "output_long_context": 270.0,
            }
        case "openai", "gpt-5.4-mini":
            return {"input": 0.75, "output": 4.5, "cached_input": 0.075}
        case "openai", "gpt-5.4":
            return {
                "input": 2.5,
                "output": 15.0,
                "cached_input": 0.25,
                "input_long_context": 5.0,
                "cached_input_long_context": 0.5,
                "output_long_context": 22.5,
            }
        case "gemini", model_name if "flash" in model_name:
            return {"input": 0.35, "output": 1.05}
        case "gemini", model_name if model_name.startswith("gemini-2.5-pro"):
            return {
                "input": 1.25,
                "output": 10.0,
                "input_above_200k": 2.5,
                "output_above_200k": 15.0,
                "threshold_input_tokens": 200_000,
            }
        case "gemini", model_name if model_name.startswith(("gemini-3.1-pro-preview", "gemini-3-pro-preview")):
            return {
                "input": 2.0,
                "output": 12.0,
                "input_above_200k": 4.0,
                "output_above_200k": 18.0,
                "threshold_input_tokens": 200_000,
            }
        case "gemini", model_name if "pro" in model_name:
            return {"input": 2.0, "output": 12.0}
        case _:
            return None


def estimate_cost(usage: dict[str, Any], pricing: dict[str, float] | None) -> dict[str, float | None]:
    if not pricing:
        return {
            "input": None,
            "output": None,
            "total": None,
        }

    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    input_price = pricing["input"]
    output_price = pricing["output"]
    threshold_input_tokens = int(pricing.get("threshold_input_tokens", 0) or 0)

    if threshold_input_tokens and input_tokens > threshold_input_tokens:
        input_price = pricing.get("input_above_200k", input_price)
        output_price = pricing.get("output_above_200k", output_price)

    input_cost = input_tokens / 1_000_000 * input_price
    output_cost = output_tokens / 1_000_000 * output_price
    return {
        "input": round(input_cost, 8),
        "output": round(output_cost, 8),
        "total": round(input_cost + output_cost, 8),
    }


def combine_estimated_costs(*costs: dict[str, float | None]) -> dict[str, float | None]:
    if any(cost["total"] is None for cost in costs):
        return {
            "input": None,
            "output": None,
            "total": None,
        }

    return {
        "input": round(sum(float(cost["input"] or 0.0) for cost in costs), 8),
        "output": round(sum(float(cost["output"] or 0.0) for cost in costs), 8),
        "total": round(sum(float(cost["total"] or 0.0) for cost in costs), 8),
    }


def combine_usage(*usages: dict[str, Any]) -> dict[str, int]:
    return {
        "input_tokens": sum(int(usage.get("input_tokens", 0) or 0) for usage in usages),
        "output_tokens": sum(int(usage.get("output_tokens", 0) or 0) for usage in usages),
        "visible_output_tokens": sum(int(usage.get("visible_output_tokens", usage.get("output_tokens", 0)) or 0) for usage in usages),
        "thinking_tokens": sum(int(usage.get("thinking_tokens", 0) or 0) for usage in usages),
        "total_tokens": sum(int(usage.get("total_tokens", 0) or 0) for usage in usages),
        "cache_creation_input_tokens": sum(int(usage.get("cache_creation_input_tokens", 0) or 0) for usage in usages),
        "cache_read_input_tokens": sum(int(usage.get("cache_read_input_tokens", 0) or 0) for usage in usages),
    }


def build_usage_report(
    provider: str,
    model: str,
    bom_usage: dict[str, Any],
    prompt_metadata: dict[str, Any],
    *,
    reference_usage: dict[str, Any] | None = None,
    timings_seconds: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    all_usage = combine_usage(*(usage for usage in [reference_usage, bom_usage] if usage))
    pricing = pricing_for_model(provider, model)
    reference_cost = estimate_cost(reference_usage or {}, pricing)
    bom_cost = estimate_cost(bom_usage, pricing)
    return {
        "provider": provider,
        "model": model,
        "prompts": prompt_metadata,
        "usage": {
            "reference_extraction": reference_usage,
            "bom_generation": bom_usage,
            "total": all_usage,
        },
        "pricing_usd_per_million_tokens": pricing,
        "timings_seconds": timings_seconds or {},
        "estimated_cost_usd": {
            "reference_extraction": reference_cost,
            "bom_generation": bom_cost,
            "total": combine_estimated_costs(reference_cost, bom_cost),
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
    parser.add_argument("--reference-image", default=None, help="Optional reference table image to extract before BOM analysis.")
    parser.add_argument("--symbols-dir", default=str(data_dir / "symbols"), help="Folder containing catalog symbol images.")
    parser.add_argument("--catalog-json", default=str(data_dir / "symbol_catalog.json"), help="Symbol catalog JSON path.")
    parser.add_argument("--output-json", default=str(data_dir / "outputs" / f"bom_{timestamp}.json"))
    parser.add_argument("--output-csv", default=str(data_dir / "outputs" / f"bom_{timestamp}.csv"))
    parser.add_argument("--raw-output", default=str(data_dir / "outputs" / f"bom_raw_{timestamp}.txt"))
    parser.add_argument("--reference-output-json", default=None)
    parser.add_argument("--reference-raw-output", default=None)
    parser.add_argument("--usage-output", default=str(data_dir / "outputs" / f"bom_usage_{timestamp}.json"))
    parser.add_argument("--prompt-dir", default=str(script_dir / "prompts" / "bom_symbol_count" / "v4_visual_symbols_only"))
    parser.add_argument("--plan-system-prompt-file", default=None)
    parser.add_argument("--plan-user-prompt-file", default=None)
    parser.add_argument("--reference-system-prompt-file", default=None)
    parser.add_argument("--reference-user-prompt-file", default=None)
    parser.add_argument("--env-file", default=str(script_dir.parent / ".env"), help="Optional .env file with provider API keys.")
    parser.add_argument(
        "--provider",
        default="anthropic",
        choices=supported_provider_choices(),
        help="AI provider. Defaults to anthropic.",
    )
    parser.add_argument("--model", default=None, help="Model name. Defaults to the selected provider default.")
    parser.add_argument("--api-key", default=None, help="Provider API key. Defaults to provider-specific env vars.")
    return parser.parse_args()


def main() -> None:
    total_started_at = time.perf_counter()
    args = parse_args()
    diagram_image = Path(args.diagram_image)
    reference_image = Path(args.reference_image) if args.reference_image else None
    symbols_dir = Path(args.symbols_dir)
    catalog_json_path = Path(args.catalog_json)
    load_env_file(Path(args.env_file))

    for required_path in [diagram_image, symbols_dir, catalog_json_path]:
        if not required_path.exists():
            raise FileNotFoundError(f"Required path not found: {required_path}")
    if reference_image and not reference_image.exists():
        raise FileNotFoundError(f"Required path not found: {reference_image}")

    catalog_json_text = catalog_json_path.read_text(encoding="utf-8")
    catalog_entries = parse_symbol_catalog_json(catalog_json_text)
    symbol_images = load_symbol_images(symbols_dir, catalog_json_text)
    prompts, prompt_metadata = load_prompt_set(resolve_prompt_files(args))
    client = find_provider_resolver(args.provider).create(api_key=args.api_key, model=args.model)

    reference_payload: dict[str, Any] = {}
    reference_raw_text = ""
    reference_usage: dict[str, Any] | None = None
    reference_elapsed_seconds: float | None = None
    if reference_image:
        reference_started_at = time.perf_counter()
        reference_payload, reference_raw_text, reference_usage = extract_reference_table_from_image(
            client,
            image_bytes=read_bytes(reference_image),
            filename=reference_image.name,
            reference_system_prompt=prompts["reference_system"],
            reference_user_prompt=prompts["reference_user"],
        )
        reference_elapsed_seconds = time.perf_counter() - reference_started_at

    bom_started_at = time.perf_counter()
    payload, raw_text, bom_usage = analyze_plan_image(
        client,
        plan_images=[(diagram_image.name, read_bytes(diagram_image))],
        symbol_images=symbol_images,
        symbol_catalog_entries=catalog_entries,
        reference_payload=reference_payload,
        plan_system_prompt=prompts["plan_system"],
        plan_user_prompt=prompts["plan_user"],
    )
    bom_elapsed_seconds = time.perf_counter() - bom_started_at
    normalized_payload = normalize_bom_payload(payload)

    output_json = Path(args.output_json)
    output_csv = Path(args.output_csv)
    raw_output = Path(args.raw_output)
    usage_output = Path(args.usage_output)
    reference_output_json = Path(args.reference_output_json) if args.reference_output_json else None
    reference_raw_output = Path(args.reference_raw_output) if args.reference_raw_output else None
    if reference_output_json:
        write_json(reference_output_json, reference_payload)
    if reference_raw_output:
        reference_raw_output.parent.mkdir(parents=True, exist_ok=True)
        reference_raw_output.write_text(reference_raw_text, encoding="utf-8")
    write_json(output_json, normalized_payload)
    write_bom_csv(output_csv, normalized_payload)
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text(raw_text, encoding="utf-8")
    write_json(
        usage_output,
        build_usage_report(
            client.provider_name,
            client.model,
            bom_usage,
            prompt_metadata,
            reference_usage=reference_usage,
            timings_seconds={
                "reference_extraction": round(reference_elapsed_seconds, 3) if reference_elapsed_seconds is not None else None,
                "bom_generation": round(bom_elapsed_seconds, 3),
                "total": round(time.perf_counter() - total_started_at, 3),
            },
        ),
    )

    if reference_output_json:
        print(f"Reference JSON: {reference_output_json}")
    if reference_raw_output:
        print(f"Reference raw output: {reference_raw_output}")
    print(f"BOM JSON: {output_json}")
    print(f"BOM CSV: {output_csv}")
    print(f"Raw AI output: {raw_output}")
    print(f"Usage/cost JSON: {usage_output}")


if __name__ == "__main__":
    main()
