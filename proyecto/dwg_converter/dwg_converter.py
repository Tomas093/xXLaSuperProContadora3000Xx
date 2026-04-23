from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import subprocess


class CadConverter(ABC):
    """Interface for CAD file converters."""

    @abstractmethod
    def can_convert(self, input_ext: str, output_ext: str) -> bool:
        """Return True when this converter supports the requested conversion."""
        raise NotImplementedError

    @abstractmethod
    def convert(self, input_path: str | Path, output_path: str | Path) -> Path:
        """Convert input_path into output_path and return the generated path."""
        raise NotImplementedError


class LibreDwgConverter(CadConverter):
    """Convert DWG files using LibreDWG command line tools."""

    _FORMAT_BY_EXTENSION = {
        ".dxf": "DXF",
        ".json": "JSON",
        ".geojson": "GeoJSON",
        ".svg": "SVG",
    }

    def can_convert(self, input_ext: str, output_ext: str) -> bool:
        return (
            input_ext.lower() == ".dwg"
            and output_ext.lower() in self._FORMAT_BY_EXTENSION
        )

    def convert(self, input_path: str | Path, output_path: str | Path) -> Path:
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_ext = output_path.suffix.lower()

        if not self.can_convert(input_path.suffix, output_ext):
            raise ValueError(f"LibreDWG cannot convert {input_path.suffix} to {output_ext}")

        dwgread = shutil.which("dwgread")
        if not dwgread:
            raise RuntimeError(
                "LibreDWG was not found. Install 'dwgread' or add it to PATH."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                dwgread,
                "-O",
                self._FORMAT_BY_EXTENSION[output_ext],
                "-o",
                str(output_path),
                str(input_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        return output_path


class OdaFileConverter(CadConverter):
    """Convert DWG to DXF using ODA File Converter when installed."""

    def can_convert(self, input_ext: str, output_ext: str) -> bool:
        return input_ext.lower() == ".dwg" and output_ext.lower() == ".dxf"

    def convert(self, input_path: str | Path, output_path: str | Path) -> Path:
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not self.can_convert(input_path.suffix, output_path.suffix):
            raise ValueError(
                f"ODA File Converter cannot convert {input_path.suffix} "
                f"to {output_path.suffix}"
            )

        executable = shutil.which("ODAFileConverter")
        if not executable:
            raise RuntimeError(
                "ODA File Converter was not found. Install it or add it to PATH."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                executable,
                str(input_path.parent),
                str(output_path.parent),
                "ACAD2018",
                "DXF",
                "0",
                "1",
                input_path.name,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        generated_path = output_path.parent / f"{input_path.stem}.dxf"
        if generated_path != output_path and generated_path.exists():
            generated_path.replace(output_path)

        if not output_path.exists():
            raise RuntimeError("ODA File Converter finished but no DXF was generated.")

        return output_path


class CadConversionService:
    """Select the first available converter that supports a conversion."""

    def __init__(self, converters: list[CadConverter] | None = None):
        self.converters = converters or [LibreDwgConverter(), OdaFileConverter()]

    def convert(self, input_path: str | Path, output_path: str | Path) -> Path:
        input_path = Path(input_path)
        output_path = Path(output_path)

        for converter in self.converters:
            if converter.can_convert(input_path.suffix, output_path.suffix):
                return converter.convert(input_path, output_path)

        raise ValueError(
            f"No converter available for {input_path.suffix} to {output_path.suffix}"
        )
