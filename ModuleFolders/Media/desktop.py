"""Desktop controller and independent, adjustable live subtitle window."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import threading

from ModuleFolders.Media.live_session import LiveConfig, LiveSession


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def default_model_root() -> str:
    override = os.environ.get("AINIEE_MEDIA_MODEL_ROOT")
    if override:
        return override
    ssd = Path("G:/AiNiee-Models")
    return str(ssd if os.name == "nt" and ssd.is_dir() else PROJECT_ROOT / "tmp/models")


class DesktopApp:
    def __init__(self, *, model_root: str | None = None, auto_start: bool = False) -> None:
        import tkinter as tk
        from tkinter import ttk

        from ModuleFolders.UserInterface.AppI18N import initialize_i18n
        self.language, self.i18n = initialize_i18n(str(PROJECT_ROOT))
        self.tk = tk
        self.session = LiveSession()
        self.device_results = queue.Queue()
        self.settings_path = PROJECT_ROOT / "Resource/media_overlay.json"
        self.closing = False
        self.closed = False
        self.state = "idle"
        self.source_text = ""
        self.translation_text = ""
        self.root = tk.Tk()
        self.root.title(self.t("title"))
        self.root.geometry("720x650")
        self.root.minsize(680, 720)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.model_root = tk.StringVar(value=model_root or default_model_root())
        self.family = tk.StringVar(value="index")
        self.source = tk.StringVar(value="ja")
        self.target = tk.StringVar(value="zh")
        self.device = tk.StringVar(value="cuda:0")
        self.speaker = tk.StringVar(value=self.t("default_output"))
        self.opacity = tk.IntVar(value=88)
        self.font_size = tk.IntVar(value=26)
        self.font_family = tk.StringVar(value="Microsoft YaHei UI")
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
        self.status = tk.StringVar(value=self.t("idle"))
        self._load_settings(model_root)

        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=self.t("heading"), font=("Segoe UI", 17, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(frame, text=self.t("description")).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))
        ttk.Label(frame, text=self.t("models")).grid(row=2, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(frame, textvariable=self.model_root).grid(row=2, column=1, sticky="ew")
        ttk.Button(frame, text=self.t("browse"), command=self.browse_models).grid(row=2, column=2, padx=(8, 0))
        ttk.Label(frame, text=self.t("translator")).grid(row=3, column=0, sticky="w", pady=12)
        ttk.Combobox(frame, textvariable=self.family, values=("index", "hymt"), state="readonly").grid(row=3, column=1, sticky="ew")
        ttk.Label(frame, text=self.t("languages")).grid(row=4, column=0, sticky="w")
        languages = ttk.Frame(frame)
        languages.grid(row=4, column=1, columnspan=2, sticky="w")
        ttk.Combobox(languages, textvariable=self.source, values=("auto", "ja", "en", "ko", "zh", "yue"), state="readonly", width=10).pack(side="left")
        ttk.Label(languages, text="  →  ").pack(side="left")
        ttk.Combobox(languages, textvariable=self.target, values=("zh", "en", "ja", "ko"), state="readonly", width=10).pack(side="left")
        ttk.Label(languages, text=self.t("device")).pack(side="left")
        ttk.Combobox(languages, textvariable=self.device, values=("cuda:0", "cpu"), state="readonly", width=9).pack(side="left")
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
        ttk.Button(appearance, text=self.t("font_colors"), command=self.show_style_dialog).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))
        toggles = ttk.Frame(appearance)
        toggles.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(toggles, text=self.t("display")).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(toggles, text=self.t("bilingual"), variable=self.show_source,
                        value=True, command=self.apply_appearance).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(toggles, text=self.t("translation_only"), variable=self.show_source,
                        value=False, command=self.apply_appearance).pack(side="left")
        locking = ttk.Frame(appearance)
        locking.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.topmost_button = ttk.Checkbutton(locking, text=self.t("topmost"), variable=self.topmost,
                                             command=self.apply_appearance)
        self.topmost_button.pack(side="left", padx=(0, 16))
        self.lock_button = ttk.Checkbutton(locking, text=self.t("lock_position"), variable=self.locked,
                                          command=self.apply_appearance)
        self.lock_button.pack(side="left")
        ttk.Label(appearance, text=self.t("lock_hint"), wraplength=620).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        sizing = ttk.Frame(appearance)
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
        ttk.Button(appearance, text=self.t("reset_position"), command=self.reset_overlay_position).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
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
        self._transparent_color = "#010203" if os.name == "nt" else "#101827"
        self.overlay.configure(bg=self._transparent_color)
        if os.name == "nt":
            self.overlay.attributes("-transparentcolor", self._transparent_color)
        else:
            self.lock_button.configure(state="disabled")
        self.overlay.protocol("WM_DELETE_WINDOW", self.hide_overlay)
        self.overlay.bind("<Escape>", lambda _: self.hide_overlay())
        self.background.bind("<Escape>", lambda _: self.hide_overlay())
        self.overlay.bind("<Map>", lambda _: self.root.after_idle(self._sync_layers))
        self.overlay.bind("<Unmap>", lambda _: self.background.withdraw())
        self.overlay.bind("<Configure>", self._resize)
        self.overlay_status = tk.Label(self.overlay, text=self.t("waiting"), bg="#101827", fg="#b6c7df",
                                       anchor="w", font=("Segoe UI", 10))
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
        self.reset_overlay_position()
        self.apply_appearance()
        self.refresh_devices()
        self._poll_after = self.root.after(60, self.poll)
        if auto_start:
            self.root.after(500, self.start)

    def t(self, key: str, **values) -> str:
        return self.i18n.get("media_" + key).format(**values)

    def _load_settings(self, explicit_root) -> None:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
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
            self.locked.set(bool(data.get("locked", False)) and os.name == "nt")
            self.overlay_width.set(max(360, min(2400, int(data.get("width", 900)))))
            self.overlay_height.set(max(120, min(1000, int(data.get("height", 240)))))
            if not explicit_root and isinstance(data.get("model_root"), str):
                self.model_root.set(data["model_root"])
            for key, variable, allowed in [
                ("family", self.family, {"index", "hymt"}),
                ("source", self.source, {"auto", "ja", "en", "ko", "zh", "yue"}),
                ("target", self.target, {"zh", "en", "ja", "ko"}),
            ]:
                if data.get(key) in allowed:
                    variable.set(data[key])
        except (OSError, ValueError, TypeError):
            pass

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
        ]}
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.settings_path)

    def browse_models(self) -> None:
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, initialdir=self.model_root.get())
        if path:
            self.model_root.set(path)

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
        self.refresh_button.configure(state="disabled")
        def discover():
            try:
                import soundcard as sc
                self.device_results.put((True, [speaker.name for speaker in sc.all_speakers()]))
            except Exception as exc:
                self.device_results.put((False, str(exc)))
        threading.Thread(target=discover, daemon=True).start()

    def _resize(self, event) -> None:
        if event.widget is self.overlay:
            width = max(280, event.width - 40)
            self.source_label.configure(wraplength=width)
            self.translation_label.configure(wraplength=width)
            self._sync_layers()

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

    def hide_overlay(self) -> None:
        self.overlay.withdraw()
        self.background.withdraw()

    def resize_overlay(self) -> None:
        if not hasattr(self, "overlay"):
            return
        try:
            width = max(360, min(2400, self.overlay_width.get()))
            height = max(120, min(1000, self.overlay_height.get()))
        except (ValueError, self.tk.TclError):
            return
        self.overlay_width.set(width)
        self.overlay_height.set(height)
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
            from ModuleFolders.Media.window_effects import set_mouse_passthrough
            for window in (self.background, self.overlay):
                set_mouse_passthrough(window, self.locked.get())
        except (self.tk.TclError, OSError, RuntimeError):
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

    def show_overlay(self) -> None:
        self.overlay.deiconify()
        self._sync_layers()
        self.overlay.lift()

    def start(self) -> None:
        from tkinter import messagebox
        if self.session.active:
            return
        try:
            config = LiveConfig(
                model_root=str(Path(self.model_root.get()).expanduser().resolve()), family=self.family.get(),
                source_lang=self.source.get(), target_lang=self.target.get(),
                speaker="" if self.speaker.get() == self.t("default_output") else self.speaker.get(),
                device=self.device.get(), asr_device=self.device.get(),
            )
            self.session.start(config)
        except Exception as exc:
            messagebox.showerror(self.t("cannot_start"), str(exc), parent=self.root)
            return
        self.source_text = self.translation_text = ""
        self.source_label.configure(text="")
        self.translation_label.configure(text=self.t("loading"))
        self.state = "loading"
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set(self.t("loading_models"))
        self.show_overlay()

    def stop(self) -> None:
        self.session.stop()
        if self.session.active:
            self.state = "stopping"
            self.status.set(self.t("stopping"))
            self.stop_button.configure(state="disabled")

    def handle_event(self, event: dict) -> None:
        kind = event.get("type")
        if self.state == "stopping" and kind not in {"stopped", "error"}:
            return
        if kind == "status":
            labels = {"loading_translation": self.t("loading_translation"),
                      "loading_asr": self.t("loading_asr"), "warming_up": self.t("warming_up")}
            self.status.set(labels.get(event["message"], event["message"]))
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
                self.translation_label.configure(text=self.t("translating"))
            else:
                self.translation_text = event.get("translated_text", "")
                self.translation_label.configure(text=self.translation_text)
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
                self.refresh_button.configure(state="normal")
                if ok:
                    self.devices.configure(values=[self.t("default_output"), *result])
                else:
                    self.status.set(self.t("audio_error", message=result))
        except queue.Empty:
            pass
        for event in self.session.poll():
            self.handle_event(event)
        if self.closing and not self.session.active:
            self.destroy()
            return
        self._poll_after = self.root.after(60, self.poll)

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.stop()
        if not self.session.active:
            self.destroy()

    def destroy(self) -> None:
        self.session.close()
        if hasattr(self, "_poll_after"):
            self.root.after_cancel(self._poll_after)
        try:
            self.save_settings()
        except OSError:
            pass
        self.closed = True
        self.root.destroy()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.session.close()
