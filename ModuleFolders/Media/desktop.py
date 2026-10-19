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


MAX_HISTORY_DIALOG_CAPTIONS = 100


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
        self._audio_recheck_pending = False
        self.settings_path = PROJECT_ROOT / "Resource/media_overlay.json"
        self.closing = False
        self.initialized = False
        self.close_requested = False
        self._fit_after = None
        self.closed = False
        self.state = "idle"
        self.mutual_window = None
        self.video_window = None
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
        self.recognizer = tk.StringVar(value='sensevoice')
        self.recognition_device = tk.StringVar(value='auto')
        self.asr_endpoint = tk.StringVar(value='http://127.0.0.1:8001/v1')
        self.source = tk.StringVar(value="ja")
        self.target = tk.StringVar(value="zh")
        self.device = tk.StringVar(value="auto")
        self.speaker = tk.StringVar(value=self.t("default_output"))
        self.application_audio = tk.BooleanVar(value=False)
        self.application_choice = tk.StringVar()
        self.audio_applications = {}
        self.application_results = queue.Queue()
        self.application_probe_busy = False
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
        self.cache_ram_mib = tk.IntVar(value=3072)
        self.glossary_profile = tk.StringVar()
        self.glossary_choice = tk.StringVar()
        self.glossary_profiles = {}
        self.glossary_dialog = None
        self.chat_character_limit = tk.IntVar(value=0)
        self.recording = tk.BooleanVar(value=False)
        self.record_directory = tk.StringVar(value=str(PROJECT_ROOT / "Resource/MediaRecords"))
        from ModuleFolders.Media.session_history import SessionHistory
        self.history = SessionHistory()
        self.status = tk.StringVar(value=self.t("idle"))
        self._load_settings(model_root)
        from ModuleFolders.Media.model_catalog import get_model, TRANSLATION_MODELS
        self.model_choice = tk.StringVar(value=get_model(self.family.get()).name)
        from ModuleFolders.Media.asr_catalog import get_recognizer, RECOGNITION_MODELS
        self.recognizer_choice = tk.StringVar(value=get_recognizer(self.recognizer.get()).name)
        self.model_details = tk.StringVar()
        self.catalog_dialog = None
        from ModuleFolders.Media.preferences import read_preferences
        from ModuleFolders.Media.runtime import selected_python
        preferences = read_preferences(self.settings_path)
        self.runtime_interpreter = selected_python(preferences.get("runtime_python", ""))
        self.device.set(preferences.get("device", "auto"))
        self.package_source = tk.StringVar(value=preferences.get("package_source", "nju"))
        self.package_source_choice = tk.StringVar(value=self.t("source_" + self.package_source.get()))

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
        asr_selection = ttk.Frame(model_selection)
        asr_selection.pack(fill='x', pady=(8, 0))
        ttk.Label(asr_selection, text=self.t('recognizer')).pack(side='left', padx=(0, 8))
        self.recognizer_selector = ttk.Combobox(asr_selection, textvariable=self.recognizer_choice,
                                               values=tuple(model.name for model in RECOGNITION_MODELS), state='readonly', width=26)
        self.recognizer_selector.pack(side='left')
        self.recognizer_selector.bind('<<ComboboxSelected>>', self.select_recognizer)
        from ModuleFolders.Media.gguf_asr import asr_device_choices
        ttk.Label(asr_selection, text=self.t('recognition_device')).pack(side='left', padx=8)
        self.recognition_device_selector = ttk.Combobox(asr_selection, textvariable=self.recognition_device,
                                                       values=asr_device_choices(self.recognizer.get()), state='readonly', width=9)
        self.recognition_device_selector.pack(side='left')
        self.recognition_device_selector.bind('<<ComboboxSelected>>', self.compute_changed)
        ttk.Label(model_selection, text=self.t('asr_endpoint')).pack(anchor='w', pady=(8, 0))
        self.asr_endpoint_entry = ttk.Entry(model_selection, textvariable=self.asr_endpoint)
        self.asr_endpoint_entry.pack(fill='x')
        self.asr_endpoint_entry.bind('<Return>', self.compute_changed)
        self.asr_endpoint_entry.bind('<FocusOut>', self.compute_changed)
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
        audio_options = ttk.Frame(frame)
        audio_options.grid(row=5, column=1, sticky="ew")
        self.devices = ttk.Combobox(audio_options, textvariable=self.speaker, state="readonly")
        self.devices.pack(fill="x")
        self.application_toggle = ttk.Checkbutton(audio_options, text=self.t("application_audio"),
                                                  variable=self.application_audio, command=self.application_audio_changed)
        self.application_toggle.pack(anchor="w", pady=(6, 0))
        application_selection = ttk.Frame(audio_options)
        application_selection.pack(fill="x", pady=(4, 0))
        self.application_selector = ttk.Combobox(application_selection, textvariable=self.application_choice,
                                                 state="disabled")
        self.application_selector.pack(side="left", fill="x", expand=True)
        self.application_refresh = ttk.Button(application_selection, text=self.t("refresh"),
                                               command=self.refresh_applications, state="disabled")
        self.application_refresh.pack(side="left", padx=(6, 0))
        ttk.Label(audio_options, text=self.t("application_audio_hint"), wraplength=440).pack(anchor="w", pady=(4, 0))
        from ModuleFolders.Media.windows_audio import supported as application_capture_supported
        if not application_capture_supported():
            self.application_toggle.configure(state="disabled")
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
        sources = ttk.Frame(setup)
        sources.pack(fill="x", pady=(0, 8))
        ttk.Label(sources, text=self.t("package_source")).pack(side="left", padx=(0, 8))
        source_selector = ttk.Combobox(sources, textvariable=self.package_source_choice,
                                      values=(self.t("source_nju"), self.t("source_official")), state="readonly", width=28)
        source_selector.pack(side="left")
        source_selector.bind("<<ComboboxSelected>>", self.select_package_source)
        setup_actions = ttk.Frame(setup)
        setup_actions.pack(fill="x")
        self.setup_buttons = []
        for key, action in (("check_environment", "check"), ("install_runtime", "install"),
                            ("configure_inference", "configure"), ("download_models", "download")):
            button = ttk.Button(setup_actions, text=self.t(key), command=lambda a=action: self.prepare_runtime(a))
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
        ttk.Label(memory, text=self.t("cache_ram")).grid(row=1, column=0, sticky="w", pady=(8, 0))
        from ModuleFolders.Media.preferences import max_cache_ram_mib
        self.cache_ram_spin = ttk.Spinbox(memory, from_=0, to=max_cache_ram_mib(), increment=256,
                                          width=8, textvariable=self.cache_ram_mib)
        self.cache_ram_spin.grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))
        self.cache_ram_display = tk.StringVar(value="3.0G")
        ttk.Label(memory, textvariable=self.cache_ram_display).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))
        self.cache_ram_mib.trace_add("write", lambda *_: self._refresh_cache_ram_display())
        self._refresh_cache_ram_display()
        ttk.Label(memory, text=self.t("cache_ram_hint", maximum=f"{max_cache_ram_mib() / 1024:.1f}G"),
                  wraplength=280).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Checkbutton(memory, text=self.t("recording"), variable=self.recording,
                        command=self.toggle_recording).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(memory, text=self.t("record_directory")).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Entry(memory, textvariable=self.record_directory, width=16).grid(row=5, column=0, sticky="ew")
        ttk.Button(memory, text=self.t("browse"), command=self.browse_record_directory).grid(row=5, column=1, padx=(8, 0), sticky="e")
        self.record_status = tk.StringVar(value=self.t("recording_off"))
        ttk.Label(memory, textvariable=self.record_status, wraplength=280).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(memory, text=self.t("show_history"), command=self.show_history).grid(row=7, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(memory, text=self.t("mutual_title"), command=self.show_mutual_window).grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(memory, text=self.t("glossary_title")).grid(row=9, column=0, columnspan=2, sticky="w")
        self.glossary_selector = ttk.Combobox(memory, textvariable=self.glossary_choice, state="readonly", width=16)
        self.glossary_selector.grid(row=10, column=0, sticky="ew")
        self.glossary_selector.bind("<<ComboboxSelected>>", self.select_glossary)
        self.glossary_edit_button = ttk.Button(memory, text=self.t("glossary_edit"), command=self.show_glossary_editor)
        self.glossary_edit_button.grid(row=10, column=1, padx=8)
        self.refresh_glossary_choices()
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
        video_actions = ttk.Frame(frame)
        video_actions.grid(row=12, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Button(video_actions, text=self.t("video_title"), command=self.show_video_window).pack(side="left", ipady=5)

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
        from ModuleFolders.Media.caption_viewport import CaptionViewport
        self.caption_viewport = CaptionViewport(self.overlay, bg=self._transparent_color)
        self.caption_viewport.pack(fill="both", expand=True, padx=8, pady=8)
        from ModuleFolders.Media.outlined_text import OutlinedText
        self.translation_label = OutlinedText(self.caption_viewport.current_frame, text=self.t("placeholder"), bg=self._transparent_color,
                                         fg="#ffffff", justify="left", anchor="w", wraplength=840)
        self.translation_label.pack(fill="both", expand=True, padx=20, pady=4)
        self.source_label = OutlinedText(self.caption_viewport.current_frame, bg=self._transparent_color, fg="#c8d4e5", justify="left", anchor="w", wraplength=840)
        self._drag_origin = None
        for widget in (self.overlay, self.background, self.caption_viewport,
                       self.caption_viewport.current_frame, self.translation_label, self.source_label):
            widget.bind("<ButtonPress-1>", self._begin_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<ButtonRelease-1>", lambda _: setattr(self, "_drag_origin", None))
        for window in (self.overlay, self.background):
            window.bind("<MouseWheel>", self._scroll_captions)
            window.bind("<Button-4>", self._scroll_captions)
            window.bind("<Button-5>", self._scroll_captions)
            window.bind("<Prior>", lambda event: self._scroll_captions(event, -self.caption_viewport.winfo_height()))
            window.bind("<Next>", lambda event: self._scroll_captions(event, self.caption_viewport.winfo_height()))
            window.bind("<End>", self._show_latest_caption)
        self.background.bind("<Configure>", self._round_layers)
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
        self._setup_after = self.root.after_idle(lambda: self.prepare_runtime("check"))
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
            self.glossary_profiles = data["glossary_profiles"]
            self.glossary_profile.set(data["glossary_profile"])
            self.chat_character_limit.set(data["chat_character_limit"])
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
            from ModuleFolders.Media.preferences import DEFAULTS, max_cache_ram_mib, validate_preference
            try:
                self.cache_ram_mib.set(validate_preference("cache_ram_mib", data.get("cache_ram_mib", DEFAULTS["cache_ram_mib"])))
            except (ValueError, TypeError):
                self.cache_ram_mib.set(min(DEFAULTS["cache_ram_mib"], max_cache_ram_mib()))
            self.recording.set(bool(data.get("recording", False)))
            if isinstance(data.get("record_directory"), str) and data["record_directory"].strip():
                self.record_directory.set(data["record_directory"])
            if not explicit_root and isinstance(data.get("model_root"), str):
                self.model_root.set(data["model_root"])
            for key, variable, allowed in [
                ("family", self.family, self._model_keys()),
                ("source", self.source, {"auto", "ja", "en", "ko", "zh", "yue"}),
                ("target", self.target, {"zh", "en", "ja", "ko"}),
                ('recognizer', self.recognizer, {'sensevoice', 'qwen-vllm-0.6b', 'qwen-vllm-1.7b', 'qwen-gguf-0.6b', 'qwen-gguf-1.7b'}),
                ('recognition_device', self.recognition_device, {'auto', 'cpu', 'cuda:0', 'mps', 'metal', 'vulkan'}),
            ]:
                if data.get(key) in allowed:
                    variable.set(data[key])
            self.asr_endpoint.set(data.get('asr_endpoint', 'http://127.0.0.1:8001/v1'))
        except (OSError, ValueError, TypeError):
            pass
        self._refresh_cache_ram_display()

    def _refresh_cache_ram_display(self):
        try:
            from ModuleFolders.Media.preferences import format_cache_ram_mib
            self.cache_ram_display.set(format_cache_ram_mib(self.cache_ram_mib.get()))
        except (AttributeError, self.tk.TclError, TypeError, ValueError):
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
            ("context_segments", self.context_segments),
            ("cache_ram_mib", self.cache_ram_mib),
            ("recording", self.recording), ("record_directory", self.record_directory),
            ("glossary_profile", self.glossary_profile), ("chat_character_limit", self.chat_character_limit),
        ]}
        data["height"] = getattr(self, "_overlay_base_height", self.overlay_height.get())
        data["glossary_profiles"] = self.glossary_profiles
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        from ModuleFolders.Media.preferences import save_preferences
        data["device"] = self.device.get()
        data["runtime_python"] = self.runtime_interpreter
        data["package_source"] = self.package_source.get()
        data['recognizer'] = self.recognizer.get()
        data['recognition_device'] = self.recognition_device.get()
        data['asr_endpoint'] = self.asr_endpoint.get()
        save_preferences(data, self.settings_path)

    def select_package_source(self, event=None):
        self.package_source.set("nju" if self.package_source_choice.get() == self.t("source_nju") else "official")
        self.save_settings()

    def _save_changed_preferences(self):
        try:
            snapshot = tuple((name, variable.get()) for name, variable in vars(self).items()
                             if isinstance(variable, (self.tk.StringVar, self.tk.IntVar, self.tk.BooleanVar))
                             and name not in {"status", "environment_status", "speaker", "record_status", "application_choice", "glossary_choice"})
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

    def prepare_runtime(self, action: str, *, confirmed: bool = False, model_key: str | None = None,
                        asr_key: str | None = None, download_scope: str = 'all') -> None:
        if self.video_active:
            self.environment_status.set(self.t("stop_before_setup"))
            return
        from ModuleFolders.Media.desktop_setup import prepare_runtime
        prepare_runtime(self, action, confirmed=confirmed, model_key=model_key, asr_key=asr_key, download_scope=download_scope)

    def runtime_signature(self):
        signature = (self.runtime_interpreter, self.device.get(), self.family.get(), self.model_root.get())
        signature += ((self.recognizer.get(), self.recognition_device.get()) if hasattr(self, 'recognizer') else ())
        return signature + ((self.asr_endpoint.get(),) if hasattr(self, 'asr_endpoint') else ())

    def select_recognizer(self, event=None):
        from ModuleFolders.Media.asr_catalog import get_recognizer
        if self.session.active or self.video_active or self.setup_busy:
            self.recognizer_choice.set(get_recognizer(self.recognizer.get()).name)
            self.environment_status.set(self.t('stop_before_setup'))
            return
        self.recognizer.set(get_recognizer(self.recognizer_choice.get()).key)
        from ModuleFolders.Media.gguf_asr import asr_device_choices
        choices = asr_device_choices(self.recognizer.get())
        self.recognition_device_selector.configure(values=choices)
        if self.recognition_device.get() not in choices:
            self.recognition_device.set('auto')
        self.update_model_details()
        self.save_settings()
        self.compute_changed()

    def compute_changed(self, event=None):
        if self.session.active or self.video_active or self.setup_busy:
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
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(8, 0))
        self._history_page_start = None
        self._history_render_key = None
        self.history_older = ttk.Button(controls, text=self.t("history_older"), command=lambda: self.move_history_page(-1))
        self.history_older.pack(side="left")
        self.history_newer = ttk.Button(controls, text=self.t("history_newer"), command=lambda: self.move_history_page(1))
        self.history_newer.pack(side="left", padx=8)
        ttk.Button(controls, text=self.t("history_latest"), command=lambda: self.move_history_page(0)).pack(side="left")
        self.history_page_status = ttk.Label(controls)
        self.history_page_status.pack(side="right")
        self.render_history()
        self.root.after_idle(self._keep_controls_accessible)

    def move_history_page(self, direction):
        start = getattr(self, "_history_page_start", None)
        if start is None:
            start = max(0, self.history.count - MAX_HISTORY_DIALOG_CAPTIONS)
        if direction < 0:
            self._history_page_start = max(0, start - MAX_HISTORY_DIALOG_CAPTIONS)
        elif direction > 0 and start + 2 * MAX_HISTORY_DIALOG_CAPTIONS < self.history.count:
            self._history_page_start = start + MAX_HISTORY_DIALOG_CAPTIONS
        else:
            self._history_page_start = None
        self.render_history()

    def render_history(self):
        if not hasattr(self, "history_text") or self.history_text is None or not self.history_text.winfo_exists():
            return
        total = self.history.count
        start = getattr(self, "_history_page_start", None)
        if start is None or start >= total:
            start = max(0, total - MAX_HISTORY_DIALOG_CAPTIONS)
        end = min(total, start + MAX_HISTORY_DIALOG_CAPTIONS)
        if hasattr(self, "history_page_status"):
            self.history_page_status.configure(text=self.t("history_page", start=start + 1 if total else 0, end=end, total=total))
            self.history_older.configure(state="normal" if start else "disabled")
            self.history_newer.configure(state="normal" if end < total else "disabled")
        render_key = (self.history.generation, start, end, self.show_source.get())
        if getattr(self, "_history_render_key", None) == render_key:
            return
        try:
            captions = self.history.read_page(start, MAX_HISTORY_DIALOG_CAPTIONS)
        except OSError:
            self.record_status.set(self.t("history_error"))
            captions = list(self.history.captions)
        else:
            self._history_render_key = render_key
        self.history_text.configure(state="normal")
        self.history_text.delete("1.0", "end")
        has_history = False
        for caption in captions:
            has_history = True
            if self.show_source.get():
                self.history_text.insert("end", self.t("history_source") + "\n")
                self.history_text.insert("end", (caption.get("source_text") or "") + "\n")
            self.history_text.insert("end", self.t("history_translation") + "\n")
            self.history_text.insert("end", (caption.get("translated_text") or "") + "\n\n")
        if not has_history:
            self.history_text.insert("end", self.t("history_empty"))
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
        captions = list(self.history.captions)
        if final and captions:
            captions.pop()
        self.caption_viewport.set_history(captions)
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
        if hasattr(self, 'recognizer'):
            from ModuleFolders.Media.asr_catalog import get_recognizer, recognition_files_present
            asr = get_recognizer(self.recognizer.get())
            self.model_details.set(self.model_details.get() + '\n' + asr.name + ' · ' +
                                   self.t('model_installed' if recognition_files_present(self.model_root.get(), asr.key) else 'model_not_downloaded') +
                                   ('\n' + self.t('qwen_gguf_hint' if asr.backend == 'gguf' else 'qwen_asr_hint') if asr.key != 'sensevoice' else ''))

    def select_model(self, event=None) -> None:
        from ModuleFolders.Media.model_catalog import get_model
        if self.session.active or self.video_active or self.setup_busy:
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
        dialog.geometry("850x640")
        dialog.minsize(650, 540)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        listing = ttk.Frame(frame)
        listing.grid(row=0, column=0, sticky="nsew")
        columns = ("name", "size", "vram", "state")
        self.model_list = ttk.Treeview(listing, columns=columns, show="headings", selectmode="browse", height=13)
        self.model_list.tag_configure('section', background='#dde7ef', foreground='#162635')
        for column, label, width in (("name", "catalog_model_name", 250), ("size", "model_download_size", 110),
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
        ttk.Label(frame, text=self.t("catalog_roles_hint"), wraplength=790).grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(frame, text=self.t("model_speed_note"), wraplength=790).grid(row=5, column=0, sticky="ew", pady=(4, 0))
        self.model_list.bind("<<TreeviewSelect>>", self.update_catalog_selection)
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        self.refresh_model_list()
        self.root.after_idle(self._keep_controls_accessible)

    def refresh_model_list(self) -> None:
        from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS, model_files_present
        from ModuleFolders.Media.asr_catalog import RECOGNITION_MODELS, recognition_files_present
        if self.catalog_dialog is None or not self.catalog_dialog.winfo_exists():
            return
        previous = self.model_list.selection()
        selected = previous[0] if previous else self.family.get()
        for key in self.model_list.get_children():
            self.model_list.delete(key)
        self.model_list.insert('', 'end', iid='section-asr', values=(self.t('catalog_asr_section'), '', '', ''), tags=('section',))
        for model in RECOGNITION_MODELS:
            installed = recognition_files_present(self.model_root.get(), model.key)
            state = self.t('model_installed' if installed else 'model_not_downloaded')
            if hasattr(self, 'recognizer') and model.key == self.recognizer.get():
                state += ' · ' + self.t('model_current')
            self.model_list.insert('', 'end', iid='asr:' + model.key,
                                   values=(model.name, f'{model.download_gb:.2f} GB', '—', state))
        self.model_list.insert('', 'end', iid='section-llm', values=(self.t('catalog_llm_section'), '', '', ''), tags=('section',))
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
        if key.startswith('section-'):
            self.catalog_details.set(self.t('catalog_asr_hint' if key == 'section-asr' else 'catalog_llm_hint'))
            self.catalog_use_button.configure(state='disabled')
            self.catalog_download_button.configure(state='disabled')
            return
        if key.startswith('asr:'):
            from ModuleFolders.Media.asr_catalog import get_recognizer, recognition_files_present
            model = get_recognizer(key.removeprefix('asr:'))
            installed = recognition_files_present(self.model_root.get(), model.key)
            self.catalog_details.set(model.name + '\n' + self.t('catalog_asr_hint') + '\n' +
                                     self.t('model_path', path=str(Path(self.model_root.get()) / model.directory)) +
                                     ('\n' + self.t('qwen_gguf_hint' if model.backend == 'gguf' else 'qwen_asr_hint') if model.key != 'sensevoice' else ''))
        else:
            self.catalog_details.set(self.t('catalog_llm_hint') + '\n' + describe_model(key, self.i18n.get))
            installed = model_files_present(self.model_root.get(), key)
        blocked = self.session.active or self.video_active or self.setup_busy or self.closing
        self.catalog_use_button.configure(state="disabled" if blocked or not installed else "normal")
        self.catalog_download_button.configure(state="disabled" if blocked else "normal")

    def use_catalog_model(self) -> None:
        from ModuleFolders.Media.model_catalog import get_model
        if self.session.active or self.video_active or self.setup_busy:
            self.environment_status.set(self.t("stop_before_setup"))
            return
        selection = self.model_list.selection()
        if not selection:
            return
        key = selection[0]
        if key.startswith('section-'):
            return
        if key.startswith('asr:'):
            from ModuleFolders.Media.asr_catalog import get_recognizer
            self.recognizer_choice.set(get_recognizer(key.removeprefix('asr:')).name)
            self.select_recognizer()
        else:
            self.model_choice.set(get_model(key).name)
            self.select_model()
        self.refresh_model_list()

    def download_catalog_model(self) -> None:
        selection = self.model_list.selection()
        if not selection:
            return
        key = selection[0]
        if key.startswith('section-'):
            return
        if key.startswith('asr:'):
            self.prepare_runtime('download', asr_key=key.removeprefix('asr:'), download_scope='asr')
        else:
            self.prepare_runtime('download', model_key=key, download_scope='llm')
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
        if not self.session.active and not self.video_active:
            self.start_button.configure(state="normal" if self.runtime_ready else "disabled")
        self.environment_status.set(event["message"])
        self.update_model_details()
        self.refresh_model_list()
        if self._audio_recheck_pending and not self.closing:
            self._audio_recheck_pending = False
            self.root.after_idle(lambda: self.prepare_runtime("check"))
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

    def application_audio_changed(self):
        enabled = self.application_audio.get()
        self.devices.configure(state="disabled" if enabled else "readonly")
        self.application_selector.configure(state="readonly" if enabled else "disabled")
        self.application_refresh.configure(state="normal" if enabled and not self.application_probe_busy else "disabled")
        if enabled and not self.audio_applications and not self.application_probe_busy:
            if getattr(self, "_application_list_attempted", False):
                return
            self.refresh_applications()

    def refresh_applications(self):
        if self.application_probe_busy or self.session.active:
            return
        self.application_probe_busy = True
        self._application_list_attempted = True
        self.application_refresh.configure(state="disabled")
        def discover():
            try:
                from ModuleFolders.Media.windows_audio import applications
                self.application_results.put((True, applications()))
            except Exception:
                self.application_results.put((False, None))
        threading.Thread(target=discover, name="media-application-list", daemon=True).start()

    def application_capture_config(self):
        if not self.application_audio.get():
            return {}
        application = self.audio_applications.get(self.application_choice.get())
        if application is None:
            raise ValueError(self.t("application_choose"))
        return {"application_pid": application.pid, "application_started": application.started,
                "application_name": application.name}

    def _resize(self, event) -> None:
        if event.widget is self.overlay:
            width = max(280, event.width - 56)
            self.source_label.configure(wraplength=width)
            self.translation_label.configure(wraplength=width)
            self._sync_layers()
            self._round_layers()
            if width != getattr(self, "_last_wrap_width", None):
                self._last_wrap_width = width
                if self._fit_after is None:
                    self._fit_after = self.root.after_idle(self.fit_caption_history)

    def _round_layers(self, event=None):
        from ModuleFolders.Media.window_effects import set_rounded_corners
        for window in (self.background, self.overlay):
            try:
                set_rounded_corners(window, 18)
            except (self.tk.TclError, OSError, RuntimeError):
                pass

    def _scroll_captions(self, event, pixels=None):
        if self.locked.get() or self.opacity.get() < 10:
            return "break"
        if pixels is None:
            button = getattr(event, "num", None)
            if button in (4, 5):
                pixels = -48 if button == 4 else 48
            else:
                delta = getattr(event, "delta", 0)
                pixels = -delta * 4 if self.is_macos else -delta / 120 * 48
        self.caption_viewport.scroll(pixels)
        return "break"

    def _show_latest_caption(self, event=None):
        if not self.locked.get() and self.opacity.get() >= 10:
            self.caption_viewport.show_latest()
        return "break"

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
            self._round_layers()
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
        self.caption_viewport.set_appearance(
            background=self._transparent_color,
            translation_font=self.translation_label.cget("font"), source_font=self.source_label.cget("font"),
            translation_color=self.translation_color.get(), source_color=self.source_color.get(),
            stroke_width=self.stroke_width.get(), stroke_color=self.stroke_color.get(), show_source=self.show_source.get())
        if self.locked.get() or self.opacity.get() < 10:
            self.caption_viewport.show_latest()
        if self.show_source.get():
            self.source_label.pack(fill="x", padx=20, pady=(2, 12))
        else:
            self.source_label.pack_forget()
        self.refresh_caption_history()

    def show_mutual_window(self) -> None:
        if self.closing:
            return
        if self.mutual_window is None:
            from ModuleFolders.Media.mutual_window import MutualTranslationWindow
            self.mutual_window = MutualTranslationWindow(self)
        else:
            self.mutual_window.window.deiconify()
            self.mutual_window.window.lift()

    def refresh_glossary_choices(self):
        self.glossary_selector.configure(values=[self.t("glossary_off"), *self.glossary_profiles])
        self.glossary_choice.set(self.glossary_profile.get() or self.t("glossary_off"))

    def select_glossary(self, event=None):
        if self.session.active or self.video_active:
            self.refresh_glossary_choices()
            self.status.set(self.t("stop_before_setup"))
            return
        choice = self.glossary_choice.get()
        self.glossary_profile.set(choice if choice in self.glossary_profiles else "")
        self.save_settings()

    def show_glossary_editor(self):
        if self.video_active:
            self.status.set(self.t("stop_before_setup"))
            return
        from ModuleFolders.Media.glossary_window import open_glossary_editor
        open_glossary_editor(self)

    def show_overlay(self) -> None:
        self.overlay.deiconify()
        self._sync_layers()
        self.overlay.lift()
        self._keep_controls_accessible()

    @property
    def video_active(self):
        window = getattr(self, "video_window", None)
        return window is not None and window.active

    def show_video_window(self):
        if self.video_window is not None:
            self.video_window.window.lift()
            return
        if self.session.active or self.video_active or self.setup_busy:
            self.status.set(self.t("stop_before_setup"))
            return
        from ModuleFolders.Media.video_window import VideoTranslationWindow
        self.video_window = VideoTranslationWindow(self)

    def start(self) -> None:
        from tkinter import messagebox
        if self.session.active or self.video_active or self.setup_busy or not self.runtime_ready:
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
                asr_device='auto' if (self._checked_compute or {}).get('asr_device') == 'vllm-service' else (self._checked_compute or {}).get("asr_device", "auto"),
                recognizer=self.recognizer.get() if hasattr(self, 'recognizer') else 'sensevoice',
                asr_endpoint=self.asr_endpoint.get() if hasattr(self, 'asr_endpoint') else 'http://127.0.0.1:8001/v1',
                context_segments=self.context_segments.get(),
                cache_ram_mib=self.cache_ram_mib.get(),
                **self.application_capture_config(),
                glossary=tuple(self.glossary_profiles.get(self.glossary_profile.get(), [])),
            )
            self.session.start(config, interpreter=self.runtime_interpreter)
        except Exception as exc:
            messagebox.showerror(self.t("cannot_start"), str(exc), parent=self.root)
            return
        self.source_text = self.translation_text = ""
        self.history.clear()
        self._history_page_start = None
        self.caption_viewport.set_history([])
        self.caption_viewport.show_latest()
        self.render_history()
        self.source_label.configure(text="")
        self.translation_label.configure(text=self.t("loading"))
        self.state = "loading"
        self.glossary_selector.configure(state="disabled")
        self.glossary_edit_button.configure(state="disabled")
        for widget in (self.application_toggle, self.application_selector, self.application_refresh, self.devices):
            widget.configure(state="disabled")
        self.context_spin.configure(state="disabled")
        self.cache_ram_spin.configure(state="disabled")
        self.compute_selector.configure(state="disabled")
        if hasattr(self, 'recognizer_selector'):
            self.recognizer_selector.configure(state='disabled')
            self.recognition_device_selector.configure(state='disabled')
            self.asr_endpoint_entry.configure(state='disabled')
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
        if kind in {"mutual_started", "mutual_result", "mutual_error"}:
            if self.mutual_window is not None:
                self.mutual_window.accept(event)
            return
        if self.managed:
            from ModuleFolders.Media.diagnostics import emit_diagnostic
            emit_diagnostic(event)
        if self.state == "stopping" and kind not in {"stopped", "error"}:
            return
        if kind in {"transcript", "caption"}:
            from ModuleFolders.Media.session_history import HistoryStorageError
            try:
                self.history.accept(event)
            except HistoryStorageError:
                self.record_status.set(self.t("history_error"))
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
                self.status.set(self.t("timing_live", asr=metadata.get("asr_ms", 0), translation=metadata.get("translation_ms", 0),
                                       latency=metadata.get('latency_from_segment_end_ms', 0),
                                       queue=metadata.get('queue_wait_ms', 0), dropped=metadata.get('dropped_segments', 0)))
            elif kind == "partial":
                self.overlay_status.configure(text=self.t("generating"))
        elif kind == "backlog":
            self.status.set(self.t("backlog", count=event["dropped_segments"]))
        elif kind == "error":
            self.state = "error"
            self.status.set(self.t("error", message=event["message"]))
            self.overlay_status.configure(text=self.t("see_error"))
        elif kind == "stopped":
            self.glossary_selector.configure(state="readonly")
            self.glossary_edit_button.configure(state="normal")
            from ModuleFolders.Media.windows_audio import supported as application_capture_supported
            self.application_toggle.configure(state="normal" if application_capture_supported() else "disabled")
            self.application_audio_changed()
            self.history.end_recording()
            self.record_status.set(self.t("recording_wait" if self.recording.get() else "recording_off"))
            self.context_spin.configure(state="normal")
            self.cache_ram_spin.configure(state="normal")
            self.compute_selector.configure(state="readonly")
            if hasattr(self, 'recognizer_selector'):
                self.recognizer_selector.configure(state='readonly')
                self.recognition_device_selector.configure(state='readonly')
                self.asr_endpoint_entry.configure(state='normal')
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
            ok, applications = self.application_results.get_nowait()
            self.application_probe_busy = False
            if ok:
                self.audio_applications = {app.selection: app for app in applications}
                self.application_selector.configure(values=list(self.audio_applications))
                if self.application_choice.get() not in self.audio_applications:
                    self.application_choice.set("")
                self.status.set(self.t("application_list_ready", count=len(applications)))
            else:
                self.status.set(self.t("application_list_error"))
            if not self.session.active:
                self.application_audio_changed()
        except queue.Empty:
            pass
        try:
            while True:
                ok, result = self.device_results.get_nowait()
                self.device_probe_busy = False
                self.refresh_button.configure(state="normal")
                if ok:
                    interpreter_changed = self.runtime_interpreter != result["interpreter"]
                    self.runtime_interpreter = result["interpreter"]
                    if interpreter_changed:
                        self.runtime_ready = False
                        self._checked_runtime_signature = None
                        self.start_button.configure(state="disabled")
                        if self.setup_busy:
                            self._audio_recheck_pending = True
                        else:
                            self.root.after_idle(lambda: self.prepare_runtime("check"))
                    result = result["speakers"]
                    if self.is_macos:
                        from ModuleFolders.Media.macos_audio import SYSTEM_AUDIO, SCREEN_AUDIO
                        result = [self.t("default_output") if name == SYSTEM_AUDIO else
                                  self.t("mac_screen_audio") if name == SCREEN_AUDIO else name for name in result]
                    self.devices.configure(values=list(dict.fromkeys([self.t("default_output"), *result])))
                    if self.speaker.get() not in self.devices.cget("values"):
                        self.speaker.set(self.t("default_output"))
                    self.status.set(self.t("audio_devices_ready", count=len(result)))
                    if not self.setup_busy:
                        self.environment_status.set(self.t("runtime_path", path=self.runtime_interpreter))
                else:
                    if isinstance(result, dict) and result.get("code") == "timeout":
                        self.status.set(self.t("audio_probe_timeout"))
                    else:
                        self.status.set(self.t("audio_error", message=result))
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
                    if self.managed and event.get('download'):
                        from ModuleFolders.Media.diagnostics import emit_diagnostic
                        emit_diagnostic(event['download'])
                    elif self.managed:
                        from ModuleFolders.Media.diagnostics import emit_setup_line
                        emit_setup_line(event['message'])
                    else:
                        print(event['message'], flush=True)
                    if self.catalog_dialog is not None and self.catalog_dialog.winfo_exists():
                        self.catalog_status.set(event["message"])
        except queue.Empty:
            pass
        for event in self.session.poll():
            self.handle_event(event)
        if self.video_window is not None:
            self.video_window.poll()
        if self.mutual_window is not None:
            self.mutual_window.refresh()
        if self.closing and not self.session.active and not self.video_active:
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
        if self.mutual_window is not None:
            self.mutual_window.close()
        if self.video_window is not None:
            self.video_window.close()
        self.stop()
        if not self.session.active and not self.video_active:
            self.destroy()

    def destroy(self) -> None:
        self.closed = True
        if self.video_window is not None:
            self.video_window.shutdown()
        if self.mutual_window is not None:
            self.mutual_window.close()
        self.session.close()
        self.history.close()
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
            self.history.close()
            if self.video_window is not None:
                self.video_window.shutdown()
