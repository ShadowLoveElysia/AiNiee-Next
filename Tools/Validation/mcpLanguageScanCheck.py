"""Regression coverage for full-file detection and isolated MCP execution."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Tools.MCPServer import file_tools


if '--stdio-server' in sys.argv:
    from types import SimpleNamespace
    from Tools.MCPServer.server import AiNieeAPIClient, _build_mcp_app

    app = _build_mcp_app(
        AiNieeAPIClient('http://127.0.0.1:1'),
        SimpleNamespace(app=SimpleNamespace(routes=[])), '127.0.0.1', 0, '/mcp',
    )
    app.run(transport='stdio')
    raise SystemExit


class FullFileLanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'source.txt'
        self.path.write_text('text', encoding='utf-8')

    def test_language_scans_beyond_transfer_limit_without_pagination(self):
        lines = ['English sentence'] * 1000 + ['これは日本語の文章です。'] * 2327
        stats = [{'language': 'ja', 'count': 2327}, {'language': 'en', 'count': 1000}]
        with patch.object(file_tools, '_source_items', return_value=(lines, {'language_stats': stats})), patch.object(
            file_tools, 'read_file_lines', side_effect=AssertionError('must not paginate detection')
        ):
            result = file_tools.detect_file_language(self.path)
        self.assertEqual(result['language'], 'ja')
        self.assertEqual(result['scanned_lines'], 3327)
        self.assertEqual(result['total_lines'], 3327)
        self.assertEqual(result['scan_scope'], 'full_file')
        for key in ('lines', 'max_lines', 'sample_lines', 'has_more', 'next_start_line', 'start_line'):
            self.assertNotIn(key, result)

    def test_transfer_limit_still_applies_to_source_reading(self):
        lines = ['text'] * 2001
        with patch.object(file_tools, '_source_items', return_value=(lines, {})):
            result = file_tools.read_file_lines(self.path)
        self.assertEqual(len(result['lines']), 1000)
        self.assertEqual(result['next_start_line'], 1000)
        with self.assertRaises(file_tools.FileToolError):
            file_tools.read_file_lines(self.path, max_lines=1001)

    def test_structured_reader_failure_never_decodes_zip_bytes_as_text(self):
        from ModuleFolders.Domain.FileReader.FileReader import FileReader

        self.path = self.path.with_suffix('.epub')
        self.path.write_bytes(b'not a valid epub')
        with patch.object(FileReader, 'read_files', side_effect=ValueError('invalid archive')), patch.object(
            file_tools, '_raw_lines', side_effect=AssertionError('binary fallback is forbidden')
        ):
            with self.assertRaises(file_tools.FileToolError) as error:
                file_tools.detect_file_language(self.path)
        self.assertEqual(error.exception.code, 'FILE_PARSE_FAILED')


class IsolatedLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'source.txt'
        self.path.write_text('text', encoding='utf-8')

    def process(self, *, payload=None, error=None):
        process = Mock(returncode=0)
        process.communicate = AsyncMock(
            return_value=(json.dumps(payload).encode(), None), side_effect=error
        )
        process.wait = AsyncMock()
        return process

    async def test_success_passes_full_result_and_requested_format(self):
        result = {'language': 'ja', 'scanned_lines': 3327, 'scan_scope': 'full_file'}
        process = self.process(payload={'ok': True, 'result': result})
        with patch('asyncio.create_subprocess_exec', new=AsyncMock(return_value=process)) as launch:
            actual = await file_tools.detect_file_language_isolated(str(self.path), project_type='Txt')
        self.assertEqual(actual, result)
        self.assertEqual(json.loads(process.communicate.call_args.args[0])['project_type'], 'Txt')
        self.assertEqual(launch.call_args.args[0], sys.executable)
        self.assertNotIn(str(self.path), launch.call_args.args)
        process.kill.assert_not_called()

    async def test_timeout_kills_worker_and_returns_stable_error(self):
        process = self.process(error=asyncio.TimeoutError())
        process.returncode = None
        with patch('asyncio.create_subprocess_exec', new=AsyncMock(return_value=process)):
            with self.assertRaises(file_tools.FileToolError) as error:
                await file_tools.detect_file_language_isolated(str(self.path))
        self.assertEqual(error.exception.code, 'LANGUAGE_SCAN_TIMEOUT')
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    async def test_cancel_kills_worker_and_propagates_cancellation(self):
        process = self.process(error=asyncio.CancelledError())
        process.returncode = None
        with patch('asyncio.create_subprocess_exec', new=AsyncMock(return_value=process)):
            with self.assertRaises(asyncio.CancelledError):
                await file_tools.detect_file_language_isolated(str(self.path))
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    async def test_worker_error_and_bad_response_are_explicit(self):
        for payload, code in (
            ({'ok': False, 'error': 'invalid source', 'error_code': 'FILE_PARSE_FAILED'}, 'FILE_PARSE_FAILED'),
            ({}, 'LANGUAGE_SCAN_FAILED'),
        ):
            with self.subTest(code=code):
                process = self.process(payload=payload)
                with patch('asyncio.create_subprocess_exec', new=AsyncMock(return_value=process)):
                    with self.assertRaises(file_tools.FileToolError) as error:
                        await file_tools.detect_file_language_isolated(str(self.path))
                self.assertEqual(error.exception.code, code)


class StdioLanguageTests(unittest.TestCase):
    def test_real_epub_returns_full_language_stats_over_stdio(self):
        import os
        import queue
        import subprocess
        import threading
        import time
        from zipfile import ZipFile

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source.epub'
            with ZipFile(source, 'w') as book:
                book.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
                book.writestr('book.opf', '<package><manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c"/></spine></package>')
                book.writestr('chapter.xhtml', '<html><body>' + '<p>これは日本語の文章です。</p>' * 1002 + '</body></html>')
            process = subprocess.Popen(
                [sys.executable, '-B', str(Path(__file__).resolve()), '--stdio-server'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', cwd=ROOT,
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
            )
            messages = queue.Queue()
            non_json_lines = []

            def reader():
                for line in process.stdout:
                    try:
                        messages.put(json.loads(line))
                    except ValueError:
                        non_json_lines.append(line)
                messages.put(None)

            thread = threading.Thread(target=reader, daemon=True)
            thread.start()

            def request(request_id, method, params):
                process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}) + '\n')
                process.stdin.flush()
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    response = messages.get(timeout=max(.01, deadline - time.monotonic()))
                    self.assertIsNotNone(response, 'stdio process exited')
                    if response.get('id') == request_id:
                        return response
                self.fail('stdio response timed out')

            try:
                initialized = request(1, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'language-scan-test', 'version': '1'}})
                self.assertIn('result', initialized)
                process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
                process.stdin.flush()
                response = request(2, 'tools/call', {'name': 'agent_detect_file_language', 'arguments': {'path': str(source)}})
                self.assertNotIn('error', response)
                result = response['result']
                self.assertFalse(result.get('isError'))
                content = json.loads(result['content'][0]['text'])
                if isinstance(content.get('result'), dict):
                    content = content['result']
                self.assertEqual(content['language'], 'ja')
                self.assertEqual(content['scanned_lines'], 1002)
                self.assertEqual(content['scan_scope'], 'full_file')
                self.assertEqual(non_json_lines, [])
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
                thread.join(timeout=5)
                process.stdin.close()
                process.stdout.close()


if __name__ == '__main__':
    unittest.main()
