"""Streamer glossary editor; persistence follows an explicit Save action."""

from copy import deepcopy

from ModuleFolders.Media.glossary import validate_entries, validate_profiles
from ModuleFolders.Media.inference_queue import LANGUAGES


def open_glossary_editor(app):
    from tkinter import ttk, messagebox
    if app.session.active:
        app.status.set(app.t("stop_before_setup"))
        return
    existing = getattr(app, "glossary_dialog", None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        return
    tk = app.tk
    dialog = tk.Toplevel(app.root)
    app.glossary_dialog = dialog
    dialog.title(app.t("glossary_title"))
    dialog.geometry("780x520")
    dialog.minsize(640, 460)
    frame = ttk.Frame(dialog, padding=16)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(2, weight=1)
    profiles = deepcopy(app.glossary_profiles)
    name = tk.StringVar(value=app.glossary_profile.get())
    ttk.Label(frame, text=app.t("glossary_name")).grid(row=0, column=0, sticky="w")
    names = ttk.Combobox(frame, textvariable=name, values=list(profiles))
    names.grid(row=1, column=0, sticky="ew", pady=(4, 8))
    columns = ("source_lang", "source", "target_lang", "target")
    table = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", height=8)
    table.grid(row=2, column=0, sticky="nsew")
    for key, label, width in [("source_lang", "mutual_source", 90), ("source", "glossary_source_term", 220),
                              ("target_lang", "mutual_target", 90), ("target", "glossary_target_term", 220)]:
        table.heading(key, text=app.t(label))
        table.column(key, width=width, minwidth=60)
    scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
    scroll.grid(row=2, column=1, sticky="ns")
    table.configure(yscrollcommand=scroll.set)
    fields = ttk.Frame(frame)
    fields.grid(row=3, column=0, sticky="ew", pady=10)
    fields.columnconfigure((1, 3), weight=1)
    variables = {key: tk.StringVar(value="ja" if key == "source_lang" else "zh" if key == "target_lang" else "") for key in columns}
    for index, key in enumerate(columns):
        ttk.Label(fields, text=app.t({"source_lang": "mutual_source", "source": "glossary_source_term",
                                    "target_lang": "mutual_target", "target": "glossary_target_term"}[key])).grid(row=0, column=index, sticky="w")
        widget = (ttk.Combobox(fields, textvariable=variables[key], values=LANGUAGES, state="readonly", width=8)
                  if key.endswith("lang") else ttk.Entry(fields, textvariable=variables[key]))
        widget.grid(row=1, column=index, sticky="ew", padx=(0, 8))
    status = tk.StringVar(value=app.t("glossary_hint"))
    ttk.Label(frame, textvariable=status, wraplength=720).grid(row=5, column=0, sticky="w", pady=8)
    controls = ttk.Frame(frame)
    controls.grid(row=4, column=0, sticky="ew")

    def rows():
        return [dict(zip(columns, table.item(item, "values"))) for item in table.get_children()]

    def load(event=None):
        table.delete(*table.get_children())
        for entry in profiles.get(name.get(), []):
            table.insert("", "end", values=[entry[key] for key in columns])

    def select(event=None):
        selected = table.selection()
        if selected:
            for key, value in zip(columns, table.item(selected[0], "values")):
                variables[key].set(value)

    def add_or_update():
        selected = table.selection()
        entry = {key: variable.get() for key, variable in variables.items()}
        entries = [dict(zip(columns, table.item(item, "values"))) for item in table.get_children() if item not in selected]
        try:
            validate_entries([*entries, entry])
        except ValueError:
            status.set(app.t("glossary_invalid"))
            return
        if selected:
            table.item(selected[0], values=[entry[key] for key in columns])
        else:
            table.insert("", "end", values=[entry[key] for key in columns])
        status.set(app.t("glossary_unsaved"))

    def remove():
        for item in table.selection():
            table.delete(item)
        status.set(app.t("glossary_unsaved"))

    def save():
        if app.session.active:
            status.set(app.t("stop_before_setup"))
            return
        try:
            updated = validate_profiles({**profiles, name.get(): rows()})
            old_profiles, old_name = app.glossary_profiles, app.glossary_profile.get()
            app.glossary_profiles = updated
            app.glossary_profile.set(name.get().strip())
            try:
                app.save_settings()
            except OSError:
                app.glossary_profiles = old_profiles
                app.glossary_profile.set(old_name)
                raise
        except (ValueError, OSError):
            status.set(app.t("glossary_invalid"))
            return
        profiles.clear()
        profiles.update(deepcopy(updated))
        names.configure(values=list(profiles))
        app.refresh_glossary_choices()
        status.set(app.t("glossary_saved"))

    def delete_profile():
        if app.session.active or name.get() not in profiles:
            return
        if not messagebox.askyesno(app.t("glossary_title"), app.t("glossary_delete_confirm"), parent=dialog):
            return
        updated = {key: value for key, value in profiles.items() if key != name.get()}
        old_profiles, old_name = app.glossary_profiles, app.glossary_profile.get()
        app.glossary_profiles = updated
        if app.glossary_profile.get() == name.get():
            app.glossary_profile.set("")
        try:
            app.save_settings()
        except OSError:
            app.glossary_profiles = old_profiles
            app.glossary_profile.set(old_name)
            status.set(app.t("glossary_invalid"))
            return
        profiles.clear()
        profiles.update(updated)
        name.set("")
        names.configure(values=list(profiles))
        load()
        app.refresh_glossary_choices()

    ttk.Button(controls, text=app.t("glossary_add_update"), command=add_or_update).pack(side="left")
    ttk.Button(controls, text=app.t("glossary_remove"), command=remove).pack(side="left", padx=8)
    ttk.Button(controls, text=app.t("glossary_save"), command=save).pack(side="right")
    ttk.Button(controls, text=app.t("glossary_delete"), command=delete_profile).pack(side="right", padx=8)
    names.bind("<<ComboboxSelected>>", load)
    table.bind("<<TreeviewSelect>>", select)
    dialog.bind("<Escape>", lambda event: dialog.destroy())
    load()
