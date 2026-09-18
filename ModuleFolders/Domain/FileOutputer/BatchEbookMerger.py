"""Merge only outputs produced by the current batch, using the bundled merger."""

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from ModuleFolders.Domain.FileAccessor.EpubAccessor import EpubAccessor
from ModuleFolders.Domain.FileOutputer.EbookOptions import resolve_epub_language
from ModuleFolders.Domain.FileOutputer.EbookNaming import (
    EbookIdentity, naming_enabled, render_ebook_name, safe_book_name, series_metadata_enabled, volume_range,
)

MERGE_EXTENSIONS = {
    '.pdf', '.cbz', '.cbr', '.epub', '.mobi', '.azw3', '.docx', '.txt', '.kepub', '.fb2',
    '.lit', '.lrf', '.pdb', '.pmlz', '.rb', '.rtf', '.tcr', '.txtz', '.htmlz',
}


def merge_batch_ebooks(records, output_dir, fallback_name, settings, script_path, language='zh'):
    from natsort import natsorted

    candidates = [(Path(path), identity) for path, identity in records
                  if Path(path).is_file() and Path(path).suffix.lower() in MERGE_EXTENSIONS]
    groups = {}
    for path, identity in candidates:
        key = identity.series.casefold() if settings.get('ebook_series_enabled', False) else ''
        groups.setdefault(key, []).append((path, identity))
    results = []
    for records in groups.values():
        if len(records) < 2:
            continue
        records = natsorted(records, key=lambda item: item[1].volume or item[0].name)
        volumes = [identity.volume for _, identity in records]
        known_series = len({identity.series.casefold() for _, identity in records}) == 1
        identity = EbookIdentity()
        if known_series and all(volumes):
            if len(set(volumes)) != len(volumes):
                raise ValueError('Duplicate volume numbers in the batch; collection was not created.')
            identity = EbookIdentity(records[0][1].series, volume_range(volumes))
        title = safe_book_name(fallback_name)
        if naming_enabled(settings) and identity.series:
            title = render_ebook_name(settings.get('ebook_name_template', 'X 第N卷'), identity) or title

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ainiee-merge-', dir=output_dir) as workspace:
            staging = Path(workspace)
            inputs = staging / 'input'
            inputs.mkdir()
            preserve_order = [path.name for path, _ in records] == natsorted(path.name for path, _ in records)
            staged_names = set()
            for index, (path, _) in enumerate(records, 1):
                name = path.name
                if not preserve_order or name.casefold() in staged_names:
                    name = f'{index:04d}_{name}'
                staged_names.add(name.casefold())
                staged = inputs / name
                shutil.copy2(path, staged)
            merged = staging / 'merged.epub'
            result = subprocess.run(
                [sys.executable, str(script_path), '-p', str(inputs), '-f', 'epub', '-m', 'novel',
                 '-op', str(staging), '-o', 'merged', '-t', title, '-l', language, '--auto-merge', '--AiNiee'],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
            )
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout)[-240:])
            if not merged.is_file() or not zipfile.is_zipfile(merged):
                detail = ((result.stdout or '') + '\n' + (result.stderr or '')).strip()[-3000:]
                raise RuntimeError('The ebook merger did not produce a valid EPUB file. ' + detail)
            final = output_dir / f'{title}.epub'
            counter = 2
            while final.exists():
                final = output_dir / f'{title} ({counter}).epub'
                counter += 1
            ready = staging / 'ready.epub'
            EpubAccessor().write_content(
                {}, ready, merged, metadata_title=title,
                html_language=resolve_epub_language(settings),
                layout_direction={'vertical_to_horizontal': 'horizontal', 'horizontal_to_vertical': 'vertical'}.get(settings.get('epub_layout_mode'), 'unchanged'),
                reader_font_control=bool(settings.get('epub_reader_font_control', False)),
                series_name=identity.series if series_metadata_enabled(settings) else '',
                series_volume=identity.volume,
                paragraph_preset=settings.get('epub_paragraph_preset', 'off'),
                repair_links=settings.get('epub_repair_links', False),
                optimize_images=settings.get('ebook_optimize_images', False),
                image_format=settings.get('ebook_image_format', 'preserve'),
                image_quality=settings.get('ebook_image_quality', 80),
            )
            # Exclusive creation preserves previous collections and individual volumes.
            with ready.open('rb') as source, final.open('xb') as target:
                shutil.copyfileobj(source, target)
            results.append(final)
    return results
