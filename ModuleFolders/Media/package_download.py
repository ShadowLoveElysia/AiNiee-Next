"""Resolve with uv, download verified artifacts with byte progress, install locally."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from ModuleFolders.Infrastructure.DownloadProgress import DownloadProgress

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'tmp/package-downloads'


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
        for attempt in range(3):
            offset = partial.stat().st_size if partial.exists() else 0
            progress.set_position('file', offset)
            if size is not None and offset > size:
                raise RuntimeError('Partial package exceeds expected size')
            if size is not None and offset == size:
                break
            headers = {'Accept-Encoding': 'identity'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            try:
                with urlopen(Request(url, headers=headers), timeout=45) as response:
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
            except OSError:
                if attempt == 2:
                    raise RuntimeError('Package download failed: ' + filename) from None
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
    main()
