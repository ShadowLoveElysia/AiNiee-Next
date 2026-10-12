"""Resolve with uv, download verified artifacts with byte progress, install locally."""

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from ModuleFolders.Infrastructure.DownloadProgress import DownloadProgress

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'tmp/package-downloads'


NETWORK_ERRORS = (URLError, TimeoutError, ConnectionError, http.client.HTTPException, ssl.SSLError)


def network_error_detail(error):
    if isinstance(error, HTTPError):
        return f'HTTP {error.code}'
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return 'TLS certificate verification failed; check system certificates or SSL_CERT_FILE'
    if isinstance(reason, TimeoutError):
        return 'Connection/read timed out'
    if isinstance(reason, socket.gaierror):
        return 'DNS lookup failed'
    if isinstance(reason, OSError):
        code = getattr(reason, 'winerror', None) or reason.errno
        return f'{type(reason).__name__} (OS error {code})'
    # Exception strings can include authenticated proxy URLs or signed links.
    return type(reason).__name__


def package_ssl_context():
    certificate = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE') or os.environ.get('CURL_CA_BUNDLE')
    return ssl.create_default_context(cafile=certificate or None, capath=os.environ.get('SSL_CERT_DIR') or None)


def curl_download(url, partial, progress, expected_size):
    executable = shutil.which('curl.exe' if sys.platform == 'win32' else 'curl')
    if not executable:
        return None
    context_certificate = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE') or os.environ.get('CURL_CA_BUNDLE')
    args = [executable, '--fail', '--location', '--silent', '--show-error', '--proto', '=https',
            '--proto-redir', '=https', '--connect-timeout', '20', '--speed-time', '60', '--speed-limit', '1',
            '--continue-at', '-', '--output', str(partial), '--user-agent', 'AiNiee-PackageDownloader/1.0']
    if context_certificate:
        args += ['--cacert', context_certificate]
    args += [url]
    previous = partial.stat().st_size if partial.exists() else 0
    progress.set_position('file', previous)
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        while True:
            try:
                _, stderr = process.communicate(timeout=.5)
                break
            except subprocess.TimeoutExpired:
                current = partial.stat().st_size if partial.exists() else 0
                if expected_size is not None and current > expected_size:
                    raise RuntimeError('Package exceeds expected size')
                progress.set_position('file', current, transferred=max(0, current - previous))
                previous = current
        current = partial.stat().st_size if partial.exists() else 0
        progress.set_position('file', current, transferred=max(0, current - previous))
        if process.returncode:
            # curl stderr may contain secrets. Return a bounded status category only.
            categories = {5: 'Proxy resolution failed', 6: 'DNS lookup failed', 7: 'Connection failed',
                          18: 'Incomplete response', 22: 'HTTP request failed', 23: 'Cannot write download file',
                          28: 'Connection/read timed out', 33: 'Server cannot resume this partial file',
                          35: 'TLS handshake failed', 60: 'TLS certificate verification failed'}
            detail = categories.get(process.returncode, 'Transfer failed')
            match = re.search(rb'(?:error|returned error):\s*(\d{3})', stderr or b'', re.I)
            if match:
                detail += ' (HTTP ' + match[1].decode('ascii') + ')'
            return f'curl exit {process.returncode}: {detail}'
        return ''
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stderr:
            process.stderr.close()


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def fetch_artifact(artifact, name, *, cache=CACHE):
    url = artifact['url']
    if urlparse(url).scheme != 'https':
        raise ValueError('Package download requires HTTPS')
    digest = artifact.get('hashes', {}).get('sha256', '')
    if not re.fullmatch('[a-fA-F0-9]{64}', digest):
        raise ValueError('Package SHA-256 is required')
    digest = digest.lower()
    filename = unquote(Path(urlparse(url).path).name)
    if Path(filename).name != filename or '\\' in filename or not filename:
        raise ValueError('Invalid package artifact name')
    destination = cache / digest / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = artifact.get('size')
    with DownloadProgress(name + ' / ' + filename, size) as progress:
        if destination.is_file():
            progress.publish(force=True, stage='verifying')
            if checksum(destination) != digest:
                raise RuntimeError('Cached package hash mismatch: ' + filename)
            progress.set_position('file', destination.stat().st_size)
            return destination
        partial = destination.with_name(filename + '.incomplete')
        context = package_ssl_context()
        last_error = ''
        for attempt in range(3):
            offset = partial.stat().st_size if partial.exists() else 0
            progress.set_position('file', offset)
            if size is not None and offset > size:
                raise RuntimeError('Partial package exceeds expected size')
            if size is not None and offset == size:
                break
            headers = {'Accept-Encoding': 'identity', 'User-Agent': 'AiNiee-PackageDownloader/1.0'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            try:
                with urlopen(Request(url, headers=headers), timeout=45, context=context) as response:
                    if response.status == 206:
                        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                        if not match or int(match[1]) != offset or (size is not None and int(match[3]) != size) or int(match[2]) != int(match[3]) - 1:
                            raise RuntimeError('Package resume response mismatch')
                        size = int(match[3])
                    elif response.status == 200:
                        offset = 0
                        progress.set_position('file', 0)
                        if size is None and response.headers.get('Content-Length'):
                            size = int(response.headers['Content-Length'])
                    else:
                        raise RuntimeError('Unexpected package download status')
                    progress.total = size
                    with partial.open('ab' if offset else 'wb') as output:
                        while block := response.read(256 * 1024):
                            if size is not None and offset + len(block) > size:
                                raise RuntimeError('Package exceeds expected size')
                            output.write(block)
                            offset += len(block)
                            progress.set_position('file', offset, transferred=len(block))
                if size is None or offset == size:
                    break
            except NETWORK_ERRORS as error:
                last_error = network_error_detail(error)
                if isinstance(error, HTTPError):
                    error.close()
                host = urlparse(url).hostname or 'download host'
                print(f'Package request {attempt + 1}/3 failed ({host}): {last_error}', flush=True)
                if attempt == 2:
                    print('Retrying the same package URL with system curl; source and SHA-256 remain unchanged.', flush=True)
                    fallback_error = curl_download(url, partial, progress, size)
                    if fallback_error == '':
                        if size is None and partial.is_file():
                            size = partial.stat().st_size
                            progress.total = size
                        break
                    if fallback_error:
                        last_error += '; ' + fallback_error
                    raise RuntimeError('Package download failed: ' + filename + ' (' + host + '): ' + last_error) from None
            time.sleep(1)
        progress.publish(force=True, stage='verifying')
        if not partial.is_file() or (size is not None and partial.stat().st_size != size) or checksum(partial) != digest:
            raise RuntimeError('Package size/hash verification failed: ' + filename)
        partial.rename(destination)
        return destination


def target_info(python):
    script = '''import json,importlib.metadata
try:
 from packaging.tags import sys_tags
 from packaging.markers import default_environment
except ImportError:
 from pip._vendor.packaging.tags import sys_tags
 from pip._vendor.packaging.markers import default_environment
print(json.dumps({'tags':[str(t) for t in sys_tags()], 'environment':default_environment(),
 'installed':{d.metadata['Name'].lower().replace('_','-'):d.version for d in importlib.metadata.distributions() if d.metadata.get('Name')}}))'''
    result = subprocess.run([str(python), '-c', script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout.splitlines()[-1])


def select_artifact(package, tags):
    ranks = {tag: index for index, tag in enumerate(tags)}
    candidates = []
    for artifact in package.get('wheels', []):
        filename = unquote(Path(urlparse(artifact['url']).path).name)
        match = re.search(r'-([^-]+)-([^-]+)-([^-]+)\.whl$', filename)
        if not match:
            continue
        score = min((ranks.get(f'{python}-{abi}-{platform}', len(tags))
                     for python in match[1].split('.') for abi in match[2].split('.') for platform in match[3].split('.')), default=len(tags))
        if score < len(tags):
            candidates.append((score, artifact))
    if candidates:
        return min(candidates, key=lambda item: item[0])[1]
    if package.get('sdist'):
        return package['sdist']
    raise RuntimeError('No compatible artifact for ' + package['name'])


def applicable_packages(python, packages):
    markers = [package.get('marker', '') for package in packages]
    if not any(markers):
        return packages
    script = '''import json,sys
try:
 from packaging.markers import Marker
except ImportError:
 from pip._vendor.packaging.markers import Marker
print(json.dumps([not m or Marker(m).evaluate() for m in json.loads(sys.argv[1])]))'''
    result = subprocess.run([str(python), '-c', script, json.dumps(markers)], check=True, capture_output=True, text=True)
    enabled = json.loads(result.stdout.splitlines()[-1])
    return [package for package, active in zip(packages, enabled, strict=True) if active]


def install_packages(uv, python, packages, *, index, extra_index='', cache=CACHE):
    info = target_info(python)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix='resolution-') as directory:
        requirements = Path(directory) / 'requirements.in'
        lock = Path(directory) / 'pylock.toml'
        requirements.write_text('\n'.join(packages) + '\n', encoding='utf-8')
        command = [uv, 'pip', 'compile', '--python', str(python), '--format', 'pylock.toml',
                   '--quiet', '--index-url', index, '--output-file', str(lock), str(requirements)]
        if extra_index and extra_index != index:
            command += ['--extra-index-url', extra_index]
        print('Resolving package artifacts; byte progress starts when downloads begin.', flush=True)
        subprocess.run(command, check=True)
        resolution = tomllib.loads(lock.read_text(encoding='utf-8'))
        artifacts = []
        for package in applicable_packages(python, resolution.get('packages', [])):
            name = package['name'].lower().replace('_', '-')
            if info['installed'].get(name) == package.get('version'):
                print(json.dumps({'model': name, 'stage': 'already-installed'}), flush=True)
                continue
            artifacts.append(fetch_artifact(select_artifact(package, info['tags']), name, cache=cache))
        if artifacts:
            # Install exactly the verified resolved artifacts; do not re-download wheels.
            subprocess.run([uv, 'pip', 'install', '--python', str(python), '--no-deps', '--index-url', index,
                            *map(str, artifacts)], check=True)
        else:
            print('Selected packages are already installed.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--index-url', required=True)
    parser.add_argument('--extra-index-url', default='')
    parser.add_argument('packages', nargs='+')
    args = parser.parse_args()
    uv = shutil.which('uv')
    if not uv:
        parser.error('uv is required for measured package downloads')
    install_packages(uv, args.python, args.packages, index=args.index_url, extra_index=args.extra_index_url)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        from ModuleFolders.Infrastructure.DownloadProgress import safe_installer_line
        detail = safe_installer_line(str(error))
        print(json.dumps({'error_detail': detail, 'error_type': type(error).__name__}), flush=True)
        raise SystemExit(1)
