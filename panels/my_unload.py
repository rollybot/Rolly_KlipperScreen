import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from ks_includes.screen_panel import ScreenPanel

PANEL_NAME = "my_unload"        # 파일명, 메뉴의 panel: 값과 동일하게
MACRO_NAME = "UNLOAD_FILAMENT"  # 실행할 gcode_macro 이름
NEXT_PANEL = "my_Uguides"       # 열고 싶은 다른 오버레이 패널 (파일명)
NEXT_TITLE = "내 옵션"          # 그 패널에 넘길 제목

CSS = b"""
.bed_overlay { background-color: rgba(0, 0, 0, 0.8); }
.bed_overlay label { color: #f5f5f5; }
.bed_overlay button { background-image: none; background-color: #000000; border: 1px solid #aaaaaa; min-height: 60px; }
.bed_overlay separator { background-color: #888888; min-height: 2px; }
"""


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.title_text = title
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

        # 제목 + 구분선
        title_label = Gtk.Label(hexpand=True, halign=Gtk.Align.CENTER)
        title_label.set_markup(
            f'<span size="xx-large" weight="bold">{self.title_text}</span>'
        )
        box.pack_start(title_label, False, False, 0)
        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # 가운데 안내 문구 (남는 공간을 모두 차지해서 버튼을 아래로 밀어냄)
        info_label = Gtk.Label(vexpand=True, hexpand=True)
        info_label.set_markup(
            '<span size="x-large" weight="bold">필라멘트 제거를 시작하시겠습니까?</span>\n\n'
            '<span size="large">핫엔드(노즐)을 가열합니다.</span>\n'
            '<span size="large">화상에 주의하세요!</span>'
        )
        info_label.set_justify(Gtk.Justification.CENTER)
        info_label.set_line_wrap(True)
        box.pack_start(info_label, True, True, 0)

        # 하단 버튼 3개
        btn_row = Gtk.Box(spacing=15, homogeneous=True)
        btn_row.add(self._make_button("필라멘트 제거", self._on_macro))
        btn_row.add(self._make_button("가이드", self._on_next_panel))
        btn_row.add(self._make_button("닫기", self._on_close))
        box.pack_end(btn_row, False, False, 0)

        # 배경을 그리는 EventBox: 아래 화면으로 터치가 새지 않게 막아줌
        event_box = Gtk.EventBox()
        event_box.get_style_context().add_class("bed_overlay")
        event_box.add(box)

        self._screen.overlay.add_overlay(event_box)
        event_box.show_all()
        self.overlay_widget = event_box
        return False

    def _make_button(self, text, callback):
        btn = Gtk.Button(hexpand=True)
        label = Gtk.Label()
        label.set_markup(f'<span size="x-large">{text}</span>')
        btn.add(label)
        btn.connect("clicked", callback)
        return btn

    def _on_macro(self, widget=None):
        logging.info("my_unload: 레벨링 버튼 눌림")
        try:
            self._screen._send_action(
                widget, "printer.gcode.script", {"script": MACRO_NAME}
            )
        except Exception as e:
            logging.exception("my_unload: 매크로 전송 실패")
            self._screen.show_popup_message(f"실행 실패: {e}")
            return
        self._remove_overlay()

    def _on_next_panel(self, widget=None):
        # 현재 오버레이를 닫고 다른 오버레이 패널을 호출
        self._remove_overlay()
        self._screen.show_panel(NEXT_PANEL, NEXT_TITLE)

    def _on_close(self, widget=None):
        self._remove_overlay()

    def _remove_overlay(self):
        if self.overlay_widget is not None:
            self._screen.overlay.remove(self.overlay_widget)
            self.overlay_widget = None
