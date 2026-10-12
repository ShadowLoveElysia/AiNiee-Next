"""Replay a short 16 kHz mono WAV and report ASR timing without recording text."""

import argparse
import json
from pathlib import Path
import statistics
import time
import wave

from ModuleFolders.Media.asr_catalog import get_recognizer, recognition_files_present, RECOGNITION_MODELS
from ModuleFolders.Media.contracts import AudioSegment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio', type=Path)
    parser.add_argument('--model-root', type=Path, required=True)
    parser.add_argument('--recognizer', choices=tuple(model.key for model in RECOGNITION_MODELS), default='sensevoice')
    parser.add_argument('--device', choices=('auto', 'cpu', 'cuda:0', 'mps', 'metal', 'vulkan'), default='cpu')
    parser.add_argument('--language', choices=('auto', 'ja', 'en', 'zh', 'ko', 'yue'), default='ja')
    parser.add_argument('--endpoint', default='http://127.0.0.1:8001/v1')
    parser.add_argument('--runs', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.runs <= 30:
        parser.error('--runs must be between 1 and 30')
    if get_recognizer(args.recognizer).backend != 'vllm' and not recognition_files_present(args.model_root, args.recognizer):
        parser.error('Recognition weights are missing; download the selected model first')
    with wave.open(str(args.audio), 'rb') as stream:
        if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth(), stream.getcomptype()) != (16000, 1, 2, 'NONE'):
            parser.error('Use an uncompressed 16 kHz mono signed-16 WAV')
        frames = stream.getnframes()
        if not 16 <= frames <= 16000 * 28:
            parser.error('Use a 0–28 second speech clip')
        pcm = stream.readframes(frames)
    model = get_recognizer(args.recognizer)
    import torch
    if model.backend == 'gguf':
        from ModuleFolders.Media.gguf_asr import select_asr_compute
        from ModuleFolders.Media.compute import detect_adapters, selected_cuda_adapters
        args.device = select_asr_compute(args.device, cuda_available=torch.cuda.is_available(),
                                         adapters=selected_cuda_adapters(torch, detect_adapters()))['translation_device']
    if model.backend == 'transformers' and args.device == 'cuda:0':
        from ModuleFolders.Media.runtime import cuda_execution_check
        cuda_execution_check(torch)
    started = time.perf_counter()
    if args.recognizer == 'sensevoice':
        from ModuleFolders.Media.local_backends import SenseVoiceRecognizer
        recognizer = SenseVoiceRecognizer(args.model_root / model.directory, device=args.device)
    elif model.backend == 'gguf':
        from ModuleFolders.Media.gguf_asr import GgufSpeechRecognizer
        recognizer = GgufSpeechRecognizer(args.model_root / model.directory, recognizer=model.key, device=args.device)
    else:
        from ModuleFolders.Media.vllm_asr import VllmSpeechRecognizer
        recognizer = VllmSpeechRecognizer(model=model.repo, endpoint=args.endpoint)
    load_ms = (time.perf_counter() - started) * 1000
    segment = AudioSegment(pcm, 0, frames * 1000 // 16000)
    durations = []
    try:
        for _ in range(args.runs + 1):
            started = time.perf_counter()
            recognizer.transcribe(segment, language=args.language)
            if model.backend == 'transformers' and args.device == 'cuda:0':
                torch.cuda.synchronize()
            elif model.backend == 'transformers' and args.device == 'mps':
                torch.mps.synchronize()
            durations.append((time.perf_counter() - started) * 1000)
        warm = sorted(durations[1:])
    finally:
        if hasattr(recognizer, "close"):
            recognizer.close()
    print(json.dumps({'recognizer': args.recognizer, 'device': 'vllm-service' if model.backend == 'vllm' else args.device, 'audio_ms': segment.end_ms,
                      'load_ms': round(load_ms, 2), 'first_asr_ms': round(durations[0], 2),
                      'warm_median_ms': round(statistics.median(warm), 2), 'warm_max_ms': round(max(warm), 2),
                      'asr_realtime_factor': round(statistics.median(warm) / segment.end_ms, 4),
                      'runs': args.runs, 'scope': 'ASR only; excludes endpoint, translation and queue'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
