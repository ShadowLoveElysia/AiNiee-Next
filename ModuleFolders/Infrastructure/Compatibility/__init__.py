"""Compatibility modules required by optional PDF dependencies."""

from importlib import import_module, util
import sys


def install_babeldoc_compatibility():
    """Expose the existing BabelDOC shims after relocating them from the root."""
    sys.modules.setdefault("hyperscan", import_module(f"{__name__}.hyperscan"))
    if "skimage" not in sys.modules and util.find_spec("skimage") is None:
        sys.modules["skimage"] = import_module(f"{__name__}.skimage")
