"""Memory-only translation panel attached to the live desktop controller."""

from ModuleFolders.Media.inference_queue import LANGUAGES, MAX_TEXT_CHARS


class DockedWindows:
    def __init__(self, parent, child):
        self.parent, self.child = parent, child
        self.side = "right"
        self._after = None
        self._positions = {}
        parent.update_idletasks()
        child.update_idletasks()
        px, py, pw, ph = self._bounds(parent)
        _, _, cw, ch = self._bounds(child)
        screen = parent.winfo_screenwidth()
        if px + pw + cw <= screen:
            self.side = "right"
        elif px >= cw:
            self.side = "left"
        elif pw + cw <= screen:
            self._move(parent, max(0, screen - pw - cw), py)
        else:
            self.side = "bottom"
            self._move(parent, px, max(0, min(py, parent.winfo_screenheight() - ph - ch)))
        self._sync(parent)
        self._bindings = [(window, window.bind("<Configure>", self._configured, add="+"))
                          for window in (parent, child)]

    @staticmethod
    def _bounds(window):
        border = max(0, window.winfo_rootx() - window.winfo_x())
        title = max(0, window.winfo_rooty() - window.winfo_y())
        return (window.winfo_x(), window.winfo_y(),
                window.winfo_width() + 2 * border, window.winfo_height() + title + border)

    def _move(self, window, x, y):
        self._positions[window] = (x, y, *self._bounds(window)[2:])
        window.geometry(f"{x:+d}{y:+d}")

    def _configured(self, event):
        window = event.widget
        if window not in (self.parent, self.child):
            return
        bounds = self._bounds(window)
        if bounds == self._positions.get(window):
            return
        self._positions[window] = bounds
        if self._after is not None:
            self.parent.after_cancel(self._after)
        self._after = self.parent.after_idle(lambda: self._sync(window))

    def _sync(self, moved):
        self._after = None
        px, py, pw, ph = self._bounds(self.parent)
        cx, cy, cw, _ = self._bounds(self.child)
        if moved is self.parent:
            self._positions[self.parent] = (px, py, pw, ph)
            x, y = {"right": (px + pw, py), "left": (px - cw, py), "bottom": (px, py + ph)}[self.side]
            self._move(self.child, x, y)
        else:
            x, y = {"right": (cx - pw, cy), "left": (cx + cw, cy), "bottom": (cx, cy - ph)}[self.side]
            self._move(self.parent, x, y)

    def close(self):
        if self._after is not None:
            self.parent.after_cancel(self._after)
            self._after = None
        for window, binding in self._bindings:
            window.unbind("<Configure>", binding)


class MutualTranslationWindow:
    def __init__(self, app):
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.app = app
        self.request_id = None
        self.closed = False
        self._was_ready = False
        self._submitted_source = ""
        self._submitted_languages = None
        tk = app.tk
        self.window = tk.Toplevel(app.root)
        self.window.title(app.t("mutual_title"))
        self.window.geometry("480x550")
        self.window.minsize(380, 500)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _: self.close())
        self.window.bind("<Control-Return>", self.submit)
        if app.is_macos:
            self.window.bind("<Command-Return>", self.submit)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(6, weight=1)
        active = app.session.config
        source = active.source_lang if active else app.source.get()
        target = active.target_lang if active else app.target.get()
        initial_source = target
        initial_target = source if source != "auto" else "ja"
        if initial_source == initial_target:
            initial_target = "en" if initial_source != "en" else "zh"
        languages = ttk.Frame(frame)
        languages.grid(row=0, column=0, sticky="ew")
        languages.columnconfigure((0, 2), weight=1)
        self._names = {key: app.t("mutual_lang_" + key) for key in (*LANGUAGES, "auto")}
        self.source_choice = tk.StringVar(value=self._names[initial_source])
        self.target_choice = tk.StringVar(value=self._names[initial_target])
        self.source_selector = ttk.Combobox(languages, textvariable=self.source_choice,
                                           values=list(self._names.values()), state="readonly", width=12)
        self.source_selector.grid(row=1, column=0, sticky="ew")
        self.target_selector = ttk.Combobox(languages, textvariable=self.target_choice,
                                           values=[self._names[key] for key in LANGUAGES], state="readonly", width=12)
        self.target_selector.grid(row=1, column=2, sticky="ew")
        ttk.Label(languages, text=app.t("mutual_source")).grid(row=0, column=0, sticky="w")
        ttk.Label(languages, text=app.t("mutual_target")).grid(row=0, column=2, sticky="w")
        self.swap_button = ttk.Button(languages, text=app.t("mutual_swap"), command=self.swap)
        self.swap_button.grid(row=1, column=1, padx=8)
        ttk.Label(frame, text=app.t("mutual_hint"), wraplength=430).grid(row=1, column=0, sticky="w", pady=10)
        ttk.Label(frame, text=app.t("mutual_input")).grid(row=2, column=0, sticky="w")
        self.input = ScrolledText(frame, height=5, wrap="word", font=(app.ui_font, 11), undo=False)
        self.input.grid(row=3, column=0, sticky="nsew", pady=(4, 8))
        self.submit_button = ttk.Button(frame, text=app.t("mutual_translate"), command=self.submit)
        self.submit_button.grid(row=4, column=0, sticky="ew", ipady=4)
        ttk.Label(frame, text=app.t("mutual_output")).grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.output = ScrolledText(frame, height=5, wrap="word", font=(app.ui_font, 11), state="disabled")
        self.output.grid(row=6, column=0, sticky="nsew", pady=4)
        length_options = ttk.Frame(frame)
        length_options.grid(row=7, column=0, sticky="ew", pady=(4, 0))
        self.length_status = tk.StringVar()
        self.limit_text = tk.StringVar(value=str(app.chat_character_limit.get()))
        ttk.Label(length_options, textvariable=self.length_status).pack(side="left", fill="x", expand=True)
        ttk.Label(length_options, text=app.t("chat_limit")).pack(side="left", padx=(8, 4))
        self.limit_spin = ttk.Spinbox(length_options, from_=0, to=1000, width=5,
                                      textvariable=self.limit_text, command=self.limit_changed)
        self.limit_spin.pack(side="left")
        self.limit_spin.bind("<FocusOut>", self.limit_changed)
        self.limit_spin.bind("<Return>", self.limit_changed)
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status, wraplength=430).grid(row=8, column=0, sticky="w", pady=6)
        actions = ttk.Frame(frame)
        actions.grid(row=9, column=0, sticky="ew")
        self.copy_button = ttk.Button(actions, text=app.t("mutual_copy"), command=self.copy, state="disabled")
        self.copy_button.pack(side="left")
        self.clear_button = ttk.Button(actions, text=app.t("mutual_clear"), command=self.clear)
        self.clear_button.pack(side="left", padx=8)
        self.shorten_button = ttk.Button(actions, text=app.t("chat_shorten"), command=self.shorten, state="disabled")
        self.shorten_button.pack(side="left")
        ttk.Button(actions, text=app.t("mutual_close"), command=self.close).pack(side="right")
        self.window.update_idletasks()
        self.dock = DockedWindows(app.root, self.window)
        self.refresh()
        self.input.bind("<<Modified>>", self.input_changed)
        self.source_selector.bind("<<ComboboxSelected>>", lambda event: self.update_length())
        self.target_selector.bind("<<ComboboxSelected>>", lambda event: self.update_length())
        self.update_length()
        self.input.focus_set()

    def _languages(self):
        codes = {name: key for key, name in self._names.items()}
        return codes[self.source_choice.get()], codes[self.target_choice.get()]

    def swap(self):
        source, target = self._languages()
        if source == "auto":
            self.status.set(self.app.t("mutual_choose_source"))
            return
        self.source_choice.set(self._names[target])
        self.target_choice.set(self._names[source])
        self.update_length()

    def _output(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")
        self.copy_button.configure(state="normal" if text else "disabled")
        self.update_length()

    def character_limit(self):
        try:
            limit = int(self.limit_text.get())
            return limit if 0 <= limit <= 1000 else 0
        except (ValueError, self.app.tk.TclError):
            return 0

    def limit_changed(self, event=None):
        from ModuleFolders.Media.preferences import validate_preference
        try:
            value = validate_preference("chat_character_limit", self.limit_text.get())
        except (ValueError, self.app.tk.TclError):
            self.limit_text.set(str(self.app.chat_character_limit.get()))
            self.status.set(self.app.t("chat_limit_invalid"))
        else:
            self.app.chat_character_limit.set(value)
            self.limit_text.set(str(value))
            try:
                self.app.save_settings()
            except OSError:
                pass
        self.update_length()

    def input_changed(self, event=None):
        if self.input.edit_modified():
            self.input.edit_modified(False)
            self.update_length()

    def update_length(self):
        if not hasattr(self, "shorten_button"):
            return
        source = self.input.get("1.0", "end-1c")
        translated = self.output.get("1.0", "end-1c")
        limit = self.character_limit()
        key = "chat_count_over" if limit and len(translated) > limit else "chat_count_limit" if limit else "chat_count"
        self.length_status.set(self.app.t(key, source=len(source), output=len(translated), limit=limit,
                                        excess=max(0, len(translated) - limit)))
        can_shorten = (limit and len(translated) > limit and self.request_id is None and self.app.session.ready
                       and source.strip() == self._submitted_source and self._languages() == self._submitted_languages)
        self.shorten_button.configure(state="normal" if can_shorten else "disabled")

    def shorten(self):
        if str(self.shorten_button.cget("state")) == "normal":
            self.submit(max_characters=self.character_limit())

    def submit(self, event=None, *, max_characters=0):
        if self.request_id is not None or not self.app.session.ready:
            return "break"
        text = self.input.get("1.0", "end-1c").strip()
        source, target = self._languages()
        if not text or len(text) > MAX_TEXT_CHARS:
            self.status.set(self.app.t("mutual_length", limit=MAX_TEXT_CHARS))
            return "break"
        if source == target:
            self.status.set(self.app.t("mutual_same_language"))
            return "break"
        try:
            options = {"max_characters": max_characters} if max_characters else {}
            self.request_id = self.app.session.translate_text(text, source_lang=source, target_lang=target, **options)
        except (RuntimeError, ValueError):
            self.status.set(self.app.t("mutual_unavailable"))
            return "break"
        self._submitted_source = text
        self._submitted_languages = (source, target)
        self._output("")
        self.status.set(self.app.t("mutual_queued"))
        self.refresh()
        return "break"

    def accept(self, event):
        if event.get("request_id") != self.request_id or self.request_id is None:
            return
        kind = event.get("type")
        if kind == "mutual_started":
            self.status.set(self.app.t("mutual_working"))
        elif kind in {"mutual_result", "mutual_error"}:
            self.request_id = None
            if kind == "mutual_result":
                self._output(event.get("translated_text", ""))
                self.status.set(self.app.t("mutual_done"))
            else:
                self.status.set(self.app.t("mutual_failed"))
            self.refresh()

    def refresh(self):
        ready = self.app.session.ready and not self.app.closing
        if not ready:
            self.request_id = None
            self.status.set(self.app.t("mutual_unavailable"))
        busy = self.request_id is not None
        self.submit_button.configure(state="normal" if ready and not busy else "disabled")
        self.swap_button.configure(state="disabled" if busy else "normal")
        self.clear_button.configure(state="disabled" if busy else "normal")
        for selector in (self.source_selector, self.target_selector):
            selector.configure(state="disabled" if busy else "readonly")
        if ready and not busy and (not self._was_ready or not self.status.get()):
            self.status.set(self.app.t("mutual_ready"))
        self._was_ready = ready
        self.update_length()

    def copy(self):
        text = self.output.get("1.0", "end-1c")
        if text:
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
            self.status.set(self.app.t("mutual_copied"))

    def clear(self):
        self._submitted_source = ""
        self._submitted_languages = None
        self.input.delete("1.0", "end")
        self._output("")
        self.status.set(self.app.t("mutual_ready" if self.app.session.ready else "mutual_unavailable"))

    def close(self):
        if self.closed:
            return
        self.limit_changed()
        self.closed = True
        self._submitted_source = ""
        self._submitted_languages = None
        if self.request_id is not None:
            self.app.session.cancel_text(self.request_id)
        self.request_id = None
        self.dock.close()
        self.window.destroy()
        self.app.mutual_window = None
