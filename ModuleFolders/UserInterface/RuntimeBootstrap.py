_RUNTIME_BOOTSTRAPPED = False


def ensure_runtime_bootstrap():
    global _RUNTIME_BOOTSTRAPPED

    if _RUNTIME_BOOTSTRAPPED:
        return

    from ModuleFolders.Infrastructure.Tokener.TiktokenLoader import initialize_tiktoken
    import ModuleFolders.Infrastructure.Tokener.TiktokenLoader as TiktokenLoaderModule
    import ModuleFolders.Domain.FileReader.ReaderUtil as ReaderUtilModule

    TiktokenLoaderModule._SUPPRESS_OUTPUT = True
    ReaderUtilModule._SUPPRESS_OUTPUT = True

    try:
        initialize_tiktoken()
    except Exception:
        pass

    _RUNTIME_BOOTSTRAPPED = True
