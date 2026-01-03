from functools import partial
from pathlib import Path
from typing import Type

from ModuleFolders.Infrastructure.Cache.CacheProject import CacheProject
from ModuleFolders.Domain.FileOutputer.AutoTypeWriter import AutoTypeWriter
from ModuleFolders.Domain.FileOutputer.BaseWriter import BaseTranslationWriter, OutputConfig, TranslationOutputConfig, WriterInitParams, BilingualOrder
from ModuleFolders.Domain.FileOutputer.DirectoryWriter import DirectoryWriter
from ModuleFolders.Domain.FileOutputer.MToolWriter import MToolWriter
from ModuleFolders.Domain.FileOutputer.OfficeConversionWriter import OfficeConversionDocWriter
from ModuleFolders.Domain.FileOutputer.ParatranzWriter import ParatranzWriter
from ModuleFolders.Domain.FileOutputer.TPPWriter import TPPWriter
from ModuleFolders.Domain.FileOutputer.VntWriter import VntWriter
from ModuleFolders.Domain.FileOutputer.SrtWriter import SrtWriter
from ModuleFolders.Domain.FileOutputer.VttWriter import VttWriter
from ModuleFolders.Domain.FileOutputer.LrcWriter import LrcWriter
from ModuleFolders.Domain.FileOutputer.TxtWriter import TxtWriter
from ModuleFolders.Domain.FileOutputer.EpubWriter import EpubWriter
from ModuleFolders.Domain.FileOutputer.DocxWriter import DocxWriter
from ModuleFolders.Domain.FileOutputer.MdWriter import MdWriter
from ModuleFolders.Domain.FileOutputer.RenpyWriter import RenpyWriter
from ModuleFolders.Domain.FileOutputer.TransWriter import TransWriter
from ModuleFolders.Domain.FileOutputer.I18nextWriter import I18nextWriter
from ModuleFolders.Domain.FileOutputer.PoWriter import PoWriter
from ModuleFolders.Domain.FileOutputer.AssWriter import AssWriter
from ModuleFolders.Domain.FileOutputer.CsvWriter import CsvWriter
from ModuleFolders.Domain.FileOutputer.PptxWriter import PptxWriter

# Optional Writers
try:
    from ModuleFolders.Domain.FileOutputer.BabeldocPdfWriter import BabeldocPdfWriter
except ImportError:
    BabeldocPdfWriter = None

from PluginScripts.IOPlugins.CustomRegistry import CustomWriter

# 文件输出器
class FileOutputer:

    def __init__(self):
        self.writer_factory_dict = {}
        self._register_system_writer()

    def register_writer(self, writer_class: Type[BaseTranslationWriter], **init_kwargs):
        """如果writer可注册，则根据project_type进行注册"""
        if writer_class.is_environ_supported():
            writer_factory = partial(writer_class, **init_kwargs) if init_kwargs else writer_class
            self.writer_factory_dict[writer_class.get_project_type()] = writer_factory

    def _register_system_writer(self):
        self.register_writer(MToolWriter)
        self.register_writer(SrtWriter)
        self.register_writer(VttWriter)
        self.register_writer(LrcWriter)
        self.register_writer(VntWriter)
        self.register_writer(AssWriter)
        self.register_writer(TxtWriter)
        self.register_writer(MdWriter)
        self.register_writer(EpubWriter)
        self.register_writer(DocxWriter)
        self.register_writer(RenpyWriter)
        self.register_writer(TransWriter)
        self.register_writer(I18nextWriter)
        self.register_writer(PoWriter)
        self.register_writer(ParatranzWriter)
        self.register_writer(TPPWriter)
        self.register_writer(OfficeConversionDocWriter)
        self.register_writer(CsvWriter)
        self.register_writer(PptxWriter)
        
        if BabeldocPdfWriter:
            try:
                self.register_writer(BabeldocPdfWriter)
            except Exception:
                pass

        # 注册插件式 Writer
        CustomWriter.register_writers(self)

        # 由于values是引用，最先注册和最后注册都一样
        self.register_writer(AutoTypeWriter, writer_factories=self.writer_factory_dict.values())

    def output_translated_content(self, cache_data: CacheProject, output_path: str, input_path:str, output_config: dict, task_config: TaskConfig = None):
        """
        输出翻译后的内容
        :param cache_data: 缓存数据
        :param output_path: 输出路径
        :param input_path: 输入路径
        :param output_config: 输出配置
        """
        
        # 根据输入路径的类型（文件或目录）选择不同的写入策略
        if os.path.isdir(input_path):
            writer = DirectoryWriter(output_path, output_config, self.plugin_manager)
            writer.write_translation_directory(cache_data, input_path, task_config)
        elif os.path.isfile(input_path):
            # For single file, we also use a writer, but call it directly
            # The AutoTypeWriter is suitable here as it can handle any file type.
            writer = AutoTypeWriter(writer_factories=self.writer_factory_dict.values())
            
            # Ensure the output directory exists
            output_file_path = os.path.join(output_path, os.path.basename(input_path))
            os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
            
            writer.write_translated_file(output_file_path, cache_data.get_first_file(), input_path, task_config)
        else:
            raise ValueError("输入路径既不是文件也不是目录")

    def _get_writer_init_params(self, project_type, output_path: Path, input_path: Path, config: dict):
        output_config = self._get_writer_default_config(project_type, output_path, input_path, config)
        if project_type == AutoTypeWriter.get_project_type():
            writer_init_params_factory = partial(
                self._get_writer_init_params,
                output_path=output_path,
                input_path=input_path,
                config=config,
            )
            # 实际writer默认的输出目录、文件名后缀等配置会被AutoTypeWriter的覆盖
            return WriterInitParams(output_config=output_config, writer_init_params_factory=writer_init_params_factory)
        return WriterInitParams(output_config=output_config)

    def _get_writer_default_config(self, project_type, output_path: Path, input_path: Path, config: dict):
        # 从配置中读取后缀，如果未配置则使用默认值
        translated_suffix = config.get("translated_suffix", "_translated")
        bilingual_suffix = config.get("bilingual_suffix", "_bilingual")
        
        # 从配置中读取双语排序
        bilingual_order_str = config.get("bilingual_order", "source_first")
        try:
            bilingual_order = BilingualOrder(bilingual_order_str)
        except ValueError:
            # 如果配置值无效，则回退到默认值
            bilingual_order = BilingualOrder.SOURCE_FIRST

        default_translated_config = TranslationOutputConfig(True, translated_suffix, output_path)

        # 创建基础的 OutputConfig，包含新的配置项
        def create_output_config(**kwargs):
            base_args = {"bilingual_order": bilingual_order, "input_root": input_path}
            base_args.update(kwargs)
            return OutputConfig(**base_args)

        if project_type == SrtWriter.get_project_type():
            return create_output_config(
                translated_config=TranslationOutputConfig(True, config.get("translated_suffix", ".translated"), output_path),
                bilingual_config=TranslationOutputConfig(True, config.get("bilingual_suffix", '.bilingual'), output_path / "bilingual_srt"),
            )
        elif project_type in (TxtWriter.get_project_type(), EpubWriter.get_project_type()) or (BabeldocPdfWriter and project_type == BabeldocPdfWriter.get_project_type()):
            bilingual_dir_map = {
                TxtWriter.get_project_type(): "bilingual_txt",
                EpubWriter.get_project_type(): "bilingual_epub",
            }
            if BabeldocPdfWriter:
                bilingual_dir_map[BabeldocPdfWriter.get_project_type()] = "bilingual_pdf"

            return create_output_config(
                translated_config=default_translated_config,
                bilingual_config=TranslationOutputConfig(True, bilingual_suffix, output_path / bilingual_dir_map[project_type]),
            )
        elif project_type == AutoTypeWriter.get_project_type():
            return create_output_config(
                translated_config=default_translated_config,
                bilingual_config=TranslationOutputConfig(True, bilingual_suffix, output_path / "bilingual_auto"),
                input_root=None # AutoTypeWriter 的 input_root 是动态的
            )
        elif project_type in (
            RenpyWriter.get_project_type(), TransWriter.get_project_type(), TPPWriter.get_project_type()
        ):
            # 这些类型通常没有后缀
            return create_output_config(translated_config=TranslationOutputConfig(True, "", output_path))
        else:
            return create_output_config(translated_config=default_translated_config)
