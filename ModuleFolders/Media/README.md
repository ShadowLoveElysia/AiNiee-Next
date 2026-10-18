# Media translation backends

## Video file translation

Use **Video translation** in the TUI main menu (including the Tasks group), or
run `python ainiee_cli.py video` / `python -m ModuleFolders.Media.video_tui`.
This terminal workflow requires no Tk window. It selects a video, output folder,
languages, local/cloud ASR, local recognition model, translation LLM and glossary
source. It asks for a subtitle mode on first use, and has its own submenu for
changing the saved subtitle mode and opening registered media settings. The
terminal shows stages, progress and elapsed time; Ctrl+C cancels the worker,
and a second Ctrl+C forces cleanup. It waits for actual completion and prints
the finished paths before returning to the menu.

Alternatively, open **Video translation** in the media controller, or run
`python -m ModuleFolders.Media --video` (`python ainiee_cli.py live --video`
through the TUI launcher). Choose the ASR, translation model and languages
in the controller, then choose a video and output folder in the file
window. Stop live capture before starting a file job.

Each start explicitly asks for local or cloud ASR, initially selecting local.
Local mode uses the controller's recognition model (including its loopback vLLM
option). Cloud mode accepts an HTTPS OpenAI-compatible API base URL, model and
API key, and uploads each speech segment to `/audio/transcriptions` only after
that selection. Cloud API URL, model and key are saved in `Resource/media_overlay.json`
and registered under **Settings → Media settings**. The key is masked in the
settings table and entered with a password prompt. The ASR dialog restores these
values on subsequent starts but still defaults to local mode. These settings do
not alter the live recognizer. Cloud errors omit response bodies;
redirects are rejected. Translation and temporary-term extraction still use the
selected local LLM.

The first job asks for **switchable subtitles** or **burned-in subtitles**.
This preference is saved as `video_subtitle_mode` in `Resource/media_overlay.json`
and can be changed with **Subtitle output**. Dismissing the choice cancels the
start; there is no implicit default.

The pipeline extracts the first audio stream to 16 kHz mono PCM with FFmpeg,
applies FFT noise reduction (`afftdn`), segments speech with Silero VAD,
recognizes every segment into a source SRT, translates each cue with the
selected local LLM, and invokes FFmpeg to create the finished video. Recognition
and translation run serially in an isolated media-runtime worker; no live
backlog policy drops segments. Cue times are VAD segment times, not word alignment.
The original audio, rather than the recognition-only denoised audio, goes into
the finished video. The selected vLLM ASR service remains available when configured.

**Glossary source** defaults to automatic temporary extraction for each new
video. After ASR, the selected LLM reads the complete transcript in bounded
batches, extracts names and specialist terms, and establishes one validated
mapping before subtitle translation begins. Temporary terms remain in worker
memory and are not saved to preferences or long-term glossaries. Malformed
extraction is retried once; repeated failure stops with the source SRT preserved.
The existing live glossary is never inherited. To use a saved glossary instead,
explicitly choose **Choose a manual glossary for this video** and a non-empty
profile in the video window. Manual mode uses only that profile. Opening a new
file resets the choice to automatic extraction; the source selection is not
persisted. At most 100 mappings are retained, with at most 16 matching terms
injected into each cue's translation prompt.

- Switchable mode produces MKV with a selectable translated SRT track and copies
  the first video stream and all audio streams without re-encoding.
- Burned-in mode produces H.264/AAC MP4 with translated subtitles rendered into
  the image. It re-encodes video and audio.
- Both retain source and translated UTF-8 SRT files. Each job creates a unique
  output folder and preserves the input. Failures or cancellation retain completed
  SRT files; the final video appears only after successful muxing/encoding.

Install FFmpeg and ffprobe on `PATH`, place their executables in
`Resource/MediaRuntime/ffmpeg/bin/`, or set `AINIEE_FFMPEG` and `AINIEE_FFPROBE`
to executable paths. Burned-in subtitles require FFmpeg with libass and libx264,
plus an installed font covering the target language. No FFmpeg binary is bundled
or downloaded automatically by this feature. Input files must contain both video
and audio. The file window reports the current stage, recognition/translation
progress, final paths and cancellation state.

## Application audio capture

On x64 Windows build 20348 or later, enable **Capture one application's audio**
in the controller, refresh the list, and select the browser or player before
starting. Capture includes that process and its children across audio devices;
other applications' audio is excluded. Multiple tabs in the same browser may
share the selected process tree. This selects an application, not an individual
browser tab. After the application restarts, refresh and select it again.

The process identity includes its creation time to reject reused PIDs. Target
exit or capture failure stops the session and requires a new selection; capture
never switches to system audio automatically. Application selection is not
persisted between launches. Existing system-output and macOS capture remain
available. This application mode is currently Windows-only.

The owned native bridge is built on first use with Windows' .NET Framework
C# compiler, without installing a compiler or audio-routing driver. Source is
`native/ProcessAudio.cs`; compiled helpers live under the MediaRuntime directory.
PCM travels through a bounded memory pipe as 16 kHz mono float samples. No audio
file is created. Packaged distributions must include the native source file.

## Streamer glossaries and chat length

Use **Streamer glossary → Edit** to name a glossary and add source language,
source term, target language and preferred translation. Each entry works in
both directions. **Save and select** persists only the explicitly entered
glossary. Choose the desired glossary, then start live translation; changing
the active glossary requires stopping the session first.

The selected glossary is shared by live subtitles and private translations.
Only matching terms for the current language pair enter the prompt (up to 16
matches and 1,200 characters). Glossaries guide the model's wording; they do
not repair speech recognition errors or guarantee that every model follows a
preferred translation. Profiles support up to 100 terms each.

The private translation panel counts Unicode code points, including spaces
and punctuation, and accepts an optional 0–1,000 character limit (0 disables
the limit). Overlong results remain visible and copyable. **Shorten** asks the
same local model to translate the submitted source more concisely, without
live context or subtitle output. It runs only on request and still displays
any excess after completion; model instructions cannot guarantee the length.
Different chat platforms may count characters differently. Only the limit
setting is persisted; typed messages and translations remain in memory.

## Two-way translation window

Open **Two-way translation** in the live controller to translate typed chat
messages with the currently running local translator. Start live translation
and wait for readiness first. The panel defaults to the reverse of the live
language pair and supports selecting either direction, swapping languages,
Ctrl+Enter (Command+Enter on macOS), and explicitly copying the result.
Input is limited to 2,000 characters; only one panel request can be pending.

The panel attaches beside the controller (or below on narrow screens). Moving
either window moves the other. Closing the panel leaves live capture running;
closing the controller also closes the panel and its owned worker. Closing the
panel clears its contents and cancels a queued request. An already running
inference finishes normally, with its result discarded by the closed panel.

Private requests run on the same inference thread and loaded translator, after
the current job and before queued audio. Audio capture continues, retaining its
bounded backlog/drop policy. Every private translation uses empty context and
temporarily disables subtitle streaming callbacks. Its dedicated result events
never reach subtitles, session history, recordings, preferences, or diagnostics.
Text stays in memory; no remote translation API or additional model is used.

## Model selection and downloads

The model catalog contains two separated sections: **ASR — audio to source
text**, and **LLM — source text to translation**. Each section lists its own
models, download sizes and installed/current status. Separator rows only explain
the role and cannot be downloaded or activated. Downloading a model row fetches
only that model; Use switches only its recognizer or translator after local
availability is checked. Download does not change the active selection.

The main controller's **Download selected models** button prepares both current
ASR and LLM choices. The confirmation names the exact models and total size.
SenseVoice remains the default recognizer; optional Qwen ASR weights can be
downloaded independently from this same catalog.

## Download feedback

ModelScope ASR/translation weights and llama.cpp archives report transferred
bytes, percentage, current transfer speed and estimated time remaining, refreshed
about twice per second. Resumed bytes count toward completion but not download
speed. Parallel archive ranges aggregate their positions; retries do not count
the same stored bytes twice. Assembly and hash verification are separate stages,
and failures never report successful completion. Unknown totals show `?` instead
of a fabricated percentage or ETA.

Direct terminal runs show readable progress; captured subprocesses emit JSON
events for the controller. The controller displays the current transfer and
forwards it to the managed TUI diagnostic panel or standalone terminal.
Media dependency installation resolves exact artifacts with uv, downloads each
wheel/source archive through a measured, resumable SHA-256 checked transfer, and
installs the local files with uv. Torch now reports actual byte speed even when
the controller captures installer output. This path requires a uv version with
`pip compile --format pylock.toml` (tested with 0.13.0); installed exact package
versions are skipped and verified downloaded artifacts are cached under
`tmp/package-downloads`. No environment is cleared. Dependency resolution and
source-package build requirements still use uv's native output; they do not have
a fabricated byte rate. Other bootstrap installers retain native uv/pip output;
stderr is no longer discarded, and inherited `UV_NO_PROGRESS` cannot suppress
preparation progress. Model/package installers remain separate
from model inference and no audio/source text is included in download events.

Package request failures report bounded HTTP/TLS/DNS/timeout categories and the
download hostname, without authenticated URLs. Python requests respect explicit
CA bundle settings. After repeated network failures, the same URL can be retried
with system curl (Windows `curl.exe`), retaining byte progress, resume and the
original hash. No certificate verification bypass or automatic source change
is used. Filesystem permission failures are reported as filesystem failures.
Both media install stages pin matching Torch/torchaudio versions. Installing
other dependencies also preserves an existing Torch pair unless explicitly
requested otherwise. The runtime report includes installed versions and bounded
import errors; it also loads the bundled Silero TorchScript model and runs one
512-sample silent-frame check. `missing: silero_vad` therefore covers both a
missing package and an unusable bundled VAD model before capture starts.
On Windows, the VAD TorchScript resource is read through Python bytes before `torch.jit.load`; this avoids the native Torch path reader failing on Chinese/non-ASCII directories. This workaround is specific to the VAD resource; other Torch model loaders still require separate path validation.
Installer GPU discovery runs in short-lived children so the installer does not
hold Torch DLLs open while replacing them. If Windows reports access denied for
`torch/_C*.pyd`, close capture and other processes using that environment before
retrying; antivirus or folder permissions can also cause this error. Verified
download cache files are preserved and no automatic process killing is performed.

Application updates, Web packages and the language detector use the same transfer
display. Manga downloads retain their existing Rich download/speed/ETA display,
with speed/ETA added to plain-terminal progress and byte callbacks. Shell uv
bootstrap curl/wget progress is visible. Builds that hide the entire console,
including a GUI shell without an attached terminal, still need their own viewer
for inherited installer output. No download benchmark or native platform render
has been established by these progress changes.

## Native Qwen3-ASR GGUF trial

SenseVoice stays the default. Select **Qwen3-ASR-0.6B · Q8_0 (GGUF)** in the
ASR section to try the resident native backend, or select the 1.7B Q8 model for
quality comparison. Configure inference, download the selected ASR row, then
start capture. No WSL or manually started service is needed. Windows supports
CUDA/Vulkan/CPU; Mac supports Metal/CPU. Automatic detection uses the same GPU
architecture/runtime selection as GGUF translation, with independent ASR device
choices. Explicit unsupported devices fail rather than silently falling back.

ModelScope downloads include exactly two files: the Q8 decoder and Q8 audio
encoder/projector (`mmproj`). Both must be present. The 0.6B pair is about1.02GB,
1.7B about2.52GB. They have separate folders from original safetensors and `-hf`
weights; files are never renamed or deleted. Download progress, resume and
SHA-256 verification use the existing public ModelScope downloader.

The controller owns a separate loopback-only llama.cpp b11552 process for ASR,
with a random session key and Windows kill-on-close job. Weights stay resident;
16kHz WAV data is sent in memory to its audio-capable chat endpoint, using the
model's ASR template and a language hint. No audio file is saved. The parser
removes ASR language markers before forwarding text to the selected translator.
Flash Attention is requested as llama.cpp `auto`, which is different from the
Python FlashAttention2 package. CPU/GPU audio encoder placement follows the
native backend's supported defaults; service startup and actual timing require
hardware validation. Generation is greedy and bounded to256tokens per segment.

Both ASR and translation resident models consume memory, so keep the same
translator/audio/segmentation settings for comparisons. Start with0.6BQ8,
then1.7BQ8. The status/TUI reports ASR time, translation time, endpoint wait,
queue wait, drops and segment-end-to-caption latency. Warmup/model loading are
excluded from per-caption timings. These values do not measure speech onset
latency. No400ms guarantee or independent benchmark is claimed.

Standalone ASR timing, after configuring/downloading:

```powershell
Resource\MediaRuntime\Scripts\python.exe -m ModuleFolders.Media.asr_benchmark "short.wav" --model-root "G:/AiNiee-Models" --recognizer qwen-gguf-0.6b --device auto --language ja --runs 5
```

```bash
Resource/MediaRuntime/macos-arm64/bin/python -m ModuleFolders.Media.asr_benchmark short.wav --model-root tmp/models --recognizer qwen-gguf-0.6b --device metal --language ja --runs 5
```

Use a16kHz mono signed16 WAV, up to28seconds. The result separates load/first
inference/warm median/max and ASR realtime factor without printing transcripts.
Repeat with1.7B or SenseVoice and the same audio. Protocol/mock tests passed,
but native model loading, encoder GPU support, recognition quality and actual
latency still need your Windows/Mac test data. Linux is not covered by the
current binary installer; vLLM remains a separate developer option below.

## Optional Qwen3-ASR via vLLM / FlashAttention 2

SenseVoice remains the default installed recognizer. The previous Qwen native
Transformers recognizer has been removed. Optional Qwen 0.6B/1.7B entries now
use a separately started local vLLM service. LLM translators remain unchanged.
Original-format Qwen weights are fetched from pinned ModelScope repositories;
the old `-hf` folders are not renamed, deleted or compatible with this service.

Official vLLM requires Linux; Windows can run the service inside WSL with NVIDIA
GPU access and connect through localhost. This is not a native macOS acceleration
path. MLX-Audio and GGUF versions exist but are not integrated in this change.
The isolated service uses `qwen-asr[vllm]==0.0.6` / vLLM 0.14.0 and its own pinned
Torch/Transformers dependencies, never installing these into the translation
runtime. Run the following from the project root in Linux/WSL:

```bash
bash prepare_qwen_vllm.sh nju qwen-vllm-0.6b tmp/models
bash LaunchQwenVllm.sh --recognizer qwen-vllm-0.6b --model-root tmp/models --attention fa2
```

Use `qwen-vllm-1.7b` in both commands for the larger model. You can reuse
original-format weights downloaded by the controller by supplying their parent
model root (e.g. `/mnt/g/AiNiee-Models` in WSL). Runtime packages use the selected
source and measured download progress; model weights use ModelScope. Setup does
not start capture or the service. Stop the service terminal with Ctrl+C.

The launcher explicitly sets `--attention-config` to `FLASH_ATTN` with
`flash_attn_version=2`. FA2 mode checks Ampere-or-newer CUDA hardware; support
and active kernels must still be confirmed in service startup logs. Unsupported
hardware fails rather than silently choosing another attention backend. You may
explicitly pass `--attention auto` to let vLLM select another backend. CUDA Graph
remains enabled by default; `--enforce-eager` is not set. The audio encoder's
attention implementation is controlled internally by vLLM, so this setting is
not proof that every encoder/decoder operation uses FA2.

In the desktop select the matching **Qwen3-ASR (vLLM)** entry and set the service
address (default `http://127.0.0.1:8001/v1`). Click Check environment after starting
the service; model ID and service availability are checked. Only loopback HTTP
addresses are accepted, proxies bypassed and redirects blocked; no remote audio
upload or disk recording is performed. The service is loopback-only and not an
authenticated remote deployment. `auto`/CPU/MPS settings in the controller do not
select service hardware; its launching terminal owns GPU and attention settings.

The adapter sends finalized 16 kHz VAD segments to `/audio/transcriptions` and
returns source text to the existing translator. This is request-based short
segment inference, not incremental streaming ASR. Compare ASR time, queue wait,
drops and segment-end-to-caption latency using the same audio and translator.
ASR time includes local HTTP transport and service work. Warmup is outside the
per-caption metric. GPU memory fraction defaults to 0.25; use `--gpu-memory`
when explicitly allocating more/less memory alongside the translation model.

ASR-only repeatable test (16 kHz mono signed-16 WAV):

```powershell
Resource\MediaRuntime\Scripts\python.exe -m ModuleFolders.Media.asr_benchmark "short.wav" --model-root "tmp/models" --recognizer qwen-vllm-0.6b --endpoint http://127.0.0.1:8001/v1 --runs 5
```

Mock/local-HTTP tests establish protocol and config behavior only. No GPU vLLM
service, FA2 kernels, native WSL networking, recognition quality or latency have
been verified by this implementation. Do not infer real-time speed from package
installation or a successful model-list response.

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
not persist automatic growth as the next launch's size. The rounded subtitle
panel follows new captions. When unlocked and background opacity is at least 10%,
the mouse wheel or trackpad scrolls through the current session's captions;
Page Up/Page Down and End also work after focusing the panel. New captions preserve
the reader's position until scrolling back to the bottom or pressing End.
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
The owned translation and GGUF ASR servers explicitly use `--cache-ram 0`.
This disables b11552's default 8192 MiB host prompt-state archive; the active
model context and its bounded prefix reuse remain available.

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
recent captions can be scrolled directly in the overlay when unlocked with
opacity at least 10%. Locking the panel
or lowering opacity below 10% returns to the latest captions and disables scrolling.
Recent translations opens a separate view with 100-caption pages read on demand
from disk, with Older, Newer and Latest controls. There is no visible
history-count setting; the complete caption history is appended to a temporary
JSONL file and only the latest 32 captions are kept in memory for the live
overlay. The offset index is also on disk, so paging does not scan or load the
whole session. Restarting or closing the controller removes the temporary files.
Stopping capture preserves them for review until then. Dynamic
translation context is off by default (0).
Users may enable up to 3 previous source/translation pairs within a
1600-character budget. Caption history and recording remain independent
of the context sent to the translation model.

When Record ASR and translations is enabled, events received from then onward
are written to a new UTF-8 JSONL file in the selected recording directory, including
ASR source text and final translated text. Intermediate generated text and audio
are not recorded. Disabling recording or stopping closes the file; earlier files
remain available. Enabling recording does not retroactively save session history.
Both recording and translation-context settings are available in the TUI and desktop.
The model directory is selected through the controller or
`AINIEE_MEDIA_MODEL_ROOT`; an existing `G:\AiNiee-Models` is detected on Windows.
Models are not downloaded automatically. Existing batch profiles are unchanged.

Startup checks the inference environment alongside audio-device discovery, so a
slow device enumeration does not delay readiness checks. Audio enumeration has a
15-second per-interpreter limit and a 20-second total budget. Successful desktop
readiness checks are reused for 60 seconds for the same interpreter and backend;
package/interpreter changes and installation invalidate this cache. Failed checks
and vLLM service checks are always retried. Direct runtime `probe` commands always
perform a fresh check. CUDA checks use Torch's selected adapter rather than an
additional system inventory; GGUF checks inspect the Transformers package version
without importing it. CUDA execution validation is still performed. A readiness
check and the installer's Torch/CUDA discovery each allow up to 600 seconds for
cold native-library loading on slower disks. These checks run outside the GUI
thread. A readiness timeout includes the limit and last completed stage for
diagnosis. This limit does not cover uv dependency synchronization or installation;
audio-device discovery retains its separate, shorter limits.

Dependencies are optional: Torch/torchaudio with matching CUDA builds,
Transformers 5.6.0, accelerate, FunASR, sentencepiece, Silero VAD, ONNX Runtime,
SoundCard and NumPy, plus Python's Tk support. The desktop entry reports missing
dependencies in the control window. Desktop labels and status messages use
the existing AppI18N loader and all seven project locales. The file-video workflow
is described above; Web/Tauri media controls are not included in this desktop integration.

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

The video-file path above supplies its own `AudioSegment` sequence and model
factories, with separate recognition and translation passes so source SRT is
available before translation starts. Other offline clients can supply model
instances to `CascadeProcessor`; it must preserve all segments rather than
reuse the live queue's drop policy. Future batch inference, speaker metadata,
word alignment and multi-cue splitting belong in richer adapters/contracts;
the current recognizer returns one final transcript per segment. Resuming a file
job and routing its translations through batch AiNiee providers are not yet
implemented.

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
