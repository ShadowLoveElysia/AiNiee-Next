"""Provider model listing shared by the TUI and API adapters."""
from urllib.parse import urlsplit, urlunsplit

from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import LLMClientFactory


def discover_models(platform_config: dict, api_format: str) -> list[str]:
    platform_config = dict(platform_config)
    url = str(platform_config.get("api_url") or "")
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    for suffix in ("/chat/completions", "/completions", "/messages", "/responses"):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    if api_format == "Anthropic" and path.endswith("/v1"):
        path = path[:-3]
    platform_config["api_url"] = urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    factory = LLMClientFactory()
    if api_format == "Anthropic":
        page = factory.get_anthropic_client(platform_config).models.list(limit=100, timeout=20)
        models = getattr(page, "data", page)
    elif api_format == "OpenAI":
        page = factory.get_openai_client(platform_config).models.list(timeout=20)
        models = getattr(page, "data", page)
    elif api_format == "Google":
        models = factory.get_google_client(platform_config).models.list(config={"page_size": 100})
    else:
        raise ValueError("The selected provider does not support model discovery")
    names = []
    for item in models:
        name = getattr(item, "id", None) or getattr(item, "name", None)
        if name:
            names.append(str(name).removeprefix("models/"))
        if len(names) >= 1000:
            break
    return sorted(set(names))
