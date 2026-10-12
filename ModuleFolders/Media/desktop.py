"""Desktop controller and independent, adjustable live subtitle window."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import threading
import sys

from ModuleFolders.Media.live_session import LiveConfig, LiveSession


PROJECT_ROOT = Path(__file__).resolve().parents[2]


from ModuleFolders.Media.preferences import default_model_root


class DesktopApp:
    def __init__(self, *, model_root: str | None = None, auto_start: bool = False, managed: bool = False) -> None:
        import tkinter as tk
        from tkinter import ttk

        from ModuleFolders.UserInterface.AppI18N import initialize_i18n
        self.language, self.i18n = initialize_i18n(str(PROJECT_ROOT))
        self.tk = tk
        self.managed = managed
        self.core_gone = threading.Event()
        self.setup_results = queue.Queue()
        self.setup_process = None
        self.setup_busy = False
        self.install_prompted = False
        self.runtime_ready = False
        self._checked_runtime_signature = None
        self._checked_compute = None
        self.auto_start_requested = auto_start
        self.runtime_interpreter = ""
        self._last_saved_preferences = None
        self.session = LiveSession()
        self.device_results = queue.Queue()
        self.device_probe_busy = False
        self._startup_check_pending = True
        self.settings_path = PROJECT_ROOT / "Resource/media_overlay.json"
        self.closing = False
        self.initialized = False
        self.close_requested = False
        self._fit_after = None
        self.closed = False
        self.state = "idle"
        self.source_text = ""
        self.translation_text = ""
        self.root = tk.Tk()
        self.is_macos = sys.platform == "darwin"
        if self.is_macos and "aqua" in ttk.Style(self.root).theme_names():
            ttk.Style(self.root).theme_use("aqua")
        self.ui_font = "Helvetica Neue" if self.is_macos else "Segoe UI"
        self.root.title(self.t("title"))
        self.root.geometry(f"720x{min(900, self.root.winfo_screenheight() - 120)}")
        self.root.minsize(680, 520)
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.after(0, self.close))
        self.root.bind("<Escape>", lambda _: self.hide_overlay())
        self.root.bind("<FocusIn>", lambda _: self.root.after_idle(self._keep_controls_accessible))
        self.model_root = tk.StringVar(value=model_root or default_model_root())
        self.family = tk.StringVar(value="index")
        self.source = tk.StringVar(value="ja")
        self.target = tk.StringVar(value="zh")
        self.device = tk.StringVar(value="auto")
        self.speaker = tk.StringVar(value=self.t("default_output"))
        self.opacity = tk.IntVar(value=88)
        self.font_size = tk.IntVar(value=26)
        self.font_family = tk.StringVar(value="PingFang SC" if self.is_macos else "Microsoft YaHei UI")
        self.font_bold = tk.BooleanVar(value=True)
        self.translation_color = tk.StringVar(value="#ffffff")
        self.source_color = tk.StringVar(value="#c8d4e5")
        self.background_color = tk.StringVar(value="#101827")
        self.stroke_width = tk.IntVar(value=2)
        self.stroke_color = tk.StringVar(value="#000000")
        self.style_dialog = None
        self.show_source = tk.BooleanVar(value=True)
        self.topmost = tk.BooleanVar(value=True)
        self.locked = tk.BooleanVar(value=False)
        self.overlay_width = tk.IntVar(value=900)
        self.overlay_height = tk.IntVar(value=240)
        self.context_segments = tk.IntVar(value=0)
        self.history_segments = tk.IntVar(value=3)
        self.recording = tk.BooleanVar(value=False)
        self.record_directory = tk.StringVar(value=str(PROJECT_ROOT / "Resource/MediaRecords"))
        from ModuleFolders.Media.session_history import SessionHistory
        self.history = SessionHistory()
        self.status = tk.StringVar(value=self.t("idle"))
        self._load_settings(model_root)
        from ModuleFolders.Media.model_catalog import get_model, TRANSLATION_MODELS
        self.model_choice = tk.StringVar(value=get_model(self.family.get()).name)
        self.model_details = tk.StringVar()
        self.catalog_dialog = None
        from ModuleFolders.Media.preferences import read_preferences
        from ModuleFolders.Media.runtime import selected_python
        preferences = read_preferences(self.settings_path)
        self.runtime_interpreter = selected_python(preferences.get("runtime_python", ""))
        self.device.set(preferences.get("device", "auto"))

        viewport = tk.Canvas(self.root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=viewport.yview)
        viewport.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        viewport.pack(side="left", fill="both", expand=True)
        frame = ttk.Frame(viewport, padding=20)
        frame_window = viewport.create_window(0, 0, window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _: viewport.configure(scrollregion=viewport.bbox("all")))
        viewport.bind("<Configure>", lambda event: viewport.itemconfigure(frame_window, width=event.width))
        self.root.bind("<MouseWheel>", lambda event: viewport.yview_scroll(
            -int(event.delta if self.is_macos else event.delta / 120), "units"))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=self.t("heading"), font=(self.ui_font, 17, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(frame, text=self.t("mac_description" if self.is_macos else "description"), wraplength=620).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))
        ttk.Label(frame, text=self.t("models")).grid(row=2, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(frame, textvariable=self.model_root).grid(row=2, column=1, sticky="ew")
        ttk.Button(frame, text=self.t("browse"), command=self.browse_models).grid(row=2, column=2, padx=(8, 0))
        ttk.Label(frame, text=self.t("translator")).grid(row=3, column=0, sticky="w", pady=12)
        model_selection = ttk.Frame(frame)
        model_selection.grid(row=3, column=1, columnspan=2, sticky="ew")
        self.model_selector = ttk.Combobox(model_selection, textvariable=self.model_choice,
                                           values=tuple(model.name for model in TRANSLATION_MODELS), state="readonly")
        self.model_selector.pack(fill="x")
        self.model_selector.bind("<<ComboboxSelected>>", self.select_model)
        ttk.Button(model_selection, text=self.t("model_catalog"), command=self.show_model_catalog).pack(anchor="w", pady=(6, 0))
        ttk.Label(frame, text=self.t("languages")).grid(row=4, column=0, sticky="w")
        languages = ttk.Frame(frame)
        languages.grid(row=4, column=1, columnspan=2, sticky="w")
        ttk.Combobox(languages, textvariable=self.source, values=("auto", "ja", "en", "ko", "zh", "yue"), state="readonly", width=10).pack(side="left")
        ttk.Label(languages, text="  →  ").pack(side="left")
        ttk.Combobox(languages, textvariable=self.target, values=("zh", "en", "ja", "ko"), state="readonly", width=10).pack(side="left")
        ttk.Label(languages, text=self.t("device")).pack(side="left")
        from ModuleFolders.Media.compute import model_device_choices
        self.compute_selector = ttk.Combobox(languages, textvariable=self.device, values=model_device_choices(self.family.get()), state="readonly", width=9)
        self.compute_selector.pack(side="left")
        self.compute_selector.bind("<<ComboboxSelected>>", self.compute_changed)
        ttk.Label(frame, text=self.t("audio")).grid(row=5, column=0, sticky="w", pady=12)
        self.devices = ttk.Combobox(frame, textvariable=self.speaker, state="readonly")
        self.devices.grid(row=5, column=1, sticky="ew")
        self.refresh_button = ttk.Button(frame, text=self.t("refresh"), command=self.refresh_devices)
        self.refresh_button.grid(row=5, column=2, padx=(8, 0))

        appearance = ttk.LabelFrame(frame, text=self.t("window"), padding=12)
        appearance.grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)
        appearance.columnconfigure(1, weight=1)
        ttk.Label(appearance, text=self.t("opacity")).grid(row=0, column=0, sticky="w")
        self.opacity_scale = tk.Scale(appearance, from_=0, to=100, orient="horizontal", variable=self.opacity,
                                     command=lambda _: self.apply_appearance(), highlightthickness=0)
        self.opacity_scale.grid(row=0, column=1, sticky="ew")
        ttk.Label(appearance, text=self.t("font_size")).grid(row=1, column=0, sticky="w")
        self.font_scale = tk.Scale(appearance, from_=16, to=48, orient="horizontal", variable=self.font_size,
                                  command=lambda _: self.apply_appearance(), highlightthickness=0)
        self.font_scale.grid(row=1, column=1, sticky="ew")
        lower_settings = ttk.Frame(appearance)
        lower_settings.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        lower_settings.columnconfigure(1, weight=1)
        controls = ttk.Frame(lower_settings)
        controls.grid(row=0, column=0, sticky="nw", padx=(0, 16))
        ttk.Button(controls, text=self.t("font_colors"), command=self.show_style_dialog).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))
        toggles = ttk.Frame(controls)
        toggles.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(toggles, text=self.t("display")).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(toggles, text=self.t("bilingual"), variable=self.show_source,
                        value=True, command=self.apply_appearance).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(toggles, text=self.t("translation_only"), variable=self.show_source,
                        value=False, command=self.apply_appearance).pack(side="left")
        locking = ttk.Frame(controls)
        locking.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.topmost_button = ttk.Checkbutton(locking, text=self.t("topmost"), variable=self.topmost,
                                             command=self.apply_appearance)
        self.topmost_button.pack(side="left", padx=(0, 16))
        self.lock_button = ttk.Checkbutton(locking, text=self.t("lock_position"), variable=self.locked,
                                          command=self.apply_appearance)
        self.lock_button.pack(side="left")
        ttk.Label(controls, text=self.t("lock_hint"), wraplength=280).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        sizing = ttk.Frame(controls)
        sizing.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(sizing, text=self.t("width")).pack(side="left")
        self.width_spin = ttk.Spinbox(sizing, from_=360, to=2400, increment=40, width=6,
                                     textvariable=self.overlay_width, command=self.resize_overlay)
        self.width_spin.pack(side="left", padx=(8, 16))
        ttk.Label(sizing, text=self.t("height")).pack(side="left")
        self.height_spin = ttk.Spinbox(sizing, from_=120, to=1000, increment=20, width=6,
                                      textvariable=self.overlay_height, command=self.resize_overlay)
        self.height_spin.pack(side="left", padx=8)
        for spin in (self.width_spin, self.height_spin):
            spin.bind("<Return>", lambda _: self.resize_overlay())
            spin.bind("<FocusOut>", lambda _: self.resize_overlay())
        ttk.Button(controls, text=self.t("reset_position"), command=self.reset_overlay_position).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        setup = ttk.Frame(frame)
        setup.grid(row=9, column=0, columnspan=3, sticky="ew", pady=8)
        self.setup_buttons = []
        for key, action in (("check_environment", "check"), ("install_runtime", "install"),
                            ("configure_inference", "configure"), ("download_models", "download")):
            button = ttk.Button(setup, text=self.t(key), command=lambda a=action: self.prepare_runtime(a))
            button.pack(side="left", padx=(0, 8), ipady=4)
            self.setup_buttons.append(button)
        self.environment_status = tk.StringVar(value=self.t("checking_environment"))
        ttk.Label(frame, textvariable=self.environment_status, wraplength=620).grid(
            row=10, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, textvariable=self.model_details, wraplength=620, justify="left").grid(
            row=11, column=0, columnspan=3, sticky="w", pady=12)
        self.update_model_details()
        memory = ttk.LabelFrame(lower_settings, text=self.t("history_context"), padding=12)
        memory.grid(row=0, column=1, sticky="new")
        memory.columnconfigure(1, weight=1)
        ttk.Label(memory, text=self.t("context_segments")).grid(row=0, column=0, sticky="w")
        self.context_spin = ttk.Spinbox(memory, from_=0, to=3, width=4, textvariable=self.context_segments)
        self.context_spin.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(memory, text=self.t("history_segments")).grid(row=1, column=0, sticky="w", pady=8)
        ttk.Spinbox(memory, from_=2, to=3, width=4, textvariable=self.history_segments,
                    command=self.refresh_caption_history).grid(row=1, column=1, sticky="w", padx=8)
        ttk.Checkbutton(memory, text=self.t("recording"), variable=self.recording,
                        command=self.toggle_recording).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(memory, text=self.t("record_directory")).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Entry(memory, textvariable=self.record_directory, width=16).grid(row=4, column=0, sticky="ew")
        ttk.Button(memory, text=self.t("browse"), command=self.browse_record_directory).grid(row=4, column=1, padx=(8, 0), sticky="e")
        self.record_status = tk.StringVar(value=self.t("recording_off"))
        ttk.Label(memory, textvariable=self.record_status, wraplength=280).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(memory, text=self.t("show_history"), command=self.show_history).grid(row=6, column=0, columnspan=2, sticky="w", pady=8)
        self.history_dialog = None
        self.history_text = None
        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=10)
        self.start_button = ttk.Button(buttons, text=self.t("start"), command=self.start)
        self.start_button.pack(side="left", ipadx=12, ipady=6)
        self.stop_button = ttk.Button(buttons, text=self.t("stop"), command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=10, ipadx=12, ipady=6)
        ttk.Button(buttons, text=self.t("show_window"), command=self.show_overlay).pack(side="left", ipady=6)
        ttk.Button(buttons, text=self.t("hide_window"), command=self.hide_overlay).pack(side="left", padx=8, ipady=6)
        ttk.Label(frame, textvariable=self.status, wraplength=620).grid(row=8, column=0, columnspan=3, sticky="w", pady=8)

        self.background = tk.Toplevel(self.root)
        self.background.title(self.t("subtitle_title") + " Background")
        self.background.overrideredirect(True)
        self.background.configure(bg="#101827")
        self.background.withdraw()
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.title(self.t("subtitle_title"))
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(900, max(360, screen_width - 80))
        self.overlay.geometry(f"{width}x240+{max(0, (screen_width - width) // 2)}+{max(0, screen_height - 340)}")
        self.overlay.minsize(360, 120)
        self._transparent_color = "systemTransparent" if self.is_macos else "#010203" if os.name == "nt" else "#101827"
        self.overlay.configure(bg=self._transparent_color)
        if os.name == "nt":
            self.overlay.attributes("-transparentcolor", self._transparent_color)
        elif self.is_macos:
            self.overlay.attributes("-transparent", True)
        else:
            self.lock_button.configure(state="disabled")
        self.overlay.protocol("WM_DELETE_WINDOW", self.hide_overlay)
        self.overlay.bind("<Escape>", lambda _: self.hide_overlay())
        self.background.bind("<Escape>", lambda _: self.hide_overlay())
        self.overlay.bind("<Map>", lambda event: self.root.after_idle(self.apply_appearance)
                          if event.widget is self.overlay else None)
        self.overlay.bind("<Unmap>", lambda _: self.background.withdraw())
        self.overlay.bind("<Configure>", self._resize)
        self.overlay_status = tk.Label(self.overlay, text=self.t("waiting"), bg="#101827", fg="#b6c7df",
                                       anchor="w", font=(self.ui_font, 10))
        from ModuleFolders.Media.outlined_text import OutlinedText
        self.translation_label = OutlinedText(self.overlay, text=self.t("placeholder"), bg=self._transparent_color,
                                         fg="#ffffff", justify="left", anchor="w", wraplength=840)
        self.translation_label.pack(fill="both", expand=True, padx=20, pady=4)
        self.source_label = OutlinedText(self.overlay, bg=self._transparent_color, fg="#c8d4e5", justify="left", anchor="w", wraplength=840)
        self._drag_origin = None
        for widget in (self.overlay, self.background, self.translation_label, self.source_label):
            widget.bind("<ButtonPress-1>", self._begin_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<ButtonRelease-1>", lambda _: setattr(self, "_drag_origin", None))
        self.overlay_width.set(min(self.overlay_width.get(), max(360, screen_width - 80)))
        self.overlay_height.set(min(self.overlay_height.get(), max(120, screen_height - 120)))
        if self.is_macos:
            self.overlay_height.set(min(self.overlay_height.get(), max(120, screen_height // 3)))
        self.reset_overlay_position()
        self.apply_appearance()
        self._poll_after = self.root.after(60, self.poll)
        if self.managed:
            from ModuleFolders.Media.supervisor import start_core_watchdog
            start_core_watchdog(self.core_gone.set)
        self.refresh_devices()
        self._setup_after = self.root.after(0, lambda: None)
        self.initialized = True
        if self.close_requested:
            self.root.after_idle(self.close)

    def _auto_start_when_ready(self):
        if self.closed or self.closing:
            return
        if not self.setup_busy and self.runtime_ready:
            self.start()

    def t(self, key: str, **values) -> str:
        if sys.platform == "darwin" and key == "default_output":
            key = "mac_system_audio"
        if sys.platform == "darwin" and key == "configure_hint":
            key = "mac_configure_hint"
        if sys.platform == "darwin" and key in {"audio", "audio_devices_ready"}:
            key = "mac_" + key
        return self.i18n.get("media_" + key).format(**values)

    def _load_settings(self, explicit_root) -> None:
        try:
            from ModuleFolders.Media.preferences import read_preferences
            data = read_preferences(self.settings_path)
            self.opacity.set(max(0, min(100, int(data.get("opacity", 88)))))
            self.font_size.set(max(16, min(48, int(data.get("font_size", 26)))))
            if isinstance(data.get("font_family"), str) and data["font_family"].strip():
                self.font_family.set(data["font_family"])
            self.font_bold.set(bool(data.get("font_bold", True)))
            self.stroke_width.set(max(0, min(6, int(data.get("stroke_width", 2)))))
            for key, variable in (("translation_color", self.translation_color),
                                  ("source_color", self.source_color), ("background_color", self.background_color),
                                  ("stroke_color", self.stroke_color)):
                value = data.get(key)
                if isinstance(value, str):
                    try:
                        self.root.winfo_rgb(value)
                    except self.tk.TclError:
                        continue
                    variable.set(value)
            self.show_source.set(bool(data.get("show_source", True)))
            self.topmost.set(bool(data.get("topmost", True)))
            self.locked.set(bool(data.get("locked", False)) and (os.name == "nt" or self.is_macos))
            self.overlay_width.set(max(360, min(2400, int(data.get("width", 900)))))
            self.overlay_height.set(max(120, min(1000, int(data.get("height", 240)))))
            self.context_segments.set(max(0, min(3, int(data.get("context_segments", 0)))))
            self.history_segments.set(max(2, min(3, int(data.get("history_segments", 3)))))
            self.recording.set(bool(data.get("recording", False)))
            if isinstance(data.get("record_directory"), str) and data["record_directory"].strip():
                self.record_directory.set(data["record_directory"])
            if not explicit_root and isinstance(data.get("model_root"), str):
                self.model_root.set(data["model_root"])
            for key, variable, allowed in [
                ("family", self.family, self._model_keys()),
                ("source", self.source, {"auto", "ja", "en", "ko", "zh", "yue"}),
                ("target", self.target, {"zh", "en", "ja", "ko"}),
            ]:
                if data.get(key) in allowed:
                    variable.set(data[key])
        except (OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _model_keys():
        from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS
        return tuple(model.key for model in TRANSLATION_MODELS)

    def save_settings(self) -> None:
        data = {key: var.get() for key, var in [
            ("opacity", self.opacity), ("font_size", self.font_size), ("show_source", self.show_source),
            ("topmost", self.topmost), ("model_root", self.model_root), ("family", self.family),
            ("source", self.source), ("target", self.target),
            ("width", self.overlay_width), ("height", self.overlay_height),
            ("locked", self.locked),
            ("font_family", self.font_family), ("font_bold", self.font_bold),
            ("translation_color", self.translation_color), ("source_color", self.source_color),
            ("background_color", self.background_color),
            ("stroke_width", self.stroke_width), ("stroke_color", self.stroke_color),
            ("context_segments", self.context_segments), ("history_segments", self.history_segments),
            ("recording", self.recording), ("record_directory", self.record_directory),
        ]}
        data["height"] = getattr(self, "_overlay_base_height", self.overlay_height.get())
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        from ModuleFolders.Media.preferences import save_preferences
        data["device"] = self.device.get()
        data["runtime_python"] = self.runtime_interpreter
        save_preferences(data, self.settings_path)

    def _save_changed_preferences(self):
        try:
            snapshot = tuple((name, variable.get()) for name, variable in vars(self).items()
                             if isinstance(variable, (self.tk.StringVar, self.tk.IntVar, self.tk.BooleanVar))
                             and name not in {"status", "environment_status", "speaker", "record_status"})
        except self.tk.TclError:
            return
        if snapshot != self._last_saved_preferences:
            try:
                self.save_settings()
                self._last_saved_preferences = snapshot
            except OSError:
                pass

    def browse_models(self) -> None:
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, initialdir=self.model_root.get())
        if path:
            self.model_root.set(path)
            self.update_model_details()
            self.compute_changed()

    def prepare_runtime(self, action: str, *, confirmed: bool = False, model_key: str | None = None) -> None:
        from ModuleFolders.Media.desktop_setup import prepare_runtime
        prepare_runtime(self, action, confirmed=confirmed, model_key=model_key)

    def runtime_signature(self):
        return (self.runtime_interpreter, self.device.get(), self.family.get(), self.model_root.get())

    def compute_changed(self, event=None):
        if self.session.active or self.setup_busy:
            self.environment_status.set(self.t("stop_before_setup"))
            return
        self.runtime_ready = False
        self.install_prompted = False
        self._checked_runtime_signature = None
        self._checked_compute = None
        self.start_button.configure(state="disabled")
        self.prepare_runtime("check")

    def browse_record_directory(self):
        from tkinter import filedialog
        selected = filedialog.askdirectory(parent=self.root, initialdir=self.record_directory.get())
        if selected:
            self.record_directory.set(selected)

    def toggle_recording(self):
        try:
            if self.recording.get() and self.session.active:
                self.history.begin_recording(self.record_directory.get())
                self.record_status.set(self.t("recording_path", path=str(self.history.record_path)))
            else:
                self.history.end_recording()
                self.record_status.set(self.t("recording_wait" if self.recording.get() else "recording_off"))
        except OSError as exc:
            self.recording.set(False)
            self.record_status.set(self.t("recording_error", detail=type(exc).__name__))

    def show_history(self):
        from tkinter import ttk
        if self.history_dialog is not None and self.history_dialog.winfo_exists():
            self.history_dialog.lift()
            return
        self.history_dialog = self.tk.Toplevel(self.root)
        self.history_dialog.title(self.t("show_history"))
        self.history_dialog.geometry("760x440")
        self.history_dialog.transient(self.root)
        frame = ttk.Frame(self.history_dialog, padding=12)
        frame.pack(fill="both", expand=True)
        self.history_text = self.tk.Text(frame, wrap="word", font=(self.ui_font, 12), state="disabled")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.history_text.yview)
        self.history_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.history_text.pack(fill="both", expand=True)
        self.render_history()
        self.root.after_idle(self._keep_controls_accessible)

    def render_history(self):
        try:
            self.history.set_limit(max(2, min(3, self.history_segments.get())))
        except self.tk.TclError:
            return
        if not hasattr(self, "history_text") or self.history_text is None or not self.history_text.winfo_exists():
            return
        chunks = []
        for caption in self.history.captions:
            if self.show_source.get():
                chunks.append(self.t("history_source") + "\n" + (caption.get("source_text") or ""))
            chunks.append(self.t("history_translation") + "\n" + (caption.get("translated_text") or "") + "\n")
        self.history_text.configure(state="normal")
        self.history_text.delete("1.0", "end")
        self.history_text.insert("1.0", "\n".join(chunks) or self.t("history_empty"))
        self.history_text.configure(state="disabled")

    def refresh_caption_history(self):
        try:
            if not self.history.captions and not self.source_text and not self.translation_text:
                self.render_history()
                return
            last = self.history.captions[-1] if self.history.captions else {}
            final = (last.get("source_text") == self.source_text and
                     last.get("translated_text") == self.translation_text)
            self.render_caption_stack(self.source_text, self.translation_text,
                                      final=final)
            self.render_history()
        except self.tk.TclError:
            return

    def render_caption_stack(self, source: str, translation: str, *, final: bool = False):
        try:
            self.history.set_limit(max(2, min(3, self.history_segments.get())))
        except self.tk.TclError:
            pass
        self.translation_label.configure(text=translation)
        self.source_label.configure(text=source)
        if self._fit_after is None:
            self._fit_after = self.root.after_idle(self.fit_caption_history)

    def fit_caption_history(self):
        self._fit_after = None
        if self.closed:
            return
        if self.translation_label.winfo_width() <= 1:
            return
        required = self.translation_label.winfo_reqheight() + 12
        if self.show_source.get():
            required += self.source_label.winfo_reqheight() + 14
        height = min(max(required, getattr(self, "_overlay_base_height", 240)),
                     1000, max(120, self.root.winfo_screenheight() - 120))
        if height != self.overlay.winfo_height():
            self.overlay_height.set(height)
            self.resize_overlay(automatic=True)

    def update_model_details(self) -> None:
        from ModuleFolders.Media.model_catalog import describe_model, get_model, model_files_present
        model = get_model(self.family.get())
        self.model_choice.set(model.name)
        installed = model_files_present(self.model_root.get(), model.key)
        self.model_details.set(describe_model(model.key, self.i18n.get) + "\n" +
                               self.t("model_installed" if installed else "model_not_downloaded") + "\n" +
                               self.t("model_memory_note"))

    def select_model(self, event=None) -> None:
        from ModuleFolders.Media.model_catalog import get_model
        if self.session.active or self.setup_busy:
            self.update_model_details()
            self.environment_status.set(self.t("stop_before_setup"))
            return
        self.family.set(get_model(self.model_choice.get()).key)
        from ModuleFolders.Media.compute import model_device_choices
        choices = model_device_choices(self.family.get())
        self.compute_selector.configure(values=choices)
        if self.device.get() not in choices:
            self.device.set("auto")
        self.update_model_details()
        self.save_settings()
        self.compute_changed()

    def show_model_catalog(self) -> None:
        from tkinter import ttk
        if self.catalog_dialog is not None and self.catalog_dialog.winfo_exists():
            self.refresh_model_list()
            self.catalog_dialog.lift()
            return
        dialog = self.tk.Toplevel(self.root)
        self.catalog_dialog = dialog
        dialog.title(self.t("model_catalog"))
        dialog.transient(self.root)
        dialog.geometry("850x470")
        dialog.minsize(650, 430)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        listing = ttk.Frame(frame)
        listing.grid(row=0, column=0, sticky="nsew")
        columns = ("name", "size", "vram", "state")
        self.model_list = ttk.Treeview(listing, columns=columns, show="headings", selectmode="browse", height=6)
        for column, label, width in (("name", "translator", 250), ("size", "model_download_size", 110),
                                     ("vram", "model_vram", 130), ("state", "model_state", 170)):
            self.model_list.heading(column, text=self.t(label))
            self.model_list.column(column, width=width, minwidth=80, anchor="w")
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.model_list.yview)
        self.model_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.model_list.pack(fill="both", expand=True)
        self.catalog_details = self.tk.StringVar()
        ttk.Label(frame, textvariable=self.catalog_details, wraplength=790, justify="left").grid(
            row=1, column=0, sticky="ew", pady=(12, 6))
        self.catalog_status = self.tk.StringVar()
        ttk.Label(frame, textvariable=self.catalog_status, wraplength=790).grid(row=2, column=0, sticky="w")
        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, sticky="ew", pady=(8, 4))
        self.catalog_use_button = ttk.Button(actions, text=self.t("use_selected_model"), command=self.use_catalog_model)
        self.catalog_use_button.pack(side="left", padx=(0, 8))
        self.catalog_download_button = ttk.Button(actions, text=self.t("download_models"), command=self.download_catalog_model)
        self.catalog_download_button.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text=self.t("refresh"), command=self.refresh_model_list).pack(side="left")
        ttk.Label(frame, text=self.t("model_memory_note"), wraplength=790).grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(frame, text=self.t("model_speed_note"), wraplength=790).grid(row=5, column=0, sticky="ew", pady=(4, 0))
        self.model_list.bind("<<TreeviewSelect>>", self.update_catalog_selection)
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        self.refresh_model_list()
        self.root.after_idle(self._keep_controls_accessible)

    def refresh_model_list(self) -> None:
        from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS, model_files_present
        if self.catalog_dialog is None or not self.catalog_dialog.winfo_exists():
            return
        previous = self.model_list.selection()
        selected = previous[0] if previous else self.family.get()
        for key in self.model_list.get_children():
            self.model_list.delete(key)
        for model in TRANSLATION_MODELS:
            installed = model_files_present(self.model_root.get(), model.key)
            state = self.t("model_installed" if installed else "model_not_downloaded")
            if model.key == self.family.get():
                state += " · " + self.t("model_current")
            self.model_list.insert("", "end", iid=model.key,
                                   values=(model.name, f"{model.download_gb:.2f} GB", model.vram_gib + " GiB", state))
        self.model_list.selection_set(selected)
        self.model_list.focus(selected)
        self.update_catalog_selection()

    def update_catalog_selection(self, event=None) -> None:
        from ModuleFolders.Media.model_catalog import describe_model, model_files_present
        selection = self.model_list.selection()
        if not selection:
            return
        key = selection[0]
        self.catalog_details.set(describe_model(key, self.i18n.get))
        blocked = self.session.active or self.setup_busy or self.closing
        installed = model_files_present(self.model_root.get(), key)
        self.catalog_use_button.configure(state="disabled" if blocked or not installed else "normal")
        self.catalog_download_button.configure(state="disabled" if blocked else "normal")

    def use_catalog_model(self) -> None:
        from ModuleFolders.Media.model_catalog import get_model
        if self.session.active or self.setup_busy:
            self.environment_status.set(self.t("stop_before_setup"))
            return
        selection = self.model_list.selection()
        if not selection:
            return
        self.model_choice.set(get_model(selection[0]).name)
        self.select_model()
        self.refresh_model_list()

    def download_catalog_model(self) -> None:
        selection = self.model_list.selection()
        if not selection:
            return
        self.prepare_runtime("download", model_key=selection[0])
        self.update_catalog_selection()

    def finish_preparation(self, event: dict) -> None:
        from tkinter import messagebox
        prepared_python = event.get("runtime_python")
        if prepared_python and not self.closing:
            self.runtime_interpreter = prepared_python
            from ModuleFolders.Media.preferences import save_preferences
            try:
                save_preferences({"runtime_python": prepared_python}, self.settings_path)
            except OSError:
                self.environment_status.set(self.t("setup_failed", detail="PreferencesWriteFailed"))
        self.setup_busy = False
        for button in self.setup_buttons:
            button.configure(state="normal")
        report = event.get("report")
        signature = event.get("runtime_signature")
        current = self.runtime_signature()
        self.runtime_ready = bool(report and report.get("ready") and
                                  (signature is None or tuple(signature) == current))
        self._checked_runtime_signature = current if self.runtime_ready else None
        self._checked_compute = report.get("compute") if self.runtime_ready else None
        if event.get("action") in {"install", "configure"} and self.runtime_ready:
            self.refresh_devices()
        if not self.session.active:
            self.start_button.configure(state="normal" if self.runtime_ready else "disabled")
        self.environment_status.set(event["message"])
        self.update_model_details()
        self.refresh_model_list()
        if self.catalog_dialog is not None and self.catalog_dialog.winfo_exists():
            self.catalog_status.set(event["message"])
        if report and report.get("missing") and not self.install_prompted and not self.closing:
            self.install_prompted = True
            consent = messagebox.askyesno(
                self.t("install_runtime"),
                self.t("missing_install_prompt", packages=", ".join(report["missing"])) + "\n\n" + self.t("install_hint"),
                parent=self.root,
            )
            if consent:
                action = "configure" if any(name.startswith("llama.cpp") for name in report["missing"]) else "install"
                self.prepare_runtime(action, confirmed=True)
                return
        if self.auto_start_requested and self.runtime_ready:
            self.auto_start_requested = False
            self.root.after_idle(self._auto_start_when_ready)

    def show_style_dialog(self) -> None:
        from tkinter import font, ttk
        if self.style_dialog is not None and self.style_dialog.winfo_exists():
            self.style_dialog.lift()
            return
        dialog = self.tk.Toplevel(self.root)
        self.style_dialog = dialog
        dialog.title(self.t("font_colors"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=self.t("font_family")).grid(row=0, column=0, sticky="w", padx=(0, 16))
        fonts = sorted(set(font.families(self.root)), key=str.casefold)
        choice = ttk.Combobox(frame, textvariable=self.font_family, values=fonts, state="readonly", width=30)
        choice.grid(row=0, column=1, sticky="ew")
        choice.bind("<<ComboboxSelected>>", lambda _: self.apply_appearance())
        ttk.Checkbutton(frame, text=self.t("bold"), variable=self.font_bold,
                        command=self.apply_appearance).grid(row=1, column=0, columnspan=2, sticky="w", pady=12)
        for row, (key, variable) in enumerate((("translation_color", self.translation_color),
                                              ("source_color", self.source_color),
                                              ("background_color", self.background_color),
                                              ("stroke_color", self.stroke_color)), 2):
            ttk.Label(frame, text=self.t(key)).grid(row=row, column=0, sticky="w", pady=8)
            button = self.tk.Button(frame, text=variable.get(), bg=variable.get(),
                                    fg=self._swatch_foreground(variable.get()), width=22)
            button.configure(command=lambda v=variable, b=button, k=key: self.choose_color(v, b, k))
            button.grid(row=row, column=1, sticky="ew", pady=8)
        ttk.Label(frame, text=self.t("stroke_width")).grid(row=6, column=0, sticky="w", pady=8)
        self.tk.Scale(frame, from_=0, to=6, orient="horizontal", variable=self.stroke_width,
                      command=lambda _: self.apply_appearance(), highlightthickness=0).grid(row=6, column=1, sticky="ew")
        ttk.Label(frame, text=self.t("style_hint"), wraplength=420).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.root.after_idle(self._keep_controls_accessible)

    def _swatch_foreground(self, color: str) -> str:
        r, g, b = self.root.winfo_rgb(color)
        return "#000000" if (.2126 * r + .7152 * g + .0722 * b) > 32768 else "#ffffff"

    def choose_color(self, variable, button, key: str) -> None:
        from tkinter import colorchooser
        _, color = colorchooser.askcolor(variable.get(), title=self.t(key), parent=self.style_dialog)
        if color:
            variable.set(color)
            button.configure(text=color, bg=color, fg=self._swatch_foreground(color))
            self.apply_appearance()

    def refresh_devices(self) -> None:
        if self.device_probe_busy or self.closed or self.closing:
            return
        self.device_probe_busy = True
        self.refresh_button.configure(state="disabled")
        interpreter = self.runtime_interpreter
        results = self.device_results
        def discover():
            try:
                from ModuleFolders.Media.runtime import discover_audio_runtime, AudioDeviceProbeTimeout
                selected, devices = discover_audio_runtime(interpreter)
                results.put((True, {"interpreter": selected, "speakers": devices}))
            except AudioDeviceProbeTimeout:
                results.put((False, {"code": "timeout"}))
            except Exception as exc:
                results.put((False, str(exc)))
        threading.Thread(target=discover, daemon=True).start()

    def _resize(self, event) -> None:
        if event.widget is self.overlay:
            width = max(280, event.width - 40)
            self.source_label.configure(wraplength=width)
            self.translation_label.configure(wraplength=width)
            self._sync_layers()
            if width != getattr(self, "_last_wrap_width", None):
                self._last_wrap_width = width
                if self._fit_after is None:
                    self._fit_after = self.root.after_idle(self.fit_caption_history)

    def _sync_layers(self) -> None:
        if self.closed or not hasattr(self, "background"):
            return
        if self.overlay.state() == "withdrawn":
            self.background.withdraw()
            return
        self.background.geometry(self.overlay.geometry())
        if self.opacity.get() == 0:
            self.background.withdraw()
            self.overlay.lift()
            return
        self.background.deiconify()
        self.overlay.lift(self.background)

    def _keep_controls_accessible(self):
        if not self.is_macos or self.closed:
            return
        from ModuleFolders.Media.macos_window import keep_controls_accessible
        dialogs = [window for name in ("style_dialog", "history_dialog", "catalog_dialog")
                   if (window := getattr(self, name, None)) is not None and window.winfo_exists()]
        try:
            keep_controls_accessible(self.root, self.overlay, dialogs,
                                     visible=self.overlay.state() != "withdrawn")
        except (RuntimeError, OSError, self.tk.TclError):
            self.status.set(self.t("unsupported_window"))

    def hide_overlay(self) -> None:
        self.overlay.withdraw()
        self.background.withdraw()
        self._keep_controls_accessible()

    def resize_overlay(self, *, automatic=False) -> None:
        if not hasattr(self, "overlay"):
            return
        try:
            width = max(360, min(2400, self.overlay_width.get()))
            height = max(120, min(1000, self.overlay_height.get()))
        except (ValueError, self.tk.TclError):
            return
        self.overlay_width.set(width)
        self.overlay_height.set(height)
        if not automatic:
            self._overlay_base_height = height
        self.overlay.geometry(f"{width}x{height}")

    def reset_overlay_position(self) -> None:
        if not hasattr(self, "overlay"):
            return
        self.resize_overlay()
        width = self.overlay_width.get()
        height = self.overlay_height.get()
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, self.root.winfo_screenheight() - height - 100)
        self.overlay.geometry(f"+{x}+{y}")

    def _begin_drag(self, event) -> None:
        if self.locked.get():
            self._drag_origin = None
            return
        self._drag_origin = (event.x_root, event.y_root, self.overlay.winfo_x(), self.overlay.winfo_y())
        self.overlay.focus_set()

    def _drag(self, event) -> None:
        if self._drag_origin and not self.locked.get():
            px, py, x, y = self._drag_origin
            x, y = x + event.x_root - px, y + event.y_root - py
            self.overlay.geometry(f"{x:+d}{y:+d}")

    def apply_appearance(self) -> None:
        if not hasattr(self, "overlay"):
            return
        from ModuleFolders.Media.window_effects import set_mouse_passthrough
        try:
            # Separate native layers keep glyphs opaque while the panel fades.
            self.overlay.attributes("-alpha", 1.0)
            self.background.attributes("-alpha", max(1 / 255, self.opacity.get() / 100))
            topmost = self.locked.get() or self.topmost.get()
            self.background.attributes("-topmost", topmost)
            self.overlay.attributes("-topmost", topmost)
            self._drag_origin = None
            self.topmost_button.configure(state="disabled" if self.locked.get() else "normal")
            self._sync_layers()
            self.root.update_idletasks()
            for window in (self.background, self.overlay):
                set_mouse_passthrough(window, self.locked.get() or (self.is_macos and window is self.background))
            self._keep_controls_accessible()
        except (self.tk.TclError, OSError, RuntimeError):
            if self.locked.get():
                self.locked.set(False)
                self.topmost_button.configure(state="normal")
                for window in (self.background, self.overlay):
                    try:
                        set_mouse_passthrough(window, self.is_macos and window is self.background)
                        window.attributes("-topmost", self.topmost.get())
                    except (self.tk.TclError, OSError, RuntimeError):
                        pass
            self.status.set(self.t("unsupported_window"))
        if os.name == "nt":
            used_colors = {self.root.winfo_rgb(self.translation_color.get()), self.root.winfo_rgb(self.source_color.get()),
                           self.root.winfo_rgb(self.stroke_color.get())}
            key = next(color for color in ("#010203", "#020304", "#030405", "#040506")
                       if self.root.winfo_rgb(color) not in used_colors)
            self._transparent_color = key
            self.overlay.attributes("-transparentcolor", key)
            self.overlay.configure(bg=key)
        self.background.configure(bg=self.background_color.get())
        self.translation_label.configure(
            font=(self.font_family.get(), self.font_size.get(), "bold" if self.font_bold.get() else "normal"),
            fg=self.translation_color.get(), bg=self._transparent_color)
        self.source_label.configure(font=(self.font_family.get(), max(12, self.font_size.get() - 8)),
                                    fg=self.source_color.get(), bg=self._transparent_color)
        for label in (self.translation_label, self.source_label):
            label.configure(stroke_width=self.stroke_width.get(), stroke_color=self.stroke_color.get())
        if self.show_source.get():
            self.source_label.pack(fill="x", padx=20, pady=(2, 12))
        else:
            self.source_label.pack_forget()
        self.refresh_caption_history()

    def show_overlay(self) -> None:
        self.overlay.deiconify()
        self._sync_layers()
        self.overlay.lift()
        self._keep_controls_accessible()

    def start(self) -> None:
        from tkinter import messagebox
        if self.session.active or self.setup_busy or not self.runtime_ready:
            return
        if self._checked_runtime_signature != self.runtime_signature():
            self.runtime_ready = False
            self.auto_start_requested = True
            self.prepare_runtime("check")
            return
        try:
            selected_audio = "" if self.speaker.get() == self.t("default_output") else self.speaker.get()
            if self.is_macos:
                from ModuleFolders.Media.macos_audio import SYSTEM_AUDIO, SCREEN_AUDIO
                if self.speaker.get() == self.t("default_output"):
                    selected_audio = SYSTEM_AUDIO
                elif self.speaker.get() == self.t("mac_screen_audio"):
                    selected_audio = SCREEN_AUDIO
            config = LiveConfig(
                model_root=str(Path(self.model_root.get()).expanduser().resolve()), family=self.family.get(),
                source_lang=self.source.get(), target_lang=self.target.get(),
                speaker=selected_audio,
                device=(self._checked_compute or {}).get("translation_device", self.device.get()),
                asr_device=(self._checked_compute or {}).get("asr_device", "auto"),
                context_segments=self.context_segments.get(),
            )
            self.session.start(config, interpreter=self.runtime_interpreter)
        except Exception as exc:
            messagebox.showerror(self.t("cannot_start"), str(exc), parent=self.root)
            return
        self.source_text = self.translation_text = ""
        self.history.clear()
        self.render_history()
        self.source_label.configure(text="")
        self.translation_label.configure(text=self.t("loading"))
        self.state = "loading"
        self.context_spin.configure(state="disabled")
        self.compute_selector.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set(self.t("starting_worker"))
        self.show_overlay()
        if self.recording.get():
            self.toggle_recording()
        else:
            self.history.end_recording()

    def stop(self) -> None:
        self.session.stop()
        if self.session.active:
            self.state = "stopping"
            self.status.set(self.t("stopping"))
            self.stop_button.configure(state="disabled")

    def handle_event(self, event: dict) -> None:
        kind = event.get("type")
        if self.managed:
            from ModuleFolders.Media.diagnostics import emit_diagnostic
            emit_diagnostic(event)
        if self.state == "stopping" and kind not in {"stopped", "error"}:
            return
        if kind in {"transcript", "caption"}:
            try:
                self.history.accept(event)
            except OSError as exc:
                self.history.end_recording()
                self.recording.set(False)
                self.record_status.set(self.t("recording_error", detail=type(exc).__name__))
            if kind == "caption":
                self.render_history()
        if kind == "status":
            labels = {"worker_started": self.t("worker_started"), "importing_runtime": self.t("importing_runtime"),
                      "translation_loaded": self.t("translation_loaded"), "loading_translation": self.t("loading_translation"),
                      "loading_asr": self.t("loading_asr"), "warming_up": self.t("warming_up"),
                      "opening_audio": self.t("opening_audio"),
                      "recognizing": self.t("recognizing"), "translating": self.t("translating")}
            self.status.set(labels.get(event["message"], event["message"]))
            self.overlay_status.configure(text=self.status.get())
        elif kind == "ready":
            print("[AiNiee live] ready", flush=True)
            self.state = "running"
            self.status.set(self.t("running_device", speaker=event["speaker"]))
            self.overlay_status.configure(text=self.t("listening"))
            self.translation_label.configure(text=self.t("play_audio"))
        elif kind in {"transcript", "partial", "caption"}:
            self.source_text = event.get("source_text", "")
            self.source_label.configure(text=self.source_text)
            if kind == "transcript":
                self.translation_text = self.t("translating")
                self.render_caption_stack(self.source_text, self.translation_text)
            else:
                self.translation_text = event.get("translated_text", "")
                self.render_caption_stack(self.source_text, self.translation_text, final=kind == "caption")
            if kind == "caption":
                metadata = event.get("metadata", {})
                self.overlay_status.configure(text=self.t("subtitles"))
                self.status.set(self.t("timing", asr=metadata.get("asr_ms", 0), translation=metadata.get("translation_ms", 0)))
            elif kind == "partial":
                self.overlay_status.configure(text=self.t("generating"))
        elif kind == "backlog":
            self.status.set(self.t("backlog", count=event["dropped_segments"]))
        elif kind == "error":
            self.state = "error"
            self.status.set(self.t("error", message=event["message"]))
            self.overlay_status.configure(text=self.t("see_error"))
        elif kind == "stopped":
            self.history.end_recording()
            self.record_status.set(self.t("recording_wait" if self.recording.get() else "recording_off"))
            self.context_spin.configure(state="normal")
            self.compute_selector.configure(state="readonly")
            if self.state != "error":
                self.status.set(self.t("stopped") if event.get("requested") or event.get("exit_code") == 0
                                else self.t("process_exit", code=event.get("exit_code")))
                self.state = "idle"
            self.overlay_status.configure(text=self.t("stopped"))
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

    def poll(self) -> None:
        if self.closed:
            return
        try:
            while True:
                ok, result = self.device_results.get_nowait()
                self.device_probe_busy = False
                self.refresh_button.configure(state="normal")
                if ok:
                    self.runtime_interpreter = result["interpreter"]
                    result = result["speakers"]
                    if self.is_macos:
                        from ModuleFolders.Media.macos_audio import SYSTEM_AUDIO, SCREEN_AUDIO
                        result = [self.t("default_output") if name == SYSTEM_AUDIO else
                                  self.t("mac_screen_audio") if name == SCREEN_AUDIO else name for name in result]
                    self.devices.configure(values=list(dict.fromkeys([self.t("default_output"), *result])))
                    if self.speaker.get() not in self.devices.cget("values"):
                        self.speaker.set(self.t("default_output"))
                    self.status.set(self.t("audio_devices_ready", count=len(result)))
                    self.environment_status.set(self.t("runtime_path", path=self.runtime_interpreter))
                else:
                    if isinstance(result, dict) and result.get("code") == "timeout":
                        self.status.set(self.t("audio_probe_timeout"))
                    else:
                        self.status.set(self.t("audio_error", message=result))
                if self._startup_check_pending:
                    self._startup_check_pending = False
                    self._setup_after = self.root.after_idle(lambda: self.prepare_runtime("check"))
        except queue.Empty:
            pass
        if self.managed and self.core_gone.is_set():
            self.session.close()
            self.destroy()
            return
        try:
            while True:
                event = self.setup_results.get_nowait()
                if event["type"] == "finished":
                    self.finish_preparation(event)
                elif event["type"] == "progress":
                    self.environment_status.set(event["message"])
                    if self.catalog_dialog is not None and self.catalog_dialog.winfo_exists():
                        self.catalog_status.set(event["message"])
        except queue.Empty:
            pass
        for event in self.session.poll():
            self.handle_event(event)
        if self.closing and not self.session.active:
            self.destroy()
            return
        if not self.closing:
            self._save_changed_preferences()
        self._poll_after = self.root.after(60, self.poll)

    def close(self) -> None:
        if not self.initialized:
            self.close_requested = True
            return
        if self.closing:
            return
        self.closing = True
        self.stop()
        if not self.session.active:
            self.destroy()

    def destroy(self) -> None:
        self.closed = True
        self.session.close()
        self.history.end_recording()
        if self._fit_after is not None:
            self.root.after_cancel(self._fit_after)
        if hasattr(self, "_poll_after"):
            self.root.after_cancel(self._poll_after)
        if getattr(self, "_setup_after", None):
            self.root.after_cancel(self._setup_after)
        try:
            self.save_settings()
        except OSError:
            pass
        if self.setup_process and self.setup_process.poll() is None:
            from ModuleFolders.Media.desktop_setup import stop_setup_process
            stop_setup_process(self.setup_process)
        self.root.destroy()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.session.close()
