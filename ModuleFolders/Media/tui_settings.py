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
    ("context_segments", "context_segments"),
    ("recording", "recording"), ("record_directory", "record_directory"),
    ("package_source", "package_source"),
    ('recognizer', 'recognizer'), ('recognition_device', 'recognition_device'),
    ('asr_endpoint', 'asr_endpoint'),
    ('cloud_asr_endpoint', 'video_asr_endpoint'),
    ('cloud_asr_model', 'video_asr_model'),
    ('cloud_asr_api_key', 'video_asr_api_key'),
]


def show_media_settings(host) -> None:
    from rich.console import Console
    from rich.prompt import Confirm, IntPrompt, Prompt
    from rich.table import Table
    from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS, describe_model, get_model
    from ModuleFolders.Infrastructure.TaskConfig.SettingsRenderer import SettingsMenuBuilder

    console = Console()
    tr = host.i18n.get
    while True:
        host.display_banner()
        data = read_preferences()
        builder = SettingsMenuBuilder({"media_" + key: value for key, value in data.items()}, host.i18n)
        builder.build_menu_items(submenu="media_settings")
        console.print(builder.render_table())
        console.print("0. " + tr("menu_back"))
        choice = IntPrompt.ask(tr("prompt_select"), choices=[str(i) for i in range(len(builder.menu_items) + 1)], show_choices=False)
        if not choice:
            return
        registered_key, item = builder.get_item_by_id(choice)
        key = registered_key.removeprefix("media_")
        label = item.i18n_key.removeprefix("media_")
        if key == "family":
            for index, model in enumerate(TRANSLATION_MODELS, 1):
                console.print(str(index) + ". " + describe_model(model.key, tr), markup=False)
            console.print(tr("media_model_memory_note"), markup=False)
            console.print(tr("media_model_speed_note"), markup=False)
            selected = IntPrompt.ask(tr("media_translator"), choices=[str(i) for i in range(1, len(TRANSLATION_MODELS)+1)])
            value = TRANSLATION_MODELS[selected-1].key
        elif key == "cloud_asr_api_key":
            value = Prompt.ask(tr("media_" + label) + " " + tr("media_video_asr_key_keep"), password=True)
            if not value:
                continue
        elif isinstance(DEFAULTS.get(key), bool):
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
