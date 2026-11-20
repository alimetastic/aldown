import json
import ctypes
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import yt_dlp

SETTINGS = Path.home() / ".ytdlp_gui.json"

THEMES = {
    "light": {"bg": "#f0f0f0", "field": "#ffffff", "fg": "#1a1a1a", "border": "#c4c4c4",
              "hover": "#e0e0e0", "disabled": "#9a9a9a", "accent": "#2f6fdf"},
    "dark":  {"bg": "#1e1e1e", "field": "#2b2b2b", "fg": "#e6e6e6", "border": "#3c3c3c",
              "hover": "#383838", "disabled": "#6a6a6a", "accent": "#3d7eff"},
}


def fmt_size(n):
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_duration(s):
    if not s:
        return "?"
    s = int(s)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ALDOWN Downloader")
        self.geometry("760x560")
        self.minsize(640, 480)

        self.info = None
        self.video_formats = []
        self.audio_formats = []
        self.mode = tk.StringVar(value="mp4")
        self.out_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        try:
            dark = json.loads(SETTINGS.read_text()).get("dark", False)
        except Exception:
            dark = False
        self.dark = tk.BooleanVar(value=dark)

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Link:").pack(side="left")
        self.url = ttk.Entry(top)
        self.url.pack(side="left", fill="x", expand=True, padx=5)
        self.url.bind("<Return>", lambda e: self.fetch())
        self.fetch_btn = ttk.Button(top, text="Fetch", command=self.fetch)
        self.fetch_btn.pack(side="left")
        ttk.Checkbutton(top, text="Dark mode", variable=self.dark,
                        command=self.apply_theme).pack(side="left", padx=(10, 0))

        info_box = ttk.LabelFrame(self, text="Information", padding=5)
        info_box.pack(fill="both", expand=True, padx=10)
        self.info_text = tk.Text(info_box, height=10, wrap="word", state="disabled")
        self.info_text.pack(fill="both", expand=True)

        opts = ttk.LabelFrame(self, text="Download options", padding=10)
        opts.pack(fill="x", padx=10, pady=10)
        opts.columnconfigure(1, weight=1)

        modes = ttk.Frame(opts)
        modes.grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(modes, text="MP4 (video)", variable=self.mode, value="mp4",
                        command=self.fill_qualities).pack(side="left")
        ttk.Radiobutton(modes, text="MP3 (audio)", variable=self.mode, value="mp3",
                        command=self.fill_qualities).pack(side="left", padx=15)

        ttk.Label(opts, text="Quality:").grid(row=1, column=0, sticky="w", pady=5)
        self.quality = ttk.Combobox(opts, state="readonly")
        self.quality.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)

        ttk.Label(opts, text="MP3 bitrate:").grid(row=2, column=0, sticky="w")
        self.bitrate = ttk.Combobox(opts, state="disabled", width=10,
                                    values=["320", "256", "192", "160", "128", "96", "64"])
        self.bitrate.set("192")
        self.bitrate.grid(row=2, column=1, sticky="w")

        ttk.Label(opts, text="Save to:").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(opts, textvariable=self.out_dir).grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Button(opts, text="Browse", command=self.browse).grid(row=3, column=2, padx=(5, 0))

        bottom = ttk.Frame(self, padding=(10, 0, 10, 10))
        bottom.pack(fill="x")
        self.dl_btn = ttk.Button(bottom, text="Download", command=self.download, state="disabled")
        self.dl_btn.pack(side="left")
        self.progress = ttk.Progressbar(bottom, maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=10)
        self.status = ttk.Label(bottom, text="Paste a link and press Fetch", width=34)
        self.status.pack(side="left")

        self.apply_theme()

    def apply_theme(self):
        dark = self.dark.get()
        c = THEMES["dark" if dark else "light"]

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["field"],
                        bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"],
                        troughcolor=c["field"], selectbackground=c["accent"],
                        selectforeground="#ffffff", insertcolor=c["fg"])
        style.map("TButton", background=[("disabled", c["bg"]), ("active", c["hover"])],
                  foreground=[("disabled", c["disabled"])])
        style.map("TCombobox", fieldbackground=[("readonly", c["field"]), ("disabled", c["bg"])],
                  foreground=[("disabled", c["disabled"])],
                  selectbackground=[("readonly", c["field"])], selectforeground=[("readonly", c["fg"])])
        style.configure("TCombobox", arrowcolor=c["fg"])
        style.map("TRadiobutton", background=[("active", c["bg"])],
                  indicatorcolor=[("selected", c["accent"]), ("!selected", c["field"])])
        style.map("TCheckbutton", background=[("active", c["bg"])],
                  indicatorcolor=[("selected", c["accent"]), ("!selected", c["field"])])
        style.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
        style.configure("Horizontal.TProgressbar", background=c["accent"])

        self.configure(bg=c["bg"])
        self.info_text.config(bg=c["field"], fg=c["fg"], insertbackground=c["fg"],
                              selectbackground=c["accent"], relief="flat",
                              highlightthickness=1, highlightbackground=c["border"])

        for cb in (self.quality, self.bitrate):
            popdown = self.tk.eval(f"ttk::combobox::PopdownWindow {cb}")
            self.tk.call(f"{popdown}.f.l", "configure", "-background", c["field"],
                         "-foreground", c["fg"], "-selectbackground", c["accent"],
                         "-selectforeground", "#ffffff")

        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1 if dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

        try:
            SETTINGS.write_text(json.dumps({"dark": dark}))
        except Exception:
            pass

    def set_status(self, text):
        self.after(0, lambda: self.status.config(text=text))

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)

    def fetch(self):
        url = self.url.get().strip()
        if not url:
            return
        self.fetch_btn.config(state="disabled")
        self.dl_btn.config(state="disabled")
        self.status.config(text="Fetching info...")
        threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _fetch(self, url):
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
                info = ydl.extract_info(url, download=False)
            self.after(0, self.show_info, info)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.set_status("Failed to fetch")
        finally:
            self.after(0, lambda: self.fetch_btn.config(state="normal"))

    def show_info(self, info):
        self.info = info
        formats = info.get("formats") or [info]

        self.video_formats = sorted(
            [f for f in formats if f.get("vcodec") != "none" and f.get("height")],
            key=lambda f: (f.get("height") or 0, f.get("fps") or 0, f.get("tbr") or 0),
            reverse=True,
        )
        self.audio_formats = sorted(
            [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")],
            key=lambda f: f.get("abr") or 0,
            reverse=True,
        )

        heights = sorted({f["height"] for f in self.video_formats}, reverse=True)
        upload = info.get("upload_date") or ""
        if len(upload) == 8:
            upload = f"{upload[:4]}-{upload[4:6]}-{upload[6:]}"
        views = info.get("view_count")
        likes = info.get("like_count")

        lines = [
            f"Title:       {info.get('title', '?')}",
            f"Channel:     {info.get('uploader') or info.get('channel') or '?'}",
            f"Duration:    {fmt_duration(info.get('duration'))}",
            f"Uploaded:    {upload or '?'}",
            f"Views:       {views:,}" if views else "Views:       ?",
            f"Likes:       {likes:,}" if likes else "Likes:       ?",
            f"Site:        {info.get('extractor_key', '?')}",
            f"Resolutions: {', '.join(f'{h}p' for h in heights) or 'none'}",
            f"Audio:       {len(self.audio_formats)} stream(s)",
            "",
            (info.get("description") or "")[:500],
        ]
        self.info_text.config(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", "\n".join(lines))
        self.info_text.config(state="disabled")

        self.fill_qualities()
        self.dl_btn.config(state="normal")
        self.status.config(text="Ready")

    def fill_qualities(self):
        if self.mode.get() == "mp4":
            self.bitrate.config(state="disabled")
            items = ["Best available"]
            for f in self.video_formats:
                fps = f.get("fps")
                fps = f"{fps:g}fps" if fps else ""
                vcodec = (f.get("vcodec") or "?").split(".")[0]
                size = fmt_size(f.get("filesize") or f.get("filesize_approx"))
                audio = "" if f.get("acodec") in (None, "none") else " | has audio"
                items.append(f"{f['height']}p {fps} | {f.get('ext')} | {vcodec} | {size}{audio} | id {f['format_id']}")
        else:
            self.bitrate.config(state="readonly")
            items = ["Best available"]
            for f in self.audio_formats:
                abr = f.get("abr")
                abr = f"{abr:.0f} kbps" if abr else "? kbps"
                acodec = (f.get("acodec") or "?").split(".")[0]
                size = fmt_size(f.get("filesize") or f.get("filesize_approx"))
                lang = f" | {f['language']}" if f.get("language") else ""
                items.append(f"{abr} | {f.get('ext')} | {acodec} | {size}{lang} | id {f['format_id']}")
        self.quality.config(values=items)
        self.quality.current(0)

    def download(self):
        if not self.info:
            return
        idx = self.quality.current()
        out = self.out_dir.get()
        url = self.info.get("webpage_url") or self.url.get().strip()

        if self.mode.get() == "mp4":
            if idx <= 0:
                fmt = "bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            else:
                f = self.video_formats[idx - 1]
                fid = f["format_id"]
                fmt = fid if f.get("acodec") not in (None, "none") else f"{fid}+bestaudio[ext=m4a]/{fid}+bestaudio"
            opts = {
                "format": fmt,
                "merge_output_format": "mp4",
                "outtmpl": str(Path(out) / "%(title)s [%(height)sp].%(ext)s"),
            }
        else:
            fmt = "bestaudio/best" if idx <= 0 else self.audio_formats[idx - 1]["format_id"]
            opts = {
                "format": fmt,
                "outtmpl": str(Path(out) / "%(title)s.%(ext)s"),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.bitrate.get(),
                }],
            }

        opts.update({"quiet": True, "noplaylist": True, "progress_hooks": [self.hook]})
        self.dl_btn.config(state="disabled")
        self.fetch_btn.config(state="disabled")
        self.progress["value"] = 0
        threading.Thread(target=self._download, args=(url, opts), daemon=True).start()

    def _download(self, url, opts):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self.set_status("Done!")
            self.after(0, lambda: self.progress.config(value=100))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Download failed", str(e)))
            self.set_status("Failed")
        finally:
            self.after(0, lambda: (self.dl_btn.config(state="normal"),
                                   self.fetch_btn.config(state="normal")))

    def hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            pct = done / total * 100 if total else 0
            speed = d.get("speed")
            eta = d.get("eta")
            text = f"{pct:.1f}% | {fmt_size(speed)}/s | ETA {fmt_duration(eta) if eta else '?'}"
            self.after(0, lambda: (self.progress.config(value=pct), self.status.config(text=text)))
        elif d["status"] == "finished":
            self.set_status("Processing (ffmpeg)...")


if __name__ == "__main__":
    App().mainloop()
