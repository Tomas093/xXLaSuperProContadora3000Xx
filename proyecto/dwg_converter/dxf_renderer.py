from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from statistics import median
import tempfile


class DxfRenderError(RuntimeError):
    """Raised when a DXF file cannot be rendered to an image."""


@dataclass(frozen=True)
class DxfRenderOptions:
    layout: str = "model"
    dpi: int = 1200
    max_pixels: int = 1568
    margin_ratio: float = 0.02
    lineweight_scaling: float = 2.0
    monochrome: bool = True
    force_text_black: bool = False
    swap_black_white: bool = False
    crop_mode: str = "content"


def render_dxf_to_png(
    input_path: str | Path,
    output_path: str | Path,
    options: DxfRenderOptions | None = None,
) -> Path:
    """Render a DXF layout to a high-resolution PNG using ezdxf + matplotlib."""

    options = options or DxfRenderOptions()
    input_path = Path(input_path)
    output_path = Path(output_path)

    if input_path.suffix.lower() != ".dxf":
        raise DxfRenderError(f"DXF renderer only accepts .dxf files: {input_path}")
    if options.dpi <= 0:
        raise DxfRenderError("--dxf-render-dpi must be greater than zero.")
    if options.max_pixels < 512:
        raise DxfRenderError("--dxf-render-max-pixels must be at least 512.")

    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))

    try:
        import ezdxf
        from ezdxf import bbox, recover
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    except ModuleNotFoundError as exc:
        raise DxfRenderError(
            "DXF rendering requires optional dependencies. Install them with:\n"
            "python3 -m pip install -r proyecto/requirements-dxf.txt"
        ) from exc

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise DxfRenderError(
            "DXF rendering requires matplotlib. Install optional dependencies with:\n"
            "python3 -m pip install -r proyecto/requirements-dxf.txt"
        ) from exc

    try:
        doc, auditor = recover.readfile(str(input_path))
    except (OSError, ezdxf.DXFError) as exc:
        raise DxfRenderError(f"Could not read DXF file: {input_path}") from exc

    if auditor.has_errors:
        raise DxfRenderError(f"DXF recover reported severe errors for: {input_path}")

    layout = _select_layout(doc, options.layout)
    extents = _get_extents(layout, bbox, options.crop_mode)
    figure_size = _figure_size_inches(extents, options)

    fig = plt.figure(figsize=figure_size, dpi=options.dpi, facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("white")
    ax.axis("off")
    ax.set_aspect("equal", adjustable="box")

    ctx = RenderContext(doc)
    out = MatplotlibBackend(ax)
    if options.monochrome:
        frontend_cls = _monochrome_frontend(Frontend)
    elif options.swap_black_white:
        frontend_cls = _light_color_black_frontend(Frontend)
    elif options.force_text_black:
        frontend_cls = _text_black_frontend(Frontend)
    else:
        frontend_cls = Frontend
    config = _drawing_config(options)
    frontend = frontend_cls(ctx, out, config=config) if config else frontend_cls(ctx, out)
    frontend.draw_layout(layout, finalize=True)

    if extents:
        min_x, min_y, max_x, max_y = extents
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        pad_x = width * options.margin_ratio
        pad_y = height * options.margin_ratio
        ax.set_xlim(min_x - pad_x, max_x + pad_x)
        ax.set_ylim(min_y - pad_y, max_y + pad_y)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(output_path, dpi=options.dpi, facecolor="white")
    finally:
        plt.close(fig)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise DxfRenderError(f"DXF render did not create a PNG: {output_path}")

    _optimize_png_for_api(output_path, options.max_pixels)

    return output_path


def _select_layout(doc, layout_name: str):
    if layout_name.lower() in {"model", "modelspace"}:
        return doc.modelspace()

    try:
        return doc.layout(layout_name)
    except KeyError as exc:
        available = ["model", *[layout.name for layout in doc.layouts]]
        raise DxfRenderError(
            f"DXF layout '{layout_name}' was not found. Available layouts: {', '.join(available)}"
        ) from exc


def _get_extents(layout, bbox_module, crop_mode: str) -> tuple[float, float, float, float] | None:
    if crop_mode == "density-focus":
        density_extents = _density_focused_extents(layout, bbox_module)
        if density_extents:
            return density_extents

    if crop_mode == "insert-focus":
        insert_extents = _insert_focused_extents(layout, bbox_module)
        if insert_extents:
            return insert_extents

    try:
        extents = bbox_module.extents(layout, fast=True)
    except Exception:
        return None

    has_data = getattr(extents, "has_data", False)
    if callable(has_data):
        has_data = has_data()
    if not has_data:
        return None

    return (
        float(extents.extmin.x),
        float(extents.extmin.y),
        float(extents.extmax.x),
        float(extents.extmax.y),
    )


def _density_focused_extents(layout, bbox_module) -> tuple[float, float, float, float] | None:
    entity_extents = []
    centers_x = []
    centers_y = []

    for entity in layout:
        extents = _bbox_extents([entity], bbox_module)
        if not extents:
            continue
        min_x, min_y, max_x, max_y = extents
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        entity_extents.append((entity, extents, center_x, center_y))
        centers_x.append(center_x)
        centers_y.append(center_y)

    if len(entity_extents) < 8:
        return None

    median_x = median(centers_x)
    median_y = median(centers_y)
    deviations_x = [abs(value - median_x) for value in centers_x]
    deviations_y = [abs(value - median_y) for value in centers_y]
    radius_x = max(_quantile(deviations_x, 0.90) * 1.35, 1.0)
    radius_y = max(_quantile(deviations_y, 0.90) * 1.35, 1.0)

    focused_entities = [
        entity
        for entity, _extents, center_x, center_y in entity_extents
        if abs(center_x - median_x) <= radius_x and abs(center_y - median_y) <= radius_y
    ]

    minimum_count = max(8, round(len(entity_extents) * 0.25))
    if len(focused_entities) < minimum_count:
        return None

    return _bbox_extents(focused_entities, bbox_module)


def _insert_focused_extents(layout, bbox_module) -> tuple[float, float, float, float] | None:
    insert_entities = [entity for entity in layout if entity.dxftype() == "INSERT"]
    if not insert_entities:
        return None

    insert_extents = _bbox_extents(insert_entities, bbox_module)
    if not insert_extents:
        return None

    min_x, min_y, max_x, max_y = insert_extents
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    focus_margin = max(width, height) * 1.5
    focus_box = (
        min_x - focus_margin,
        min_y - focus_margin,
        max_x + focus_margin,
        max_y + focus_margin,
    )

    nearby_entities = []
    for entity in layout:
        entity_extents = _bbox_extents([entity], bbox_module)
        if not entity_extents:
            continue
        center_x = (entity_extents[0] + entity_extents[2]) / 2
        center_y = (entity_extents[1] + entity_extents[3]) / 2
        if focus_box[0] <= center_x <= focus_box[2] and focus_box[1] <= center_y <= focus_box[3]:
            nearby_entities.append(entity)

    return _bbox_extents(nearby_entities or insert_entities, bbox_module)


def _bbox_extents(entities, bbox_module) -> tuple[float, float, float, float] | None:
    try:
        extents = bbox_module.extents(entities, fast=True)
    except Exception:
        return None

    has_data = getattr(extents, "has_data", False)
    if callable(has_data):
        has_data = has_data()
    if not has_data:
        return None

    return (
        float(extents.extmin.x),
        float(extents.extmin.y),
        float(extents.extmax.x),
        float(extents.extmax.y),
    )


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, max(0, round((len(sorted_values) - 1) * q)))
    return sorted_values[index]


def _figure_size_inches(
    extents: tuple[float, float, float, float] | None,
    options: DxfRenderOptions,
) -> tuple[float, float]:
    max_inches = options.max_pixels / options.dpi
    if not extents:
        return (max_inches, max_inches)

    min_x, min_y, max_x, max_y = extents
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    aspect = width / height

    if aspect >= 1:
        return (max_inches, max(max_inches / aspect, 1.0))
    return (max(max_inches * aspect, 1.0), max_inches)


def _drawing_config(options: DxfRenderOptions):
    try:
        from ezdxf.addons.drawing import Configuration
    except ImportError:
        try:
            from ezdxf.addons.drawing.config import Configuration
        except ImportError:
            return None

    return Configuration(lineweight_scaling=options.lineweight_scaling)


def _monochrome_frontend(base_frontend):
    class MonochromeFrontend(base_frontend):
        def override_properties(self, entity, properties) -> None:
            properties.color = "#000000"

    return MonochromeFrontend


def _text_black_frontend(base_frontend):
    class TextBlackFrontend(base_frontend):
        def override_properties(self, entity, properties) -> None:
            if _is_text_entity(entity):
                properties.color = "#000000"

    return TextBlackFrontend


def _light_color_black_frontend(base_frontend):
    class LightColorBlackFrontend(base_frontend):
        def override_properties(self, entity, properties) -> None:
            if _is_light_render_color(getattr(properties, "color", "")):
                properties.color = "#000000"

    return LightColorBlackFrontend


def _is_light_render_color(color: str) -> bool:
    if not isinstance(color, str):
        return False

    normalized = color.strip().lower()
    if normalized in {"white", "#fff", "#ffffff"}:
        return True
    if not normalized.startswith("#"):
        return False

    hex_value = normalized[1:]
    if len(hex_value) == 3:
        hex_value = "".join(char * 2 for char in hex_value)
    if len(hex_value) != 6:
        return False

    try:
        red = int(hex_value[0:2], 16)
        green = int(hex_value[2:4], 16)
        blue = int(hex_value[4:6], 16)
    except ValueError:
        return False

    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return luminance >= 245


def _is_text_entity(entity) -> bool:
    dxftype = entity.dxftype()
    if "TEXT" in dxftype or dxftype in {"ATTRIB", "ATTDEF"}:
        return True

    dxf = getattr(entity, "dxf", None)
    return bool(dxf and hasattr(dxf, "text"))


def _optimize_png_for_api(path: Path, max_pixels: int) -> None:
    try:
        from PIL import Image
    except ModuleNotFoundError:
        return

    # The renderer creates very large local rasters before downscaling them for
    # provider input. Pillow's decompression-bomb guard is aimed at untrusted
    # external images, so it is safe to disable here for our generated file.
    Image.MAX_IMAGE_PIXELS = None

    with Image.open(path) as image:
        image = image.convert("RGB")
        image = _trim_white_border(image)
        width, height = image.size
        long_side = max(width, height)
        if long_side > max_pixels:
            scale = max_pixels / long_side
            new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            image = image.resize(new_size, resampling)

        image.save(path, optimize=True)


def _trim_white_border(image):
    try:
        from PIL import Image
        from PIL import ImageChops
    except ModuleNotFoundError:
        return image

    background = Image.new(image.mode, image.size, "white")
    diff = ImageChops.difference(image, background)
    bbox = diff.getbbox()
    if not bbox:
        return image

    left, top, right, bottom = bbox
    width, height = image.size
    pad = max(8, round(max(width, height) * 0.015))
    crop_box = (
        max(0, left - pad),
        max(0, top - pad),
        min(width, right + pad),
        min(height, bottom + pad),
    )
    return image.crop(crop_box)
