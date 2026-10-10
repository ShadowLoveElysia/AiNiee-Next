"""The TUI and desktop edit the same live-translation preferences."""

from ModuleFolders.Media.preferences import (
    CHOICES, DEFAULTS, RANGES, read_preferences, save_preferences, validate_preference,
)

FIELDS = [
    ("model_root", "models"), ("family", "translator"), ("source", "source_language"),
    ("target", "target_language"), ("device", "device"), ("opacity", "opacity"),
    ("font_size", "font_size"), ("font_family", "font_family"), ("font_bold", "bold"),
    ("translation_color", "translation_color"), ("source_color", "source_color"),
    ("background_color", "background_color"), ("stroke_width", "stroke_width"),
    ("stroke_color", "stroke_color"), ("show_source", "bilingual"), ("topmost", "topmost"),
    ("locked", "lock_position"), ("width", "width"), ("height", "height"),
]


def show_media_settings(host) -> None:
    from rich.console import Console
    from rich.prompt import Confirm, IntPrompt, Prompt
    from rich.table import Table

    console = Console()
    tr = host.i18n.get
    while True:
        host.display_banner()
        data = read_preferences()
        table = Table(title=tr("media_settings"))
        table.add_column("#")
        table.add_column(tr("media_settings"))
        table.add_column(tr("media_value"))
        for index, (key, label) in enumerate(FIELDS, 1):
            value = data.get(key, "")
            if isinstance(value, bool):
                value = tr("media_enabled") if value else tr("media_disabled")
            table.add_row(str(index), tr("media_" + label), str(value))
        console.print(table)
        console.print("0. " + tr("menu_back"))
        choice = IntPrompt.ask(tr("prompt_select"), choices=[str(i) for i in range(len(FIELDS) + 1)], show_choices=False)
        if not choice:
            return
        key, label = FIELDS[choice - 1]
        if isinstance(DEFAULTS.get(key), bool):
            value = Confirm.ask(tr("media_" + label), default=data[key])
        elif key in RANGES:
            value = IntPrompt.ask(tr("media_" + label), default=data[key])
        else:
            value = Prompt.ask(tr("media_" + label), default=str(data[key]), choices=CHOICES.get(key))
        try:
            value = validate_preference(key, value)
            save_preferences({key: value})
        except ValueError as exc:
            console.print(tr("media_invalid_setting").format(detail=str(exc)), markup=False)
