"""Isolated, user-started Qwen vLLM ASR service on Linux/WSL CUDA."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from ModuleFolders.Media.asr_catalog import get_recognizer, recognition_files_present

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT = ROOT / 'Resource/MediaRuntime/vllm-asr-linux'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('install', 'download', 'serve'))
    parser.add_argument('--recognizer', choices=('qwen-vllm-0.6b', 'qwen-vllm-1.7b'), default='qwen-vllm-0.6b')
    parser.add_argument('--model-root', type=Path, default=ROOT / 'tmp/models')
    parser.add_argument('--source', choices=('nju', 'official'), default='nju')
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--gpu-memory', type=float, default=.25)
    parser.add_argument('--attention', choices=('auto', 'fa2'), default='fa2')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run the vLLM service in Linux or WSL with NVIDIA CUDA; native Windows/macOS is unsupported')
    if not 1024 <= args.port <= 65535 or not 0 < args.gpu_memory < 1:
        parser.error('Invalid port or GPU memory fraction')
    model = get_recognizer(args.recognizer)
    python = ENVIRONMENT / 'bin/python'
    if args.action == 'install':
        uv = shutil.which('uv')
        if not uv:
            parser.error('Install uv first')
        from ModuleFolders.Media.package_sources import SOURCES
        index = SOURCES[args.source][0]
        if not python.is_file():
            subprocess.run([uv, 'venv', '--python', '3.12', '--seed', '--allow-existing', str(ENVIRONMENT)], check=True)
        # The official package pins its own Transformers/Torch stack in this environment.
        from ModuleFolders.Media.package_download import install_packages
        install_packages(uv, python, ['qwen-asr[vllm]==0.0.6'], index=index)
        print('vLLM ASR environment installed separately from the translation runtime.')
        return
    if args.action == 'download':
        from ModuleFolders.Media.modelscope_download import download_model
        download_model(model.repo, model.revision, args.model_root / model.directory)
        return
    if not python.is_file() or not recognition_files_present(args.model_root, model.key):
        parser.error('Install the vLLM environment and download its original-format model first')
    check = "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.cuda.get_device_capability(0)); "
    if args.attention == 'fa2':
        check += "assert torch.cuda.get_device_capability(0)[0] >= 8, 'FA2 requires supported Ampere-or-newer hardware'"
    subprocess.run([str(python), '-c', check], check=True)
    environment = os.environ.copy()
    environment.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    launcher = ENVIRONMENT / 'bin/qwen-asr-serve'
    if not launcher.is_file():
        parser.error('qwen-asr-serve is missing; rerun the isolated install')
    args_list = [str(launcher), str((args.model_root / model.directory).resolve()),
                 '--host', '127.0.0.1', '--port', str(args.port), '--served-model-name', model.repo,
                 '--gpu-memory-utilization', str(args.gpu_memory), '--max-model-len', '4096', '--max-num-seqs', '1',
                 '--dtype', 'half', '--disable-log-requests']
    if args.attention == 'fa2':
        args_list += ['--attention-config', json.dumps({'backend': 'FLASH_ATTN', 'flash_attn_version': 2})]
    print(f'Local ASR endpoint: http://127.0.0.1:{args.port}/v1; attention={args.attention}. Confirm the active backend in vLLM startup output.')
    os.execvpe(str(launcher), args_list, environment)


if __name__ == '__main__':
    main()
