"""Shared optional ebook export settings and language resolution."""

import re


EXPORT_DEFAULTS = {
    'epub_language_follow_source': 'interface',
    'epub_paragraph_preset': 'off',
    'epub_repair_links': False,
    'ebook_optimize_images': False,
    'ebook_image_format': 'preserve',
    'ebook_image_quality': 80,
    'txt_generate_epub': False,
}


def language_tag(value):
    value = str(value or '').strip().replace('_', '-')
    aliases = {
        'chinese': 'zh-CN', 'chinese-simplified': 'zh-CN', 'simplified chinese': 'zh-CN',
        'chinese-traditional': 'zh-TW', 'traditional chinese': 'zh-TW', 'zh-cntw': 'zh-TW',
        'japanese': 'ja', 'english': 'en', 'korean': 'ko', 'russian': 'ru',
        'spanish': 'es', 'french': 'fr', 'german': 'de', 'italian': 'it',
        'portuguese': 'pt', 'arabic': 'ar', 'thai': 'th', 'vietnamese': 'vi',
        'indonesian': 'id', '中文': 'zh-CN', '简体中文': 'zh-CN', '繁体中文': 'zh-TW',
    }
    if value.lower() in aliases:
        return aliases[value.lower()]
    if value.lower() in {'auto', 'disabled', 'unknown', 'un'}:
        return ''
    if re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*', value):
        parts = value.split('-')
        return '-'.join([parts[0].lower()] + [p.upper() if len(p) == 2 else p.title() if len(p) == 4 else p for p in parts[1:]])
    return ''


def resolve_epub_language(settings):
    mode = settings.get('epub_language_update_mode', 'auto') or 'auto'
    if mode == 'disabled':
        return ''
    if mode == 'auto':
        source = 'target_language' if settings.get('epub_language_follow_source', 'interface') == 'target' else 'interface_language'
        mode = settings.get(source, 'Chinese' if source == 'target_language' else 'zh_CN')
    return language_tag(mode)
