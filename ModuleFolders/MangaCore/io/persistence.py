from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image

from ModuleFolders.MangaCore.constants import (
    DEFAULT_LAYER_PATHS,
    DEFAULT_MASK_PATHS,
    FINAL_DIR_NAME,
    LOGS_DIR_NAME,
    PAGE_STATUS_PREPARED,
    PROJECT_DIR_NAME,
    PROJECT_STATUS_EDITABLE,
)
from ModuleFolders.MangaCore.io.blobStore import BlobStore
from ModuleFolders.MangaCore.io.importers import ImportedInput, discover_input_images
from ModuleFolders.MangaCore.io.thumbnails import generate_thumbnail
from ModuleFolders.MangaCore.project.layers import MangaLayerSet, MangaMaskSet
from ModuleFolders.MangaCore.project.manifest import MangaProjectManifest
from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.scene import MangaScene, ScenePageRef
from ModuleFolders.MangaCore.project.session import MangaProjectSession


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> object:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_image(source: Path, target: Path) -> tuple[int, int]:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.save(target, format="PNG")
        return image.size


def _create_blank_mask(target: Path, size: tuple[int, int]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", size, 0).save(target, format="PNG")


class MangaProjectPersistence:
    """Create, load, and save MangaCore projects on disk."""

    @classmethod
    def create_project_from_input(
        cls,
        input_path: str | Path,
        output_root: str | Path,
        config_snapshot: dict[str, object] | None = None,
        profile_name: str = "default",
        rules_profile_name: str = "default",
        source_lang: str = "ja",
        target_lang: str = "zh_cn",
    ) -> MangaProjectSession:
        imported = discover_input_images(input_path)
        output_root_path = Path(output_root)
        project_root = output_root_path / PROJECT_DIR_NAME
        final_root = output_root_path / FINAL_DIR_NAME
        blob_store = BlobStore(project_root)
        cls._ensure_layout(output_root_path, blob_store)

        created_at = _now_iso()
        time_token = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        project_name = Path(input_path).stem if Path(input_path).is_file() else Path(input_path).name
        manifest = MangaProjectManifest(
            project_id=f"mproj_{time_token}",
            task_id=f"task_{time_token}",
            name=project_name,
            source_type=imported.source_type,
            created_at=created_at,
            updated_at=created_at,
            source_lang=source_lang,
            target_lang=target_lang,
            profile_name=profile_name,
            rules_profile_name=rules_profile_name,
            status=PROJECT_STATUS_EDITABLE,
        )

        pages: dict[str, MangaPage] = {}
        scene_pages: list[ScenePageRef] = []

        try:
            for index, image_path in enumerate(imported.images, start=1):
                page_key = f"{index:04d}"
                page_id = f"page_{page_key}"
                page_dir = blob_store.page_dir(page_key)
                rel_page_dir = Path("pages") / page_key

                source_path = page_dir / DEFAULT_LAYER_PATHS["source"]
                inpainted_path = page_dir / DEFAULT_LAYER_PATHS["inpainted"]
                rendered_path = page_dir / DEFAULT_LAYER_PATHS["rendered"]
                overlay_path = page_dir / DEFAULT_LAYER_PATHS["overlay_text"]
                segment_mask_path = page_dir / DEFAULT_MASK_PATHS["segment"]
                bubble_mask_path = page_dir / DEFAULT_MASK_PATHS["bubble"]
                brush_mask_path = page_dir / DEFAULT_MASK_PATHS["brush"]

                width, height = _normalize_image(image_path, source_path)
                shutil.copy2(source_path, inpainted_path)
                shutil.copy2(source_path, rendered_path)
                _create_blank_mask(segment_mask_path, (width, height))
                _create_blank_mask(bubble_mask_path, (width, height))
                _create_blank_mask(brush_mask_path, (width, height))
                _write_json(overlay_path, {"blocks": []})

                thumbnail_path = blob_store.thumbs_dir() / f"{page_key}.webp"
                generate_thumbnail(source_path, thumbnail_path)

                final_page_path = final_root / "pages" / f"{page_key}.png"
                final_page_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(rendered_path, final_page_path)

                page = MangaPage(
                    page_id=page_id,
                    index=index,
                    width=width,
                    height=height,
                    status=PAGE_STATUS_PREPARED,
                    thumbnail_path=cls._relative_to_project(project_root, thumbnail_path),
                    layers=MangaLayerSet(
                        source=cls._relative_to_project(project_root, source_path),
                        overlay_text=cls._relative_to_project(project_root, overlay_path),
                        inpainted=cls._relative_to_project(project_root, inpainted_path),
                        rendered=cls._relative_to_project(project_root, rendered_path),
                    ),
                    masks=MangaMaskSet(
                        segment=cls._relative_to_project(project_root, segment_mask_path),
                        bubble=cls._relative_to_project(project_root, bubble_mask_path),
                        brush=cls._relative_to_project(project_root, brush_mask_path),
                    ),
                )
                pages[page_id] = page
                scene_pages.append(
                    ScenePageRef(
                        page_id=page.page_id,
                        index=page.index,
                        status=page.status,
                        thumbnail_path=page.thumbnail_path,
                    )
                )

            manifest.page_count = len(pages)
            scene = MangaScene(
                project_id=manifest.project_id,
                current_page_id=scene_pages[0].page_id if scene_pages else "",
                pages=scene_pages,
            )
            session = MangaProjectSession(
                project_path=project_root,
                output_root=output_root_path,
                manifest=manifest,
                scene=scene,
                pages=pages,
                config_snapshot=config_snapshot or {},
            )
            cls.save_session(session)
            return session
        finally:
            if imported.temp_root and imported.temp_root.exists():
                shutil.rmtree(imported.temp_root, ignore_errors=True)

    @classmethod
    def load_project(cls, project_path: str | Path) -> MangaProjectSession:
        project_root = Path(project_path)
        output_root = project_root.parent
        manifest = MangaProjectManifest.from_dict(_read_json(project_root / "manifest.json"))
        scene = MangaScene.from_dict(_read_json(project_root / "scene.json"))
        config_snapshot = _read_json(project_root / "configSnapshot.json") if (project_root / "configSnapshot.json").exists() else {}
        pages: dict[str, MangaPage] = {}

        for page_ref in scene.pages:
            page_key = f"{page_ref.index:04d}"
            page_dir = project_root / "pages" / page_key
            meta = _read_json(page_dir / "pageMeta.json")
            blocks = _read_json(page_dir / "blocks.json")
            page = MangaPage.from_disk(
                meta=meta if isinstance(meta, dict) else {},
                blocks=blocks if isinstance(blocks, list) else [],
                thumbnail_path=page_ref.thumbnail_path,
            )
            pages[page.page_id] = page

        return MangaProjectSession(
            project_path=project_root,
            output_root=output_root,
            manifest=manifest,
            scene=scene,
            pages=pages,
            config_snapshot=dict(config_snapshot) if isinstance(config_snapshot, dict) else {},
        )

    @classmethod
    def save_session(cls, session: MangaProjectSession) -> None:
        project_root = session.project_path
        cls.sync_scene(session)
        _write_json(project_root / "manifest.json", session.manifest.to_dict())
        _write_json(project_root / "scene.json", session.scene.to_dict())
        _write_json(project_root / "configSnapshot.json", session.config_snapshot)
        (project_root / "historyLog.log").touch(exist_ok=True)

        for page in session.pages.values():
            cls.save_page(session, page)

    @classmethod
    def save_page(cls, session: MangaProjectSession, page: MangaPage) -> None:
        page_key = f"{page.index:04d}"
        page_dir = session.project_path / "pages" / page_key
        _write_json(page_dir / "pageMeta.json", page.to_meta_dict())
        _write_json(page_dir / "blocks.json", page.to_blocks_dict())
        overlay_path = session.project_path / page.layers.overlay_text
        _write_json(overlay_path, {"blocks": page.to_blocks_dict()})

    @classmethod
    def append_history(cls, session: MangaProjectSession, lines: list[dict[str, object]]) -> None:
        history_path = session.project_path / "historyLog.log"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(history_path, "a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    @classmethod
    def write_page_artifact(cls, session: MangaProjectSession, page: MangaPage, filename: str, payload: object) -> None:
        page_key = f"{page.index:04d}"
        page_dir = session.project_path / "pages" / page_key
        _write_json(page_dir / filename, payload)

    @classmethod
    def sync_scene(cls, session: MangaProjectSession) -> None:
        pages = sorted(session.pages.values(), key=lambda page: page.index)
        session.manifest.page_count = len(pages)
        session.scene.pages = [
            ScenePageRef(
                page_id=page.page_id,
                index=page.index,
                status=page.status,
                thumbnail_path=page.thumbnail_path,
            )
            for page in pages
        ]
        if not session.scene.current_page_id and session.scene.pages:
            session.scene.current_page_id = session.scene.pages[0].page_id

    @staticmethod
    def _ensure_layout(output_root: Path, blob_store: BlobStore) -> None:
        for path in (
            output_root / FINAL_DIR_NAME / "pages",
            output_root / FINAL_DIR_NAME / "pdf",
            output_root / FINAL_DIR_NAME / "epub",
            output_root / FINAL_DIR_NAME / "cbz",
            output_root / FINAL_DIR_NAME / "zip",
            output_root / FINAL_DIR_NAME / "rar",
            output_root / LOGS_DIR_NAME,
            blob_store.project_root,
            blob_store.project_root / "pages",
            blob_store.thumbs_dir(),
            blob_store.cache_dir(),
            blob_store.exports_dir(),
        ):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _relative_to_project(project_root: Path, path: Path) -> str:
        return path.relative_to(project_root).as_posix()
