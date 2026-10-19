"""Lazy model factories for file translation using the media model catalog."""

from pathlib import Path


def compute_devices(config):
    import torch
    from ModuleFolders.Media.compute import detect_adapters, select_compute, selected_cuda_adapters
    from ModuleFolders.Media.model_catalog import get_model
    from ModuleFolders.Media.asr_catalog import get_recognizer
    from ModuleFolders.Media.qwen_asr import recognition_device

    torch.set_num_threads(4)
    checkpoint = get_model(config.family)
    adapters = selected_cuda_adapters(torch, detect_adapters())
    compute = select_compute(
        config.device, gguf=checkpoint.backend == "gguf", cuda_available=torch.cuda.is_available(),
        adapters=adapters, mlx_compatible=checkpoint.family == "index",
        mps_available=torch.backends.mps.is_available(),
    )
    backend = get_recognizer(config.recognizer).backend
    if config.asr_mode == "cloud":
        asr_device = "cloud"
    elif backend == "vllm":
        asr_device = "vllm-service"
    elif backend == "gguf":
        from ModuleFolders.Media.gguf_asr import select_asr_compute
        asr_device = select_asr_compute(config.asr_device, cuda_available=torch.cuda.is_available(),
                                        adapters=adapters)["translation_device"]
    else:
        asr_device = (compute["asr_device"] if config.asr_device == "auto" else
                      recognition_device(config.asr_device, config.recognizer, torch))
    if "cuda:0" in (compute["translation_device"], asr_device):
        from ModuleFolders.Media.runtime import cuda_execution_check
        cuda_execution_check(torch)
    return compute["translation_device"], asr_device


def load_recognizer(config, device):
    if config.asr_mode == "cloud":
        from ModuleFolders.Media.cloud_asr import CloudSpeechRecognizer
        return CloudSpeechRecognizer(endpoint=config.cloud_asr_endpoint, model=config.cloud_asr_model,
                                       api_key=config.cloud_asr_api_key)
    from ModuleFolders.Media.asr_catalog import get_recognizer
    model = get_recognizer(config.recognizer)
    root = Path(config.model_root) / model.directory
    if config.recognizer == "sensevoice":
        from ModuleFolders.Media.local_backends import SenseVoiceRecognizer
        return SenseVoiceRecognizer(root, device=device)
    if model.backend == "gguf":
        from ModuleFolders.Media.gguf_asr import GgufSpeechRecognizer
        return GgufSpeechRecognizer(root, recognizer=config.recognizer, device=device,
                                    cache_ram_mib=config.cache_ram_mib)
    if model.backend == "vllm":
        from ModuleFolders.Media.vllm_asr import VllmSpeechRecognizer
        return VllmSpeechRecognizer(model=model.repo, endpoint=config.asr_endpoint)
    raise ValueError("Unsupported recognition backend")


def load_translator(config, device):
    from ModuleFolders.Media.model_catalog import get_model
    model = get_model(config.family)
    if model.backend == "gguf":
        from ModuleFolders.Media.gguf_backend import GgufTranslator
        translator = GgufTranslator(config.translation_dir / model.filename, family=config.family, device=device,
                                     context_size=4096, cache_ram_mib=config.cache_ram_mib)
    elif device == "mlx":
        from ModuleFolders.Media.mlx_backend import MlxTextTranslator
        translator = MlxTextTranslator(config.translation_dir, family=config.family)
    else:
        from ModuleFolders.Media.local_backends import LocalTextTranslator
        translator = LocalTextTranslator(config.translation_dir, family=config.family, device=device,
                                          dtype="float32" if device == "cpu" else "float16")
    from ModuleFolders.Media.glossary import validate_entries
    translator.glossary = tuple(validate_entries(config.glossary))
    return translator
