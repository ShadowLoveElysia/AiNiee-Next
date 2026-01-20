"""
术语高亮处理模块
负责在原文和译文中自动识别和高亮术语
"""
import re
from rich.text import Text
from typing import Dict, List, Optional, Tuple


class GlossaryHighlighter:
    """术语高亮处理类"""

    def __init__(self, glossary_data: Optional[List[Dict]] = None):
        self.glossary_data = glossary_data or []
        self.term_cache = {}  # 缓存术语匹配结果
        self._build_term_patterns()

    def _build_term_patterns(self):
        """构建术语匹配模式"""
        self.source_patterns = []
        self.target_patterns = []

        for term in self.glossary_data:
            src = term.get('src', '').strip()
            dst = term.get('dst', '').strip()

            if src:
                # 为源术语创建匹配模式（考虑单词边界）
                pattern = r'\b' + re.escape(src) + r'\b'
                self.source_patterns.append({
                    'pattern': re.compile(pattern, re.IGNORECASE),
                    'term': src,
                    'translation': dst,
                    'info': term.get('info', '')
                })

            if dst:
                # 为译文术语创建匹配模式
                pattern = re.escape(dst)
                self.target_patterns.append({
                    'pattern': re.compile(pattern, re.IGNORECASE),
                    'term': dst,
                    'source': src,
                    'info': term.get('info', '')
                })

    def highlight_source(self, text: str) -> Text:
        """高亮源文本中的术语"""
        if not text or not self.source_patterns:
            return Text(text)

        # 使用缓存避免重复计算
        cache_key = f"src:{text}"
        if cache_key in self.term_cache:
            return self.term_cache[cache_key]

        result = Text()
        last_end = 0
        matches = []

        # 查找所有术语匹配
        for pattern_data in self.source_patterns:
            pattern = pattern_data['pattern']
            for match in pattern.finditer(text):
                matches.append({
                    'start': match.start(),
                    'end': match.end(),
                    'text': match.group(),
                    'term_data': pattern_data
                })

        # 按位置排序，处理重叠
        matches.sort(key=lambda x: x['start'])
        filtered_matches = self._filter_overlapping_matches(matches)

        # 构建高亮文本
        for match in filtered_matches:
            # 添加匹配前的普通文本
            if match['start'] > last_end:
                result.append(text[last_end:match['start']])

            # 添加高亮的术语
            term_text = match['text']
            translation = match['term_data']['translation']
            info = match['term_data']['info']

            # 根据术语状态设置样式
            if translation:
                style = "bold cyan"  # 有译文的术语
                tooltip = f"{term_text} → {translation}"
            else:
                style = "bold yellow"  # 没有译文的术语
                tooltip = term_text

            if info:
                tooltip += f" ({info})"

            result.append(term_text, style=style)
            last_end = match['end']

        # 添加剩余的普通文本
        if last_end < len(text):
            result.append(text[last_end:])

        # 缓存结果
        self.term_cache[cache_key] = result
        return result

    def highlight_translation(self, text: str) -> Text:
        """高亮译文中的术语"""
        if not text or not self.target_patterns:
            return Text(text)

        # 使用缓存避免重复计算
        cache_key = f"tgt:{text}"
        if cache_key in self.term_cache:
            return self.term_cache[cache_key]

        result = Text()
        last_end = 0
        matches = []

        # 查找所有术语匹配
        for pattern_data in self.target_patterns:
            pattern = pattern_data['pattern']
            for match in pattern.finditer(text):
                matches.append({
                    'start': match.start(),
                    'end': match.end(),
                    'text': match.group(),
                    'term_data': pattern_data
                })

        # 按位置排序，处理重叠
        matches.sort(key=lambda x: x['start'])
        filtered_matches = self._filter_overlapping_matches(matches)

        # 构建高亮文本
        for match in filtered_matches:
            # 添加匹配前的普通文本
            if match['start'] > last_end:
                result.append(text[last_end:match['start']])

            # 添加高亮的术语
            term_text = match['text']
            source = match['term_data']['source']
            info = match['term_data']['info']

            # 已翻译术语用绿色高亮
            style = "bold green"
            tooltip = f"{source} → {term_text}" if source else term_text

            if info:
                tooltip += f" ({info})"

            result.append(term_text, style=style)
            last_end = match['end']

        # 添加剩余的普通文本
        if last_end < len(text):
            result.append(text[last_end:])

        # 缓存结果
        self.term_cache[cache_key] = result
        return result

    def _filter_overlapping_matches(self, matches: List[Dict]) -> List[Dict]:
        """过滤重叠的匹配项，保留最长的匹配"""
        if not matches:
            return []

        filtered = []
        for match in matches:
            # 检查是否与已有匹配重叠
            overlaps = False
            for existing in filtered:
                if (match['start'] < existing['end'] and match['end'] > existing['start']):
                    # 有重叠，保留更长的匹配
                    if match['end'] - match['start'] > existing['end'] - existing['start']:
                        filtered.remove(existing)
                        break
                    else:
                        overlaps = True
                        break

            if not overlaps:
                filtered.append(match)

        return sorted(filtered, key=lambda x: x['start'])

    def find_missing_terms(self, source_text: str, translation_text: str) -> List[Dict]:
        """查找源文本中存在但译文中缺失的术语"""
        missing_terms = []

        if not source_text or not translation_text:
            return missing_terms

        # 在源文本中查找术语
        source_terms = set()
        for pattern_data in self.source_patterns:
            pattern = pattern_data['pattern']
            for match in pattern.finditer(source_text):
                source_terms.add(pattern_data['term'])

        # 检查这些术语的翻译是否在译文中
        for term in source_terms:
            # 找到对应的翻译
            translation = None
            for pattern_data in self.source_patterns:
                if pattern_data['term'] == term:
                    translation = pattern_data['translation']
                    break

            if translation:
                # 检查翻译是否在译文中
                found = False
                for pattern_data in self.target_patterns:
                    if pattern_data['term'] == translation:
                        if pattern_data['pattern'].search(translation_text):
                            found = True
                            break

                if not found:
                    missing_terms.append({
                        'source_term': term,
                        'missing_translation': translation,
                        'info': next((p['info'] for p in self.source_patterns if p['term'] == term), '')
                    })

        return missing_terms

    def get_term_suggestions(self, prefix: str, max_suggestions: int = 10) -> List[Dict]:
        """根据前缀获取术语建议"""
        suggestions = []

        if not prefix or len(prefix) < 2:
            return suggestions

        prefix_lower = prefix.lower()

        # 在源术语中查找
        for pattern_data in self.source_patterns:
            term = pattern_data['term']
            if term.lower().startswith(prefix_lower):
                suggestions.append({
                    'type': 'source',
                    'term': term,
                    'translation': pattern_data['translation'],
                    'info': pattern_data['info']
                })

        # 在译文术语中查找
        for pattern_data in self.target_patterns:
            term = pattern_data['term']
            if term.lower().startswith(prefix_lower):
                suggestions.append({
                    'type': 'target',
                    'term': term,
                    'source': pattern_data['source'],
                    'info': pattern_data['info']
                })

        # 去重并限制数量
        seen = set()
        unique_suggestions = []
        for suggestion in suggestions:
            key = suggestion['term']
            if key not in seen:
                seen.add(key)
                unique_suggestions.append(suggestion)

        return unique_suggestions[:max_suggestions]

    def analyze_text_terms(self, source_text: str, translation_text: str) -> Dict:
        """分析文本中的术语使用情况"""
        analysis = {
            'source_terms_found': [],
            'target_terms_found': [],
            'missing_translations': [],
            'potential_issues': []
        }

        # 分析源文本术语
        for pattern_data in self.source_patterns:
            pattern = pattern_data['pattern']
            matches = list(pattern.finditer(source_text))
            if matches:
                analysis['source_terms_found'].append({
                    'term': pattern_data['term'],
                    'translation': pattern_data['translation'],
                    'count': len(matches),
                    'positions': [(m.start(), m.end()) for m in matches]
                })

        # 分析译文术语
        for pattern_data in self.target_patterns:
            pattern = pattern_data['pattern']
            matches = list(pattern.finditer(translation_text))
            if matches:
                analysis['target_terms_found'].append({
                    'term': pattern_data['term'],
                    'source': pattern_data['source'],
                    'count': len(matches),
                    'positions': [(m.start(), m.end()) for m in matches]
                })

        # 查找缺失翻译
        analysis['missing_translations'] = self.find_missing_terms(source_text, translation_text)

        # TODO: 添加更多分析逻辑，如术语一致性检查等

        return analysis

    def clear_cache(self):
        """清空缓存"""
        self.term_cache.clear()

    def update_glossary(self, new_glossary_data: List[Dict]):
        """更新术语表数据"""
        self.glossary_data = new_glossary_data
        self.clear_cache()
        self._build_term_patterns()