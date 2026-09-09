from __future__ import annotations

import os
from typing import Any, Dict

from Tools.Skills.skill_base import (
    Skill,
    SkillMeta,
    SkillParameter,
    SkillResult,
    normalize_skill_action,
    reject_unknown_skill_fields,
)
from Tools.Skills.skills.common import (
    SkillPathError,
    validate_skill_glob_pattern,
    validate_skill_path,
)


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


class FileSkill(Skill):
    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            name="file",
            description="File discovery and staging for translation tasks.",
            category="files",
            parameters=[
                SkillParameter(
                    name="action",
                    description="Operation: list, info, upload_path.",
                    type="string",
                    required=True,
                    enum=["list", "info", "upload_path"],
                ),
                SkillParameter(
                    name="path",
                    description="Directory path (for list) or file path (for info).",
                    type="string",
                    required=False,
                ),
                SkillParameter(
                    name="pattern",
                    description="Glob pattern for file filtering (e.g., '*.txt', '*.epub').",
                    type="string",
                    required=False,
                    default="*",
                ),
            ],
            examples=[
                {"action": "list", "path": "/path/to/input", "pattern": "*.txt"},
                {"action": "info", "path": "/path/to/file.txt"},
                {"action": "upload_path", "path": "/path/to/file.txt"},
            ],
        )

    def execute(self, args: Dict[str, Any]) -> SkillResult:
        invalid = reject_unknown_skill_fields(
            args, {"action", "path", "pattern"}, skill_name="file"
        )
        if invalid:
            return invalid
        action = normalize_skill_action(args)
        if action is None:
            return SkillResult.fail("action must be a string.", "INVALID_ACTION")

        if action == "list":
            import glob as glob_module

            try:
                requested_path = args.get("path")
                path = validate_skill_path(
                    PROJECT_ROOT if requested_path is None or requested_path == "" else requested_path,
                    field_name="path",
                    must_exist=True,
                    expect_dir=True,
                )
                requested_pattern = args.get("pattern")
                pattern = validate_skill_glob_pattern(
                    "*" if requested_pattern is None or requested_pattern == "" else requested_pattern
                )
            except SkillPathError as exc:
                return SkillResult.fail(str(exc), exc.code)

            search = os.path.join(path, pattern)
            files = sorted(glob_module.glob(search))
            result = []
            for f in files:
                try:
                    safe_path = validate_skill_path(f, field_name="path", must_exist=True)
                    stat = os.stat(safe_path)
                except (SkillPathError, OSError) as exc:
                    # A file can disappear between glob and stat; omit it rather
                    # than turning an otherwise valid discovery request into a 500.
                    if isinstance(exc, SkillPathError):
                        continue
                    continue
                result.append({
                    "name": os.path.basename(safe_path),
                    "path": safe_path,
                    "size": stat.st_size,
                    "is_dir": os.path.isdir(safe_path),
                    "ext": os.path.splitext(safe_path)[1].lower(),
                })
            return SkillResult.ok({
                "count": len(result),
                "files": result,
                "search_path": search,
            })

        if action == "info":
            path = args.get("path", "")
            if path is None or path == "":
                return SkillResult.fail("Missing required parameter: path", "MISSING_PARAM")
            try:
                path = validate_skill_path(path, field_name="path", must_exist=True)
                stat = os.stat(path)
            except SkillPathError as exc:
                return SkillResult.fail(str(exc), exc.code)
            except OSError as exc:
                return SkillResult.fail(f"Unable to inspect path: {exc}", "IO_ERROR")
            supported_exts = {
                ".txt", ".epub", ".docx", ".srt", ".ass", ".vtt", ".lrc",
                ".json", ".po", ".xlsx", ".csv", ".mobi", ".azw3", ".fb2",
                ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".cbz", ".cbr",
                ".html", ".htm", ".md", ".xml", ".yaml", ".yml", ".ts", ".srt",
            }
            ext = os.path.splitext(path)[1].lower()
            return SkillResult.ok({
                "name": os.path.basename(path),
                "path": os.path.abspath(path),
                "size": stat.st_size,
                "is_dir": os.path.isdir(path),
                "ext": ext,
                "supported": ext in supported_exts,
            })

        if action == "upload_path":
            """Return the project staging path suggestion for a file."""
            path = args.get("path", "")
            if path is None or path == "":
                return SkillResult.fail("Missing required parameter: path", "MISSING_PARAM")
            try:
                path = validate_skill_path(
                    path,
                    field_name="path",
                    must_exist=True,
                    expect_file=True,
                )
            except SkillPathError as exc:
                return SkillResult.fail(str(exc), exc.code)

            return SkillResult.ok({
                "local_path": path,
                "note": "Use this path as input_path for translate skill or queue skill.",
            })

        return SkillResult.fail(f"Unknown file action: {action}", "INVALID_ACTION")
