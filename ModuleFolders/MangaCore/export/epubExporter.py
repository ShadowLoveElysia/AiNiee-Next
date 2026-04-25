from __future__ import annotations

import html
import zipfile
from pathlib import Path

from ModuleFolders.MangaCore.export.archiveCommon import iter_rendered_pages
from ModuleFolders.MangaCore.project.session import MangaProjectSession


class EpubExporter:
    def export(self, session: MangaProjectSession) -> Path | None:
        files = iter_rendered_pages(session)
        if not files:
            return None

        output_path = session.output_root / "final" / "epub" / f"{session.manifest.name}.epub"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        title = html.escape(session.manifest.name or "Manga Project")
        identifier = html.escape(session.manifest.project_id)

        manifest_items = ['    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>']
        spine_items: list[str] = []
        nav_links: list[str] = []
        page_documents: list[tuple[str, str]] = []

        for index, (archive_name, image_path) in enumerate(files, start=1):
            image_id = f"img_{index:04d}"
            page_id = f"page_{index:04d}"
            image_href = f"images/{archive_name}"
            page_href = f"{page_id}.xhtml"
            manifest_items.append(f'    <item id="{image_id}" href="{image_href}" media-type="image/png"/>')
            manifest_items.append(f'    <item id="{page_id}" href="{page_href}" media-type="application/xhtml+xml"/>')
            spine_items.append(f'    <itemref idref="{page_id}"/>')
            nav_links.append(f'      <li><a href="{page_href}">Page {index}</a></li>')
            page_documents.append(
                (
                    page_href,
                    "\n".join(
                        [
                            '<?xml version="1.0" encoding="utf-8"?>',
                            '<html xmlns="http://www.w3.org/1999/xhtml">',
                            "  <head>",
                            f"    <title>Page {index}</title>",
                            '    <meta charset="utf-8"/>',
                            "    <style>",
                            "      body { margin: 0; padding: 0; background: #000; text-align: center; }",
                            "      img { width: 100%; height: auto; display: block; }",
                            "    </style>",
                            "  </head>",
                            "  <body>",
                            f'    <img src="{image_href}" alt="Page {index}"/>',
                            "  </body>",
                            "</html>",
                        ]
                    ),
                )
            )

        nav_document = "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">',
                "  <head>",
                f"    <title>{title}</title>",
                '    <meta charset="utf-8"/>',
                "  </head>",
                "  <body>",
                f"    <nav epub:type=\"toc\" id=\"toc\"><h1>{title}</h1><ol>",
                *nav_links,
                "    </ol></nav>",
                "  </body>",
                "</html>",
            ]
        )

        content_opf = "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<package version="3.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid">',
                "  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">",
                f"    <dc:identifier id=\"bookid\">{identifier}</dc:identifier>",
                f"    <dc:title>{title}</dc:title>",
                "    <dc:language>zh</dc:language>",
                "  </metadata>",
                "  <manifest>",
                *manifest_items,
                "  </manifest>",
                "  <spine>",
                *spine_items,
                "  </spine>",
                "</package>",
            ]
        )

        with zipfile.ZipFile(output_path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr(
                "META-INF/container.xml",
                "\n".join(
                    [
                        '<?xml version="1.0" encoding="UTF-8"?>',
                        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">',
                        "  <rootfiles>",
                        '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>',
                        "  </rootfiles>",
                        "</container>",
                    ]
                ),
                compress_type=zipfile.ZIP_DEFLATED,
            )
            archive.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr("OEBPS/nav.xhtml", nav_document, compress_type=zipfile.ZIP_DEFLATED)

            for page_href, page_document in page_documents:
                archive.writestr(f"OEBPS/{page_href}", page_document, compress_type=zipfile.ZIP_DEFLATED)
            for archive_name, image_path in files:
                archive.write(image_path, arcname=f"OEBPS/images/{archive_name}")

        return output_path
