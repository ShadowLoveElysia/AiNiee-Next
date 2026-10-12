"""Wrapped subtitle text with an adjustable, fully opaque outline."""

import math
import sys
import tkinter as tk


class OutlinedText(tk.Canvas):
    def __init__(self, master, *, text="", fg="#ffffff", font=None, wraplength=840,
                 stroke_width=2, stroke_color="#000000", **kwargs):
        for option in ("justify", "anchor"):
            kwargs.pop(option, None)
        kwargs.setdefault("width", 1)
        kwargs.setdefault("height", 1)
        super().__init__(master, highlightthickness=0, borderwidth=0, **kwargs)
        self._text_options = dict(text=text, fg=fg, font=font or ("Segoe UI", 26),
                                  wraplength=wraplength, stroke_width=stroke_width, stroke_color=stroke_color)
        self._render_after = None
        self.bind("<Configure>", self._schedule_render)
        self.bind("<Destroy>", self._cancel_render)
        self._schedule_render()

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
            cnf = None
        changed = False
        for key in tuple(kwargs):
            if key in self._text_options:
                self._text_options[key] = kwargs.pop(key)
                changed = True
        result = super().configure(cnf, **kwargs)
        if changed or kwargs:
            self._schedule_render()
        return result

    config = configure

    def cget(self, key):
        if key in self._text_options:
            return self._text_options[key]
        return super().cget(key)

    def _schedule_render(self, event=None):
        if self._render_after is None:
            self._render_after = self.after_idle(self._render)

    def _cancel_render(self, event):
        if event.widget is self and self._render_after is not None:
            self.after_cancel(self._render_after)
            self._render_after = None

    def _render(self):
        self._render_after = None
        # Wait for the packer to allocate width; a 1px wrap would inflate the panel.
        if self.winfo_width() <= 1:
            return
        self.delete("all")
        options = self._text_options
        radius = max(0, min(6, int(options["stroke_width"])))
        padding = radius + 2
        width = max(1, min(int(options["wraplength"]), self.winfo_width() - 2 * padding))
        text = dict(text=options["text"], font=options["font"], anchor="nw", justify="left", width=width)
        front = self.create_text(padding, padding, fill=options["fg"], tags="foreground", **text)
        bounds = self.bbox(front)
        height = max(1, bounds[3] - bounds[1] if bounds else 1) + 2 * padding
        # Tk dimensions may contain units or Tcl_Obj values, depending on the build.
        if self.winfo_pixels(super().cget("height")) != height:
            super().configure(height=height)
        y = max(padding, (self.winfo_height() - height) // 2 + padding)
        self.coords(front, padding, y)
        if radius and options["text"]:
            # Offset glyph copies cover the disk; foreground is raised last.
            offsets = {(round(radius * math.cos(angle)), round(radius * math.sin(angle)))
                       for angle in (i * math.tau / (radius * 12) for i in range(radius * 12))}
            for dx, dy in sorted(offsets):
                self.create_text(padding + dx, y + dy, fill=options["stroke_color"], tags="outline", **text)
            self.tag_raise(front)
        if sys.platform == "darwin":
            from ModuleFolders.Media.macos_window import invalidate_content
            try:
                invalidate_content(self.winfo_toplevel())
            except (OSError, RuntimeError, tk.TclError):
                pass
