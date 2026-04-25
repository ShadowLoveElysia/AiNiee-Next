"""Adapters that map existing AiNiee settings into MangaCore."""

from .configAdapter import build_cli_config_snapshot
from .providerAdapter import (
    RuntimeAssetStatus,
    RuntimeDetectOutput,
    RuntimeInpaintOutput,
    RuntimeOcrOutput,
    download_runtime_assets,
    get_detect_runtime_ids,
    get_inpaint_runtime_id,
    get_ocr_runtime_id,
    get_runtime_asset_status,
    run_detect_runtime,
    run_inpaint_runtime,
    run_region_ocr_runtime,
)

__all__ = [
    "RuntimeAssetStatus",
    "RuntimeDetectOutput",
    "RuntimeInpaintOutput",
    "RuntimeOcrOutput",
    "build_cli_config_snapshot",
    "download_runtime_assets",
    "get_detect_runtime_ids",
    "get_inpaint_runtime_id",
    "get_ocr_runtime_id",
    "get_runtime_asset_status",
    "run_detect_runtime",
    "run_inpaint_runtime",
    "run_region_ocr_runtime",
]
