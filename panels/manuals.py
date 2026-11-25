import os
import glob
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf
from ks_includes.screen_panel import ScreenPanel

MANUAL_DIR = os.path.expanduser("~/printer_data/config/documents/manuals")
EXTENSIONS = ("png", "gif", "jpg", "jpeg")


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)

        # 폴더 안의 이미지를 이름순으로 자동 정렬
        self.pages = []
        for ext in EXTENSIONS:
            self.pages += glob.glob(os.path.join(MANUAL_DIR, f"*.{ext}"))
        self.pages = sorted(self.pages)
        self.index = 0

        self.image = Gtk.Image()
        self.page_label = Gtk.Label()

        prev_btn = Gtk.Button(label="◀")
        prev_btn.connect("clicked", self.change_page, -1)
        next_btn = Gtk.Button(label="▶")
        next_btn.connect("clicked", self.change_page, 1)

        btn_box = Gtk.Box(spacing=10, homogeneous=False)
        btn_box.pack_start(prev_btn, True, True, 0)
        btn_box.pack_start(self.page_label, False, False, 10)
        btn_box.pack_start(next_btn, True, True, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.add(self.image)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.add(scroll)
        box.add(btn_box)

        self.content.add(box)
        self.load_image()

    def load_image(self):
        # 폴더가 비어 있을 때 에러 방지
        if not self.pages:
            self.page_label.set_text("이미지 없음")
            return

        path = self.pages[self.index]
        try:
            if path.lower().endswith(".gif"):
                anim = GdkPixbuf.PixbufAnimation.new_from_file(path)
                self.image.set_from_animation(anim)
            else:
                #w = self._screen.width
                #h = self._screen.height
                #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, True)
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)   #No scale pic.  700x400 300dpi
                self.image.set_from_pixbuf(pixbuf)
        except Exception as e:
            self.page_label.set_text("로드 실패")
            print(f"manual panel: {path}: {e}")
            return

        self.page_label.set_text(f"{self.index + 1} / {len(self.pages)}")

    def change_page(self, widget, step):
        if not self.pages:
            return
        self.index = (self.index + step) % len(self.pages)
        self.load_image()
