"""Explicit language-pair terminology shared by live and private translations."""

import json
import re

from ModuleFolders.Media.inference_queue import LANGUAGES

MAX_ENTRIES = 100


def validate_entries(entries):
    if not isinstance(entries, (list, tuple)) or len(entries) > MAX_ENTRIES:
        raise ValueError("A glossary supports at most 100 entries")
    seen = set()
    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid glossary entry")
        row = {key: entry.get(key) for key in ("source_lang", "source", "target_lang", "target")}
        if row["source_lang"] not in LANGUAGES or row["target_lang"] not in LANGUAGES or row["source_lang"] == row["target_lang"]:
            raise ValueError("Choose different glossary languages")
        for key in ("source", "target"):
            if not isinstance(row[key], str) or not row[key].strip() or len(row[key]) > 128 or any(ch in row[key] for ch in "\r\n\t"):
                raise ValueError("Terms must contain 1 to 128 characters without tabs or newlines")
            row[key] = row[key].strip()
        for source_lang, source, target_lang in [(row["source_lang"], row["source"], row["target_lang"]),
                                                (row["target_lang"], row["target"], row["source_lang"])]:
            identity = (source_lang, source.casefold(), target_lang)
            if identity in seen:
                raise ValueError("Duplicate or ambiguous glossary mapping")
            seen.add(identity)
        normalized.append(row)
    return normalized


def matching_terms(entries, text, source_lang, target_lang):
    selected = []
    budget = 0
    for entry in entries:
        pairs = [(entry["source_lang"], entry["source"], entry["target_lang"], entry["target"]),
                 (entry["target_lang"], entry["target"], entry["source_lang"], entry["source"])]
        for language, source, target_language, target in pairs:
            if target_language != target_lang or source_lang not in {language, "auto"}:
                continue
            pattern = re.escape(source)
            if source.isascii() and source[0].isalnum():
                pattern = r"(?<![A-Za-z0-9_])" + pattern
            if source.isascii() and source[-1].isalnum():
                pattern += r"(?![A-Za-z0-9_])"
            if re.search(pattern, text, re.IGNORECASE):
                pair = {"source": source, "target": target}
                size = len(json.dumps(pair, ensure_ascii=False))
                if budget + size > 1200 or len(selected) >= 16:
                    return selected
                selected.append(pair)
                budget += size
    return selected


def validate_profiles(profiles):
    if not isinstance(profiles, dict) or len(profiles) > 50:
        raise ValueError("A maximum of 50 streamer glossaries is supported")
    normalized = {}
    for name, entries in profiles.items():
        if not isinstance(name, str) or not name.strip() or len(name) > 64:
            raise ValueError("Invalid streamer glossary name")
        if name.strip() in normalized:
            raise ValueError("Duplicate glossary profile name")
        normalized[name.strip()] = validate_entries(entries)
    return normalized
