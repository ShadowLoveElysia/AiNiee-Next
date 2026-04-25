from __future__ import annotations

import asyncio
import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops

from ModuleFolders.MangaCore.render.bubbleAssign import TextSeed


@dataclass(slots=True)
class RuntimeAssetStatus:
    supported: bool
    available: bool
    storage_path: str = ""
    runtime_engine_id: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeDetectOutput:
    runtime_detector_id: str
    runtime_segmenter_id: str
    text_regions: list[dict[str, object]]
    bubble_regions: list[dict[str, object]] = field(default_factory=list)
    segment_mask: np.ndarray | None = None
    bubble_mask: np.ndarray | None = None


@dataclass(slots=True)
class RuntimeOcrOutput:
    runtime_engine_id: str
    seeds: list[TextSeed]


@dataclass(slots=True)
class RuntimeInpaintOutput:
    runtime_engine_id: str
    mask_pixels: int


_OCR_RUNTIME_SPECS: dict[str, dict[str, str]] = {
    "paddleocr-vl-1.5": {
        "module": "manga_translator.ocr.model_paddleocr_vl",
        "class": "ModelPaddleOCRVL",
        "runtime": "paddleocr-vl-1.5/transformers",
        "kind": "ocr",
    },
    "manga-ocr": {
        "module": "manga_translator.ocr.model_manga_ocr",
        "class": "ModelMangaOCR",
        "runtime": "manga-ocr/transformers",
        "kind": "ocr",
    },
    "mit48px-ocr": {
        "module": "manga_translator.ocr.model_48px",
        "class": "Model48pxOCR",
        "runtime": "mit48px-ocr/torch",
        "kind": "ocr",
    },
}

_DETECT_RUNTIME_SPECS: dict[str, dict[str, str]] = {
    "comic-text-bubble-detector": {
        "module": "manga_translator.detection.ctd",
        "class": "ComicTextDetector",
        "runtime": "comic-text-bubble-detector/ctd",
        "kind": "detect",
    },
}

_INPAINT_RUNTIME_SPECS: dict[str, dict[str, str]] = {
    "aot-inpainting": {
        "module": "manga_translator.inpainting.inpainting_aot",
        "class": "AotInpainter",
        "runtime": "aot-inpainting/torch",
        "kind": "inpaint",
    },
    "lama-manga": {
        "module": "manga_translator.inpainting.inpainting_lama_mpe",
        "class": "LamaLargeInpainter",
        "runtime": "lama-manga/onnx-or-torch",
        "kind": "inpaint",
    },
}

_RUNTIME_SPECS: dict[str, dict[str, str]] = {
    **_OCR_RUNTIME_SPECS,
    **_DETECT_RUNTIME_SPECS,
    **_INPAINT_RUNTIME_SPECS,
}

_RUNTIME_CLASS_CACHE: dict[tuple[str, str, str], type] = {}
_RUNTIME_INSTANCE_CACHE: dict[tuple[str, str, str], Any] = {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_model_root() -> Path:
    return _repo_root() / "Resource" / "Models" / "MangaCore"


def _resolve_model_root(root_dir: str | Path | None = None) -> Path:
    return Path(root_dir) if root_dir is not None else _default_model_root()


def _ensure_upstream_import_path() -> None:
    upstream_root = _repo_root() / "manga-translator-ui-main"
    upstream_path = str(upstream_root)
    if upstream_path not in sys.path:
        sys.path.insert(0, upstream_path)


def _await_sync(coro):
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is None or not running_loop.is_running():
        return asyncio.run(coro)

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _select_device(preferred: str | None = None) -> str:
    if preferred:
        return str(preferred)

    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _resolve_runtime_spec(model_id: str) -> dict[str, str] | None:
    return _RUNTIME_SPECS.get(str(model_id))


def _runtime_storage_path(model_id: str, root_dir: str | Path | None = None) -> str:
    spec = _resolve_runtime_spec(model_id)
    if spec is None:
        return ""
    subdir = {
        "ocr": "ocr",
        "detect": "detection",
        "inpaint": "inpainting",
    }[spec["kind"]]
    return str(_resolve_model_root(root_dir) / subdir)


def _build_runtime_wrapper(model_id: str, root_dir: str | Path | None = None):
    spec = _resolve_runtime_spec(model_id)
    if spec is None:
        raise KeyError(f"Unsupported runtime-backed manga model: {model_id}")

    model_root = _resolve_model_root(root_dir)
    cache_key = (str(model_root), spec["module"], spec["class"])
    wrapper_cls = _RUNTIME_CLASS_CACHE.get(cache_key)
    if wrapper_cls is None:
        _ensure_upstream_import_path()
        module = importlib.import_module(spec["module"])
        base_cls = getattr(module, spec["class"])
        wrapper_cls = type(
            f"MangaCore{spec['class']}",
            (base_cls,),
            {"_MODEL_DIR": str(model_root)},
        )
        _RUNTIME_CLASS_CACHE[cache_key] = wrapper_cls

    instance_key = (str(model_root), spec["kind"], str(model_id))
    wrapper = _RUNTIME_INSTANCE_CACHE.get(instance_key)
    if wrapper is None:
        wrapper = wrapper_cls()
        _RUNTIME_INSTANCE_CACHE[instance_key] = wrapper
    return wrapper


def _ensure_loaded(model_id: str, root_dir: str | Path | None = None, device: str | None = None):
    wrapper = _build_runtime_wrapper(model_id, root_dir)
    if not wrapper.is_downloaded():
        raise FileNotFoundError(f"Runtime assets are not ready for manga model: {model_id}")
    if not wrapper.is_loaded():
        _await_sync(wrapper.load(device=_select_device(device)))
    return wrapper


def _load_rgb_image(path: str | Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("RGB"), dtype=np.uint8)


def _load_mask_image(path: str | Path | None, size: tuple[int, int]) -> Image.Image:
    if not path:
        return Image.new("L", size, 0)

    candidate = Path(path)
    if not candidate.exists():
        return Image.new("L", size, 0)

    with Image.open(candidate) as image:
        mask = image.convert("L")
    if mask.size != size:
        mask = mask.resize(size, resample=Image.Resampling.NEAREST)
    return mask


def _normalize_mask_array(mask: np.ndarray | None) -> np.ndarray | None:
    if mask is None:
        return None
    array = np.asarray(mask)
    if array.ndim == 3:
        array = array[:, :, 0]
    return np.where(array > 0, 255, 0).astype(np.uint8)


def _runtime_backend_suffix(wrapper: Any) -> str:
    backend = getattr(wrapper, "backend", "")
    if backend:
        return str(backend)

    device = str(getattr(wrapper, "device", "cpu"))
    if device.startswith("cuda"):
        return "torch-cuda"
    if device == "mps":
        return "torch-mps"
    if getattr(wrapper, "use_gpu", False):
        return "torch-gpu"
    return "cpu"


def _region_polygon(region: Any) -> np.ndarray:
    polygon = getattr(region, "polygon", None)
    if isinstance(polygon, list) and len(polygon) >= 4:
        return np.asarray(polygon[:4], dtype=np.float32)

    bbox = getattr(region, "bbox", None)
    if isinstance(bbox, list) and len(bbox) == 4:
        x1, y1, x2, y2 = bbox
        return np.asarray(
            [
                [x1, y1],
                [x2, y1],
                [x2, y2],
                [x1, y2],
            ],
            dtype=np.float32,
        )
    raise ValueError(f"Unsupported region payload for OCR runtime bridge: {region!r}")


def _region_id(region: Any, index: int) -> str:
    candidate = getattr(region, "region_id", "")
    return str(candidate) if candidate else f"seed_{index:04d}"


def get_runtime_asset_status(model_id: str, root_dir: str | Path | None = None) -> RuntimeAssetStatus:
    spec = _resolve_runtime_spec(model_id)
    if spec is None:
        return RuntimeAssetStatus(supported=False, available=False)

    try:
        wrapper = _build_runtime_wrapper(model_id, root_dir)
        storage_path = str(Path(wrapper.model_dir))
        available = bool(wrapper.is_downloaded())
    except Exception:
        storage_path = _runtime_storage_path(model_id, root_dir)
        available = False
    extra: dict[str, str] = {}
    if spec["kind"] == "detect":
        extra["runtime_segmenter_id"] = "comic-text-bubble-detector/mask"
    return RuntimeAssetStatus(
        supported=True,
        available=available,
        storage_path=storage_path,
        runtime_engine_id=spec["runtime"],
        extra=extra,
    )


def download_runtime_assets(model_id: str, root_dir: str | Path | None = None) -> RuntimeAssetStatus | None:
    spec = _resolve_runtime_spec(model_id)
    if spec is None:
        return None

    wrapper = _build_runtime_wrapper(model_id, root_dir)
    _await_sync(wrapper.download())
    return get_runtime_asset_status(model_id, root_dir)


def get_detect_runtime_ids(
    detector_id: str,
    segmenter_id: str,
    root_dir: str | Path | None = None,
) -> tuple[str, str]:
    detector_status = get_runtime_asset_status(detector_id, root_dir)
    if not detector_status.available:
        return "heuristic-grouping", "pil-mask-rasterizer"
    return (
        detector_status.runtime_engine_id,
        detector_status.extra.get("runtime_segmenter_id", segmenter_id),
    )


def get_ocr_runtime_id(engine_id: str, root_dir: str | Path | None = None) -> str:
    status = get_runtime_asset_status(engine_id, root_dir)
    if not status.available:
        return "rapidocr-onnxruntime"
    return status.runtime_engine_id


def get_inpaint_runtime_id(engine_id: str, root_dir: str | Path | None = None) -> str:
    status = get_runtime_asset_status(engine_id, root_dir)
    if not status.available:
        return "opencv-telea/pil-fallback"
    return status.runtime_engine_id


def run_detect_runtime(
    image_path: str | Path,
    detector_id: str,
    *,
    root_dir: str | Path | None = None,
    device: str | None = None,
) -> RuntimeDetectOutput | None:
    if detector_id not in _DETECT_RUNTIME_SPECS:
        return None

    wrapper = _ensure_loaded(detector_id, root_dir=root_dir, device=device)
    import cv2

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Unable to read image for detect runtime: {image_path}")

    textlines, raw_mask, refined_mask = _await_sync(
        wrapper.detect(
            image,
            detect_size=1536,
            text_threshold=0.3,
            box_threshold=0.6,
            unclip_ratio=2.0,
            verbose=False,
        )
    )
    segment_mask = refined_mask if isinstance(refined_mask, np.ndarray) else raw_mask
    segment_mask = _normalize_mask_array(segment_mask)

    text_regions: list[dict[str, object]] = []
    for index, quad in enumerate(textlines, start=1):
        pts = np.asarray(getattr(quad, "pts"), dtype=np.float32)
        bbox = [
            int(np.min(pts[:, 0])),
            int(np.min(pts[:, 1])),
            int(np.max(pts[:, 0])),
            int(np.max(pts[:, 1])),
        ]
        text_regions.append(
            {
                "region_id": f"region_{index:04d}",
                "kind": "text",
                "bbox": bbox,
                "polygon": pts.tolist(),
                "score": float(getattr(quad, "prob", 1.0) or 0.0),
            }
        )

    runtime_detector_id = f"comic-text-bubble-detector/{_runtime_backend_suffix(wrapper)}"
    runtime_segmenter_id = "comic-text-bubble-detector/mask"
    return RuntimeDetectOutput(
        runtime_detector_id=runtime_detector_id,
        runtime_segmenter_id=runtime_segmenter_id,
        text_regions=text_regions,
        segment_mask=segment_mask,
    )


def run_region_ocr_runtime(
    image_path: str | Path,
    engine_id: str,
    regions: list[Any],
    *,
    root_dir: str | Path | None = None,
    device: str | None = None,
) -> RuntimeOcrOutput | None:
    if engine_id not in _OCR_RUNTIME_SPECS:
        return None
    if not regions:
        return RuntimeOcrOutput(runtime_engine_id=get_ocr_runtime_id(engine_id, root_dir), seeds=[])

    wrapper = _ensure_loaded(engine_id, root_dir=root_dir, device=device)
    _ensure_upstream_import_path()
    config_module = importlib.import_module("manga_translator.config")
    utils_module = importlib.import_module("manga_translator.utils")
    OcrConfig = getattr(config_module, "OcrConfig")
    Quadrilateral = getattr(utils_module, "Quadrilateral")

    image = _load_rgb_image(image_path)
    quads = [Quadrilateral(_region_polygon(region), "", 1.0) for region in regions]
    recognized = _await_sync(wrapper.recognize(image, quads, OcrConfig(ignore_bubble=0), False))

    seeds: list[TextSeed] = []
    for index, region in enumerate(recognized, start=1):
        source_text = str(getattr(region, "text", "") or "").strip()
        if not source_text:
            continue
        pts = np.asarray(getattr(region, "pts"), dtype=np.float32)
        bbox = [
            int(np.min(pts[:, 0])),
            int(np.min(pts[:, 1])),
            int(np.max(pts[:, 0])),
            int(np.max(pts[:, 1])),
        ]
        direction = "vertical" if str(getattr(region, "direction", "h")) == "v" else "horizontal"
        seeds.append(
            TextSeed(
                seed_id=_region_id(regions[index - 1], index),
                bbox=bbox,
                polygon=pts.tolist(),
                source_text=source_text,
                confidence=float(getattr(region, "prob", 1.0) or 0.0),
                direction=direction,
            )
        )

    runtime_engine_id = f"{engine_id}/{_runtime_backend_suffix(wrapper)}"
    return RuntimeOcrOutput(runtime_engine_id=runtime_engine_id, seeds=seeds)


def run_inpaint_runtime(
    *,
    source_path: str | Path,
    segment_mask_path: str | Path,
    output_path: str | Path,
    engine_id: str,
    brush_mask_path: str | Path | None = None,
    root_dir: str | Path | None = None,
    device: str | None = None,
) -> RuntimeInpaintOutput | None:
    if engine_id not in _INPAINT_RUNTIME_SPECS:
        return None

    wrapper = _ensure_loaded(engine_id, root_dir=root_dir, device=device)
    _ensure_upstream_import_path()
    config_module = importlib.import_module("manga_translator.config")
    InpainterConfig = getattr(config_module, "InpainterConfig")

    image = _load_rgb_image(source_path)
    size = (image.shape[1], image.shape[0])
    segment_mask = _load_mask_image(segment_mask_path, size)
    brush_mask = _load_mask_image(brush_mask_path, size)
    merged_mask = ImageChops.lighter(segment_mask, brush_mask)
    merged_mask_array = np.array(merged_mask, dtype=np.uint8)
    mask_pixels = int(np.count_nonzero(merged_mask_array))

    result = _await_sync(
        wrapper.inpaint(
            image,
            merged_mask_array,
            InpainterConfig(),
            inpainting_size=max(size),
            verbose=False,
        )
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(result, dtype=np.uint8)).save(output_path, format="PNG")

    backend_suffix = _runtime_backend_suffix(wrapper)
    if engine_id == "lama-manga" and backend_suffix in {"torch-cpu", "cpu"}:
        runtime_engine_id = "lama-manga/onnx"
    else:
        runtime_engine_id = f"{engine_id}/{backend_suffix}"
    return RuntimeInpaintOutput(
        runtime_engine_id=runtime_engine_id,
        mask_pixels=mask_pixels,
    )
