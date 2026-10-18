"""Native file-translation controls sharing the desktop model selection."""

from pathlib import Path

from ModuleFolders.Media.preferences import read_preferences, save_preferences
from ModuleFolders.Media.video_pipeline import VideoConfig, VideoSession, VIDEO_EXTENSIONS, find_tool, validate_video_input


def choose_asr(parent, t, local_model, *, settings_path=None):
    import tkinter as tk
    from tkinter import ttk

    dialog = tk.Toplevel(parent)
    dialog.title(t("video_asr_title"))
    dialog.transient(parent)
    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    selected = tk.StringVar(value="local")
    ttk.Label(frame, text=t("video_asr_hint"), wraplength=480).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Radiobutton(frame, text=t("video_asr_local", model=local_model), variable=selected, value="local").grid(
        row=1, column=0, columnspan=2, sticky="w", pady=10)
    ttk.Radiobutton(frame, text=t("video_asr_cloud"), variable=selected, value="cloud").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))
    preferences = read_preferences(settings_path) if settings_path is not None else {}
    variables = {key: tk.StringVar(value=preferences.get("cloud_asr_" + key, ""))
                 for key in ("endpoint", "model", "api_key")}
    inputs = []
    for row, key in enumerate(variables, 3):
        ttk.Label(frame, text=t("video_asr_" + key)).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = ttk.Entry(frame, textvariable=variables[key], width=42, state="disabled",
                          **({"show": "*"} if key == "api_key" else {}))
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        inputs.append(entry)
    status = tk.StringVar()
    ttk.Label(frame, textvariable=status, wraplength=480).grid(row=6, column=0, columnspan=2, sticky="w", pady=6)
    result = []

    def changed(*_):
        for entry in inputs:
            entry.configure(state="normal" if selected.get() == "cloud" else "disabled")

    def accept():
        mode = selected.get()
        if mode == "local":
            result.append({"asr_mode": "local"})
        else:
            from ModuleFolders.Media.cloud_asr import validate_cloud_settings
            endpoint, model, api_key = (variables[key].get().strip() for key in variables)
            try:
                validate_cloud_settings(endpoint, model, api_key)
            except ValueError:
                status.set(t("video_asr_invalid"))
                return
            if settings_path is not None:
                try:
                    save_preferences({"cloud_asr_endpoint": endpoint, "cloud_asr_model": model,
                                       "cloud_asr_api_key": api_key}, settings_path)
                except OSError:
                    status.set(t("video_asr_save_failed"))
                    return
            result.append({"asr_mode": "cloud", "cloud_asr_endpoint": endpoint,
                           "cloud_asr_model": model, "cloud_asr_api_key": api_key})
        dialog.destroy()

    selected.trace_add("write", changed)
    actions = ttk.Frame(frame)
    actions.grid(row=7, column=0, columnspan=2, sticky="e", pady=(12, 0))
    ttk.Button(actions, text=t("video_cancel"), command=dialog.destroy).pack(side="left", padx=8)
    ttk.Button(actions, text=t("video_confirm"), command=accept).pack(side="left")
    dialog.bind("<Escape>", lambda _: dialog.destroy())
    dialog.grab_set()
    dialog.wait_window()
    return result[0] if result else None


def choose_subtitle_mode(parent, t, current=""):
    import tkinter as tk
    from tkinter import ttk

    dialog = tk.Toplevel(parent)
    dialog.title(t("video_mode_title"))
    dialog.transient(parent)
    dialog.resizable(False, False)
    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=t("video_mode_hint"), wraplength=460).pack(anchor="w", pady=(0, 12))
    selected = tk.StringVar(value=current)
    result = []
    for mode in ("soft", "hard"):
        ttk.Radiobutton(frame, text=t("video_" + mode), variable=selected, value=mode).pack(anchor="w", pady=8)
    actions = ttk.Frame(frame)
    actions.pack(fill="x", pady=(16, 0))

    def accept():
        if selected.get() in {"soft", "hard"}:
            result.append(selected.get())
            dialog.destroy()

    confirm = ttk.Button(actions, text=t("video_confirm"), command=accept,
                         state="normal" if current else "disabled")
    confirm.pack(side="right", padx=(8, 0))
    selected.trace_add("write", lambda *_: confirm.configure(state="normal"))
    ttk.Button(actions, text=t("video_cancel"), command=dialog.destroy).pack(side="right")
    dialog.bind("<Escape>", lambda _: dialog.destroy())
    dialog.bind("<Return>", lambda _: accept())
    dialog.grab_set()
    dialog.wait_window()
    return result[0] if result else None


class VideoTranslationWindow:
    def __init__(self, app):
        import tkinter as tk
        from tkinter import ttk

        self.app = app
        self.t = app.t
        self.session = VideoSession()
        self.closing = False
        self.terminal_event = False
        self.window = tk.Toplevel(app.root)
        self.window.title(self.t("video_title"))
        self.window.minsize(580, 430)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.input_path = tk.StringVar()
        self.output_directory = tk.StringVar(value=str(Path.home() / "Videos/AiNiee"))
        self.mode = read_preferences(app.settings_path)["video_subtitle_mode"]
        self.mode_label = tk.StringVar()
        self.status = tk.StringVar(value=self.t("video_idle"))
        self.glossary_source = tk.StringVar(value=self.t("video_glossary_temporary"))
        self.glossary_profile = tk.StringVar()
        self._update_mode_label()
        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=self.t("video_hint"), wraplength=540).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Label(frame, text=self.t("video_input")).grid(row=1, column=0, sticky="w")
        self.input_entry = ttk.Entry(frame, textvariable=self.input_path)
        self.input_entry.grid(row=2, column=0, sticky="ew", pady=(4, 12))
        self.input_button = ttk.Button(frame, text=self.t("browse"), command=self.browse_input)
        self.input_button.grid(row=2, column=1, padx=(8, 0), pady=(4, 12))
        ttk.Label(frame, text=self.t("video_output")).grid(row=3, column=0, sticky="w")
        self.output_entry = ttk.Entry(frame, textvariable=self.output_directory)
        self.output_entry.grid(row=4, column=0, sticky="ew", pady=(4, 12))
        self.output_button = ttk.Button(frame, text=self.t("browse"), command=self.browse_output)
        self.output_button.grid(row=4, column=1, padx=(8, 0), pady=(4, 12))
        ttk.Label(frame, textvariable=self.mode_label, wraplength=430).grid(row=5, column=0, sticky="w")
        self.mode_button = ttk.Button(frame, text=self.t("video_mode_title"), command=self.change_mode)
        self.mode_button.grid(row=5, column=1, padx=(8, 0))
        ttk.Label(frame, text=self.t("video_glossary_source")).grid(row=6, column=0, sticky="w", pady=(12, 4))
        self.glossary_selector = ttk.Combobox(frame, textvariable=self.glossary_source, state="readonly",
            values=(self.t("video_glossary_temporary"), self.t("video_glossary_manual")))
        self.glossary_selector.grid(row=7, column=0, columnspan=2, sticky="ew")
        self.glossary_selector.bind("<<ComboboxSelected>>", self.glossary_changed)
        self.profile_selector = ttk.Combobox(frame, textvariable=self.glossary_profile, state="disabled")
        self.profile_selector.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(frame, text=self.t("video_glossary_hint"), wraplength=540).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.input_path.trace_add("write", self.reset_glossary_source)
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(20, 8))
        ttk.Label(frame, textvariable=self.status, wraplength=540, justify="left").grid(row=11, column=0, columnspan=2, sticky="w")
        actions = ttk.Frame(frame)
        actions.grid(row=12, column=0, columnspan=2, sticky="w", pady=(16, 0))
        self.start_button = ttk.Button(actions, text=self.t("video_start"), command=self.start)
        self.start_button.pack(side="left", ipady=5)
        self.cancel_button = ttk.Button(actions, text=self.t("video_cancel"), command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8, ipady=5)

    @property
    def active(self):
        return self.session.active

    def _update_mode_label(self):
        self.mode_label.set(self.t("video_" + self.mode) if self.mode else self.t("video_mode_unset"))

    def reset_glossary_source(self, *_):
        self.glossary_source.set(self.t("video_glossary_temporary"))
        self.glossary_profile.set("")
        self.glossary_changed()

    def glossary_changed(self, event=None):
        manual = self.glossary_source.get() == self.t("video_glossary_manual")
        self.profile_selector.configure(values=list(self.app.glossary_profiles), state="readonly" if manual else "disabled")
        if not manual:
            self.glossary_profile.set("")

    def selected_glossary(self):
        if self.glossary_source.get() == self.t("video_glossary_temporary"):
            return "temporary", ()
        entries = self.app.glossary_profiles.get(self.glossary_profile.get(), [])
        if not entries:
            raise ValueError(self.t("video_glossary_choose"))
        return "manual", tuple(entries)

    def change_mode(self):
        from tkinter import messagebox
        if self.active:
            return
        choice = choose_subtitle_mode(self.window, self.t, self.mode)
        if choice:
            try:
                save_preferences({"video_subtitle_mode": choice}, self.app.settings_path)
            except OSError as exc:
                messagebox.showerror(self.t("video_title"), str(exc), parent=self.window)
                return
            self.mode = choice
            self._update_mode_label()

    def browse_input(self):
        from tkinter import filedialog
        selected = filedialog.askopenfilename(parent=self.window,
            filetypes=[(self.t("video_input"), " ".join("*" + suffix for suffix in VIDEO_EXTENSIONS))])
        if selected:
            self.input_path.set(selected)

    def browse_output(self):
        from tkinter import filedialog
        selected = filedialog.askdirectory(parent=self.window, initialdir=self.output_directory.get())
        if selected:
            self.output_directory.set(selected)

    def start(self):
        from tkinter import messagebox
        app = self.app
        if self.active or app.session.active or app.setup_busy or self.closing:
            return
        try:
            if not self.mode:
                self.change_mode()
                if not self.mode:
                    return
            validate_video_input(self.input_path.get(), self.mode)
            find_tool("ffmpeg")
            find_tool("ffprobe")
            glossary_mode, glossary = self.selected_glossary()
            from ModuleFolders.Media.asr_catalog import get_recognizer
            asr = choose_asr(self.window, self.t, get_recognizer(app.recognizer.get()).name,
                             settings_path=app.settings_path)
            if asr is None:
                return
            current_runtime = app._checked_runtime_signature == app.runtime_signature()
            if asr["asr_mode"] == "local" and (not app.runtime_ready or not current_runtime):
                self.status.set(self.t("video_check_runtime"))
                app.prepare_runtime("check")
                return
            compute = (app._checked_compute or {}) if current_runtime else {}
            asr_device = compute.get("asr_device", app.recognition_device.get())
            config = VideoConfig(
                model_root=str(Path(app.model_root.get()).expanduser().resolve()), family=app.family.get(),
                source_lang=app.source.get(), target_lang=app.target.get(),
                device=compute.get("translation_device", app.device.get()),
                asr_device="auto" if asr_device == "vllm-service" else asr_device,
                recognizer=app.recognizer.get(), asr_endpoint=app.asr_endpoint.get(),
                context_segments=app.context_segments.get(),
                glossary=glossary, glossary_mode=glossary_mode,
                input_path=str(Path(self.input_path.get()).expanduser().resolve()),
                output_directory=str(Path(self.output_directory.get()).expanduser().resolve()),
                subtitle_mode=self.mode,
                **asr,
            )
            self.session.start(config, interpreter=app.runtime_interpreter)
        except Exception as exc:
            messagebox.showerror(self.t("video_title"), str(exc), parent=self.window)
            return
        self.terminal_event = False
        self._set_busy(True)
        self.status.set(self.t("video_stage_loading_asr"))

    def _set_busy(self, busy):
        for widget in (self.start_button, self.input_entry, self.input_button, self.output_entry,
                       self.output_button, self.mode_button):
            widget.configure(state="disabled" if busy else "normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self.glossary_selector.configure(state="disabled" if busy else "readonly")
        if busy:
            self.profile_selector.configure(state="disabled")
        else:
            self.glossary_changed()
        self.app.start_button.configure(state="disabled" if busy or not self.app.runtime_ready else "normal")
        for widget, idle_state in ((self.app.compute_selector, "readonly"),
                                   (self.app.recognizer_selector, "readonly"),
                                   (self.app.recognition_device_selector, "readonly"),
                                   (self.app.asr_endpoint_entry, "normal"),
                                   (self.app.glossary_selector, "readonly"),
                                   (self.app.glossary_edit_button, "normal")):
            widget.configure(state="disabled" if busy else idle_state)
        if busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.stop()

    def cancel(self):
        self.session.stop()
        self.status.set(self.t("video_cancelling"))
        self.cancel_button.configure(state="disabled")

    def poll(self):
        for event in self.session.poll():
            kind = event.get("type")
            if kind == "video_progress" and not self.closing and self.session._stop_deadline is None:
                total, completed = event.get("total", 0), event.get("completed", 0)
                self.progress.stop()
                self.progress.configure(mode="determinate" if total else "indeterminate")
                if total:
                    self.progress.configure(maximum=total, value=completed)
                else:
                    self.progress.start(12)
                suffix = (f" ({completed / total:.0%})" if event["stage"] == "recognizing" else
                          f" ({completed}/{total})") if total else ""
                self.status.set(self.t("video_stage_" + event["stage"]) + suffix)
            elif kind == "video_output":
                self.output_path = event["directory"]
            elif kind in {"video_complete", "video_error", "video_cancelled", "error"}:
                self.terminal_event = True
                if kind == "video_complete":
                    self.status.set(self.t("video_done", video=event["video"], srt=event["translated_srt"]))
                elif kind == "video_cancelled":
                    self.status.set(self.t("video_cancelled"))
                else:
                    self.status.set(self.t("error", message=event["message"]))
            elif kind == "stopped":
                self._set_busy(False)
                if not self.terminal_event:
                    self.status.set(self.t("video_cancelled") if event.get("requested") else
                                    self.t("process_exit", code=event.get("exit_code")))
        if self.closing and not self.active:
            self.window.destroy()
            self.app.video_window = None

    def close(self):
        if self.active:
            self.closing = True
            self.cancel()
        else:
            self.window.destroy()
            self.app.video_window = None

    def shutdown(self):
        self.session.close()
