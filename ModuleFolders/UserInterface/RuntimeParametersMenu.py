"""基于共享参数元数据的运行覆盖编辑器。"""

import copy
import json

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from ModuleFolders.Infrastructure.TaskConfig.RuntimeOverrides import normalize_runtime_overrides, runtime_parameter_schema


def edit_runtime_parameters(host, current=None):
    values = copy.deepcopy(current or {})
    console = Console()
    schema = runtime_parameter_schema()
    tr = host.i18n.get
    while True:
        table = Table(title=tr("runtime_parameters_title"))
        table.add_column("#")
        table.add_column(tr("runtime_parameter"))
        table.add_column(tr("runtime_value"))
        for index, spec in enumerate(schema, 1):
            value = values.get(spec["key"])
            label = tr(spec["label"])
            table.add_row(str(index), label, tr("runtime_inherit") if value is None else str(value))
        console.print(table)
        choice = Prompt.ask(tr("runtime_edit_hint"), default="0")
        if choice == "0":
            return values
        if not choice.isdigit() or not 1 <= int(choice) <= len(schema):
            continue
        spec = schema[int(choice) - 1]
        key = spec["key"]
        if spec["choices"]:
            console.print(", ".join(str(value) for value in spec["choices"]))
        if key == "platform":
            console.print(", ".join(host.config.get("platforms", {})))
        if key == "model":
            interface = values.get("platform") or host.config.get("api_settings", {}).get("translate")
            models = host.config.get("platforms", {}).get(interface, {}).get("model_datas", [])
            console.print(str(models))
        raw = Prompt.ask(tr("runtime_input_hint"), default="inherit")
        if raw == "inherit":
            values.pop(key, None)
            continue
        try:
            value = json.loads(raw) if spec["type"] in {"int", "float", "bool"} else raw
            values.update(normalize_runtime_overrides({key: value}))
        except (ValueError, TypeError) as exc:
            console.print(str(exc), style="red", markup=False)
