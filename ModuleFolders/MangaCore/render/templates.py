from __future__ import annotations


DEFAULT_RENDER_TEMPLATE = {
    "base_layer": "inpainted",
    "use_source_text_fallback": False,
}


def get_render_template(_preset: str) -> dict[str, object]:
    return dict(DEFAULT_RENDER_TEMPLATE)
