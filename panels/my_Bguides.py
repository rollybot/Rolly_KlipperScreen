import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from ks_includes.screen_panel import ScreenPanel

PANEL_NAME = "my_Bguides"   # 파일명, 호출할 때 쓰는 패널 이름과 동일하게
IMAGE_DIR = os.path.expanduser("~/printer_data/config/documents/guides/Bguides")
EXTENSIONS = (".png", ".jpg", ".jpeg")
BUTTON_AREA_HEIGHT = 100   # 하단 버튼 + 여백이 차지하는 높이(px). 화면에 맞게 조절

CSS = b"""
.guide_overlay { background-color: rgba(255, 255, 255, 0.95); }
.guide_overlay label { color: #000000; }
.guide_overlay button { background-image: none; background-color: #e0e0e0; border: 1px solid #aaaaaa; min-height: 45px; }
"""


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.title_text = title
        self.overlay_widget = None
        self.images = []
        self.index = 0

        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def activate(self):
        # 패널이 붙은 직후에 실행되도록 한 박자 늦춤
        GLib.idle_add(self._show_overlay)

    def _load_image_list(self):
        if not os.path.isdir(IMAGE_DIR):
            return []
        names = sorted(
            f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(EXTENSIONS)
        )
        return [os.path.join(IMAGE_DIR, n) for n in names]

    def _show_overlay(self):
        # 껍데기 패널을 닫고 이전 화면으로 복귀
        if self._screen._cur_panels and self._screen._cur_panels[-1] == PANEL_NAME:
            self._screen._menu_go_back()

        self._remove_overlay()
        self.images = self._load_image_list()
        self.index = 0

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        # 이미지 영역 (남는 공간을 모두 차지)
        self.image_widget = Gtk.Image(hexpand=True, vexpand=True)
        self.image_widget.set_halign(Gtk.Align.CENTER)
        self.image_widget.set_valign(Gtk.Align.CENTER)
        box.pack_start(self.image_widget, True, True, 0)

        # 하단: 이전 / 페이지 표시 / 다음 / 닫기
        self.prev_btn = self._make_button("◀ 이전", self._on_prev)
        self.next_btn = self._make_button("다음 ▶", self._on_next)
        close_btn = self._make_button("닫기", self._on_close)

        self.page_label = Gtk.Label(hexpand=True)

        btn_row = Gtk.Box(spacing=15)
        btn_row.pack_start(self.prev_btn, True, True, 0)
        btn_row.pack_start(self.page_label, True, True, 0)
        btn_row.pack_start(self.next_btn, True, True, 0)
        btn_row.pack_start(close_btn, True, True, 0)
        box.pack_end(btn_row, False, False, 0)

        # 배경을 그리는 EventBox: 아래 화면으로 터치가 새지 않게 막아줌
        event_box = Gtk.EventBox()
        event_box.get_style_context().add_class("guide_overlay")
        event_box.add(box)

        self._screen.overlay.add_overlay(event_box)
        event_box.show_all()
        self.overlay_widget = event_box

        self._update_page()
        return False

    def _make_button(self, text, callback):
        btn = Gtk.Button(hexpand=True)
        label = Gtk.Label()
        label.set_markup(f'<span size="x-large">{text}</span>')
        btn.add(label)
        btn.connect("clicked", callback)
        return btn

    def _update_page(self):
        total = len(self.images)

        if total == 0:
            self.image_widget.clear()
            self.page_label.set_markup('<span size="large">이미지 없음</span>')
            self.prev_btn.set_sensitive(False)
            self.next_btn.set_sensitive(False)
            return

        max_w = int(self._screen.width - 40)
        max_h = int(self._screen.height - BUTTON_AREA_HEIGHT)
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                self.images[self.index], max_w, max_h, True
            )
            self.image_widget.set_from_pixbuf(pixbuf)
        except GLib.Error:
            self.image_widget.clear()

        self.page_label.set_markup(
            f'<span size="large">{self.index + 1} / {total}</span>'
        )
        self.prev_btn.set_sensitive(self.index > 0)
        self.next_btn.set_sensitive(self.index < total - 1)

    def _on_prev(self, widget=None):
        if self.index > 0:
            self.index -= 1
            self._update_page()

    def _on_next(self, widget=None):
        if self.index < len(self.images) - 1:
            self.index += 1
            self._update_page()

    def _on_close(self, widget=None):
        self._remove_overlay()
        self._screen.show_panel("my_leveling", "베드 레벨")

    def _remove_overlay(self):
        if self.overlay_widget is not None:
            self._screen.overlay.remove(self.overlay_widget)
            self.overlay_widget = None
