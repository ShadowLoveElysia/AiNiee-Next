# Media translation backends

## Windows extension installer

### Package download source

The controller offers **China mirror (Nanjing University)** and **Official
(PyTorch / PyPI)**. China is the default. The selection is shared with media
installers and saved after verification; it affects dependency packages only,
not model weights, llama.cpp release archives, uv itself or managed Python.
Actual mirror speed and package availability depend on the network and sync.
Download failure does not silently switch sources; select the other source
and retry. Torch and torchaudio always use matching architecture-specific builds.

The BAT prompts for a source; its fourth argument skips the prompt:

```bat
prepare_media.bat auto index "" nju
prepare_media.bat cuda:0 index cu128 official
```

The Mac SH prompts when run interactively, defaults to China otherwise, and
accepts the source as its third argument:

```bash
bash prepare_media.sh auto index nju
bash prepare_media.sh auto index official
```

`AINIEE_MEDIA_PACKAGE_SOURCE=nju` or `official` can also control the runtime
installer. The desktop selector and TUI live settings expose the same preference.

RTX 50-series / Blackwell needs a CUDA 12.8+ PyTorch build. CUDA extension
installation selects matching Torch/torchaudio 2.9.1 builds by compute capability.
Maxwell/Pascal uses cu126; Blackwell uses cu128. Turing/Ampere/Ada/Hopper/Volta
keeps an installed compatible cu126/cu128 build; a fresh install uses cu128.
This includes A100, RTX A6000, RTX 6000 Ada, Quadro RTX 6000 and RTX PRO 6000
Blackwell without treating their shared model numbers as the same architecture.
Unknown models use nvidia-smi compute capability where available; otherwise the
installer requests an explicit choice. Mixed legacy/Blackwell GPUs require
selecting a visible CUDA device or an explicit build. Environment checks execute
a small CUDA matrix operation instead of
relying on GPU enumeration. For RTX 50-series GGUF, a separate pinned llama.cpp
CUDA 13.4 runtime is used; older GPUs retain the existing CUDA 12.4 runtime.
Keep the NVIDIA driver current, including support for the selected GGUF runtime.
This change has no RTX 5070 hardware validation yet.

For an existing installation reporting `no kernel image is available`, close
the controller, update the NVIDIA driver, update project files, and rerun
`prepare_media.bat cuda:0`. Then reopen the controller and check its environment.
No separate CUDA Toolkit installation is required by these prebuilt wheels.

Double-click root `prepare_media.bat` to install live translation extensions
with uv into `Resource/MediaRuntime`. It uses the saved controller model (Index
by default), detects NVIDIA for the CUDA build, otherwise installs CPU Torch,
prepares the selected GGUF runtime when applicable, and verifies readiness.
Full uv installation errors remain visible in the console. uv must already
exist; `prepare.bat` or manual uv installation can provide it.

Optional commands from the project root:

```bat
prepare_media.bat cpu
prepare_media.bat auto index-q4
prepare_media.bat cuda:0 hymt
prepare_media.bat cuda:0 index cu126
prepare_media.bat cuda:0 index cu128
```

Successful verification saves the inference Python path for the controller.
The third BAT argument overrides detection when the architecture cannot be
identified; it still runs the final CUDA execution check. Window configuration
can use `AINIEE_MEDIA_CUDA_BUILD=cu126` or `cu128` as an explicit override.
Restart the controller and check the environment. Model weights are downloaded
separately. A failed CUDA check does not silently switch to CPU. This installs
the complete live ASR/translation libraries directly; it does not sync the older
Index-Echo experimental project extra into the base environment.

## macOS testing build

For a terminal installer that exposes complete dependency errors, run
`bash prepare_media.sh`, or double-click `PrepareMedia.command`. It reads the
saved model, creates the same native arm64 inference environment as the
controller, installs Torch/ASR/translation libraries directly with uv, and
selects MLX, Metal GGUF or MPS as appropriate. Existing runtime assets are
preserved with `--allow-existing`. Verification saves the Python path only
after successful readiness checks. uv must already be installed.

```bash
bash prepare_media.sh
bash prepare_media.sh cpu
bash prepare_media.sh auto index-q4
```

The installer currently targets Apple Silicon macOS. It reports inference
readiness separately from optional native audio-helper compilation; missing
Command Line Tools does not make installed inference libraries fail. Models
and recording permission remain separate. Audio-helper build errors stay
visible for diagnosis. No automatic device/model fallback is performed.

From Finder, open `LaunchLive.command` (or run `bash LaunchLive.command` in the
project directory). The MLX path needs macOS 14+ and native Apple Silicon.
The launcher needs Python 3.12 with Tk; the python.org
macOS installer includes Tk. Homebrew users need `python@3.12` and
`python-tk@3.12`. Use native arm64 Python on M-series Macs; Rosetta cannot run
the MLX path. The launcher prepares a small isolated desktop environment on
first use. Existing CLI/TUI live-translation entries also select macOS behavior
automatically via the same `DesktopApp`, without a separate set of preferences.

The Mac controller uses Aqua controls, PingFang subtitles, trackpad scrolling,
transparent subtitle/background layers and Cocoa mouse passthrough. Lock/unlock
remains accessible from the controller. The Cocoa layers join Spaces and allow
full-screen auxiliary windows; actual full-screen ordering depends on macOS.
The background layer always ignores mouse events on macOS; the controller and
its dialogs sit above the subtitle layer while it is visible. Subtitle sizing
waits for layout, returns to the selected base height after long text, and does
not persist automatic growth as the next launch's size. Each new caption replaces
the displayed text; previous captions remain available in the history dialog.
Mac transparent content is explicitly invalidated after redraw.
Windows device/font preferences copied to a Mac are normalized in memory;
unrelated preferences are preserved.
Compute choices follow the selected model: GGUF offers Metal/CPU and excludes
MPS/MLX. An incompatible saved backend is reset to auto, and choosing a different
model rechecks its backend while preserving compatible manual choices.

On native Apple Silicon, `auto` selects:

| Selected checkpoint | Translation library | Recognition |
|---|---|---|
| Index original safetensors (Qwen3.5) | Apple MLX / mlx-lm on Metal | SenseVoice CPU |
| Index / HY-MT GGUF | llama.cpp Metal | SenseVoice CPU |
| HY-MT original safetensors | PyTorch MPS | SenseVoice CPU |

Click **Configure inference** to prepare the isolated inference environment,
then **Download models** for the selected checkpoint. MLX 0.32.3 / mlx-lm 0.32.0
load the existing local Index weights; no third-party converted weights or
implicit model switch are used. Current MLX support requires `model_type=qwen3_5`.
An older/different Index checkpoint reports an error; choose MPS or Metal GGUF
explicitly in that case. MPS operator support for HY-MT requires runtime
validation. Accelerated errors never trigger an automatic CPU/quality fallback.
Intel Macs select CPU, but automatic Python inference installation currently
requires Apple Silicon because Torch 2.9.1 has no Intel macOS wheel. Opening the
controller and GGUF runtime support do not establish Intel inference readiness.
MLX requires Apple Silicon. For smaller unified
memory systems, the selectable Q4 GGUF models reduce weight memory usage.

Metal/CPU llama.cpp macOS arm64 and x64 archives are pinned to b11552 and their
GitHub release SHA-256 digests, use filtered tar extraction, and retain executable
permissions. Native inference environments and llama.cpp installs have separate
architecture directories. The controller checks Metal/MPS availability; the
GGUF backend also checks llama.cpp's actual device list before loading weights.

### Native macOS system audio

The audio selector defaults to **System audio (native capture)**. macOS 14.2+
uses Core Audio Process Tap; macOS 13–14.1 uses ScreenCaptureKit audio. A separate
**System audio (ScreenCaptureKit)** option permits explicit selection on newer
systems too. Neither path needs a virtual driver or changes the system output.
Tap capture is unmuted so normal playback remains audible. Permission failure
never selects a microphone or a different backend automatically.

The source build compiles `native/SystemAudio.swift` into a private capture
helper app using Xcode 15.3+ Command Line Tools. Install the tools with
`xcode-select --install`, then click **Configure inference**. Capture also checks
and builds the helper on first start if necessary. The app has a stable bundle
identifier, recording usage description, and local ad-hoc signature; it is not
Developer ID signed or notarized. First use requires consent in macOS **Privacy
& Security → Screen & System Audio Recording** (wording depends on OS version).
Depending on launch context, the permission may be associated with the helper
or Terminal; restart after changing it. SDK/compiler/permission failures appear
in the controller. Opening **System audio** does not prompt until capture starts.

The native helper converts input using AVAudioConverter to 16 kHz mono float32,
sends a validated format header plus PCM over an owned pipe, and the existing
worker converts to signed-16 PCM for VAD/ASR. No capture file or video frame is
saved. Buffers are bounded; overflow errors are explicit. ScreenCaptureKit
silence without buffers is padded with zero samples. Closing the input pipe or
receiving a termination signal stops capture and releases tap/aggregate objects.
Switching audio output/Bluetooth devices may require restarting capture.

For optional virtual-device capture instead:

1. Install [BlackHole 2ch](https://existential.audio/blackhole/) or use Loopback.
2. Open **Audio MIDI Setup** and create a **Multi-Output Device** containing
   both the listening speaker/headphones and BlackHole; enable drift correction
   for the non-clock device as appropriate.
3. Choose that multi-output device as the system output. In the controller,
   refresh and choose **BlackHole 2ch** explicitly.
4. Grant **Microphone** access to the launching application (normally Terminal /
   Python) in **System Settings → Privacy & Security**, and restart it if needed.
5. Choose languages, start translation and play speech. The controller continues
   showing recognition/translation timing and dropped-segment telemetry.

Driver installation, changing system audio routing and granting OS permissions
are manual; the app does not alter them.
An explicitly selected microphone supports live speech and mono CoreAudio input.
The explicit microphone/virtual-device path does not use ScreenCaptureKit.
Bluetooth/device switches may require refreshing and restarting the session.

This is a source testing build, not a signed/notarized macOS app bundle. Linux
unit tests cover platform routing, helper build plans, real pipe transport with
a fake producer, and mock streaming; Swift compilation and macOS audio,
Cocoa/Tk rendering, MLX/MPS inference and latency require real Mac validation.
See `Docs/MACOS_LIVE_TRANSLATION_TEST.md` for the tester handoff.

## GGUF and Windows GPU backends

The model list also offers Index-Translate-2B and HY-MT2-1.8B in Q4_K_M / Q6_K.
These use a local, loopback-only llama.cpp server with streamed text, a random
session API key, owned process lifetime and model-resident inference. Downloads
include only the selected GGUF, not every quantization tier in the repository.

Compute choices are `auto`, `cuda:0`, `vulkan` and `cpu`. Auto uses CUDA when
Torch can use the NVIDIA GPU; AMD/Intel GGUF translation uses Vulkan, with CPU
SenseVoice recognition. Without a detected GPU it selects CPU. Transformers
checkpoints cannot use Vulkan and use CPU on AMD Windows instead. DirectML is
not included. Vendor discovery is a selection hint: llama.cpp must actually list
a usable CUDA/Vulkan device; a driver failure reports an error rather than
pretending GPU acceleration is active. Manual backend selection is available.

Configure inference prepares Python dependencies as needed and the selected
official Windows x64 llama.cpp backend. CUDA, Vulkan and CPU archives are pinned
to b11552 and SHA-256 verified before extraction. It does not download models
or switch a model implicitly. Vulkan has been exercised on the available
RTX 2080 Ti; AMD driver compatibility and performance require the AMD device.

## Desktop live translation

On first launch, choose Use live translation only to open the controller without
language/provider/Agent setup. Closing the controller ends that launch; the
general wizard remains pending for the next normal launch. Environment checks
and dependency/model preparation remain available inside the live controller.

The desktop and TUI list concrete checkpoints. Model selection and download
use the same catalog, with separate directories so installed models coexist:
The desktop catalog uses a selectable table of model names, download sizes,
estimated VRAM and local status. Selecting a row displays its introduction.
Download fetches that row's model without changing the active translator;
Use selected model switches to a locally available checkpoint. The current
selection and download result remain visible in the same window.

| Model | Download | Estimated translation VRAM (FP16, short text) |
|---|---:|---:|
| Index-Translate-2B | 4.57 GB | 6–8 GiB |
| HY-MT2-1.8B | 4.09 GB | 5–7 GiB |
| Index-Translate-9B | 19.33 GB | 24–28 GiB |
| HY-MT2-7B | 16.07 GB | 20–24 GiB |

HY-MT2 suits general-purpose translation. Index is better suited to anime,
games, ACG communities and related online expressions. Both families support
general translation; these recommendations help users choose for their content.

Larger models may improve quality but run more slowly; smaller models use less
space and run faster with average quality. Actual results depend on hardware
and text. VRAM ranges are planning estimates, not hard limits; allow another
1–2 GiB for GPU SenseVoice and more for longer context. Downloads include the
shared SenseVoice assets if needed. The download confirmation names the chosen
checkpoint, total size and destination. Existing `index` / `hymt` preferences
continue to select the original 2B / 1.8B models. The catalog validates all
required shards for larger checkpoints before reporting local availability.

The TUI Settings menu includes Live translation settings. Its
ConfigRegistry-backed submenu is rendered inside the normal settings table;
individual media fields are registered under `media_settings` and use the same
table renderer. The desktop and TUI persist their values in the shared media
preferences file rather than separate copies of a batch Profile.
It edits the same
project-level preferences as the desktop, including fonts, colors, outline,
background opacity, bilingual mode, lock, dimensions, model and device choices.
Desktop changes are saved as they are edited, so the TUI sees them on return.
While the desktop is open through the core, the TUI blocks menu interaction and
monitors its process. Closing the controller resumes the TUI; terminating the
core closes the desktop via a control-pipe watchdog. Inference also watches its
GUI parent so it does not retain audio/CUDA resources after abnormal termination.
While locked, the core displays a diagnostic panel refreshed four times per
second. It includes current local time, runtime/stage elapsed time, recent
events, audio segment duration, ASR/translation/first-text times, queue and
endpoint waits, end-of-segment-to-caption latency, backlog/drop counts and
per-second capture/VAD heartbeats. Narrow terminals show a compact event list
with the latest metrics above it. Frame capture time includes waiting for audio;
it is not CPU compute time. The diagnostic channel contains no source or
translated text and does not write a diagnostic log file by default; text
recording remains controlled by the recording option.
Inference uses an explicit `python -u -m ModuleFolders.Media.worker` subprocess
in the selected environment, avoiding the multiprocessing spawn handshake.
Startup reports worker start, runtime imports, translation loading, ASR loading
and warmup separately. Windows lifetime monitoring polls PeekNamedPipe instead
of blocking CRT input reads that can stall NumPy/Torch native DLL imports. A
worker with no startup event within 60 seconds reports an error rather than
waiting indefinitely.

Every desktop launch automatically checks dependencies and the chosen device
in a subprocess. Imports, relevant versions and CUDA availability are inspected.
Audio output enumeration runs independently first, using the saved media Python
and falling back to available installed environments. Child probes receive empty
standard input and sanitized Python path variables, so the core's lifetime pipe
is not inherited by probes. The core pauses ordinary background prewarming while
the live window is active. The TUI and CLI supervisor launch the desktop with
the core Python environment (including Tk/Tcl and UI dependencies). The chosen
media interpreter is used for audio discovery, environment checks and inference.
Missing Torch or model files do not prevent the controller from opening.
Desktop startup failures appear in the terminal and managed diagnostic panel.
If required dependencies are missing or broken, a consent dialog offers automatic setup;
declining does not install or start capture. The installation button can retry.
Torch and other media libraries remain outside base dependencies and are installed
into `Resource/MediaRuntime`. CUDA and CPU builds are selected explicitly.
The model-download button separately asks permission, downloads SenseVoice plus
the selected translator into the chosen model directory, resumes partial files,
and verifies pinned official ModelScope revisions and SHA-256 hashes. Downloads
use `https://modelscope.cn` directly, including SenseVoice (`iic/SenseVoiceSmall`),
Index (`IndexTeam`) and HY-MT2 (`Tencent-Hunyuan`), with no Hugging Face fallback.
Only the selected GGUF file is fetched for quantized models. Existing model
directory names remain compatible; `HF_ENDPOINT` does not affect this downloader.
No automatic model download
runs when the window opens. Network failures leave settings and downloaded parts
available for retry. A source Python 3.12 environment (or uv) is required for setup;
frozen-distribution installation and cross-platform capture need separate validation.
The current source launcher has been validated on Windows. Fresh multi-GB
installation and public-model downloading require network access and have not
been repeated as part of the desktop integration tests; installer commands,
consent branches and download hash verification have regression coverage.


Open the independent desktop controller from the TUI's **Live Translation
(Subtitle Window)** menu, or from the project root:

```powershell
.venv-win\Scripts\python.exe ainiee_cli.py live
.venv-win\Scripts\python.exe -m ModuleFolders.Media --model-root G:\AiNiee-Models
```

The controller selects an audio output device, source/target languages, CPU or
CUDA, and Index/HY-MT2. Press Start to load local models and begin capturing the
selected output. Stop releases the worker process; closing the controller also
stops it. Opening the controller alone does not start capture. `--start` opts in
to starting after the windows open. The audio and model path is currently
validated on native Windows; other desktops require platform validation.

Subtitles appear in a separate borderless window. Drag the subtitles to move
it; adjust width/height or reset its position in the controller. It supports
0–100% background opacity, 16–48 point text, always-on-top, and explicit bilingual
or translation-only display modes. Text stays fully opaque on its own color-keyed
window; a separate background window follows its geometry. At 0% background,
drag the visible text to move the subtitles. Escape or Hide subtitles hides both layers without stopping capture;
Show subtitles restores it.
Font and colors opens system-font selection, translation boldness and separate
color pickers for translation, source text and background.
An outline-width slider supports 0–6 pixels (0 disables it), with a separate
outline-color picker. Source and translation use the same outline setting. Changes apply live
and are restored from preferences on the next launch. Font/color changes do
not reduce glyph opacity. The transparent key is kept distinct from selected
text colors on Windows so choosing that color cannot make the text disappear.
Lock position forces both layers to remain on top, disables dragging, and passes
mouse clicks through to underlying applications. Unlock in the controller to
restore dragging; the previous always-on-top preference is retained. Windows
uses native layered-window input styles. Lock/click-through is disabled on other
platforms; background-only transparency is currently validated on Windows only.
The controller remains fully opaque for accessible controls. It can be moved
away or minimized while the subtitle window stays visible.

Model and appearance preferences are saved to `Resource/media_overlay.json`
as they are edited and when closing the controller. Recording is off by default;
only the last 2–3 completed captions are retained in memory and displayed in the
overlay. Recent translations opens a scrollable view of these entries so wrapped
text can be read fully. Dynamic translation context is off by default (0).
Users may enable up to 3 previous source/translation pairs within a
1600-character budget. In-memory caption history and recording remain independent
of the context sent to the translation model.

When Record ASR and translations is enabled, events received from then onward
are written to a new UTF-8 JSONL file in the selected recording directory, including
ASR source text and final translated text. Intermediate generated text and audio
are not recorded. Disabling recording or stopping closes the file; earlier files
remain available. Enabling recording does not retroactively save in-memory history.
Both recording and history/context settings are available in the TUI and desktop.
The model directory is selected through the controller or
`AINIEE_MEDIA_MODEL_ROOT`; an existing `G:\AiNiee-Models` is detected on Windows.
Models are not downloaded automatically. Existing batch profiles are unchanged.

Dependencies are optional: Torch/torchaudio with matching CUDA builds,
Transformers 5.6.0, accelerate, FunASR, sentencepiece, Silero VAD, ONNX Runtime,
SoundCard and NumPy, plus Python's Tk support. The desktop entry reports missing
dependencies in the control window. Desktop labels and status messages use
the existing AppI18N loader and all seven project locales. The Web/Tauri interface, offline-video
workflow are not included in this desktop integration.

The simultaneous-translation candidate pipeline is:

```text
16 kHz mono PCM -> Silero VAD -> endpoint detector -> segment queue
    -> SenseVoiceSmall -> Index-Translate-2B / Hy-MT2-1.8B -> CaptionEvent
```

Index-Translate-2B is the initial desktop selection. Native Windows capture
and inference have been exercised, including short-sentence Hy-MT2 comparisons;
these do not establish general quality or performance guarantees. CLI/TUI now
launch the desktop controller; Web integration is pending. Existing Index-Echo
experiments remain available separately.

## Shared interfaces

- `SpeechRecognizer.transcribe(AudioSegment, language=...) -> Transcript`:
  replace SenseVoice with a higher-quality local or remote ASR for offline video.
- `TextTranslator.translate(text, source_lang=..., target_lang=..., context=...)`:
  replace the small local model with a higher-quality translation backend.
- `CaptionSink.emit(CaptionEvent)`:
  output consumers can implement this contract for overlays, Web events or
  subtitle writers; the experiment currently writes JSONL directly.
- `CascadeProcessor` composes recognition and translation independently of
  capture, VAD, model choice, file decoding and queue policy.

Backend imports are lazy; importing `ModuleFolders.Media` does not require
Torch, FunASR, audio libraries or model downloads. Local translation weights
must already exist on disk. Downloading models is an explicit separate step.

## Live policy

Capture and segmentation continue on the main thread while a single inference
worker preserves segment order and translation context. The experiment uses
512-sample Silero ONNX frames, a 450 ms endpoint silence, up to approximately
6 seconds of audio per segment (one frame of rounding is possible), 256 ms
pre-roll, a 160 ms trailing pad and a queue of four segments. Only observed
speech contributes to the 160 ms minimum speech requirement.

An overloaded live queue drops the oldest pending segment and reports the
total drop count. This is an explicit experimental latency policy, not a
lossless mode. In-flight inference finishes normally. Context is bounded to
two translated segments and 1600 combined characters by default.

SenseVoiceSmall recognizes Chinese, Cantonese, English, Japanese and Korean.
It is used for finalized short-segment recognition, not native incremental
streaming. Emitted timestamps describe VAD segments, not word or sentence
alignment. The JSONL includes ASR, translation and queue times, plus final
latency from the segment end; no token-first latency is currently measured.

## Offline extension

Offline processing supplies its own `AudioSegment` sequence and model
instances to `CascadeProcessor`; it must preserve all segments rather than
reuse the live queue's drop policy. Future batch inference, speaker metadata,
word alignment and multi-cue splitting belong in richer adapters/contracts;
the current recognizer returns one final transcript per segment. File decoding,
resume, subtitle export and AiNiee provider integration are not implemented
by this prototype.

The experiment's `--audio` mode is a serial, lossless recording replay using
the same live endpoint settings. It is not the future offline-video product.

## Live latency experiment update

The Windows launcher now captures every physical channel and mixes down in
Python, avoiding SoundCard's documented WASAPI single-channel recording issue.
It uses a 450 ms normal endpoint; after 3 seconds, a 192 ms speech pause can
submit the segment early. An 8-second maximum remains as a bounded fallback,
so uninterrupted speech can still be cut within a word. These are acoustic
boundaries, not word alignment or semantic sentence detection.

Live context defaults to off; optional context uses up to three completed segments
with a 1600-character budget. Provisional
translation text is displayed as the model generates it; final JSONL events
remain unchanged and include `translation_first_text_ms`. This metric starts
after recognition and measures the first nonempty decoded text callback; it
does not include audio buffering, endpoint wait or ASR, and is not final-caption
latency. No claim is made that this speeds up complete model generation.

## Model/runtime notes

Official checkpoints:

- <https://huggingface.co/IndexTeam/Index-Translate-2B>
- <https://huggingface.co/tencent/Hy-MT2-1.8B>
- <https://huggingface.co/FunAudioLLM/SenseVoiceSmall>

The translation experiment uses Transformers 5.6.0 and greedy generation with
thinking disabled and a 256-token output limit. Hy-MT2's official recommended
sampling settings differ; greedy generation is an experiment setting for a
controlled live comparison. Float16 is the initial CUDA dtype for the tested
RTX 2080 Ti; native BF16 support must not be assumed. ASR defaults to CPU so
its GPU use does not compete with translation; `--asr-device` can override it.

No optional dependency has been added to the main project or lockfile. Use an
isolated/native runtime when installing model dependencies. Keep Torch and
torchaudio versions and CUDA builds matched.

## Windows experiment

Run these from the project root after preparing dependencies:

```powershell
.venv-win\Scripts\python.exe tmp\test\test_prepare_media_models.py index hymt sensevoice

.venv-win\Scripts\python.exe tmp\test\test_media_cascade_runner.py --smoke --family index
.venv-win\Scripts\python.exe tmp\test\test_media_cascade_runner.py --smoke --family hymt

.venv-win\Scripts\python.exe tmp\test\test_media_cascade_runner.py --list-devices
.venv-win\Scripts\python.exe tmp\test\test_media_cascade_runner.py --live --family index --source-lang ja --target-lang zh --seconds 60
.venv-win\Scripts\python.exe tmp\test\test_media_cascade_runner.py --live --family hymt --source-lang ja --target-lang zh --seconds 60
```

Each run writes a new JSONL file under `tmp/test/`; existing output paths are
never overwritten. Use `--audio PATH` to replay a recording and
`--context-segments 0` to test isolated-segment translation.
