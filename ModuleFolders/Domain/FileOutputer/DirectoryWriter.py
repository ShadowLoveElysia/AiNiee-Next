from pathlib import Path
from typing import Callable
from ModuleFolders.Domain.FileOutputer.EbookNaming import identify_ebook, output_book_name

import rich

from ModuleFolders.Infrastructure.Cache.CacheProject import CacheProject
from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
from ModuleFolders.Domain.FileOutputer.BaseWriter import (
    BaseBilingualWriter,
    BaseTranslatedWriter,
    BaseTranslationWriter,
    TranslationOutputConfig
)


class DirectoryWriter:
    def __init__(self, create_writer: Callable[[], BaseTranslationWriter]):
        self.create_writer = create_writer

    WRITER_TYPE_CONFIG = {
        BaseTranslatedWriter: ("translated_config", "write_translated_file"),
        BaseBilingualWriter: ("bilingual_config", "write_bilingual_file"),
    }

    def write_translation_directory(
        self, project: CacheProject, source_directory: Path,
        translation_directory: Path = None, task_config: TaskConfig = None,
    ):
        """translation_directory 用于覆盖配置"""
        outputs = []
        planned_paths = set()
        with self.create_writer() as writer:
            # 判断输入路径是目录还是文件
            is_source_a_directory = source_directory.is_dir()
            
            # 把翻译片段按文件名分组
            for storage_path, file_items in project.files.items():
                # 根据输入路径的类型决定如何构造源文件路径
                if is_source_a_directory:
                    # 如果是目录，则拼接相对路径
                    source_file_path = source_directory / storage_path
                else:
                    # 如果是文件，则输入路径本身就是源文件路径
                    source_file_path = source_directory
                for translation_mode in BaseTranslationWriter.TranslationMode:
                    if writer.can_write(translation_mode):
                        translation_config: TranslationOutputConfig = getattr(
                            writer.output_config, translation_mode.config_attr
                        )
                        # 替换文件后缀
                        new_storage_path = self.with_file_suffix(storage_path, translation_config.name_suffix)
                        book_name = output_book_name(source_file_path, vars(writer.output_config))
                        if book_name:
                            new_storage_path = str(Path(storage_path).with_name(book_name + translation_config.name_suffix + Path(storage_path).suffix))
                        output_root = translation_directory or translation_config.output_root
                        translation_file_path = output_root / new_storage_path
                        normalized_path = str(translation_file_path.resolve()).casefold()
                        if normalized_path in planned_paths or translation_file_path.resolve() == source_file_path.resolve():
                            raise ValueError(f'Ebook output path conflicts with another file: {translation_file_path.name}')
                        planned_paths.add(normalized_path)
                        if not translation_file_path.parent.exists():
                            translation_file_path.parent.mkdir(parents=True, exist_ok=True)
                        write_translation_file = getattr(writer, translation_mode.write_method)

                        # 执行写入
                        write_translation_file(translation_file_path, file_items, source_file_path, task_config)
                        if translation_mode == BaseTranslationWriter.TranslationMode.TRANSLATED and translation_file_path.is_file():
                            outputs.append((translation_file_path, identify_ebook(source_file_path, writer.output_config.ebook_series_name)))
        # 释放Ainiee配置实例
        return outputs

    @classmethod
    def with_file_suffix(self, file_path: str, name_suffix: str) -> Path:
        parts = file_path.rsplit(".", 1)
        if len(parts) == 2:
            return f"{parts[0]}{name_suffix}.{parts[1]}"
        else:
            return f"{parts[0]}{name_suffix}"
