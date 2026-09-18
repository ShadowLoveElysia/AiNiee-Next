"""Optional EPUB paragraph, local-link and image processing without format conversion."""

import copy
import io
import posixpath
import re
import zipfile
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ModuleFolders.Domain.FileAccessor.EpubUtilities import _css_separators, plain_text


HTML_EXTENSIONS = ('.xhtml', '.html', '.htm', '.xht')
TEXT_EXTENSIONS = HTML_EXTENSIONS + ('.opf', '.ncx', '.css', '.svg')


def paragraph_preset(content, preset):
    styles = {
        'indent': 'text-indent:2em!important;margin-block:0!important;line-height:1.6!important;',
        'spaced': 'text-indent:0!important;margin-block:0 0.8em!important;line-height:1.6!important;',
        'reader': 'text-indent:inherit!important;margin-block:0!important;line-height:inherit!important;',
    }
    if preset not in styles:
        return content
    doc = BeautifulSoup(content, 'xml')
    changed = False
    for node in doc.find_all('p'):
        parents = [node, *node.parents]
        if any(parent.name in {'pre', 'code', 'blockquote', 'table', 'nav', 'figure', 'aside'} for parent in parents):
            continue
        if any(re.search(r'(?:poem|poetry|verse|caption|title|note|center|right|toc|separator)',
                         str(parent.get('class', '')) + ' ' + str(parent.get('epub:type', '')), re.I) for parent in parents):
            continue
        if node.find(['br', 'img', 'svg']) or not any(char.isalnum() for char in plain_text(node)):
            continue
        style = node.get('style', '')
        if re.search(r'text-align\s*:\s*(?:center|right|end)', style, re.I):
            continue
        parts, start = [], 0
        for position, token in [*_css_separators(style), (len(style), ';')]:
            if token != ';':
                continue
            declaration = style[start:position]
            name = declaration.split(':', 1)[0].strip().lower()
            if name and name not in {'text-indent', 'margin', 'margin-top', 'margin-bottom', 'margin-block',
                                     'margin-block-start', 'margin-block-end', 'line-height'}:
                parts.append(declaration + ';')
            start = position + 1
        node['style'] = ''.join(parts) + styles[preset]
        if preset in {'indent', 'spaced'}:
            first = node.find(string=True)
            if first is not None:
                first.replace_with(str(first).lstrip(' \t\u3000'))
        changed = True
    return str(doc) if changed else content


def local_target(current, value):
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or not value:
        return None
    path = unquote(parsed.path).replace('\\', '/')
    target = posixpath.normpath(posixpath.join(posixpath.dirname(current), path)) if path else current
    return parsed, target


def rewrite_links(documents, resolver):
    """Apply a local URL resolver to package, navigation, HTML, SVG and CSS references."""
    updates = {}
    css_pattern = re.compile(r'url\(\s*([\'"]?)(.*?)\1\s*\)|(@import\s+)([\'"])(.*?)\4', re.I)

    def css_urls(current, css):
        def replace(match):
            if match[3]:
                value = resolver(current, match[5])
                return match[3] + match[4] + value + match[4]
            value = resolver(current, match[2])
            return 'url(' + (match[1] or '"') + value + (match[1] or '"') + ')'
        return css_pattern.sub(replace, css)

    for name, text in documents.items():
        if name.lower().endswith('.css'):
            rewritten = css_urls(name, text)
        else:
            doc = BeautifulSoup(text, 'xml')
            changed = False
            for node in doc.find_all(True):
                for attr in ('href', 'src', 'poster', 'xlink:href', 'data'):
                    if attr in node.attrs:
                        original = node[attr]
                        replacement = resolver(name, original)
                        if replacement != original:
                            node[attr] = replacement
                            changed = True
                if 'srcset' in node.attrs and 'data:' not in node['srcset']:
                    entries = []
                    for entry in node['srcset'].split(','):
                        parts = entry.strip().split(maxsplit=1)
                        if parts:
                            entries.append(resolver(name, parts[0]) + (' ' + parts[1] if len(parts) > 1 else ''))
                    replacement = ', '.join(entries)
                    if replacement != node['srcset']:
                        node['srcset'] = replacement
                        changed = True
                if 'style' in node.attrs:
                    replacement = css_urls(name, node['style'])
                    if replacement != node['style']:
                        node['style'] = replacement
                        changed = True
                if node.name == 'style':
                    original = node.get_text()
                    replacement = css_urls(name, original)
                    if replacement != original:
                        node.string = replacement
                        changed = True
            rewritten = str(doc) if changed else text
        if rewritten != text:
            updates[name] = rewritten
    return updates


def repair_local_links(documents, filenames):
    by_case = {}
    for name in filenames:
        by_case.setdefault(name.casefold(), []).append(name)
    anchors = {}
    for name, content in documents.items():
        if name.lower().endswith(HTML_EXTENSIONS + ('.svg',)):
            doc = BeautifulSoup(content, 'xml')
            anchors[name] = {str(node.get('id') or node.get('name')) for node in doc.find_all(True)
                             if node.get('id') or node.get('name')}

    def resolve(current, value):
        target = local_target(current, value)
        if target is None:
            return value
        parsed, path = target
        actual = path
        if path not in filenames:
            candidates = by_case.get(path.casefold(), [])
            if len(candidates) != 1:
                return value
            actual = candidates[0]
        fragment = unquote(parsed.fragment)
        if fragment and actual in anchors and fragment not in anchors[actual]:
            matches = [anchor for anchor in anchors[actual] if anchor.casefold() == fragment.casefold()]
            if len(matches) != 1:
                return value
            fragment = matches[0]
        rel = posixpath.relpath(actual, posixpath.dirname(current) or '.') if parsed.path else ''
        return urlunsplit(('', '', quote(rel, safe='/-._~'), parsed.query, quote(fragment, safe='-._~:')))

    updates = rewrite_links(documents, resolve)
    for name, original in documents.items():
        if not name.lower().endswith('.opf'):
            continue
        text = updates.get(name, original)
        doc = BeautifulSoup(text, 'xml')
        manifest, spine = doc.find('manifest'), doc.find('spine')
        if manifest is None or spine is None:
            continue
        changed = False
        items = {item.get('id'): item for item in manifest.find_all('item')}
        if spine.get('toc') not in items:
            ncx = [item for item in items.values() if item.get('media-type') == 'application/x-dtbncx+xml'
                   and local_target(name, item.get('href', ''))
                   and local_target(name, item['href'])[1] in filenames]
            if len(ncx) == 1:
                spine['toc'] = ncx[0]['id']
                changed = True
        navs = []
        for item in items.values():
            href = item.get('href', '')
            target = local_target(name, href)
            if target and target[1] in documents:
                page = BeautifulSoup(documents[target[1]], 'xml')
                if any('toc' in str(nav.get('epub:type', nav.get('type', ''))).split() for nav in page.find_all('nav')):
                    navs.append(item)
        package = doc.find('package')
        if package and str(package.get('version', '')).startswith('3') and len(navs) == 1:
            properties = str(navs[0].get('properties', '')).split()
            if 'nav' not in properties:
                navs[0]['properties'] = ' '.join([*properties, 'nav'])
                changed = True
        if changed:
            updates[name] = str(doc)
    return updates


def optimize_image(data, mode, quality):
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as source:
            if getattr(source, 'is_animated', False) or source.format not in {'JPEG', 'PNG', 'WEBP'}:
                return None
            original_format = source.format
            picture = ImageOps.exif_transpose(source)
            output_format = 'WEBP' if mode == 'webp' else original_format
            options = {'icc_profile': source.info['icc_profile']} if source.info.get('icc_profile') else {}
            if output_format in {'JPEG', 'WEBP'}:
                if picture.mode not in (('RGB', 'L', 'CMYK') if output_format == 'JPEG' else ('RGB', 'RGBA')):
                    picture = picture.convert('RGBA' if 'A' in picture.getbands() or 'transparency' in source.info else 'RGB')
                options.update(quality=max(1, min(100, int(quality))))
            if output_format == 'JPEG':
                options.update(optimize=True, progressive=True)
            elif output_format == 'PNG':
                options.update(optimize=True)
            elif output_format == 'WEBP':
                options.update(method=6)
            result = io.BytesIO()
            picture.save(result, format=output_format, **options)
            encoded = result.getvalue()
            return (encoded, output_format) if len(encoded) < len(data) else None
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


def write_processed_epub(source_path, destination, updates, *, paragraph='off', repair=False,
                         optimize=False, image_format='preserve', image_quality=80):
    """Write one EPUB pass, preserving unchanged resources and rewriting converted-image references."""
    from ModuleFolders.Domain.FileAccessor.EpubAccessor import EpubAccessor

    with zipfile.ZipFile(source_path) as source:
        names = set(source.namelist())
        originals = {info.filename: EpubAccessor()._read_text(source, info) for info in source.infolist()
                     if info.filename.lower().endswith(TEXT_EXTENSIONS)}
        documents = dict(originals)
        documents.update({name: text for name, text in updates.items() if name in documents})
        payloads = dict(updates)
        if paragraph != 'off':
            for name, content in list(documents.items()):
                if name.lower().endswith(HTML_EXTENSIONS):
                    documents[name] = paragraph_preset(content, paragraph)
        if repair:
            documents.update(repair_local_links(documents, names))
        renames = {}
        if optimize:
            for name in sorted(names):
                if not name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    continue
                candidate = optimize_image(source.read(name), image_format, image_quality)
                if candidate is None:
                    continue
                data, format_name = candidate
                target = name
                if format_name == 'WEBP' and not name.lower().endswith('.webp'):
                    target = posixpath.splitext(name)[0] + '.webp'
                    if target.casefold() in {path.casefold() for path in names | set(renames.values())}:
                        continue
                    renames[name] = target
                payloads[name] = data
            def renamed(current, value):
                link = local_target(current, value)
                if not link or link[1] not in renames:
                    return value
                parsed, path = link
                relative = posixpath.relpath(renames[path], posixpath.dirname(current) or '.')
                return urlunsplit(('', '', quote(relative, safe='/-._~'), parsed.query, parsed.fragment))
            if renames:
                documents.update(rewrite_links(documents, renamed))
                for name, content in list(documents.items()):
                    if name.lower().endswith('.opf'):
                        doc = BeautifulSoup(content, 'xml')
                        for item in doc.find_all('item', href=True):
                            link = local_target(name, item['href'])
                            if link and link[1] in renames.values():
                                item['media-type'] = 'image/webp'
                        documents[name] = str(doc)
        for name, text in documents.items():
            original = updates.get(name)
            if text != (original if original is not None else originals[name]):
                payloads[name] = EpubAccessor()._normalize_output_text(name, text)
        with zipfile.ZipFile(destination, 'w') as target:
            for entry in source.infolist():
                info = copy.copy(entry)
                info.filename = renames.get(entry.filename, entry.filename)
                data = payloads[entry.filename] if entry.filename in payloads else source.read(entry.filename)
                target.writestr(info, data)
