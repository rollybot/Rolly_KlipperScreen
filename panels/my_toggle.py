import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from ks_includes.screen_panel import ScreenPanel

PANEL_NAME = "my_toggle"   # 파일명, 메뉴의 panel: 값과 동일하게

# (표시 이름, 매크로 이름)
OPTIONS = [
    ("     Run-out Sensor", "OPTION_1"),
    ("     Option2"     , "OPTION_2"),
    ("     Option3"         , "OPTION_3"),
]

CSS = b"""
.my_overlay { background-color: rgba(0, 0, 0, 0.8); }
.my_overlay label { color: #f5f5f5; }
.my_overlay separator { background-color: #888888; min-height: 2px; }
switch.my_big { min-width: 90px; min-height: 44px; }
switch.my_big slider { min-width: 44px; min-height: 44px; }
"""


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.title_text = "시작전 준비사항"
        self.overlay_widget = None

        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def activate(self):
        # 패널이 붙은 직후에 실행되도록 한 박자 늦춤
        GLib.idle_add(self._show_overlay)

    def _show_overlay(self):
        # 껍데기 패널을 닫고 메인 메뉴로 복귀
        if self._screen._cur_panels and self._screen._cur_panels[-1] == PANEL_NAME:
            self._screen._menu_go_back()

        self._remove_overlay()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(30)
        box.set_margin_end(30)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_valign(Gtk.Align.CENTER)

        # 제목
        title_label = Gtk.Label(hexpand=True, halign=Gtk.Align.CENTER)
        title_label.set_markup(
            f'<span size="xx-large" weight="bold">{self.title_text}</span>'
        )
        title_label.set_margin_bottom(10)
        box.add(title_label)

        # 구분선
        box.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # 옵션 3줄
        for text, macro in OPTIONS:
            label = Gtk.Label(hexpand=True, halign=Gtk.Align.START)
            label.set_markup(f'<span size="x-large">{text}</span>')

            switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            switch.get_style_context().add_class("my_big")
            switch.set_active(self._read_state(macro))
            switch.connect("notify::active", self._on_switch, macro)

            row = Gtk.Box(spacing=20)
            row.add(label)
            row.add(switch)
            box.add(row)

        # 닫기 버튼
        close_btn = Gtk.Button()
        close_label = Gtk.Label()
        close_label.set_markup('<span size="x-large">CLOSE</span>')
        close_btn.add(close_label)
        close_btn.connect("clicked", self._on_close)
        box.add(close_btn)

        # 배경을 그리는 EventBox: 아래 화면으로 터치가 새지 않게 막아줌
        event_box = Gtk.EventBox()
        event_box.get_style_context().add_class("my_overlay")
        event_box.add(box)

        self._screen.overlay.add_overlay(event_box)
        event_box.show_all()
        self.overlay_widget = event_box
        return False

    def _read_state(self, macro):
        enabled = self._printer.get_stat(f"gcode_macro {macro}", "enabled")
        return bool(enabled)

    def _on_switch(self, switch, gparam, macro):
        value = 1 if switch.get_active() else 0
        self._screen._ws.klippy.gcode_script(
            f"SET_GCODE_VARIABLE MACRO={macro} VARIABLE=enabled VALUE={value}"
        )

    def _on_close(self, widget=None):
        self._remove_overlay()

    def _remove_overlay(self):
        if self.overlay_widget is not None:
            self._screen.overlay.remove(self.overlay_widget)
            self.overlay_widget = None
