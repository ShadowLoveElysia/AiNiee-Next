"""EPUB presentation, navigation and series metadata updates during export."""

import posixpath
import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup


def plain_text(node):
    copy = BeautifulSoup(str(node), 'html.parser')
    for annotation in copy.find_all(['rt', 'rp']):
        annotation.decompose()
    return ' '.join(copy.get_text(' ', strip=True).split())


def _css_separators(css):
    """Locate structural delimiters without splitting strings, comments or URLs."""
    index = depth = 0
    quote = ''
    while index < len(css):
        char = css[index]
        if char == '\\':
            index += 2
            continue
        if quote:
            if char == quote:
                quote = ''
        elif css.startswith('/*', index):
            end = css.find('*/', index + 2)
            index = len(css) if end < 0 else end + 2
            continue
        elif char in "\"'":
            quote = char
        elif char in '([':
            depth += 1
        elif char in ')]':
            depth = max(0, depth - 1)
        elif not depth and char in ';{}':
            yield index, char
        index += 1


def _font_declaration(declaration):
    clean = re.sub(r'/\*.*?\*/', '', declaration, flags=re.DOTALL)
    name, separator, value = clean.partition(':')
    if not separator:
        return declaration
    name = re.sub(r'\\([0-9a-fA-F]{1,6})\s?|\\(.)',
                  lambda m: chr(int(m[1], 16)) if m[1] else m[2], name).strip().lower()
    if name not in {'font', 'font-family', 'font-size'}:
        return declaration
    if name != 'font':
        return ''
    # Keep emphasis carried by shorthand; size and family are left to the reader.
    result = []
    important = ' !important' if re.search(r'!\s*important', value, re.I) else ''
    for token in value.lower().split():
        prop = 'font-style' if token in {'italic', 'oblique'} else 'font-weight' if token in {
            'bold', 'bolder', 'lighter', '100', '200', '300', '400', '500', '600', '700', '800', '900',
        } else 'font-variant' if token == 'small-caps' else None
        if prop:
            result.append(f'{prop}:{token}{important};')
        elif token != 'normal':
            break
    return ''.join(result)


def reader_font_css(css, inline=False):
    separators = list(_css_separators(css))
    result = []
    start = index = 0
    while index < len(separators):
        position, token = separators[index]
        if token == '{':
            closing = index + 1
            depth = 1
            while closing < len(separators):
                depth += (separators[closing][1] == '{') - (separators[closing][1] == '}')
                if not depth:
                    break
                closing += 1
            if depth:
                result.append(css[start:])
                return ''.join(result)
            end = separators[closing][0]
            selector = css[start:position]
            clean_selector = re.sub(r'/\*.*?\*/', '', selector, flags=re.DOTALL).strip().lower()
            block = css[position + 1:end]
            if not clean_selector.startswith('@font-face'):
                nested_rules = clean_selector.startswith(('@media', '@supports', '@layer', '@container', '@document', '@scope', '@keyframes', '@-webkit-keyframes'))
                block = reader_font_css(block, inline=not nested_rules)
            result.append(selector + '{' + block + '}')
            start, index = end + 1, closing + 1
            continue
        segment = css[start:position + 1]
        result.append(_font_declaration(segment) if inline else segment)
        start, index = position + 1, index + 1
    result.append(_font_declaration(css[start:]) if inline else css[start:])
    return ''.join(result)


def release_reader_fonts(filename, content):
    if filename.lower().endswith('.css'):
        return reader_font_css(content)
    soup = BeautifulSoup(content, 'xml')
    changed = False
    for node in soup.find_all(style=True):
        style = reader_font_css(node['style'], inline=True)
        if style != node['style']:
            node['style'] = style
            changed = True
    for node in soup.find_all('style'):
        original = node.get_text()
        css = reader_font_css(original)
        if css != original:
            node.string = css
            changed = True
    for node in soup.find_all('font'):
        for attribute in ('face', 'size'):
            if attribute in node.attrs:
                del node[attribute]
                changed = True
    return str(soup) if changed else content


def sync_navigation(documents, originals, translated_fragments):
    """Resolve navigation targets against source anchors and known translated fragments."""
    source_docs = {}
    translations = {}
    for filename, fragments in translated_fragments.items():
        mapping = {}
        for original_html, translated_text in fragments:
            key = plain_text(original_html)
            mapping.setdefault(key, set()).add(translated_text.strip())
        translations[filename] = {key: next(iter(values)) for key, values in mapping.items() if len(values) == 1}

    def target_title(current, href):
        link = urlsplit(href)
        if link.scheme or link.netloc:
            return ''
        target = posixpath.normpath(posixpath.join(posixpath.dirname(current), unquote(link.path))) if link.path else current
        if target not in translations:
            return ''
        if target not in source_docs:
            source_docs[target] = BeautifulSoup(originals.get(target, ''), 'xml')
        doc = source_docs[target]
        if link.fragment:
            node = doc.find(id=unquote(link.fragment)) or doc.find(attrs={'name': unquote(link.fragment)})
            if node is None:
                return ''
            if node.name not in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7'}:
                heading = node.find(re.compile(r'^h[1-7]$'))
                if heading is not None:
                    node = heading
                elif not plain_text(node):
                    sibling = node.find_next_sibling()
                    if sibling is not None and re.fullmatch(r'h[1-7]', sibling.name or ''):
                        node = sibling
        else:
            node = doc.find(re.compile(r'^h[1-7]$'))
        return translations[target].get(plain_text(node), '') if node is not None else ''

    updates = {}
    for filename, content in documents.items():
        if not filename.lower().endswith(('.xhtml', '.html', '.htm', '.xht', '.ncx')):
            continue
        doc = BeautifulSoup(content, 'xml')
        changed = False
        if filename.lower().endswith('.ncx'):
            for point in doc.find_all('navPoint'):
                target = point.find('content', recursive=False)
                label = point.find('navLabel', recursive=False)
                label = label.find('text') if label else None
                title = target_title(filename, target.get('src', '')) if target else ''
                if title and label is not None:
                    label.string = title
                    changed = True
        else:
            for nav in doc.find_all('nav'):
                types = str(nav.get('epub:type', nav.get('type', ''))).split()
                if 'toc' not in types:
                    continue
                for anchor in nav.find_all('a', href=True):
                    title = target_title(filename, anchor['href'])
                    if title:
                        anchor.string = title
                        changed = True
            page_title = doc.find('title')
            title = target_title(filename, '')
            if title and page_title is not None:
                page_title.string = title
                changed = True
        if changed:
            updates[filename] = str(doc)
    return updates


def update_series_metadata(content, series, volume, title=''):
    doc = BeautifulSoup(content, 'xml')
    metadata = doc.find('metadata')
    if metadata is None:
        return content

    def legacy(name, value):
        for node in metadata.find_all('meta', attrs={'name': name}):
            node.decompose()
        node = doc.new_tag('meta', attrs={'name': name, 'content': value})
        metadata.append(node)

    if title:
        node = metadata.find('dc:title') or metadata.find('title')
        if node is None:
            node = doc.new_tag('dc:title')
            metadata.append(node)
        node.string = title
    if series and volume:
        first_volume = re.split(r'[-,]', volume)[0]
        legacy('calibre:series', series)
        legacy('calibre:series_index', first_volume)
        legacy('ainiee:volume-range', volume)
        package = doc.find('package')
        if package and str(package.get('version', '')).startswith('3'):
            for node in list(metadata.find_all('meta', attrs={'property': 'belongs-to-collection'})):
                node_id = node.get('id', '')
                refinements = metadata.find_all('meta', attrs={'refines': '#' + node_id}) if node_id else []
                if node.get('id') == 'ainiee-series' or any(x.get('property') == 'collection-type' and x.get_text() == 'series' for x in refinements):
                    for refinement in refinements:
                        refinement.decompose()
                    node.decompose()
            series_id = 'ainiee-series'
            while doc.find(id=series_id):
                series_id += '-1'
            for attrs, value in (
                ({'property': 'belongs-to-collection', 'id': series_id}, series),
                ({'property': 'collection-type', 'refines': '#' + series_id}, 'series'),
                ({'property': 'group-position', 'refines': '#' + series_id}, first_volume),
            ):
                node = doc.new_tag('meta', attrs=attrs)
                node.string = value
                metadata.append(node)
    return str(doc)
