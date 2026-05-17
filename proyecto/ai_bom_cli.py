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
    extract_valid_materials_from_reference_table,
    generate_catalog_visual_analysis,
    parse_symbol_catalog_json,
)
from ai_detection.provider_resolvers import find_provider_resolver, supported_provider_choices
from dwg_converter.dxf_renderer import DxfRenderOptions, render_dxf_to_png


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


def render_dxf_inputs(
    *,
    dxf_paths: list[Path],
    output_dir: Path,
    prefix: str,
    purpose: str,
    layout: str,
    dpi: int,
    max_pixels: int,
    monochrome: bool,
    force_text_black: bool,
    swap_black_white: bool,
    crop_mode: str,
    render_tiles: bool = False,
    tile_count: int = 4,
    tile_source_max_pixels: int = 6000,
    tile_overlap: float = 0.12,
) -> tuple[list[Path], list[dict[str, Any]]]:
    options = DxfRenderOptions(
        layout=layout,
        dpi=dpi,
        max_pixels=max_pixels,
        monochrome=monochrome,
        force_text_black=force_text_black,
        swap_black_white=swap_black_white,
        crop_mode=crop_mode,
    )
    rendered_paths: list[Path] = []
    metadata: list[dict[str, Any]] = []

    for index, dxf_path in enumerate(dxf_paths, start=1):
        safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in dxf_path.stem)
        output_path = output_dir / f"{prefix}_{index}_{safe_stem}.png"
        rendered_path = render_dxf_to_png(dxf_path, output_path, options)
        rendered_paths.append(rendered_path)
        metadata.append(
            {
                "source": str(dxf_path),
                "rendered_png": str(rendered_path),
                "purpose": purpose,
                "layout": layout,
                "dpi": dpi,
                "max_pixels": max_pixels,
                "monochrome": monochrome,
                "force_text_black": force_text_black,
                "swap_black_white": swap_black_white,
                "crop_mode": crop_mode,
            }
        )

        if render_tiles:
            source_path = output_dir / f"{prefix}_{index}_{safe_stem}_tile_source.png"
            source_options = DxfRenderOptions(
                layout=layout,
                dpi=dpi,
                max_pixels=tile_source_max_pixels,
                monochrome=monochrome,
                force_text_black=force_text_black,
                swap_black_white=swap_black_white,
                crop_mode=crop_mode,
            )
            render_dxf_to_png(dxf_path, source_path, source_options)
            tile_paths = build_zoom_tiles(
                source_path=source_path,
                output_dir=output_dir,
                output_stem=f"{prefix}_{index}_{safe_stem}",
                tile_count=tile_count,
                max_pixels=max_pixels,
                overlap=tile_overlap,
            )
            source_path.unlink(missing_ok=True)
            for tile_number, tile_path in enumerate(tile_paths, start=1):
                rendered_paths.append(tile_path)
                metadata.append(
                    {
                        "source": str(dxf_path),
                        "rendered_png": str(tile_path),
                        "purpose": f"{purpose}_zoom_tile",
                        "tile_number": tile_number,
                        "tile_count": len(tile_paths),
                        "layout": layout,
                        "dpi": dpi,
                        "max_pixels": max_pixels,
                        "tile_source_max_pixels": tile_source_max_pixels,
                        "tile_overlap": tile_overlap,
                        "monochrome": monochrome,
                        "force_text_black": force_text_black,
                        "swap_black_white": swap_black_white,
                        "crop_mode": crop_mode,
                    }
                )

    return rendered_paths, metadata


def build_zoom_tiles(
    *,
    source_path: Path,
    output_dir: Path,
    output_stem: str,
    tile_count: int,
    max_pixels: int,
    overlap: float,
) -> list[Path]:
    if tile_count < 1:
        return []

    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "DXF zoom tiles require Pillow. Install optional dependencies with:\n"
            "python3 -m pip install -r proyecto/requirements-dxf.txt"
        ) from exc

    overlap = min(max(overlap, 0.0), 0.45)
    with Image.open(source_path) as image:
        image = image.convert("RGB")
        width, height = image.size
        horizontal = width >= height
        segment_count = min(tile_count, width if horizontal else height)
        tile_paths: list[Path] = []

        for tile_index in range(segment_count):
            axis_length = width if horizontal else height
            start = round(tile_index * axis_length / segment_count)
            end = round((tile_index + 1) * axis_length / segment_count)
            pad = round((end - start) * overlap)
            start = max(0, start - pad)
            end = min(axis_length, end + pad)

            if horizontal:
                crop_box = (start, 0, end, height)
            else:
                crop_box = (0, start, width, end)

            tile = image.crop(crop_box)
            tile.thumbnail((max_pixels, max_pixels), Image.Resampling.LANCZOS)
            tile_path = output_dir / f"{output_stem}_tile_{tile_index + 1:02d}.png"
            tile.save(tile_path, optimize=True)
            tile_paths.append(tile_path)

    return tile_paths


def normalize_bom_payload(payload: dict[str, Any], valid_materials: list[str] | None = None) -> dict[str, Any]:
    del valid_materials
    bom = []
    include_specification = any(
        isinstance(item, dict) and "especificacion" in item for item in payload.get("bom", [])
    )
    for item in payload.get("bom", []):
        if not isinstance(item, dict):
            continue
        material = str(item.get("material", "")).strip()
        if not material:
            continue

        try:
            quantity = int(item.get("cantidad", 0))
        except (TypeError, ValueError):
            quantity = 0

        specification = item.get("especificacion")
        row = {"material": material}
        if specification is not None:
            specification_text = str(specification).strip()
            specification = specification_text or None
        if include_specification:
            row["especificacion"] = specification
        row["cantidad"] = quantity
        bom.append(row)

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
    fieldnames = ["material", "cantidad"]
    if any(isinstance(item, dict) and "especificacion" in item for item in payload.get("bom", [])):
        fieldnames = ["material", "especificacion", "cantidad"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for item in payload.get("bom", []):
            writer.writerow({fieldname: item.get(fieldname, "") for fieldname in fieldnames})


def pricing_for_model(provider: str, model: str) -> dict[str, float] | None:
    normalized_provider = provider.lower()
    normalized_model = model.lower()

    match normalized_provider, normalized_model:
        case "anthropic", model_name if any(opus_version in model_name for opus_version in ["opus-4-7", "opus-4.7", "opus-4-6", "opus-4.6", "opus-4-5", "opus-4.5"]):
            return {"input": 5.0, "output": 25.0}
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
    catalog_visual_analysis_usage: dict[str, Any] | None = None,
    timings_seconds: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    all_usage = combine_usage(*(usage for usage in [catalog_visual_analysis_usage, reference_usage, bom_usage] if usage))
    pricing = pricing_for_model(provider, model)
    catalog_visual_analysis_cost = estimate_cost(catalog_visual_analysis_usage or {}, pricing)
    reference_cost = estimate_cost(reference_usage or {}, pricing)
    bom_cost = estimate_cost(bom_usage, pricing)
    return {
        "provider": provider,
        "model": model,
        "prompts": prompt_metadata,
        "usage": {
            "catalog_visual_analysis": catalog_visual_analysis_usage,
            "reference_extraction": reference_usage,
            "bom_generation": bom_usage,
            "total": all_usage,
        },
        "pricing_usd_per_million_tokens": pricing,
        "timings_seconds": timings_seconds or {},
        "estimated_cost_usd": {
            "catalog_visual_analysis": catalog_visual_analysis_cost,
            "reference_extraction": reference_cost,
            "bom_generation": bom_cost,
            "total": combine_estimated_costs(catalog_visual_analysis_cost, reference_cost, bom_cost),
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
    }
    if not args.reference_table_has_standard and not args.reference_table_only:
        files.update(
            {
                "reference_system": Path(args.reference_system_prompt_file)
                if args.reference_system_prompt_file
                else prompt_dir / "reference_system.md",
                "reference_user": Path(args.reference_user_prompt_file)
                if args.reference_user_prompt_file
                else prompt_dir / "reference_user.md",
            }
        )

    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Prompt file(s) not found: " + ", ".join(missing))

    return files


def resolve_catalog_visual_analysis_prompt_files(args: argparse.Namespace) -> dict[str, Path]:
    prompt_dir = Path(args.prompt_dir)
    files = {
        "catalog_visual_analysis_system": (
            Path(args.catalog_visual_analysis_system_prompt_file)
            if args.catalog_visual_analysis_system_prompt_file
            else prompt_dir / "catalog_visual_analysis_system.md"
        ),
        "catalog_visual_analysis_user": (
            Path(args.catalog_visual_analysis_user_prompt_file)
            if args.catalog_visual_analysis_user_prompt_file
            else prompt_dir / "catalog_visual_analysis_user.md"
        ),
    }

    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Catalog visual analysis prompt file(s) not found: " + ", ".join(missing))

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
    default_symbols_dir = data_dir / "symbols" / "investigacion-1"
    default_catalog_json = script_dir / "symbol-catalog" / "investigacion_1" / "symbol_catalog.json"
    default_prompt_dir = (
        script_dir
        / "prompts"
        / "investigacion_1"
        / "bom_symbol_count"
        / "etapa1"
        / "v4_visual_symbols_only"
    )
    default_reference_table_only_prompt_dir = script_dir / "prompts" / "mvp" / "v2"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    parser = argparse.ArgumentParser(
        description="Generate a symbol-count BOM JSON and CSV from an electrical diagram image."
    )
    parser.add_argument(
        "--diagram-image",
        nargs="*",
        default=[],
        help="One to five electrical diagram images to analyze as one combined BOM.",
    )
    parser.add_argument(
        "--diagram-dxf",
        nargs="*",
        default=[],
        help="One to five DXF electrical diagrams to render to PNG and analyze as one combined BOM.",
    )
    parser.add_argument("--reference-image", default=None, help="Optional reference table image to extract before BOM analysis.")
    parser.add_argument("--reference-dxf", default=None, help="Optional reference table DXF to render to PNG before extraction.")
    parser.add_argument(
        "--render-dxf-only",
        action="store_true",
        help="Render --diagram-dxf and/or --reference-dxf to PNG, print the output paths, then exit without calling any AI provider.",
    )
    parser.add_argument(
        "--dxf-render-dir",
        default=str(data_dir / "rendered_dxf" / timestamp),
        help="Folder where rendered DXF PNGs are written.",
    )
    parser.add_argument("--dxf-layout", default="model", help="DXF layout to render. Use 'model' for modelspace.")
    parser.add_argument(
        "--dxf-render-dpi",
        type=int,
        default=1600,
        help="DPI used for plan DXF rendering.",
    )
    parser.add_argument(
        "--dxf-render-max-pixels",
        type=int,
        default=4096,
        help="Target maximum long-side pixels for rendered plan DXF PNGs.",
    )
    parser.add_argument(
        "--dxf-reference-render-dpi",
        type=int,
        default=1600,
        help="DPI used for reference-table DXF rendering.",
    )
    parser.add_argument(
        "--dxf-reference-render-max-pixels",
        type=int,
        default=4096,
        help="Target maximum long-side pixels for rendered reference-table DXF PNGs.",
    )
    parser.add_argument(
        "--dxf-render-tiles",
        action="store_true",
        help="For each diagram DXF, render the full plan plus zoom tiles for better model accuracy on dense plans.",
    )
    parser.add_argument(
        "--dxf-render-tile-count",
        type=int,
        default=4,
        help="Number of zoom tiles to create per diagram DXF when --dxf-render-tiles is enabled.",
    )
    parser.add_argument(
        "--dxf-render-tile-source-max-pixels",
        type=int,
        default=12000,
        help="Long-side pixel size for the temporary high-resolution image used to create zoom tiles.",
    )
    parser.add_argument(
        "--dxf-render-tile-overlap",
        type=float,
        default=0.12,
        help="Fractional overlap between neighboring DXF zoom tiles.",
    )
    color_group = parser.add_mutually_exclusive_group()
    color_group.add_argument(
        "--dxf-render-monochrome",
        dest="dxf_render_monochrome",
        action="store_true",
        default=True,
        help="Render DXF entities in black on white for OCR and symbol-counting legibility. This is the default.",
    )
    color_group.add_argument(
        "--dxf-render-color",
        dest="dxf_render_monochrome",
        action="store_false",
        help="Preserve DXF colors when layer colors carry meaning.",
    )
    parser.add_argument(
        "--dxf-force-text-black",
        action="store_true",
        help="When preserving DXF colors, force text-like entities to render in black for readability.",
    )
    parser.add_argument(
        "--dxf-swap-black-white",
        action="store_true",
        help="When preserving DXF colors on a white background, swap only black/white color handling so AutoCAD color 7 stays visible.",
    )
    parser.add_argument(
        "--reference-table-has-standard",
        action="store_true",
        help=(
            "Do not pass or extract a reference table. Use the provided symbol catalog JSON and images "
            "as the standard material source."
        ),
    )
    parser.add_argument(
        "--reference-table-only",
        action="store_true",
        help=(
            "Skip the manual symbol catalog and count from the rendered plan plus extracted reference table. "
            "Use with --reference-image or --reference-dxf and a prompt-dir designed for reference-only counting."
        ),
    )
    parser.add_argument("--symbols-dir", default=str(default_symbols_dir), help="Folder containing catalog symbol images.")
    parser.add_argument("--catalog-json", default=str(default_catalog_json), help="Symbol catalog JSON path.")
    parser.add_argument(
        "--generate-catalog-visual-analysis",
        action="store_true",
        help="Generate visual-only symbol catalog analysis from --catalog-json and --symbols-dir, then exit.",
    )
    parser.add_argument(
        "--catalog-visual-analysis-output",
        default=None,
        help="Where to write catalog visual analysis JSON when --generate-catalog-visual-analysis is used.",
    )
    parser.add_argument(
        "--catalog-visual-analysis",
        default=None,
        help="Optional catalog visual analysis JSON from a previous run to include in BOM counting.",
    )
    parser.add_argument(
        "--catalog-visual-analysis-raw-output",
        default=None,
        help="Optional raw AI output path for catalog visual analysis generation.",
    )
    parser.add_argument("--output-json", default=str(data_dir / "outputs" / f"bom_{timestamp}.json"))
    parser.add_argument("--output-csv", default=str(data_dir / "outputs" / f"bom_{timestamp}.csv"))
    parser.add_argument("--raw-output", default=str(data_dir / "outputs" / f"bom_raw_{timestamp}.txt"))
    parser.add_argument("--reference-output-json", default=None)
    parser.add_argument("--reference-raw-output", default=None)
    parser.add_argument("--usage-output", default=str(data_dir / "outputs" / f"bom_usage_{timestamp}.json"))
    parser.add_argument("--prompt-dir", default=None)
    parser.add_argument("--plan-system-prompt-file", default=None)
    parser.add_argument("--plan-user-prompt-file", default=None)
    parser.add_argument("--catalog-visual-analysis-system-prompt-file", default=None)
    parser.add_argument("--catalog-visual-analysis-user-prompt-file", default=None)
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
    args = parser.parse_args()
    if args.prompt_dir is None:
        args.prompt_dir = str(default_reference_table_only_prompt_dir if args.reference_table_only else default_prompt_dir)
    return args


def main() -> None:
    total_started_at = time.perf_counter()
    args = parse_args()
    diagram_images = [Path(image_path) for image_path in args.diagram_image]
    diagram_dxfs = [Path(dxf_path) for dxf_path in args.diagram_dxf]
    reference_dxf = Path(args.reference_dxf) if args.reference_dxf else None
    rendered_dxf_metadata: list[dict[str, Any]] = []
    dxf_render_elapsed_seconds: float | None = None

    if args.reference_image and reference_dxf:
        raise ValueError("Use either --reference-image or --reference-dxf, not both.")
    if not args.generate_catalog_visual_analysis and not args.render_dxf_only and not diagram_images and not diagram_dxfs:
        raise ValueError("--diagram-image is required unless --generate-catalog-visual-analysis is used.")
    if args.render_dxf_only and not diagram_dxfs and not reference_dxf:
        raise ValueError("--render-dxf-only requires --diagram-dxf and/or --reference-dxf.")
    if diagram_images or diagram_dxfs:
        total_diagram_inputs = len(diagram_images) + len(diagram_dxfs)
        if not 1 <= total_diagram_inputs <= 5:
            raise ValueError("--diagram-image and --diagram-dxf accept between 1 and 5 total diagram inputs.")
    reference_image = Path(args.reference_image) if args.reference_image else None
    symbols_dir = Path(args.symbols_dir)
    catalog_json_path = Path(args.catalog_json)
    catalog_visual_analysis_path = Path(args.catalog_visual_analysis) if args.catalog_visual_analysis else None
    load_env_file(Path(args.env_file))

    if args.reference_table_has_standard and reference_image:
        raise ValueError(
            "Do not pass --reference-image when --reference-table-has-standard is enabled. "
            "In standard mode, provide only --catalog-json and --symbols-dir for the symbol images."
        )
    if args.reference_table_has_standard and reference_dxf:
        raise ValueError(
            "Do not pass --reference-dxf when --reference-table-has-standard is enabled. "
            "In standard mode, provide only --catalog-json and --symbols-dir for the symbol images."
        )
    if args.reference_table_only and args.reference_table_has_standard:
        raise ValueError("--reference-table-only cannot be combined with --reference-table-has-standard.")
    if args.reference_table_only and args.generate_catalog_visual_analysis:
        raise ValueError("--reference-table-only cannot be combined with --generate-catalog-visual-analysis.")
    if args.reference_table_only and catalog_visual_analysis_path:
        raise ValueError("--reference-table-only cannot be combined with --catalog-visual-analysis.")

    for required_path in [*diagram_images, *diagram_dxfs, *([reference_dxf] if reference_dxf else []), *([catalog_visual_analysis_path] if catalog_visual_analysis_path else [])]:
        if not required_path.exists():
            raise FileNotFoundError(f"Required path not found: {required_path}")
    if reference_image and not reference_image.exists():
        raise FileNotFoundError(f"Required path not found: {reference_image}")

    if diagram_dxfs or reference_dxf:
        dxf_render_started_at = time.perf_counter()
        rendered_dir = Path(args.dxf_render_dir)
        rendered_diagram_images, diagram_render_metadata = render_dxf_inputs(
            dxf_paths=diagram_dxfs,
            output_dir=rendered_dir,
            prefix="diagram",
            purpose="plan",
            layout=args.dxf_layout,
            dpi=args.dxf_render_dpi,
            max_pixels=args.dxf_render_max_pixels,
            monochrome=args.dxf_render_monochrome,
            force_text_black=args.dxf_force_text_black,
            swap_black_white=args.dxf_swap_black_white,
            crop_mode="density-focus",
            render_tiles=args.dxf_render_tiles,
            tile_count=args.dxf_render_tile_count,
            tile_source_max_pixels=args.dxf_render_tile_source_max_pixels,
            tile_overlap=args.dxf_render_tile_overlap,
        )
        diagram_images.extend(rendered_diagram_images)
        rendered_dxf_metadata.extend(diagram_render_metadata)

        if len(diagram_images) > 5 and not args.render_dxf_only:
            raise ValueError(
                "DXF rendering produced more than 5 plan images. Reduce --dxf-render-tile-count, "
                "or run one diagram DXF at a time."
            )

        if reference_dxf:
            rendered_reference_images, reference_render_metadata = render_dxf_inputs(
                dxf_paths=[reference_dxf],
                output_dir=rendered_dir,
                prefix="reference",
                purpose="reference_table",
                layout=args.dxf_layout,
                dpi=args.dxf_reference_render_dpi,
                max_pixels=args.dxf_reference_render_max_pixels,
                monochrome=args.dxf_render_monochrome,
                force_text_black=args.dxf_force_text_black,
                swap_black_white=args.dxf_swap_black_white,
                crop_mode="content",
            )
            reference_image = rendered_reference_images[0]
            rendered_dxf_metadata.extend(reference_render_metadata)
        dxf_render_elapsed_seconds = time.perf_counter() - dxf_render_started_at

    if args.render_dxf_only:
        for item in rendered_dxf_metadata:
            print(f"Rendered {item['purpose']} DXF PNG: {item['rendered_png']}")
        return

    if args.reference_table_only and not reference_image:
        raise ValueError("--reference-table-only requires --reference-image or --reference-dxf.")

    catalog_json_text = ""
    catalog_entries = []
    symbol_images: list[tuple[str, bytes]] = []
    if not args.reference_table_only:
        for required_path in [symbols_dir, catalog_json_path]:
            if not required_path.exists():
                raise FileNotFoundError(f"Required path not found: {required_path}")
        catalog_json_text = catalog_json_path.read_text(encoding="utf-8")
        catalog_entries = parse_symbol_catalog_json(catalog_json_text)
        symbol_images = load_symbol_images(symbols_dir, catalog_json_text)

    client = find_provider_resolver(args.provider).create(api_key=args.api_key, model=args.model)

    if args.generate_catalog_visual_analysis:
        if not args.catalog_visual_analysis_output:
            raise ValueError("--catalog-visual-analysis-output is required with --generate-catalog-visual-analysis.")

        catalog_scan_prompts, catalog_scan_prompt_metadata = load_prompt_set(
            resolve_catalog_visual_analysis_prompt_files(args)
        )
        scan_started_at = time.perf_counter()
        visual_analysis_payload, visual_analysis_raw_text, visual_analysis_usage = generate_catalog_visual_analysis(
            client,
            symbol_images=symbol_images,
            symbol_catalog_entries=catalog_entries,
            catalog_visual_analysis_system_prompt=catalog_scan_prompts["catalog_visual_analysis_system"],
            catalog_visual_analysis_user_prompt=catalog_scan_prompts["catalog_visual_analysis_user"],
        )
        scan_elapsed_seconds = time.perf_counter() - scan_started_at

        visual_analysis_output = Path(args.catalog_visual_analysis_output)
        write_json(visual_analysis_output, visual_analysis_payload)

        if args.catalog_visual_analysis_raw_output:
            visual_analysis_raw_output = Path(args.catalog_visual_analysis_raw_output)
            visual_analysis_raw_output.parent.mkdir(parents=True, exist_ok=True)
            visual_analysis_raw_output.write_text(visual_analysis_raw_text, encoding="utf-8")

        write_json(
            Path(args.usage_output),
            build_usage_report(
                client.provider_name,
                client.model,
                {},
                catalog_scan_prompt_metadata,
                catalog_visual_analysis_usage=visual_analysis_usage,
                timings_seconds={
                    "catalog_visual_analysis": round(scan_elapsed_seconds, 3),
                    "total": round(time.perf_counter() - total_started_at, 3),
                },
            ),
        )
        print(f"Catalog visual analysis JSON: {visual_analysis_output}")
        if args.catalog_visual_analysis_raw_output:
            print(f"Catalog visual analysis raw output: {args.catalog_visual_analysis_raw_output}")
        print(f"Usage/cost JSON: {args.usage_output}")
        return

    prompts, prompt_metadata = load_prompt_set(resolve_prompt_files(args))
    if rendered_dxf_metadata:
        prompt_metadata["rendered_dxf_inputs"] = rendered_dxf_metadata

    catalog_visual_analysis_payload = None
    if catalog_visual_analysis_path:
        catalog_visual_analysis_payload = json.loads(catalog_visual_analysis_path.read_text(encoding="utf-8"))

    reference_payload: dict[str, Any] = {}
    reference_raw_text = ""
    reference_usage: dict[str, Any] | None = None
    reference_elapsed_seconds: float | None = None
    valid_materials: list[str] | None = None
    if reference_image and not args.reference_table_has_standard and not args.reference_table_only:
        reference_started_at = time.perf_counter()
        reference_payload, reference_raw_text, reference_usage = extract_reference_table_from_image(
            client,
            image_bytes=read_bytes(reference_image),
            filename=reference_image.name,
            reference_system_prompt=prompts["reference_system"],
            reference_user_prompt=prompts["reference_user"],
        )
        reference_elapsed_seconds = time.perf_counter() - reference_started_at
    elif reference_image and args.reference_table_only:
        reference_started_at = time.perf_counter()
        reference_payload, reference_raw_text, reference_usage = extract_valid_materials_from_reference_table(
            client,
            image_bytes=read_bytes(reference_image),
            filename=reference_image.name,
        )
        valid_materials = reference_payload.get("valid_materials", [])
        reference_elapsed_seconds = time.perf_counter() - reference_started_at

    bom_started_at = time.perf_counter()
    payload, raw_text, bom_usage = analyze_plan_image(
        client,
        plan_images=[(diagram_image.name, read_bytes(diagram_image)) for diagram_image in diagram_images],
        reference_images=[(reference_image.name, read_bytes(reference_image))] if args.reference_table_only and reference_image else [],
        symbol_images=symbol_images,
        symbol_catalog_entries=catalog_entries,
        reference_payload=reference_payload,
        valid_materials=valid_materials,
        plan_system_prompt=prompts["plan_system"],
        plan_user_prompt=prompts["plan_user"],
        catalog_visual_analysis=catalog_visual_analysis_payload,
        reference_table_has_standard=args.reference_table_has_standard,
        reference_table_only=args.reference_table_only,
    )
    bom_elapsed_seconds = time.perf_counter() - bom_started_at
    normalized_payload = normalize_bom_payload(payload, valid_materials=valid_materials)

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
                "dxf_rendering": round(dxf_render_elapsed_seconds, 3) if dxf_render_elapsed_seconds is not None else None,
                "reference_extraction": round(reference_elapsed_seconds, 3) if reference_elapsed_seconds is not None else None,
                "bom_generation": round(bom_elapsed_seconds, 3),
                "total": round(time.perf_counter() - total_started_at, 3),
            },
        ),
    )

    if rendered_dxf_metadata:
        for item in rendered_dxf_metadata:
            print(f"Rendered DXF PNG: {item['rendered_png']}")
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
