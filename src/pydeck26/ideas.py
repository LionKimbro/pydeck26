"""Idea editor and directory windows sharing PyDeck's ideas document."""
from __future__ import annotations
from copy import deepcopy
from datetime import date
import re, tkinter as tk
from tkinter import ttk
import uuid

g={"save":None,"root":None,"document":{"items":[]},"sort-column":None,"sort-reverse":False}
widgets={}
DIRECTORY_COLUMNS = [("pinned", "Pinned", 55), ("status", "Status", 110),
                     ("date", "Date conceived", 110), ("title", "Title", 430)]

def set_context(ctx: dict) -> None:
    g.update(ctx)

def open_directory() -> None:
    existing = widgets.get("directory-tree")
    if existing is not None and existing.winfo_exists():
        existing.winfo_toplevel().lift()
        return
    w=tk.Toplevel(g["root"]); w.title("PyDeck 26 — Ideas Directory"); w.geometry("760x430"); w.columnconfigure(0,weight=1); w.rowconfigure(0,weight=1)
    tree=ttk.Treeview(w,columns=("pinned","status","date","title"),show="headings")
    for key, label, width in DIRECTORY_COLUMNS:
        tree.heading(key, text=label, command=lambda key=key: handle_when_user_sorts_ideas_directory(key))
        tree.column(key, width=width, stretch=key=="title")
    tree.grid(row=0,column=0,sticky="nsew",padx=8,pady=8); tree.bind("<Double-Button-1>",lambda e: open_editor(tree.selection()[0] if tree.selection() else None))
    ttk.Button(w,text="New Idea",command=lambda:open_editor(None)).grid(row=1,column=0,sticky="w",padx=8,pady=(0,8)); widgets["directory-tree"]=tree; refresh_directory()

def refresh_directory() -> None:
    tree=widgets.get("directory-tree")
    if not tree or not tree.winfo_exists(): return
    selected = tree.selection()
    tree.delete(*tree.get_children())
    items = g["document"]["items"]
    if g["sort-column"] is not None:
        items = sorted(items, key=get_directory_sort_key, reverse=g["sort-reverse"])
    for item in items: tree.insert("","end",iid=item["guid"],values=("★" if item.get("pinned") else "",item.get("status",""),item.get("date-conceived",""),item.get("title", "")))
    for key, label, width in DIRECTORY_COLUMNS:
        arrow = (" ▼" if g["sort-reverse"] else " ▲") if key == g["sort-column"] else ""
        tree.heading(key, text=label + arrow)
    if selected and tree.exists(selected[0]):
        tree.selection_set(selected[0])
        tree.focus(selected[0])


def get_directory_sort_key(item: dict):
    column = g["sort-column"]
    if column == "pinned":
        return bool(item.get("pinned", False))
    field = "date-conceived" if column == "date" else column
    return str(item.get(field) or "").strip().casefold()


def handle_when_user_sorts_ideas_directory(column: str) -> None:
    if column == g["sort-column"]:
        g["sort-reverse"] = not g["sort-reverse"]
    else:
        g["sort-column"] = column
        g["sort-reverse"] = column == "pinned"
    refresh_directory()
    widgets["directory-tree"].yview_moveto(0)

def open_editor(guid: str | None) -> None:
    source=find_item(guid) if guid else make_new_item()
    if source is None: return
    item=deepcopy(source)
    item.setdefault("hook", "")
    w=tk.Toplevel(g["root"]); w.title("PyDeck 26 — Idea Editor"); w.columnconfigure(1,weight=1)
    fields={};
    for row,key,label in [(0,"guid","GUID"),(1,"title","Title"),(2,"hook","Hook"),(3,"status","Status"),(4,"date-conceived","Date conceived"),(5,"date-entered","Date entered"),(6,"tags","Tags")]:
        ttk.Label(w,text=label).grid(row=row,column=0,sticky="w",padx=8,pady=3)
        if key=="status": control=ttk.Combobox(w,values=["conceived","sketching","implementing","implemented","aborted"])
        else: control=ttk.Entry(w)
        control.grid(row=row,column=1,sticky="ew",padx=8,pady=3); control.insert(0," ".join(item[key]) if key=="tags" else item[key]); fields[key]=control
        if key=="guid": control.configure(state="readonly")
    for row,key,height in [(7,"description",5),(8,"notes",10)]:
        ttk.Label(w,text=key.title()).grid(row=row,column=0,sticky="nw",padx=8,pady=3); t=tk.Text(w,height=height,wrap="word"); t.grid(row=row,column=1,sticky="ew",padx=8,pady=3); t.insert("1.0",item[key]); fields[key]=t
    pinned=tk.BooleanVar(value=item["pinned"]); ttk.Checkbutton(w,text="Pinned",variable=pinned).grid(row=9,column=1,sticky="w",padx=8)
    ttk.Button(w,text="Save",command=lambda:save_editor({"fields":fields,"pinned":pinned,"window":w,"item":item})).grid(row=10,column=1,sticky="e",padx=8,pady=8)
    fields["title"].focus_set(); widgets["idea-editor"]=w

def make_new_item() -> dict:
    today=date.today().isoformat(); return {"guid":str(uuid.uuid4()),"title":"","hook":"","description":"","status":"conceived","date-conceived":today,"date-entered":today,"notes":"","tags":[],"pinned":False}

def find_item(guid: str | None) -> dict | None:
    for item in g["document"]["items"]:
        if item.get("guid")==guid:return item
    return None

def save_editor(draft: dict) -> None:
    fields=draft["fields"]; pinned=draft["pinned"]; window=draft["window"]
    tags=fields["tags"].get().split()
    if any(not re.fullmatch(r"[a-z0-9_]+",tag) for tag in tags): return
    item=draft["item"]; item.update({"title":fields["title"].get(),"hook":fields["hook"].get(),"status":fields["status"].get(),"date-conceived":fields["date-conceived"].get(),"date-entered":fields["date-entered"].get(),"tags":tags,"pinned":pinned.get(),"description":fields["description"].get("1.0","end-1c"),"notes":fields["notes"].get("1.0","end-1c")})
    g["save"](item); window.destroy()
