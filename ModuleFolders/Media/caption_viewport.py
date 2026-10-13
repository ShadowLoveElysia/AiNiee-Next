"""Scrollable subtitle pairs that preserve the reader's position during updates."""

import math
import tkinter as tk


class CaptionViewport(tk.Canvas):
    def __init__(self, master, **kwargs):
        super().__init__(master, highlightthickness=0, borderwidth=0, **kwargs)
        self.current_frame = tk.Frame(self, bg=self.cget("bg"))
        self._current_window = self.create_window(0, 0, anchor="nw", window=self.current_frame)
        self._captions = []
        self._drawn = []
        self._history_height = 0
        self._style = None
        self._width = 0
        self._layout_after = None
        self.follow_latest = True
        self.bind("<Configure>", self._schedule_layout)
        self.current_frame.bind("<Configure>", self._schedule_layout)
        self.bind("<Destroy>", self._cancel_layout)

    def set_history(self, captions):
        self._captions = list(captions)
        self._schedule_layout()

    def set_appearance(self, *, background, translation_font, source_font,
                       translation_color, source_color, stroke_width, stroke_color, show_source):
        style = (translation_font, source_font, translation_color, source_color,
                 stroke_width, stroke_color, show_source)
        if style != self._style:
            self._style = style
            self._drawn = []
            self.delete("history")
            self._history_height = 0
        self.configure(bg=background)
        self.current_frame.configure(bg=background)
        self._schedule_layout()

    def _schedule_layout(self, event=None):
        if self._layout_after is None:
            self._layout_after = self.after_idle(self._layout)

    def _cancel_layout(self, event):
        if event.widget is self and self._layout_after is not None:
            self.after_cancel(self._layout_after)
            self._layout_after = None

    def _draw_text(self, text, y, font, color):
        stroke, stroke_color = self._style[4:6]
        padding = stroke + 2
        x = 20 + padding
        options = dict(text=text or "", font=font, anchor="nw", justify="left",
                       width=max(1, self._width - 40 - 2 * padding), tags="history")
        front = self.create_text(x, y + padding, fill=color, **options)
        bounds = self.bbox(front)
        height = max(1, bounds[3] - bounds[1] if bounds else 1) + 2 * padding
        if stroke and text:
            offsets = {(round(stroke * math.cos(angle)), round(stroke * math.sin(angle)))
                       for angle in (i * math.tau / (stroke * 12) for i in range(stroke * 12))}
            for dx, dy in offsets:
                self.create_text(x + dx, y + padding + dy, fill=stroke_color, **options)
            self.tag_raise(front)
        return height

    def _layout(self):
        self._layout_after = None
        width = self.winfo_width()
        if width <= 1 or self._style is None:
            return
        top = self.canvasy(0)
        if width != self._width or self._captions[:len(self._drawn)] != self._drawn:
            self.delete("history")
            self._drawn = []
            self._history_height = 0
        self._width = width
        translation_font, source_font, translation_color, source_color, _, _, show_source = self._style
        for caption in self._captions[len(self._drawn):]:
            y = self._history_height + 4
            y += self._draw_text(caption.get("translated_text"), y, translation_font, translation_color)
            if show_source:
                y += 6
                y += self._draw_text(caption.get("source_text"), y, source_font, source_color)
            self._history_height = y + 12
        self._drawn = list(self._captions)
        self.itemconfigure(self._current_window, width=width)
        self.coords(self._current_window, 0, self._history_height)
        height = max(self.winfo_height(), self._history_height + self.current_frame.winfo_reqheight())
        self.configure(scrollregion=(0, 0, width, height))
        if self.follow_latest:
            self.yview_moveto(1.0)
        else:
            self.yview_moveto(top / height)
        self._redraw_native()

    def scroll(self, pixels):
        bounds = self.bbox("all")
        height = max(self.winfo_height(), bounds[3] if bounds else 0)
        maximum = max(0, height - self.winfo_height())
        top = max(0, min(maximum, self.canvasy(0) + pixels))
        self.yview_moveto(top / height)
        self.follow_latest = self.yview()[1] >= 0.999
        self._redraw_native()

    def show_latest(self):
        self.follow_latest = True
        self.yview_moveto(1.0)
        self._redraw_native()

    def _redraw_native(self):
        import sys
        if sys.platform == "darwin":
            from ModuleFolders.Media.macos_window import invalidate_content
            try:
                invalidate_content(self.winfo_toplevel())
            except (OSError, RuntimeError, tk.TclError):
                pass
