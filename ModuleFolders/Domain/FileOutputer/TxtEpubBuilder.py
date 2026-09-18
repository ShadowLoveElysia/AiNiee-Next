"""Create a companion EPUB from exported TXT using conservative heading recognition."""

import html
import re
import tempfile
from pathlib import Path
from uuid import uuid4

from ModuleFolders.Domain.FileAccessor.EpubAccessor import EpubAccessor
from ModuleFolders.Domain.FileOutputer.EbookNaming import identify_ebook, output_book_name, series_metadata_enabled
from ModuleFolders.Domain.FileOutputer.EbookOptions import language_tag, resolve_epub_language


CHAPTER_HEADING = re.compile(
    r'^(?:第\s*[0-9０-９零〇一二三四五六七八九十百千万两壹贰叁肆伍陆柒捌玖拾佰仟]+\s*[章回节節幕篇卷巻].*'
    r'|(?:chapter|part|book)\s+(?:\d+|[ivxlcdm]+)(?:\s|[.:：-]|$).*'
    r'|序章|序言|前言|楔子|终章|終章|尾声|尾聲|后记|後記|あとがき|プロローグ|エピローグ|prologue|epilogue)$',
    re.IGNORECASE,
)


def split_chapters(text, fallback_title):
    chapters = []
    title, lines = fallback_title, []
    found_heading = False
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) <= 80 and CHAPTER_HEADING.fullmatch(stripped):
            if found_heading or any(part.strip() for part in lines):
                chapters.append((title, lines))
            title, lines, found_heading = stripped, [], True
        else:
            lines.append(line)
    if found_heading or lines or not chapters:
        chapters.append((title, lines))
    return chapters


def build_txt_epub(text, source_path, destination, settings):
    from ebooklib import epub

    source_path, destination = Path(source_path), Path(destination)
    identity = identify_ebook(source_path, settings.get('ebook_series_name', ''))
    title = output_book_name(source_path, settings) or source_path.stem
    language = resolve_epub_language(settings) or language_tag(settings.get('target_language', '')) or 'und'
    book = epub.EpubBook()
    book.set_identifier(str(uuid4()))
    book.set_title(title)
    book.set_language(language)
    chapters = []
    for index, (heading, lines) in enumerate(split_chapters(text, title), 1):
        chapter = epub.EpubHtml(title=heading, file_name=f'chapter_{index:04d}.xhtml', lang=language)
        body = ''.join(f'<p>{html.escape(line)}</p>' if line.strip() else '<p><br/></p>' for line in lines)
        chapter.content = f'<html><body><h1>{html.escape(heading)}</h1>{body}</body></html>'
        book.add_item(chapter)
        chapters.append(chapter)
    book.toc = chapters
    book.spine = ['nav', *chapters]
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())
    with tempfile.TemporaryDirectory(prefix='ainiee-txt-', dir=destination.parent) as folder:
        draft = Path(folder) / 'draft.epub'
        if not epub.write_epub(str(draft), book, {'raise_exceptions': True}):
            raise RuntimeError('Unable to create TXT companion EPUB.')
        EpubAccessor().write_content(
            {}, destination, draft, html_language=language, metadata_title=title,
            layout_direction={'vertical_to_horizontal': 'horizontal', 'horizontal_to_vertical': 'vertical'}.get(settings.get('epub_layout_mode'), 'unchanged'),
            reader_font_control=settings.get('epub_reader_font_control', False),
            series_name=identity.series if series_metadata_enabled(settings) else '', series_volume=identity.volume,
            paragraph_preset=settings.get('epub_paragraph_preset', 'off'),
            repair_links=settings.get('epub_repair_links', False),
        )
