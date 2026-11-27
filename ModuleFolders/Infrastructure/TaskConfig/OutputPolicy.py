"""Apply an explicitly selected existing-output policy without prompting."""
from pathlib import Path
import shutil
import uuid


def apply_output_policy(output_path, input_path, policy, *, confirmed=False):
    if policy not in {"resume", "archive", "overwrite", "cancel"}:
        raise ValueError("Unsupported output policy")
    output = Path(output_path).expanduser().resolve()
    source = Path(input_path).expanduser().resolve()
    if policy in {"archive", "overwrite"}:
        if not confirmed:
            raise ValueError("Output replacement requires explicit confirmation")
        if output == Path(output.anchor) or output == source or output in source.parents:
            raise ValueError("Output replacement cannot contain the source or filesystem root")
        if (output / ".git").exists() or (output / "ainiee_cli.py").exists():
            raise ValueError("Output replacement cannot target a source checkout")
        if Path(output_path).is_symlink():
            raise ValueError("Output replacement cannot target a symbolic link")
    if not output.exists():
        return False
    if not output.is_dir():
        raise ValueError("Output destination must be a directory")
    if policy == "cancel":
        raise ValueError("Output already exists; task cancelled by output policy")
    if policy == "resume":
        return (output / "cache/AinieeCacheData.json").is_file()
    if policy == "archive":
        output.rename(output.with_name(f"{output.name}_archive_{uuid.uuid4().hex[:12]}"))
    else:
        shutil.rmtree(output)
    return False
