import json as std_json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.modules.setdefault("rapidjson", std_json)


class _MsgspecJson:
    @staticmethod
    def encode(value):
        return std_json.dumps(value).encode("utf-8")

    @staticmethod
    def decode(value, type=None):
        return std_json.loads(value)


sys.modules.setdefault(
    "msgspec",
    SimpleNamespace(json=_MsgspecJson, ValidationError=ValueError),
)

from ModuleFolders.Infrastructure.Cache.CacheFile import CacheFile
from ModuleFolders.Infrastructure.Cache.CacheItem import CacheItem, TranslationStatus
from ModuleFolders.Infrastructure.Cache.CacheProject import CacheProject
from ModuleFolders.Domain.FileOutputer.BaseWriter import OutputConfig, TranslationOutputConfig
from ModuleFolders.Domain.FileOutputer.TxtWriter import TxtWriter
from ModuleFolders.UserInterface.AIProofreadMenu import AIProofreadMenu
from ModuleFolders.UserInterface.ExportFlow import ExportFlow


class AIProofreadExportTests(unittest.TestCase):
    def _report_item(self, translated_text, target_field=None):
        ai_check = {}
        if target_field:
            ai_check["target_field"] = target_field
        return SimpleNamespace(translated_text=translated_text, ai_check=ai_check)

    def test_translated_correction_clears_stale_polished_text(self):
        cache_item = CacheItem(
            text_index=1,
            translation_status=TranslationStatus.POLISHED,
            translated_text="old translation",
            polished_text="stale polish",
        )
        report_item = self._report_item("old translation", "translated_text")

        target_field = AIProofreadMenu._apply_correction_to_cache_item(
            report_item,
            cache_item,
            "fixed translation",
        )

        self.assertEqual(target_field, "translated_text")
        self.assertEqual(cache_item.translated_text, "fixed translation")
        self.assertEqual(cache_item.polished_text, "")
        self.assertEqual(cache_item.translation_status, TranslationStatus.TRANSLATED)
        self.assertEqual(cache_item.final_text, "fixed translation")

    def test_polished_correction_keeps_polished_output(self):
        cache_item = CacheItem(
            text_index=1,
            translation_status=TranslationStatus.POLISHED,
            translated_text="translation",
            polished_text="old polish",
        )
        report_item = self._report_item("old polish", "polished_text")

        target_field = AIProofreadMenu._apply_correction_to_cache_item(
            report_item,
            cache_item,
            "fixed polish",
        )

        self.assertEqual(target_field, "polished_text")
        self.assertEqual(cache_item.translated_text, "translation")
        self.assertEqual(cache_item.polished_text, "fixed polish")
        self.assertEqual(cache_item.translation_status, TranslationStatus.POLISHED)
        self.assertEqual(cache_item.final_text, "fixed polish")

    def test_legacy_report_matches_translated_text_before_fallback(self):
        cache_item = CacheItem(
            text_index=1,
            translation_status=TranslationStatus.POLISHED,
            translated_text="reported translation",
            polished_text="existing polish",
        )
        report_item = self._report_item("reported translation")

        target_field = AIProofreadMenu._apply_correction_to_cache_item(
            report_item,
            cache_item,
            "fixed translation",
        )

        self.assertEqual(target_field, "translated_text")
        self.assertEqual(cache_item.translated_text, "fixed translation")
        self.assertEqual(cache_item.polished_text, "")
        self.assertEqual(cache_item.translation_status, TranslationStatus.TRANSLATED)
        self.assertEqual(cache_item.final_text, "fixed translation")

    def test_legacy_report_prefers_translated_text_when_both_fields_match(self):
        cache_item = CacheItem(
            text_index=1,
            translation_status=TranslationStatus.POLISHED,
            translated_text="same text",
            polished_text="same text",
        )
        report_item = self._report_item("same text")

        target_field = AIProofreadMenu._apply_correction_to_cache_item(
            report_item,
            cache_item,
            "fixed translation",
        )

        self.assertEqual(target_field, "translated_text")
        self.assertEqual(cache_item.translated_text, "fixed translation")
        self.assertEqual(cache_item.polished_text, "")
        self.assertEqual(cache_item.translation_status, TranslationStatus.TRANSLATED)

    def test_ai_proofread_status_is_normalized_for_export(self):
        project = CacheProject(project_type="Txt")
        cache_file = CacheFile(storage_path="book.txt", file_project_type="Txt")
        cache_file.items = [
            CacheItem(
                text_index=1,
                translation_status=TranslationStatus.AI_PROOFREAD,
                translated_text="translation",
                polished_text="proofread polish",
            ),
            CacheItem(
                text_index=2,
                translation_status=TranslationStatus.AI_PROOFREAD,
                translated_text="proofread translation",
                polished_text="",
            ),
        ]
        project.add_file(cache_file)

        ExportFlow._normalize_ai_proofread_status_for_export(project)

        self.assertEqual(cache_file.items[0].translation_status, TranslationStatus.POLISHED)
        self.assertEqual(cache_file.items[0].final_text, "proofread polish")
        self.assertEqual(cache_file.items[1].translation_status, TranslationStatus.TRANSLATED)
        self.assertEqual(cache_file.items[1].final_text, "proofread translation")

    def test_normalized_ai_proofread_cache_is_written_by_txt_writer(self):
        cache_file = CacheFile(storage_path="book.txt", file_project_type="Txt")
        cache_file.items = [
            CacheItem(
                text_index=1,
                translation_status=TranslationStatus.AI_PROOFREAD,
                source_text="source",
                translated_text="proofread translation",
                polished_text="",
                extra={"line_break": 0},
            )
        ]
        project = CacheProject(project_type="Txt")
        project.add_file(cache_file)

        ExportFlow._normalize_ai_proofread_status_for_export(project)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "book_translated.txt"
            writer = TxtWriter(
                OutputConfig(
                    translated_config=TranslationOutputConfig(True, "", Path(tmp_dir))
                )
            )
            writer.write_translated_file(
                output_path,
                cache_file,
                task_config=SimpleNamespace(keep_original_encoding=True),
            )

            self.assertEqual(output_path.read_text(encoding="utf-8"), "proofread translation\n")


if __name__ == "__main__":
    unittest.main()
