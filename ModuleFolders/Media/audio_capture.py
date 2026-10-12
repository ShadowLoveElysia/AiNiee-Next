"""Platform-specific device selection; macOS captures routed CoreAudio inputs."""

import sys


def is_virtual_input(name: str) -> bool:
    return any(marker in name.casefold() for marker in ("blackhole", "loopback", "soundflower"))


def devices(soundcard) -> list:
    if sys.platform == "darwin":
        return soundcard.all_microphones(include_loopback=False)
    return soundcard.all_speakers()


def capture_device(soundcard, selected: str):
    available = devices(soundcard)
    if sys.platform == "darwin":
        device = next((item for item in available if item.name == selected), None) if selected else next(
            (item for item in available if is_virtual_input(item.name)), None)
        if device is None:
            raise RuntimeError("Select a CoreAudio input or install BlackHole/Loopback and route playback to it")
        if device.channels < 1:
            raise RuntimeError("Selected CoreAudio input has no recording channels")
        return device
    speaker = next((item for item in available if item.name == selected), None) if selected else soundcard.default_speaker()
    if speaker is None:
        raise RuntimeError("Selected audio output device is unavailable")
    device = soundcard.get_microphone(id=speaker.id, include_loopback=True)
    if sys.platform == "win32" and device.channels < 2:
        raise RuntimeError("Select a stereo audio output; WASAPI mono capture is unreliable")
    return device
