import os
import ast
import logging
import configparser
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib, Pango
from ks_includes.screen_panel import ScreenPanel

IMAGE_PATH = os.path.expanduser("~/printer_data/config/documents/notice/notice.png")

# save_variables 파일 경로 (printer.cfg의 [save_variables] filename과 같아야 함)
VARS_PATH = os.path.expanduser("~/printer_data/config/variables.cfg")
VAR_NAME = "notice_text"

# 공지 닫은 뒤 보여줄 패널
TARGET_PANEL = "gcodes"          # editedy by rollybot    프린터 버튼을 누르면 my_notice 그리고 gcodes 패널에서 출력할 파일 고르기

# ===== 텍스트 설정 =====
TEXT_HALIGN = Gtk.Align.CENTER   # 좌우: START(왼쪽) / CENTER(가운데) / END(오른쪽)
TEXT_VALIGN = Gtk.Align.CENTER   # 위아래: START(위) / CENTER(가운데) / END(아래)
TEXT_MARGIN = 20                 # 가장자리와의 여백(px)
TEXT_SIZE = "x-large"            # large / x-large / xx-large 또는 숫자(1/1024 pt)
TEXT_BG = True                   # 글자 뒤 반투명 검정 배경 사용 여부
TEXT_WRAP_CHARS = 54             # 한 줄 최대 글자 폭 (넘으면 자동 줄바꿈, 한글은 폭이 넓어 영문의 절반 정도로 잡음)


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.overlay_widget = None

    def activate(self):
        # 패널이 붙은 직후에 실행되도록 한 박자 늦춤
        GLib.idle_add(self._show_overlay)

    def _open_target_panel(self):
        # 껍데기 패널(my_notice)을 닫고 gcodes 패널로 이동
        if self._screen._cur_panels and self._screen._cur_panels[-1] == "my_notice":
            self._screen._menu_go_back()
        self._screen.show_panel(TARGET_PANEL, remove_all=False)

    def _show_overlay(self):
        text = self._load_text()

        # gcodes 패널은 문구 유무와 상관없이 항상 연다
        self._open_target_panel()

        # 문구가 비어 있으면 오버레이를 띄우지 않음
        if not text:
            return False

        self._remove_overlay()

        # 줄바꿈은 라벨(Pango)이 실제 글자 폭 기준으로 처리
        content = self._build_content(text)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)

        event_box = Gtk.EventBox()
        event_box.set_visible_window(False)   # 배경을 그리지 않아 알파가 유지됨
        event_box.set_above_child(True)       # 화면 어디를 눌러도 이벤트를 받음
        event_box.add(content)
        event_box.connect("button-press-event", self._on_click)

        self._screen.overlay.add_overlay(event_box)
        event_box.show_all()
        self.overlay_widget = event_box
        return False

    def _load_text(self):
        """save_variables 파일에서 공지 문구를 읽어 옴. 없거나 비면 빈 문자열"""
        try:
            cp = configparser.ConfigParser()
            cp.read(VARS_PATH, encoding="utf-8")
            raw = cp.get("Variables", VAR_NAME)
            text = str(ast.literal_eval(raw)).strip()
            return text.replace("\\n", "\n")   # 입력칸의 \n 을 줄바꿈으로 변환
        except Exception as e:
            logging.info(f"notice: no text ({e})")
            return ""

    def _build_content(self, text):
        # 이미지 로드 (없거나 손상된 경우 안내 문구)
        try:
            if not os.path.exists(IMAGE_PATH):
                return Gtk.Label(label="notice.png 파일을 찾을 수 없습니다")
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                IMAGE_PATH, self._screen.width, self._screen.height, True
            )
            image = Gtk.Image.new_from_pixbuf(pixbuf)
        except GLib.Error as e:
            return Gtk.Label(label=f"이미지를 불러올 수 없습니다: {e.message}")

        overlay = Gtk.Overlay()
        overlay.add(image)

        label = Gtk.Label()
        label.set_markup(
            f'<span foreground="white" size="{TEXT_SIZE}" weight="bold">'
            f'{GLib.markup_escape_text(text)}</span>'
        )
        label.set_halign(TEXT_HALIGN)
        label.set_valign(TEXT_VALIGN)
        label.set_margin_start(TEXT_MARGIN)
        label.set_margin_end(TEXT_MARGIN)
        label.set_margin_top(TEXT_MARGIN)
        label.set_margin_bottom(TEXT_MARGIN)

        # 자동 줄바꿈: 단어 단위로 먼저, 안 되면 글자 단위로 (띄어쓰기 없는 한글 대응)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(TEXT_WRAP_CHARS)

        # 여러 줄일 때 줄 내부 정렬도 좌우 정렬에 맞춤
        if TEXT_HALIGN == Gtk.Align.START:
            label.set_justify(Gtk.Justification.LEFT)
            label.set_xalign(0.0)
        elif TEXT_HALIGN == Gtk.Align.END:
            label.set_justify(Gtk.Justification.RIGHT)
            label.set_xalign(1.0)
        else:
            label.set_justify(Gtk.Justification.CENTER)

        # 반투명 배경 (밝은 이미지에서도 흰 글씨가 보이도록)
        if TEXT_BG:
            css = Gtk.CssProvider()
            css.load_from_data(
                b"label.notice-text { background-color: rgba(0,0,0,0.6);"
                b" padding: 10px; border-radius: 8px; }"
            )
            ctx = label.get_style_context()
            ctx.add_class("notice-text")
            ctx.add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        overlay.add_overlay(label)
        overlay.set_overlay_pass_through(label, True)  # 글자 위를 눌러도 클릭 전달
        return overlay

    def _on_click(self, widget=None, event=None):
        self._remove_overlay()
        return True

    def _remove_overlay(self):
        if self.overlay_widget is not None:
            if self.overlay_widget.get_parent() is not None:
                self._screen.overlay.remove(self.overlay_widget)
            self.overlay_widget = None