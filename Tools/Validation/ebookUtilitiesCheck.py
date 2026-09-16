import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup

from ModuleFolders.Domain.FileAccessor.EpubAccessor import EpubAccessor
from ModuleFolders.Domain.FileAccessor.EpubUtilities import reader_font_css, update_series_metadata
from ModuleFolders.Domain.FileOutputer.BaseWriter import OutputConfig, TranslationOutputConfig
from ModuleFolders.Domain.FileOutputer.BatchEbookMerger import merge_batch_ebooks
from ModuleFolders.Domain.FileOutputer.DirectoryWriter import DirectoryWriter
from ModuleFolders.Domain.FileOutputer.EbookNaming import (
    EbookIdentity, UTILITY_DEFAULTS, identify_ebook, output_book_name, render_ebook_name, volume_range,
)
from ModuleFolders.Domain.FileOutputer.EpubWriter import EpubWriter
from ModuleFolders.Infrastructure.Cache.CacheFile import CacheFile
from ModuleFolders.Infrastructure.Cache.CacheItem import CacheItem, TranslationStatus
from ModuleFolders.Infrastructure.Cache.CacheProject import CacheProject, ProjectType
from ModuleFolders.Infrastructure.TaskConfig.ConfigRegistry import CONFIG_REGISTRY
from ModuleFolders.Infrastructure.TaskConfig.SettingsRenderer import SettingsMenuBuilder


HEADING = '<h1 id="chapter">Original chapter</h1>'


def make_epub(path, chapter_title='Original chapter'):
    heading = HEADING.replace('Original chapter', chapter_title)
    documents = {
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'OEBPS/book.opf': '''<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">test-book</dc:identifier><dc:title>Original book</dc:title><dc:language>ja</dc:language><dc:creator>Author</dc:creator><meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/><item id="css" href="style.css" media-type="text/css"/></manifest><spine toc="ncx"><itemref idref="chapter"/></spine></package>''',
        'OEBPS/chapter.xhtml': f'''<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>Original page</title><link rel="stylesheet" href="style.css"/><style>p {{ font-size:18px; margin:1em; }}</style></head><body>{heading}<p style="font-family:Old; font-size:18px; font-weight:bold">Original paragraph</p><h2 id="untranslated">Untouched heading</h2></body></html>''',
        'OEBPS/nav.xhtml': '''<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml#chapter">Original chapter</a><ol><li><a href="chapter.xhtml#untranslated">Untouched heading</a></li><li><a href="chapter.xhtml#missing">Missing anchor</a></li></ol></li></ol></nav></body></html>''',
        'OEBPS/toc.ncx': '''<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta name="dtb:uid" content="test-book"/></head><docTitle><text>Original book</text></docTitle><navMap><navPoint id="point" playOrder="1"><navLabel><text>Original chapter</text></navLabel><content src="chapter.xhtml#chapter"/><navPoint id="child" playOrder="2"><navLabel><text>Untouched heading</text></navLabel><content src="chapter.xhtml#untranslated"/></navPoint></navPoint></navMap></ncx>''',
        'OEBPS/style.css': 'body {font-family:Old; font-size:18px; color:#222;} h1{font-weight:bold} img{max-width:100%}',
        'OEBPS/untouched.bin': b'preserve-resource',
    }
    with zipfile.ZipFile(path, 'w') as archive:
        for name, value in documents.items():
            archive.writestr(name, value)
    return documents


def cache_for(path):
    documents = EpubAccessor().read_content(path)
    item_id = next(item_id for item_id, name, _ in documents if name == 'OEBPS/chapter.xhtml')
    return CacheFile(storage_path=path.name, file_project_type=ProjectType.EPUB, items=[
        CacheItem(source_text='Original chapter', translated_text='译后章节',
                  translation_status=TranslationStatus.TRANSLATED,
                  extra={'item_id': item_id, 'original_html': HEADING}),
    ])


class EbookNamingTests(unittest.TestCase):
    def test_master_and_independent_subswitches(self):
        from ModuleFolders.Domain.FileOutputer.EbookNaming import naming_enabled, series_metadata_enabled
        disabled = {'ebook_series_enabled': False, 'ebook_fill_series_metadata': True, 'ebook_apply_name_template': True}
        self.assertFalse(naming_enabled(disabled))
        self.assertFalse(series_metadata_enabled(disabled))
        metadata_only = {**disabled, 'ebook_series_enabled': True, 'ebook_apply_name_template': False}
        self.assertTrue(series_metadata_enabled(metadata_only))
        self.assertFalse(naming_enabled(metadata_only))
        naming_only = {**disabled, 'ebook_series_enabled': True, 'ebook_fill_series_metadata': False}
        self.assertTrue(naming_enabled(naming_only))
        self.assertFalse(series_metadata_enabled(naming_only))

    def test_single_and_merged_templates(self):
        for name, volume in [('作品 第十二卷.epub', '12'), ('作品 ０２.epub', '2'),
                             ('作品 Vol. 3.epub', '3'), ('作品(004).epub', '4')]:
            identity = identify_ebook(name)
            self.assertEqual(identity, EbookIdentity('作品', volume))
        self.assertEqual(identify_ebook(Path('作品') / '01.epub'), EbookIdentity('作品', '1'))
        settings = {'ebook_series_enabled': True, 'ebook_name_template': 'X 第N卷'}
        self.assertEqual(output_book_name('作品 01.epub', settings), '作品 第1卷')
        self.assertEqual(render_ebook_name('X N', EbookIdentity('无职转生', '1-7')), '无职转生 1-7')
        self.assertEqual(render_ebook_name('X N', EbookIdentity('NEXT', '1')), 'NEXT 1')
        self.assertEqual(volume_range(['7', '1', '3', '2', '5', '6']), '1-3,5-7')
        self.assertEqual(output_book_name('没有卷号.epub', settings), '')
        self.assertEqual(output_book_name('作品 1.srt', settings), '')
        self.assertEqual(output_book_name('作品 1.epub', {**settings, 'ebook_series_enabled': False}), '')
        with self.assertRaises(ValueError):
            render_ebook_name('../N', EbookIdentity('Book', '1'))

    def test_all_settings_and_locales(self):
        keys = [*UTILITY_DEFAULTS, 'enable_batch_auto_merge_ebook']
        for key in keys:
            self.assertEqual(CONFIG_REGISTRY[key].category, 'utility')
        self.assertTrue(CONFIG_REGISTRY['epub_sync_chapter_titles'].default)
        self.assertFalse(CONFIG_REGISTRY['enable_batch_auto_merge_ebook'].default)
        for path in (ROOT / 'I18N').glob('*.json'):
            locale = json.loads(path.read_text(encoding='utf-8'))
            for key in keys:
                self.assertTrue(locale['setting_' + key])
                self.assertTrue(locale['setting_' + key + '_desc'])
            class Locale:
                def get(self, key):
                    return locale.get(key, key)
            menu = SettingsMenuBuilder({}, Locale())
            rows = menu.build_menu_items()
            self.assertTrue(all(row[3] == 'label_category_utility' for row in rows if row[1] in keys))
            visible = {row[1] for row in rows}
            self.assertTrue({'ebook_series_enabled', 'ebook_series_settings', 'enable_batch_auto_merge_ebook'} <= visible)
            self.assertNotIn('ebook_name_template', visible)
            menu.render_table()
            subrows = menu.build_menu_items(submenu='ebook_series_settings')
            self.assertEqual({row[1] for row in subrows}, {
                'ebook_fill_series_metadata', 'ebook_series_name', 'ebook_apply_name_template', 'ebook_name_template',
            })
            menu.render_table()

    def test_submenu_saves_flat_settings_without_touching_master_or_merge(self):
        from ModuleFolders.UserInterface.SettingsMenu import SettingsMenu
        locale = json.loads((ROOT / 'I18N' / 'zh_CN.json').read_text(encoding='utf-8'))
        host = SimpleNamespace(config={'ebook_series_enabled': False, 'enable_batch_auto_merge_ebook': True},
                               i18n=SimpleNamespace(get=lambda key: locale.get(key, key)),
                               display_banner=Mock(), save_config=Mock())
        with patch('ModuleFolders.UserInterface.SettingsMenu.IntPrompt.ask', side_effect=[2, 4, 0]), patch(
            'ModuleFolders.Infrastructure.TaskConfig.SettingsRenderer.Prompt.ask', side_effect=['无职转生', 'X N']
        ), patch('ModuleFolders.UserInterface.SettingsMenu.console'):
            SettingsMenu(host)._show_ebook_series_settings()
        self.assertEqual(host.config['ebook_series_name'], '无职转生')
        self.assertEqual(host.config['ebook_name_template'], 'X N')
        self.assertFalse(host.config['ebook_series_enabled'])
        self.assertTrue(host.config['enable_batch_auto_merge_ebook'])
        self.assertEqual(host.save_config.call_count, 2)


class EpubUtilityTests(unittest.TestCase):
    def test_cache_only_export_passes_utilities_and_calls_batch_hook(self):
        from ModuleFolders.Domain.FileOutputer.FileOutputer import FileOutputer
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.UserInterface.ExportFlow import ExportFlow
        with tempfile.TemporaryDirectory() as folder:
            source_dir = Path(folder) / 'books'
            source_dir.mkdir()
            source = source_dir / '无职转生 01.epub'
            make_epub(source)
            cache = cache_for(source)
            project = CacheProject(project_type='Epub', files={cache.storage_path: cache})
            writer = FileOutputer.__new__(FileOutputer)
            writer.writer_factory_dict = {'Epub': EpubWriter}
            writer.last_output_files = []
            settings = {**UTILITY_DEFAULTS, 'ebook_series_enabled': True, 'epub_reader_font_control': True,
                        'enable_batch_auto_merge_ebook': True, 'output_filename_suffix': ''}
            host = SimpleNamespace(config=settings, cache_manager=Mock(), file_outputer=writer,
                                   task_executor=SimpleNamespace(config=TaskConfig()),
                                   i18n=SimpleNamespace(get=lambda key: key), _auto_merge_batch_ebooks=Mock())
            flow = ExportFlow(host)
            with patch.object(flow, '_maybe_switch_to_single_file', return_value=str(source_dir)), patch.object(
                flow, '_resolve_cache_path', return_value='synthetic-cache'
            ), patch('ModuleFolders.Infrastructure.Cache.CacheManager.CacheManager.read_from_file', return_value=project):
                flow.run_export_only(str(source_dir), non_interactive=True)
            self.assertEqual(len(writer.last_output_files), 1)
            result = writer.last_output_files[0][0]
            self.assertEqual(result.name, '无职转生 第1卷.epub')
            with zipfile.ZipFile(result) as archive:
                self.assertIn('译后章节', archive.read('OEBPS/nav.xhtml').decode())
                self.assertNotIn('font-size', archive.read('OEBPS/style.css').decode())
            host._auto_merge_batch_ebooks.assert_called_once()

    def test_navigation_handles_encoded_paths_and_ruby(self):
        from ModuleFolders.Domain.FileAccessor.EpubUtilities import sync_navigation
        original = '<html><head><title>old</title></head><body><a id="start"/><h1><ruby>漢字<rt>かんじ</rt></ruby></h1></body></html>'
        nav = '<html xmlns:epub="http://www.idpf.org/2007/ops"><nav epub:type="toc"><a href="../Text/ch%20one.xhtml#start">old</a><a href="https://example.invalid/x">external</a></nav></html>'
        documents = {'Text/ch one.xhtml': original, 'Nav/toc.xhtml': nav}
        result = sync_navigation(documents, documents, {'Text/ch one.xhtml': [('<h1><ruby>漢字<rt>かんじ</rt></ruby></h1>', '汉字')]})
        parsed = BeautifulSoup(result['Nav/toc.xhtml'], 'xml')
        self.assertEqual([a.get_text() for a in parsed.find_all('a')], ['汉字', 'external'])
        self.assertEqual(parsed.a['href'], '../Text/ch%20one.xhtml#start')

    def test_css_preserves_urls_comments_and_emphasis(self):
        css = '''@font-face{font-family:"Embedded";src:url(font.woff)}
        @media screen {p {FONT-SIZE:16px!important; font-family:"A;B"; color:red;
        background:url("data:image/svg+xml;a{b}"); content:"font-size:100px;{}";}}
        p{font:italic bold 16px/1.5 "Old" !important; padding:1em}
        /* font-size:99px; */ img{width:100%;}'''
        result = reader_font_css(css)
        self.assertIn('@font-face{font-family:"Embedded";src:url(font.woff)}', result)
        self.assertNotIn('FONT-SIZE', result)
        self.assertNotIn('font-family:"A;B"', result)
        self.assertIn('font-style:italic !important', result)
        self.assertIn('font-weight:bold !important', result)
        self.assertIn('data:image/svg+xml;a{b}', result)
        self.assertIn('content:"font-size:100px;{}"', result)
        self.assertIn('padding:1em', result)
        self.assertEqual(reader_font_css(result), result)

    def test_writer_syncs_navigation_and_series_and_preserves_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / '无职转生 01.epub'
            original = make_epub(source)
            digest = hashlib.sha256(source.read_bytes()).digest()
            output = Path(folder) / 'out.epub'
            writer = EpubWriter(OutputConfig(epub_reader_font_control=True, ebook_series_enabled=True,
                                            epub_language_update_mode='disabled'))
            writer.write_translated_file(output, cache_for(source), source)
            with zipfile.ZipFile(output) as archive:
                nav = BeautifulSoup(archive.read('OEBPS/nav.xhtml'), 'xml')
                links = nav.find_all('a')
                self.assertEqual([link.get_text() for link in links], ['译后章节', 'Untouched heading', 'Missing anchor'])
                self.assertEqual(links[0]['href'], 'chapter.xhtml#chapter')
                ncx = BeautifulSoup(archive.read('OEBPS/toc.ncx'), 'xml')
                self.assertEqual(ncx.find('navLabel').get_text(), '译后章节')
                page = BeautifulSoup(archive.read('OEBPS/chapter.xhtml'), 'xml')
                self.assertEqual(page.title.get_text(), '译后章节')
                self.assertIn('font-weight:bold', page.p['style'])
                self.assertNotIn('font-size', page.p['style'])
                self.assertNotIn('font-size', archive.read('OEBPS/style.css').decode())
                opf = BeautifulSoup(archive.read('OEBPS/book.opf'), 'xml')
                self.assertEqual(opf.find('title').get_text(), '无职转生 第1卷')
                self.assertEqual(opf.find('meta', attrs={'name': 'calibre:series'})['content'], '无职转生')
                self.assertEqual(opf.find('meta', attrs={'property': 'group-position'}).get_text(), '1')
                self.assertEqual(archive.read('OEBPS/untouched.bin'), original['OEBPS/untouched.bin'])
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), digest)

    def test_disabled_options_and_metadata_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'Book 1.epub', Path(folder) / 'out.epub'
            original = make_epub(source)
            writer = EpubWriter(OutputConfig(epub_sync_chapter_titles=False, epub_language_update_mode='disabled'))
            writer.write_translated_file(output, cache_for(source), source)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read('OEBPS/nav.xhtml').decode(), original['OEBPS/nav.xhtml'])
                self.assertEqual(archive.read('OEBPS/style.css').decode(), original['OEBPS/style.css'])
                self.assertIn(b'Original book', archive.read('OEBPS/book.opf'))
            once = update_series_metadata(original['OEBPS/book.opf'], 'Book', '1-3,5-7')
            twice = update_series_metadata(once, 'Book', '1-3,5-7')
            self.assertEqual(once, twice)
            doc = BeautifulSoup(twice, 'xml')
            self.assertEqual(doc.find('meta', attrs={'name': 'calibre:series_index'})['content'], '1')
            self.assertEqual(doc.find('meta', attrs={'name': 'ainiee:volume-range'})['content'], '1-3,5-7')

    def test_directory_names_and_output_tracking(self):
        with tempfile.TemporaryDirectory() as folder:
            source_dir, output_dir = Path(folder) / 'input', Path(folder) / 'output'
            source_dir.mkdir()
            source = source_dir / '无职转生 01.epub'
            make_epub(source)
            cache = cache_for(source)
            project = CacheProject(project_type='Epub', files={cache.storage_path: cache})
            config = OutputConfig(ebook_series_enabled=True, translated_config=TranslationOutputConfig(True, ''))
            records = DirectoryWriter(lambda: EpubWriter(config)).write_translation_directory(project, source_dir, output_dir)
            self.assertEqual(records, [(output_dir / '无职转生 第1卷.epub', EbookIdentity('无职转生', '1'))])
            self.assertTrue(records[0][0].is_file())


class BatchMergeTests(unittest.TestCase):
    def test_cli_merge_hook_works_without_translation_ui(self):
        tree = ast.parse((ROOT / 'ainiee_cli.py').read_text(encoding='utf-8'))
        cli = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'CLIMenu')
        method = next(node for node in cli.body if isinstance(node, ast.FunctionDef) and node.name == '_auto_merge_batch_ebooks')
        console = Mock()
        namespace = {'os': os, 'PROJECT_ROOT': str(ROOT), 'console': console,
                     'i18n': SimpleNamespace(get=lambda key: key), 'current_lang': 'en',
                     'get_calibre_lang_code': lambda lang: lang}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(ROOT / 'ainiee_cli.py'), 'exec'), namespace)
        host = SimpleNamespace(config={'ebook_series_enabled': True},
                               file_outputer=SimpleNamespace(last_output_files=[('1.epub', EbookIdentity('Book', '1')),
                                                                              ('2.epub', EbookIdentity('Book', '2'))]))
        with patch('ModuleFolders.Domain.FileOutputer.BatchEbookMerger.merge_batch_ebooks', return_value=[Path('Book 1-2.epub')]) as merge:
            self.assertTrue(namespace['_auto_merge_batch_ebooks'](host, '.', '.', 'collection', False))
        merge.assert_called_once()
        console.print.assert_called()

    def test_collection_preserves_existing_outputs_and_missing_volumes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records = []
            for number in (1, 2, 4):
                path = root / f'Book {number}.epub'
                make_epub(path)
                records.append((path, EbookIdentity('Book', str(number))))
            old = root / 'Book 1-2,4.epub'
            old.write_bytes(b'old-collection')
            def run(command, **kwargs):
                make_epub(Path(command[command.index('-op') + 1]) / 'merged.epub')
                return subprocess.CompletedProcess(command, 0, '', '')
            with patch('ModuleFolders.Domain.FileOutputer.BatchEbookMerger.subprocess.run', side_effect=run):
                results = merge_batch_ebooks(records, root, 'fallback',
                                            {'ebook_series_enabled': True, 'ebook_name_template': 'X N'},
                                            ROOT / '批量电子书整合.py')
            self.assertEqual(results[0].name, 'Book 1-2,4 (2).epub')
            self.assertEqual(old.read_bytes(), b'old-collection')
            self.assertTrue(all(path.exists() for path, _ in records))

    def test_uses_standalone_script_only_and_excludes_stale_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second, stale = root / 'Book 1.epub', root / 'Book 2.epub', root / 'old.epub'
            for path in (first, second, stale):
                make_epub(path)
            def run(command, **kwargs):
                self.assertEqual(Path(command[1]), ROOT / '批量电子书整合.py')
                self.assertIn('--auto-merge', command)
                inputs = Path(command[command.index('-p') + 1])
                self.assertEqual({p.name for p in inputs.iterdir()}, {'Book 1.epub', 'Book 2.epub'})
                self.assertEqual(command[command.index('-t') + 1], 'Book 1-2')
                make_epub(Path(command[command.index('-op') + 1]) / 'merged.epub')
                return subprocess.CompletedProcess(command, 0, '', '')
            with patch('ModuleFolders.Domain.FileOutputer.BatchEbookMerger.subprocess.run', side_effect=run):
                result = merge_batch_ebooks([(first, EbookIdentity('Book', '1')), (second, EbookIdentity('Book', '2'))],
                                           root, 'fallback', {'ebook_series_enabled': True, 'ebook_name_template': 'X N'},
                                           ROOT / '批量电子书整合.py', 'en')
            self.assertEqual(result[0].name, 'Book 1-2.epub')
            self.assertTrue(stale.exists())

    def test_success_without_output_is_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records = []
            for index in (1, 2):
                source = root / f'Book {index}.epub'
                make_epub(source)
                records.append((source, EbookIdentity('Book', str(index))))
            with patch('ModuleFolders.Domain.FileOutputer.BatchEbookMerger.subprocess.run',
                       return_value=subprocess.CompletedProcess([], 0, '', '')):
                with self.assertRaisesRegex(RuntimeError, 'did not produce'):
                    merge_batch_ebooks(records, root, 'collection', {}, ROOT / '批量电子书整合.py')

    @unittest.skipUnless(os.environ.get('AINIEE_TEST_REAL_EBOOK_MERGE') == '1', 'opt-in standalone merger integration')
    def test_real_standalone_script_collection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records = []
            for index in (1, 2):
                source = root / f'无职转生 {index}.epub'
                make_epub(source, f'Chapter {index}')
                records.append((source, EbookIdentity('无职转生', str(index))))
            settings = {'ebook_series_enabled': True, 'ebook_name_template': 'X 第N卷'}
            result = merge_batch_ebooks(records, root, 'collection', settings, ROOT / '批量电子书整合.py', 'en')
            self.assertEqual(result[0].name, '无职转生 第1-2卷.epub')
            with zipfile.ZipFile(result[0]) as archive:
                opf_name = next(name for name in archive.namelist() if name.endswith('.opf'))
                opf = BeautifulSoup(archive.read(opf_name), 'xml')
                self.assertEqual(opf.find('title').get_text(), '无职转生 第1-2卷')
                self.assertEqual(opf.find('meta', attrs={'name': 'ainiee:volume-range'})['content'], '1-2')
                html = '\n'.join(archive.read(name).decode() for name in archive.namelist() if name.endswith('.xhtml'))
                self.assertIn('Chapter 1', html)
                self.assertIn('Chapter 2', html)


if __name__ == '__main__':
    unittest.main()
