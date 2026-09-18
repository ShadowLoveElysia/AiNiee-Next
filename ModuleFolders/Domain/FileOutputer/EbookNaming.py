"""Shared ebook identity and output naming for individual volumes and collections."""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


EBOOK_EXTENSIONS = {'.epub', '.txt', '.mobi', '.azw3', '.fb2', '.kepub', '.docx'}
UTILITY_DEFAULTS = {
    'epub_reader_font_control': False,
    'epub_sync_chapter_titles': True,
    'ebook_series_enabled': False,
    'ebook_fill_series_metadata': True,
    'ebook_series_name': '',
    'ebook_apply_name_template': True,
    'ebook_name_template': 'X 第N卷',
}


@dataclass(frozen=True)
class EbookIdentity:
    series: str = ''
    volume: str = ''


def _volume_number(value):
    value = unicodedata.normalize('NFKC', value)
    if re.fullmatch(r'\d+(?:\.\d+)?', value):
        return format(Decimal(value).normalize(), 'f')
    digits = dict(zip('零〇一二三四五六七八九两', (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 2)))
    units = {'十': 10, '百': 100, '千': 1000}
    if not value or any(char not in digits and char not in units for char in value):
        return ''
    if not any(char in units for char in value):
        return str(int(''.join(str(digits[char]) for char in value)))
    total = current = 0
    for char in value:
        if char in units:
            total += (current or 1) * units[char]
            current = 0
        else:
            current = digits[char]
    return str(total + current)


def identify_ebook(path, series_override='', suffix=''):
    path = Path(path)
    stem = unicodedata.normalize('NFKC', path.stem)
    series_override = str(series_override or '')
    if suffix and stem.endswith(suffix):
        stem = stem[:-len(suffix)]
    stem = re.sub(r'(?i)(?:_translated|\.translated|_bilingual)$', '', stem).strip()
    number = r'[0-9零〇一二三四五六七八九十百千两]+(?:\.\d+)?'
    patterns = (
        rf'^(.*?)\s*第\s*({number})\s*[卷巻册冊部集](?:\s+.*)?$',
        rf'^(.*?)\s*({number})\s*[卷巻册冊](?:\s+.*)?$',
        r'^(.+?)\s+(?i:vol(?:ume)?|book)\.?\s*(\d+(?:\.\d+)?)(?:\s+.*)?$',
        r'^(.*?)[\s._\-\[(]*(\d+(?:\.\d+)?)[\])]?$'
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, stem)
        if match:
            series = match[1].strip(' ._-[(])') or path.parent.name
            return EbookIdentity(series_override.strip() or series, _volume_number(match[2]))
    return EbookIdentity(series_override.strip() or stem, '')


def safe_book_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip().rstrip('. ')
    if not value or value in {'.', '..'}:
        raise ValueError('The ebook name is empty after removing invalid filename characters.')
    if re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', value):
        value = '_' + value
    return value


def render_ebook_name(template, identity):
    template = str(template).strip()
    if not template or 'X' not in template or re.search(r'[<>:"/\\|?*\x00-\x1f]', template):
        raise ValueError('The ebook naming template must contain X (book name).')
    if 'N' in template and not identity.volume:
        return ''
    # Substitute once so X/N inside the actual book name remain literal.
    return safe_book_name(re.sub(r'[XN]', lambda m: identity.series if m[0] == 'X' else identity.volume, template))


def naming_enabled(settings):
    return bool(settings.get('ebook_series_enabled', False) and settings.get('ebook_apply_name_template', True))


def series_metadata_enabled(settings):
    return bool(settings.get('ebook_series_enabled', False) and settings.get('ebook_fill_series_metadata', True))


def output_book_name(path, settings):
    if Path(path).suffix.lower() not in EBOOK_EXTENSIONS or not naming_enabled(settings):
        return ''
    return render_ebook_name(
        settings.get('ebook_name_template', 'X 第N卷'),
        identify_ebook(path, settings.get('ebook_series_name', '')),
    )


def volume_range(volumes):
    """Compress consecutive volumes without implying that missing volumes exist."""
    values = sorted({Decimal(value) for value in volumes})
    groups = []
    start = end = None
    for value in values:
        if end is not None and value == end + 1 and value == value.to_integral() and end == end.to_integral():
            end = value
        else:
            if start is not None:
                groups.append((start, end))
            start = end = value
    if start is not None:
        groups.append((start, end))
    return ','.join(format(a, 'f') if a == b else f'{a:f}-{b:f}' for a, b in groups)
