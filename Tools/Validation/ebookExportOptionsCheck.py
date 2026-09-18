"""Regression checks for optional ebook export transformations."""

import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup
from PIL import Image

from ebookUtilitiesCheck import make_epub, cache_for
from ModuleFolders.Domain.FileAccessor.EpubAccessor import EpubAccessor
from ModuleFolders.Domain.FileAccessor.EpubPostProcessor import paragraph_preset, repair_local_links
from ModuleFolders.Domain.FileOutputer.BaseWriter import OutputConfig, TranslationOutputConfig
from ModuleFolders.Domain.FileOutputer.DirectoryWriter import DirectoryWriter
from ModuleFolders.Domain.FileOutputer.EbookOptions import EXPORT_DEFAULTS, resolve_epub_language
from ModuleFolders.Domain.FileOutputer.EpubWriter import EpubWriter
from ModuleFolders.Domain.FileOutputer.TxtEpubBuilder import build_txt_epub, split_chapters
from ModuleFolders.Domain.FileOutputer.TxtWriter import TxtWriter
from ModuleFolders.Infrastructure.Cache.CacheFile import CacheFile
from ModuleFolders.Infrastructure.Cache.CacheItem import CacheItem, TranslationStatus
from ModuleFolders.Infrastructure.Cache.CacheProject import CacheProject
from ModuleFolders.Infrastructure.TaskConfig.ConfigRegistry import CONFIG_REGISTRY
from ModuleFolders.Infrastructure.TaskConfig.SettingsRenderer import SettingsMenuBuilder, choice_label


def image_book(path):
    documents = make_epub(path)
    picture = Image.new('RGB', (480, 640))
    picture.putdata([((x * 13) % 256, (x * 7) % 256, (x // 480) % 256) for x in range(480 * 640)])
    stream = io.BytesIO()
    picture.save(stream, 'PNG', compress_level=0)
    documents['OEBPS/Images/cover.png'] = stream.getvalue()
    documents['OEBPS/book.opf'] = documents['OEBPS/book.opf'].replace(
        '</manifest>', '<item id="cover" href="Images/cover.png" media-type="image/png" properties="cover-image"/></manifest>')
    documents['OEBPS/chapter.xhtml'] = documents['OEBPS/chapter.xhtml'].replace(
        '</body>', '<img src="Images/cover.png" srcset="Images/cover.png 1x"/><svg xmlns:xlink="http://www.w3.org/1999/xlink"><image xlink:href="Images/cover.png"/></svg></body>')
    documents['OEBPS/style.css'] += ' .cover {background-image:url("Images/cover.png");}'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in documents.items():
            archive.writestr(name, content)
    return documents


class ExportSettingsTests(unittest.TestCase):
    def test_defaults_and_menu_categories(self):
        output_keys = {'ebook_optimize_images', 'ebook_image_format', 'ebook_image_quality', 'epub_language_follow_source'}
        for key, value in EXPORT_DEFAULTS.items():
            item = CONFIG_REGISTRY[key]
            self.assertEqual(item.default, value)
            self.assertEqual(item.category, 'output' if key in output_keys else 'utility')
        for path in (ROOT / 'I18N').glob('*.json'):
            locale = json.loads(path.read_text(encoding='utf-8'))
            translation = SimpleNamespace(get=lambda key: locale.get(key, key))
            menu = SettingsMenuBuilder({}, translation)
            menu.build_menu_items()
            menu.render_table()
            for key in EXPORT_DEFAULTS:
                self.assertIn('setting_' + key, locale)
                self.assertIn('setting_' + key + '_desc', locale)
                for choice in CONFIG_REGISTRY[key].choices:
                    self.assertNotEqual(choice_label(key, choice, translation), choice)

    def test_follow_source_preserves_explicit_and_disabled_modes(self):
        settings = {'interface_language': 'ja', 'target_language': 'Chinese_Traditional'}
        self.assertEqual(resolve_epub_language(settings), 'ja')
        settings['epub_language_follow_source'] = 'target'
        self.assertEqual(resolve_epub_language(settings), 'zh-TW')
        for value, expected in [('English', 'en'), ('French', 'fr'), ('zh_Hans', 'zh-Hans'), ('pt-BR', 'pt-BR')]:
            self.assertEqual(resolve_epub_language({**settings, 'target_language': value}), expected)
        self.assertEqual(resolve_epub_language({**settings, 'epub_language_update_mode': 'ko'}), 'ko')
        self.assertEqual(resolve_epub_language({**settings, 'epub_language_update_mode': 'disabled'}), '')
        self.assertEqual(resolve_epub_language({**settings, 'target_language': '<invalid>'}), '')

    def test_language_settings_reach_real_writer(self):
        from ModuleFolders.Domain.FileOutputer.FileOutputer import FileOutputer
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'Book.epub'
            make_epub(source)
            writer = FileOutputer.__new__(FileOutputer)
            writer.writer_factory_dict = {'Epub': EpubWriter}
            project = CacheProject(project_type='Epub', files={source.name: cache_for(source)})
            writer.output_translated_content(project, str(Path(folder) / 'out'), str(source), {},
                                             SimpleNamespace(epub_language_follow_source='target', target_language='English',
                                                             interface_language='ja', japanese_text_quote_style_switch=False))
            with zipfile.ZipFile(writer.last_output_files[0][0]) as archive:
                self.assertEqual(BeautifulSoup(archive.read('OEBPS/book.opf'), 'xml').find('language').get_text(), 'en')
                self.assertEqual(BeautifulSoup(archive.read('OEBPS/chapter.xhtml'), 'xml').html['lang'], 'en')

    def test_bilingual_blocks_keep_source_and_target_languages(self):
        writer = EpubWriter(OutputConfig(epub_language_follow_source='target', target_language='English', source_language='Japanese'))
        fragment = BeautifulSoup(writer._rebuild_bilingual_tag('<p>日本語</p>', 'English'), 'html.parser')
        self.assertEqual([node['lang'] for node in fragment.find_all('p')], ['en', 'ja'])


class ParagraphAndLinkTests(unittest.TestCase):
    def test_paragraph_presets_are_optional_and_preserve_special_content(self):
        content = '<html><body><h1>Title</h1><p style="color:red;text-indent:9em!important;">　Body</p><blockquote><p>Quote</p></blockquote><p class="poem">Poem</p><p>* * *</p><p><img src="x.png"/></p></body></html>'
        self.assertEqual(paragraph_preset(content, 'off'), content)
        for preset in ('indent', 'spaced', 'reader'):
            output = paragraph_preset(content, preset)
            doc = BeautifulSoup(output, 'xml')
            self.assertIn('color:red', doc.p['style'])
            self.assertEqual(doc.h1.get_text(), 'Title')
            self.assertNotIn('style', doc.blockquote.p.attrs)
            self.assertNotIn('style', doc.find('p', class_='poem').attrs)
            self.assertEqual(paragraph_preset(output, preset), output)

    def test_local_paths_and_anchors_are_repaired_only_when_unique(self):
        documents = {
            'Text/Chapter One.xhtml': '<html><body><h1 id="Section">Heading</h1></body></html>',
            'Nav/nav.xhtml': '<html><nav><a href="../text/chapter%20one.xhtml#section">Fix</a><a href="../Text/absent.xhtml">Missing</a><a href="https://example.invalid/X">External</a></nav></html>',
        }
        output = repair_local_links(documents, set(documents))
        links = BeautifulSoup(output['Nav/nav.xhtml'], 'xml').find_all('a')
        self.assertEqual(links[0]['href'], '../Text/Chapter%20One.xhtml#Section')
        self.assertEqual(links[1]['href'], '../Text/absent.xhtml')
        self.assertEqual(links[2]['href'], 'https://example.invalid/X')
        ambiguous = {**documents, 'Text/chapter one.xhtml': '<html/>'}
        unresolved = repair_local_links(ambiguous, set(ambiguous))
        self.assertNotIn('Nav/nav.xhtml', unresolved)

    def test_navigation_manifest_declarations(self):
        with tempfile.TemporaryDirectory() as folder:
            source, destination = Path(folder) / 'source.epub', Path(folder) / 'output.epub'
            documents = make_epub(source)
            opf = documents['OEBPS/book.opf'].replace(' properties="nav"', '').replace('toc="ncx"', 'toc="missing"')
            EpubAccessor().write_content({'OEBPS/book.opf': opf}, destination, source, repair_links=True)
            with zipfile.ZipFile(destination) as archive:
                doc = BeautifulSoup(archive.read('OEBPS/book.opf'), 'xml')
                self.assertEqual(doc.spine['toc'], 'ncx')
                self.assertEqual(doc.find('item', id='nav')['properties'], 'nav')


class ImageOptimizationTests(unittest.TestCase):
    def test_jpeg_compression_and_webp_name_collision(self):
        from ModuleFolders.Domain.FileAccessor.EpubPostProcessor import optimize_image
        picture = Image.effect_noise((256, 256), 60).convert('RGB')
        stream = io.BytesIO()
        picture.save(stream, 'JPEG', quality=100)
        compressed, format_name = optimize_image(stream.getvalue(), 'preserve', 50)
        self.assertEqual(format_name, 'JPEG')
        self.assertLess(len(compressed), len(stream.getvalue()))
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'source.epub', Path(folder) / 'output.epub'
            documents = image_book(source)
            with zipfile.ZipFile(source, 'a') as archive:
                archive.writestr('OEBPS/Images/cover.webp', b'existing-resource')
            EpubAccessor().write_content({}, output, source, optimize_images=True, image_format='webp')
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read('OEBPS/Images/cover.webp'), b'existing-resource')
                self.assertEqual(archive.read('OEBPS/Images/cover.png'), documents['OEBPS/Images/cover.png'])

    def test_off_preserves_image_bytes_and_preserve_mode_keeps_format(self):
        with tempfile.TemporaryDirectory() as folder:
            source, unchanged, optimized = [Path(folder) / name for name in ('source.epub', 'off.epub', 'on.epub')]
            documents = image_book(source)
            digest = hashlib.sha256(source.read_bytes()).digest()
            EpubAccessor().write_content({}, unchanged, source)
            EpubAccessor().write_content({}, optimized, source, optimize_images=True)
            with zipfile.ZipFile(unchanged) as archive:
                self.assertEqual(archive.read('OEBPS/Images/cover.png'), documents['OEBPS/Images/cover.png'])
            with zipfile.ZipFile(optimized) as archive:
                result = archive.read('OEBPS/Images/cover.png')
                self.assertEqual(archive.read('OEBPS/style.css').decode(), documents['OEBPS/style.css'])
                self.assertLess(len(result), len(documents['OEBPS/Images/cover.png']))
                self.assertEqual(Image.open(io.BytesIO(result)).format, 'PNG')
                self.assertEqual(Image.open(io.BytesIO(result)).tobytes(), Image.open(io.BytesIO(documents['OEBPS/Images/cover.png'])).tobytes())
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), digest)

    def test_webp_updates_cover_html_svg_srcset_and_css(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'source.epub', Path(folder) / 'webp.epub'
            image_book(source)
            EpubAccessor().write_content({}, output, source, optimize_images=True, image_format='webp', image_quality=75)
            with zipfile.ZipFile(output) as archive:
                self.assertNotIn('OEBPS/Images/cover.png', archive.namelist())
                self.assertEqual(Image.open(io.BytesIO(archive.read('OEBPS/Images/cover.webp'))).format, 'WEBP')
                opf = BeautifulSoup(archive.read('OEBPS/book.opf'), 'xml')
                cover = opf.find('item', id='cover')
                self.assertEqual(cover['href'], 'Images/cover.webp')
                self.assertEqual(cover['media-type'], 'image/webp')
                self.assertEqual(cover['properties'], 'cover-image')
                page = BeautifulSoup(archive.read('OEBPS/chapter.xhtml'), 'xml')
                self.assertEqual(page.img['srcset'], 'Images/cover.webp 1x')
                self.assertEqual(page.find('image')['xlink:href'], 'Images/cover.webp')
                self.assertIn('Images/cover.webp', archive.read('OEBPS/style.css').decode())
                self.assertEqual(archive.read('OEBPS/untouched.bin'), b'preserve-resource')

    def test_invalid_or_animated_images_are_preserved(self):
        from ModuleFolders.Domain.FileAccessor.EpubPostProcessor import optimize_image
        self.assertIsNone(optimize_image(b'not an image', 'webp', 80))
        first, second = Image.new('RGBA', (16, 16), 'red'), Image.new('RGBA', (16, 16), 'blue')
        data = io.BytesIO()
        first.save(data, 'PNG', save_all=True, append_images=[second], duration=100, loop=0)
        self.assertIsNone(optimize_image(data.getvalue(), 'webp', 80))


class TxtEpubTests(unittest.TestCase):
    def test_chapter_recognition_keeps_preface_and_no_heading_content(self):
        text = 'Preface < & >\n\n第一章开始\nText\n第二章 继续\nMore\nChapter 3: End\nLast'
        parts = split_chapters(text, 'Book')
        self.assertEqual([title for title, _ in parts], ['Book', '第一章开始', '第二章 继续', 'Chapter 3: End'])
        self.assertEqual(split_chapters('Only one\nparagraph', 'Book'), [('Book', ['Only one', 'paragraph'])])
        self.assertEqual(split_chapters('第十章', 'Book'), [('第十章', [])])
        from ModuleFolders.Domain.FileOutputer.EbookNaming import identify_ebook
        self.assertEqual(identify_ebook('Book 1.txt').series, 'Book')

    def test_generated_epub_has_navigation_and_escaped_text(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'Book.epub'
            build_txt_epub('Foreword <&>\n第一章 开始\nA < B & C\n第二章 继续\nD', 'Book 1.txt', destination,
                           {'ebook_series_enabled': True, 'epub_language_follow_source': 'target', 'target_language': 'English'})
            with zipfile.ZipFile(destination) as archive:
                chapter_names = [name for name in archive.namelist() if '/chapter_' in name]
                self.assertEqual(len(chapter_names), 3)
                content = '\n'.join(archive.read(name).decode() for name in chapter_names)
                self.assertIn('A &lt; B &amp; C', content)
                opf = BeautifulSoup(archive.read('EPUB/content.opf'), 'xml')
                self.assertEqual(opf.find('language').get_text(), 'en')
                self.assertEqual(opf.find('title').get_text(), 'Book 第1卷')
                self.assertIn('第二章', archive.read('EPUB/nav.xhtml').decode())

    def test_directory_option_keeps_txt_and_does_not_overwrite_epub(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'Book 1.txt'
            source.write_text('source', encoding='utf-8')
            cache = CacheFile(storage_path=source.name, file_project_type='Txt', items=[
                CacheItem(source_text='source', translated_text='第一章\n内容', translation_status=TranslationStatus.TRANSLATED, extra={'line_break': 0}),
            ])
            project = CacheProject(project_type='Txt', files={source.name: cache})
            config = OutputConfig(translated_config=TranslationOutputConfig(True, ''), txt_generate_epub=False)
            writer = DirectoryWriter(lambda: TxtWriter(config))
            out = root / 'out'
            records = writer.write_translation_directory(project, root, out)
            self.assertEqual(records[0][0].suffix, '.txt')
            self.assertFalse(list(out.glob('*.epub')))
            existing = out / 'Book 1.epub'
            existing.write_bytes(b'keep-existing')
            config.txt_generate_epub = True
            records = writer.write_translation_directory(project, root, out)
            self.assertEqual(records[0][0].name, 'Book 1 (2).epub')
            self.assertEqual(existing.read_bytes(), b'keep-existing')
            self.assertTrue((out / source.name).exists())


if __name__ == '__main__':
    unittest.main()
