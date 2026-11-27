"""Noninteractive adapters for the TUI's glossary and prompt services."""
from copy import deepcopy
from pathlib import Path
import json

from ModuleFolders.Infrastructure.TaskConfig import ConfigProfileService as profiles
from ModuleFolders.Service.TaskRuntime.jobs import CancelledJob

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class _QuietConsole:
    def print(self, *args, **kwargs):
        return None


class _Messages(dict):
    lang = "zh_CN"


class ReviewHost:
    def __init__(self, config):
        self.config = deepcopy(config)
        self.i18n = _Messages()
        self.PROJECT_ROOT = str(PROJECT_ROOT)
        self._reader = None

    @property
    def file_reader(self):
        if self._reader is None:
            from ModuleFolders.Domain.FileReader.FileReader import FileReader
            self._reader = FileReader()
        return self._reader

    def save_config(self):
        raise RuntimeError("Persist through the review configuration transaction")


def load_configuration(profile=None, rules_profile=None):
    for name, root, allow_none in ((profile, profiles.PROFILES_PATH, False), (rules_profile, profiles.RULES_PROFILES_PATH, True)):
        if name is not None:
            path, _ = profiles.resolve_profile_path(root, name, allow_none=allow_none)
            if path and not Path(path).is_file():
                raise FileNotFoundError("Selected profile does not exist")
    return profiles.load_effective_config(
        active_profile_name=profile, active_rules_profile_name=rules_profile, create_missing=False,
    )


def analyzer_for(config, cancel=None):
    from ModuleFolders.Service.GlossaryAnalysis.GlossaryAnalyzer import GlossaryAnalyzer
    return GlossaryAnalyzer(ReviewHost(config), output_console=_QuietConsole(), cancel_event=cancel, write_diagnostics=False)


def resolve_prompt(filename, category):
    root = (PROJECT_ROOT / "Resource/Prompt" / category).resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Prompt must name an existing file in its prompt category")
    return path


def scan_glossary(payload):
    analyzer = analyzer_for(load_configuration(payload.profile, payload.rules_profile))
    scan = analyzer.prepare_analysis_scan(payload.input_path, payload.analysis_percent, payload.analysis_lines)
    if scan is None:
        raise ValueError("No readable source text was found")
    return {key: scan[key] for key in ("input_path", "total_lines", "lines_to_analyze", "estimated_tokens", "language_profile")}


def frequency(payload):
    analyzer = analyzer_for(load_configuration(payload.profile, payload.rules_profile))
    scan = analyzer.prepare_analysis_scan(payload.input_path)
    if scan is None:
        raise ValueError("No readable source text was found")
    terms = [term.model_dump() for term in payload.terms]
    result = analyzer._calculate_term_frequency(terms, scan["selected_text"])
    return {key: value for key, value in result.items() if value["count"] >= payload.min_frequency}


def analyze_glossary(payload, config, cancel):
    from ModuleFolders.Base.Base import Base
    analyzer = analyzer_for(config, cancel)
    prompt = resolve_prompt(payload.prompt_file, "System") if payload.prompt_file else None
    if prompt is None and config.get("glossary_analysis_prompt_file"):
        prompt = resolve_prompt(config["glossary_analysis_prompt_file"], "System")
    results = []
    with Base.independent_request_scope(cancel):
        for source in payload.inputs:
            if cancel.is_set():
                raise CancelledJob()
            result = analyzer.execute_analysis(
                source.input_path, payload.analysis_percent, payload.analysis_lines,
                payload.temp_platform_config, analysis_mode=payload.analysis_mode,
                prompt_file=str(prompt) if prompt else None,
                translate_during_analysis=payload.translate_during_analysis,
                new=payload.new, replace=payload.replace, source_label=source.source_label,
                source_volume=source.source_volume,
                incremental_split_target_tokens=payload.incremental_split_target_tokens,
                legacy_mode=payload.legacy_mode,
            )
            if cancel.is_set():
                raise CancelledJob()
            if result is None:
                raise ValueError("Glossary analysis did not produce usable results")
            filtered = {key: value for key, value in result["term_freq"].items() if value["count"] >= payload.min_frequency}
            structured = analyzer._build_structured_rules_config(filtered, result["structured_analysis"])
            options = result["incremental_options"]
            analyzer._annotate_text_history_legacy(structured, options, result["legacy_mode"])
            if options["enabled"]:
                analyzer._annotate_structured_rules_source(structured, options)
            results.append({
                "input_path": source.input_path, "term_frequency": filtered,
                "rules": structured, "incremental_options": options,
                "legacy_mode": result["legacy_mode"],
                "legacy_mapping": analyzer.summarize_legacy_mapping_result(structured),
                "completed_batches": result.get("completed_batches", 0),
                "failed_batches": result.get("failed_batches", 0),
            })
            analyzer._merge_structured_rules_into_config(structured, merge_options=options)
    return {"volumes": results, "merged_rules": rules_payload(analyzer.config),
            "partial": any(result["failed_batches"] for result in results)}


def translate_terms(payload, config, cancel):
    from ModuleFolders.Base.Base import Base
    analyzer = analyzer_for(config, cancel)
    terms = {term.src: term.model_dump(exclude={"src"}) for term in payload.terms}
    with Base.independent_request_scope(cancel):
        if payload.mode == "batch":
            options = analyzer.collect_batch_translation_candidates(terms, payload.temp_platform_config)
        else:
            options = analyzer.collect_translation_candidates(terms, payload.temp_platform_config, payload.rounds, avoid=payload.avoid)
    if cancel.is_set():
        raise CancelledJob()
    return {"candidates": options, "missing": [src for src in terms if src not in {row["src"] for row in options}]}


def rules_payload(config):
    return {key: deepcopy(config.get(key, False if key.endswith("_switch") else [] if key.endswith(("_data", "_history")) else ""))
            for key in profiles.RULE_PROFILE_KEYS}


def validate_rules(rules):
    from ModuleFolders.Infrastructure.SensitiveData import contains_sensitive_data
    if not isinstance(rules, dict) or set(rules) - set(profiles.RULE_PROFILE_KEYS):
        raise ValueError("Expected a glossary array or structured rules object")
    if contains_sensitive_data(rules):
        raise ValueError("Rules cannot contain credential fields")
    for key, value in rules.items():
        if key.endswith("_switch"):
            valid = type(value) is bool
        elif key.endswith(("_data", "_history")):
            valid = isinstance(value, list) and all(isinstance(item, dict) for item in value)
        else:
            valid = isinstance(value, str)
        if not valid:
            raise ValueError(f"Invalid value type for {key}")
    return rules


def parse_rules(payload):
    if payload.repair:
        try:
            import json_repair
        except ImportError as exc:
            raise RuntimeError("JSON repair dependency is unavailable") from exc
        value = json_repair.loads(payload.content)
    else:
        value = json.loads(payload.content)
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        value = {"prompt_dictionary_data": value}
    return validate_rules(value)


@profiles.config_transaction()
def import_rules(payload):
    config = load_configuration(payload.profile, payload.rules_profile)
    if config["active_rules_profile"] == "None":
        raise ValueError("Select a writable rules profile before importing rules")
    if payload.expected_revision != profiles.config_revision(config):
        raise profiles.ConfigConflictError()
    rules = deepcopy(payload.rules)
    if payload.terms is not None:
        rules["prompt_dictionary_data"] = [term.model_dump() for term in payload.terms]
    validate_rules(rules)
    analyzer = analyzer_for(config)
    if any(isinstance(item, dict) and (item.get("_glossary_origin") == "mapped_from_legacy_translation" or item.get("_mapping_status") == "mapped")
           for key in ("prompt_dictionary_data", "characterization_data") for item in rules.get(key, [])):
        if not payload.legacy_mapping_confirmed:
            raise ValueError("Confirm review of legacy mapping before importing it")
    if payload.mode == "replace":
        analyzer.config.update(deepcopy(rules))
        summary = {key: len(value) if isinstance(value, list) else int(bool(value)) for key, value in rules.items()}
    else:
        summary = analyzer._merge_structured_rules_into_config(rules, merge_options=payload.merge.model_dump())
        for key in ("pre_translation_data", "post_translation_data", *profiles.RULE_SWITCH_KEYS):
            if key in rules:
                analyzer.config[key] = deepcopy(rules[key])
    # Preserve profile selection and apply only the rule fields to the loaded snapshot.
    for key in profiles.RULE_PROFILE_KEYS:
        if key in analyzer.config:
            config[key] = deepcopy(analyzer.config[key])
    profiles.save_effective_config(config, write_root=False)
    return {"summary": summary, "revision": profiles.config_revision(config)}


@profiles.config_transaction()
def create_rules_profile(payload):
    name = profiles.sanitize_profile_name(payload.name)
    path, name = profiles.resolve_profile_path(profiles.RULES_PROFILES_PATH, name)
    if Path(path).exists():
        raise FileExistsError("Rules profile already exists")
    validate_rules(payload.rules)
    if payload.activate:
        current = load_configuration()
        if payload.expected_revision != profiles.config_revision(current):
            raise profiles.ConfigConflictError()
    profiles.atomic_write_json(path, profiles.normalize_rules_payload(payload.rules))
    if payload.activate:
        root = profiles.load_root_config()
        root["active_rules_profile"] = name
        profiles.save_root_config(root)
    revision = profiles.config_revision(load_configuration()) if payload.activate else None
    return {"profile": name, "activated": payload.activate, "revision": revision}


def preview_rules(profile=None, rules_profile=None):
    from ModuleFolders.UserInterface.RulePreview import RuleInspector
    config = load_configuration(profile, rules_profile)
    return {**RuleInspector(config, _Messages()).inspect(), "rules": rules_payload(config), "revision": profiles.config_revision(config)}


def export_rules(payload):
    config = load_configuration(payload.profile, payload.rules_profile)
    rules = deepcopy(payload.rules) if payload.rules is not None else rules_payload(config)
    if payload.terms is not None:
        rules["prompt_dictionary_data"] = [term.model_dump() for term in payload.terms]
    validate_rules(rules)
    value = rules if payload.format == "structured" else rules.get("prompt_dictionary_data", [])
    return {
        "filename": f"{config['active_rules_profile']}-{payload.format}.json",
        "content": json.dumps(value, ensure_ascii=False, indent=2),
        "revision": profiles.config_revision(config),
    }


def volume_rules(payload):
    from ModuleFolders.Domain.PromptBuilder.DynamicGlossary import rules_for_volume
    config = load_configuration(payload.profile, payload.rules_profile)
    return {"rules": rules_for_volume(config, payload.volume), "revision": profiles.config_revision(config)}


def build_prompt_test(config, text, prompt_content, prompt_id, *, pure_prompt=True):
    from ModuleFolders.Domain.PromptBuilder.PromptBuilder import PromptBuilder
    from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
    from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
    task = TaskConfig()
    task.load_config_from_dict(deepcopy(config))
    task.prepare_for_translation(TaskType.TRANSLATION)
    task.translation_prompt_selection = {"last_selected_id": prompt_id, "prompt_content": prompt_content}
    if pure_prompt:
        for key in ("prompt_dictionary_switch", "exclusion_list_switch", "characterization_switch", "world_building_switch",
                    "writing_style_switch", "translation_example_switch", "few_shot_and_example_switch"):
            setattr(task, key, False)
        task.pre_line_counts = 0
    texts = {str(index): line for index, line in enumerate(line for line in text.splitlines() if line.strip())}
    if not texts:
        raise ValueError("Prompt test requires nonempty source text")
    messages, system, _ = PromptBuilder.generate_prompt(task, texts, [], task.source_language)
    return {"messages": messages, "system_prompt": system, "source_lines": len(texts)}, task


def build_prompt(payload, config):
    path = resolve_prompt(payload.prompt_file, "Translate")
    return build_prompt_test(config, payload.text, path.read_text(encoding="utf-8"), path.stem, pure_prompt=payload.pure_prompt)


def test_prompt(payload, config, cancel):
    from ModuleFolders.Base.Base import Base
    from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
    prompt, task = build_prompt(payload, config)
    with Base.independent_request_scope(cancel):
        skip, reasoning, content, input_tokens, output_tokens = LLMRequester().sent_request(
            prompt["messages"], prompt["system_prompt"],
            payload.temp_platform_config or task.get_platform_configuration("translationReq"),
        )
    if cancel.is_set():
        raise CancelledJob()
    if skip:
        raise ValueError("Prompt request failed")
    return {"content": content, "reasoning": reasoning, "input_tokens": input_tokens, "output_tokens": output_tokens}
