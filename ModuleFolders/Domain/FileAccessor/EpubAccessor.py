import posixpath
import re
import urllib.parse
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup

from ModuleFolders.Domain.FileAccessor import ZipUtil


class EpubAccessor:
    DIRTY_CONFIDENCE_TRIGGER = 70
    DIRTY_SCORE_CONFIDENCE_MAX = 7
    XHTML_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}
    NCX_MEDIA_TYPE = "application/x-dtbncx+xml"
    CSS_MEDIA_TYPE = "text/css"
    NOISE_PAGE_TEXTS = {
        "次ページへ",
        "次のページへ",
        "次頁へ",
        "下一页",
        "下一頁",
        "nextpage",
        "next",
    }

    def __init__(self):
        self.last_profile = {}
        self.last_reading_mode = "legacy"

    def read_content(self, source_file_path: Path):
        self.last_profile = {}
        self.last_reading_mode = "legacy"
        with zipfile.ZipFile(source_file_path, 'r') as zipf:
            opf_file = self._find_opf_file(zipf)
            if opf_file is None:
                return []

            files = {x.filename: x for x in zipf.infolist()}
            if opf_file not in files:
                return []

            opf_text = self._read_text(zipf, files[opf_file])
            opf_soup = BeautifulSoup(opf_text, "xml")
            manifest_items = self._read_manifest(opf_soup, opf_file)
            spine_entries = self._read_spine(opf_soup)

            profile = self._inspect_profile(zipf, files, manifest_items, spine_entries, opf_text)
            self.last_profile = profile

            if profile.get("use_conservative_reader"):
                conservative_items = self._read_conservative_items(
                    zipf, files, manifest_items, spine_entries
                )
                if conservative_items:
                    self.last_reading_mode = "conservative"
                    return conservative_items

            self.last_reading_mode = "legacy"
            return self._read_legacy_items(zipf, files, manifest_items)

    def _find_opf_file(self, zipf):
        try:
            meta_content = zipf.read("META-INF/container.xml")
        except KeyError:
            return None

        meta_soup = BeautifulSoup(meta_content, "xml")
        for root_file in meta_soup.select('container rootfiles rootfile'):
            if root_file.get("media-type") == "application/oebps-package+xml":
                return root_file.get("full-path")
        return None

    def _read_manifest(self, opf_soup, opf_file):
        manifest_items = []
        opf_dir = posixpath.dirname(opf_file)
        for item in opf_soup.select("manifest item"):
            item_id = item.get("id")
            href = item.get("href")
            if not item_id or not href:
                continue

            filename = self._resolve_href(opf_dir, href)
            media_type = (item.get("media-type") or "").lower()
            properties = item.get("properties") or ""
            manifest_items.append({
                "id": item_id,
                "href": href,
                "filename": filename,
                "media_type": media_type,
                "properties": properties,
            })
        return manifest_items

    def _read_spine(self, opf_soup):
        spine_entries = []
        for itemref in opf_soup.select("spine itemref"):
            item_id = itemref.get("idref")
            if not item_id:
                continue
            spine_entries.append({
                "idref": item_id,
                "linear": (itemref.get("linear") or "yes").lower(),
            })
        return spine_entries

    def _resolve_href(self, base_dir, href):
        href_path = urllib.parse.urlsplit(href).path
        href_path = urllib.parse.unquote(href_path)
        if base_dir:
            return posixpath.normpath(posixpath.join(base_dir, href_path))
        return posixpath.normpath(href_path)

    def _read_text(self, zipf, file_info):
        data = zipf.read(file_info)
        for encoding in ("utf-8-sig", "utf-8", "utf-16", "gb18030", "cp932"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _is_xhtml_item(self, item):
        filename = item["filename"].lower()
        return (
            item["media_type"] in self.XHTML_MEDIA_TYPES
            or filename.endswith((".xhtml", ".xhtm", ".html", ".htm"))
        )

    def _is_ncx_item(self, item):
        return (
            item["media_type"] == self.NCX_MEDIA_TYPE
            or item["filename"].lower().endswith(".ncx")
        )

    def _is_css_item(self, item):
        return item["media_type"] == self.CSS_MEDIA_TYPE or item["filename"].lower().endswith(".css")

    def _read_legacy_items(self, zipf, files, manifest_items):
        items = []
        for item in manifest_items:
            filename = item["filename"]
            if filename not in files:
                continue
            if self._is_xhtml_item(item) or self._is_ncx_item(item):
                content = self._read_text(zipf, files[filename])
                items.append((item["id"], filename, content))
        return items

    def _read_conservative_items(self, zipf, files, manifest_items, spine_entries):
        manifest_by_id = {item["id"]: item for item in manifest_items}
        items = []

        for spine_entry in spine_entries:
            if spine_entry["linear"] == "no":
                continue
            item = manifest_by_id.get(spine_entry["idref"])
            if not item or not self._is_xhtml_item(item):
                continue

            filename = item["filename"]
            if filename not in files:
                continue

            content = self._read_text(zipf, files[filename])
            if self._is_navigation_document(content):
                continue
            if self._is_noise_document(content):
                continue
            items.append((item["id"], filename, content))

        return items

    def _inspect_profile(self, zipf, files, manifest_items, spine_entries, opf_text):
        spine_ids = {entry["idref"] for entry in spine_entries}
        xhtml_items = [item for item in manifest_items if self._is_xhtml_item(item)]
        css_items = [item for item in manifest_items if self._is_css_item(item)]
        ncx_count = len([item for item in manifest_items if self._is_ncx_item(item)])
        manifest_missing_count = len([item for item in manifest_items if item["filename"] not in files])

        non_spine_xhtml = [
            item for item in xhtml_items
            if item["id"] not in spine_ids and not self._is_manifest_nav_item(item)
        ]

        stats = {
            "xhtml_count": len(xhtml_items),
            "spine_count": len(spine_entries),
            "ncx_count": ncx_count,
            "manifest_missing_count": manifest_missing_count,
            "non_spine_xhtml_count": len(non_spine_xhtml),
            "broken_link_count": 0,
            "short_noise_page_count": 0,
            "navigation_document_count": 0,
            "page_anchor_count": 0,
            "mechanical_class_count": 0,
            "ruby_count": 0,
            "is_calibre_export": False,
            "dirty_score": 0,
            "dirty_confidence": 0,
            "dirty_reasons": [],
            "use_conservative_reader": False,
        }

        stats["is_calibre_export"] = "calibre" in opf_text.lower()

        docs_to_scan = xhtml_items[:200]
        for item in docs_to_scan:
            filename = item["filename"]
            if filename not in files:
                continue

            content = self._read_text(zipf, files[filename])
            stats["page_anchor_count"] += len(re.findall(r'\b(?:id|name)=["\']page[_-]?\d+', content, re.IGNORECASE))
            stats["mechanical_class_count"] += len(re.findall(r'\bclass=["\'](?:class_s[0-9A-Za-z_-]*|kfx[0-9A-Za-z_-]*)', content))
            stats["ruby_count"] += len(re.findall(r'<ruby\b', content, re.IGNORECASE))

            if self._is_navigation_document(content):
                stats["navigation_document_count"] += 1
            if self._is_noise_document(content):
                stats["short_noise_page_count"] += 1

        stats["broken_link_count"] = len(self._find_missing_links(zipf, files, docs_to_scan + css_items[:50]))

        if manifest_missing_count:
            self._add_dirty_score(stats, 2, "manifest references missing files")
        if stats["broken_link_count"] > 0:
            self._add_dirty_score(stats, 3, "broken local links")
        if non_spine_xhtml:
            self._add_dirty_score(stats, 2, "non-spine XHTML documents")
        if stats["short_noise_page_count"] >= 2:
            self._add_dirty_score(stats, 2, "short noise pages")
        if stats["navigation_document_count"] >= 2 and ncx_count:
            self._add_dirty_score(stats, 1, "duplicate navigation documents")
        if stats["page_anchor_count"] >= 20 and stats["mechanical_class_count"] >= 50:
            self._add_dirty_score(stats, 1, "Kindle-style page anchors and generated classes")
        if stats["xhtml_count"] >= 40 and stats["mechanical_class_count"] >= 50:
            self._add_dirty_score(stats, 1, "highly fragmented generated XHTML")

        stats["dirty_confidence"] = self._dirty_confidence(stats["dirty_score"])
        stats["use_conservative_reader"] = stats["dirty_confidence"] >= self.DIRTY_CONFIDENCE_TRIGGER
        return stats

    def _add_dirty_score(self, stats, score, reason):
        stats["dirty_score"] += score
        stats["dirty_reasons"].append(reason)

    def _dirty_confidence(self, dirty_score):
        return min(100, round((dirty_score / self.DIRTY_SCORE_CONFIDENCE_MAX) * 100))

    def _find_missing_links(self, zipf, files, manifest_items):
        missing_links = set()
        for item in manifest_items:
            filename = item["filename"]
            if filename not in files:
                continue

            content = self._read_text(zipf, files[filename])
            if self._is_css_item(item):
                urls = self._extract_css_urls(content)
            else:
                urls = self._extract_html_urls(content)

            for link_url in urls:
                target = self._resolve_local_link(filename, link_url)
                if target and target not in files:
                    missing_links.add((filename, target))
        return missing_links

    def _extract_html_urls(self, content):
        return [
            match.group(2)
            for match in re.finditer(r'\b(?:src|href|poster)=([\'"])(.*?)\1', content, re.IGNORECASE | re.DOTALL)
        ]

    def _extract_css_urls(self, content):
        urls = []
        for match in re.finditer(r'url\(\s*([^)]+?)\s*\)', content, re.IGNORECASE):
            raw_url = match.group(1).strip().strip('"\'')
            urls.append(raw_url)
        for match in re.finditer(r'@import\s+([\'"])(.*?)\1', content, re.IGNORECASE):
            urls.append(match.group(2))
        return urls

    def _resolve_local_link(self, current_filename, link_url):
        if not link_url:
            return None
        if link_url.startswith(("#", "data:", "mailto:", "tel:", "javascript:")):
            return None

        parsed = urllib.parse.urlsplit(link_url)
        if parsed.scheme or parsed.netloc or not parsed.path:
            return None

        link_path = urllib.parse.unquote(parsed.path)
        return posixpath.normpath(posixpath.join(posixpath.dirname(current_filename), link_path))

    def _is_manifest_nav_item(self, item):
        properties = item.get("properties") or ""
        filename = item["filename"].lower()
        return "nav" in properties.split() or filename.endswith(".ncx")

    def _is_navigation_document(self, content):
        if re.search(r'<nav\b[^>]*\b(?:epub:)?type\s*=\s*["\'][^"\']*\b(?:toc|landmarks)\b', content, re.IGNORECASE):
            return True

        soup = BeautifulSoup(content, "html.parser")
        title_text = " ".join(tag.get_text(" ", strip=True) for tag in soup.find_all(["title", "h1", "h2"], limit=3))
        compact_title = re.sub(r"\s+", "", title_text).lower()
        if not any(token in compact_title for token in ("目次", "目录", "目錄", "contents", "tableofcontents")):
            return False

        link_count = len(soup.find_all("a"))
        block_count = len(soup.find_all(["p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"]))
        return link_count >= 5 and link_count >= max(1, block_count // 2)

    def _is_noise_document(self, content):
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("", strip=True)
        compact_text = re.sub(r"\s+", "", text)
        if not compact_text:
            return True
        if compact_text.lower() in self.NOISE_PAGE_TEXTS:
            return True
        return re.fullmatch(r"(?:page)?[0-9０-９]+", compact_text, flags=re.IGNORECASE) is not None

    def write_content(
        self, content: dict[str, str], write_file_path: Path,
        source_file_path: Path,
    ):
        ZipUtil.replace_in_zip_file(source_file_path, write_file_path, content)
