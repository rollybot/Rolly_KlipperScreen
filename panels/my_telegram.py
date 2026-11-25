import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from ks_includes.screen_panel import ScreenPanel

NEXT_PANEL = "my_guide_tele"      # 열고 싶은 패널 (panels/my_guide_tele.py)
NEXT_TITLE = "텔레그램 가이드"

# 이미 등록된 ID 확인용 (printer.cfg 의 TELEGRAM_VARS.user_id)
TELEGRAM_VARS_OBJECT = "gcode_macro TELEGRAM_VARS"
TELEGRAM_VARS_KEY = "user_id"
TELEGRAM_UNSET_VALUES = ("", "0", "none")   # 이 값이면 미등록
MASK_TEXT = "******"                         # 등록된 ID 대신 보여줄 표시

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.entry = None
        self._from_guide = False
        self._masked = False      # 입력창에 ****** 표시 중인지

        # --- 메인 가로 분할 레이아웃 박스 (좌우 분할) ---
        main_layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        main_layout.set_property("margin", 10)
        main_layout.set_valign(Gtk.Align.FILL)
        main_layout.set_halign(Gtk.Align.FILL)

        # =========================================================================
        # [왼쪽 영역] 제목, 입력창, 저장/취소 버튼 + 하단 안내 텍스트(3줄)
        # =========================================================================
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left_box.set_hexpand(False)
        left_box.set_valign(Gtk.Align.START)

        # 1. 입력창 상단 제목 안내 문구
        label_title = Gtk.Label()
        label_title.set_markup(
            '<span foreground="#aaaaaa" size="large" weight="bold">🤖 Telegram Chat ID 입력</span>'
        )
        label_title.set_halign(Gtk.Align.CENTER)
        left_box.pack_start(label_title, False, False, 2)

        # 2. 입력창과 버튼의 가로폭을 동기화하기 위한 중앙 정렬 컨테이너
        upper_center_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        upper_center_container.set_halign(Gtk.Align.CENTER)
        upper_center_container.set_size_request(340, -1)

        # 입력창
        self.entry = Gtk.Entry()
        self.entry.set_alignment(0.5)
        self.entry.set_hexpand(True)
        self.entry.set_size_request(-1, 80)
        self.entry.set_width_chars(1)   # 글자 수 때문에 입력창이 넓어지지 않게
        self.entry.set_can_focus(True)

        ctx = self.entry.get_style_context()
        css = Gtk.CssProvider()
        css.load_from_data(
            b"entry { font-size: 22px; font-weight: bold; background-color: #1a1a1a;"
            b" color: #00e676; border: 2px solid #444; border-radius: 6px; margin: 0; }"
        )
        ctx.add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        upper_center_container.pack_start(self.entry, False, False, 0)

        # 제어 버튼 가로 배치 박스
        btn_action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        btn_action_box.set_hexpand(True)
        btn_action_box.set_property("homogeneous", True)

        btn_cancel = Gtk.Button(label="입력 취소")
        btn_cancel.connect("clicked", self._on_cancel)
        btn_cancel.set_size_request(-1, 80)
        btn_cancel.get_style_context().add_class("split-nav-btn")
        if btn_cancel.get_child():
            btn_cancel.get_child().get_style_context().add_class("split-nav-text")

        btn_confirm = Gtk.Button(label="ID 저장")
        btn_confirm.connect("clicked", self._on_confirm)
        btn_confirm.set_size_request(-1, 80)
        btn_confirm.get_style_context().add_class("split-save-btn")
        if btn_confirm.get_child():
            btn_confirm.get_child().get_style_context().add_class("split-save-text")

        btn_action_box.pack_start(btn_cancel, True, True, 0)
        btn_action_box.pack_start(btn_confirm, True, True, 0)
        upper_center_container.pack_start(btn_action_box, False, False, 0)

        left_box.pack_start(upper_center_container, False, False, 0)

        # 1. ID 삭제 버튼 (위쪽 배치)
        btn_delete = Gtk.Button(label="저장된 ID 삭제")
        btn_delete.connect("clicked", self._on_delete_id)
        btn_delete.set_size_request(340, 85)
        btn_delete.set_halign(Gtk.Align.CENTER)
        btn_delete.set_property("margin-top", 20)  # 위쪽 여백 20 적용
        btn_delete.get_style_context().add_class("split-del-btn")
        if btn_delete.get_child():
            btn_delete.get_child().get_style_context().add_class("split-del-text")
        left_box.pack_start(btn_delete, False, False, 0)

        # 2. 가이드 버튼 (아래쪽 배치)
        btn_guide = Gtk.Button(label="가이드")
        btn_guide.connect("clicked", self._on_next_panel)
        btn_guide.set_size_request(340, 85)
        btn_guide.set_halign(Gtk.Align.CENTER)
        btn_guide.set_property("margin-top", 6)   # 버튼 사이 간격 6 적용
        btn_guide.get_style_context().add_class("split-guide-btn")
        if btn_guide.get_child():
            btn_guide.get_child().get_style_context().add_class("split-guide-text")
        left_box.pack_start(btn_guide, False, False, 0)

        # 입력창/취소·저장 줄과 두 버튼의 폭을 항상 똑같이 맞춤
        self._row_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        self._row_group.add_widget(upper_center_container)
        self._row_group.add_widget(btn_guide)
        self._row_group.add_widget(btn_delete)

        # 왼쪽 영역 배치
        main_layout.pack_start(left_box, False, False, 0)

        # =========================================================================
        # [오른쪽 영역] 화면의 오른쪽을 가득 채우는 숫자 키패드 격자
        # =========================================================================
        right_grid = Gtk.Grid()
        right_grid.set_column_spacing(12)
        right_grid.set_row_spacing(10)
        right_grid.set_column_homogeneous(True)
        right_grid.set_row_homogeneous(True)
        right_grid.set_hexpand(True)
        right_grid.set_vexpand(True)

        buttons = [
            ('7', 0, 0), ('8', 1, 0), ('9', 2, 0),
            ('4', 0, 1), ('5', 1, 1), ('6', 2, 1),
            ('1', 0, 2), ('2', 1, 2), ('3', 2, 2),
            ('0', 1, 3)
        ]

        for (text, col, row) in buttons:
            btn = Gtk.Button(label=text)
            btn.set_hexpand(True)
            btn.set_vexpand(True)
            btn.get_style_context().add_class("split-num-btn")
            btn.connect("clicked", self._on_num_clicked, text)

            btn_label = btn.get_child()
            if btn_label:
                btn_label.get_style_context().add_class("split-num-text")

            right_grid.attach(btn, col, row, 1, 1)

        # 지우기(←) 버튼
        btn_clear = Gtk.Button(label="←")
        btn_clear.set_hexpand(True)
        btn_clear.set_vexpand(True)
        btn_clear.get_style_context().add_class("split-clear-btn")
        btn_clear.connect("clicked", self._on_clear_clicked)
        if btn_clear.get_child():
            btn_clear.get_child().get_style_context().add_class("split-clear-text")
        right_grid.attach(btn_clear, 0, 3, 1, 1)

        # 전체 지우기(C) 버튼
        btn_reset = Gtk.Button(label="C")
        btn_reset.set_hexpand(True)
        btn_reset.set_vexpand(True)
        btn_reset.get_style_context().add_class("split-clear-btn")
        btn_reset.connect("clicked", self._on_reset_clicked)
        if btn_reset.get_child():
            btn_reset.get_child().get_style_context().add_class("split-clear-text")
        right_grid.attach(btn_reset, 2, 3, 1, 1)

        main_layout.pack_start(right_grid, True, True, 0)

        # =========================================================================
        # 글로벌 UI 테마 스타일시트
        # =========================================================================
        theme_css = Gtk.CssProvider()
        theme_css.load_from_data(
            b".split-num-text { font-size: 35px; font-weight: bold; color: white; }"
            b".split-clear-text { font-size: 35px; font-weight: bold; color: white; }"
            b".split-num-btn { font-size: 32px; font-weight: bold; background-color: #2b2b2b;"
            b" color: white; border-radius: 8px; }"
            b".split-num-btn:active { background-color: #444444; }"
            b".split-clear-btn { font-size: 24px; background-color: #1e1e1e; color: white;"
            b" border-radius: 8px; }"
            b".split-clear-btn:active { background-color: #555555; }"
            b".split-nav-btn { font-size: 20px; background-color: #424242; color: white;"
            b" font-weight: bold; border-radius: 6px; }"
            b".split-save-btn { font-size: 20px; background-color: #007bc2; color: white;"
            b" font-weight: bold; border-radius: 6px; }"
            b".split-save-btn:active { background-color: #0096ff; }"
            b".split-guide-btn { font-size: 18px; background-color: #2e7d32; color: white;"
            b" font-weight: bold; border-radius: 6px; }"
            b".split-guide-btn:active { background-color: #43a047; }"
            b".split-guide-text { font-size: 25px; font-weight: bold; color: white; }"
            b".split-guide-btn { background-color: #2e7d32; border-radius: 6px; }"
            b".split-guide-btn:active { background-color: #43a047; }"
            b".split-del-btn { background-color: #c62828; border-radius: 6px; }"
            b".split-del-btn:active { background-color: #e53935; }"
            b".split-del-text { font-size: 25px; font-weight: bold; color: white; }"
            b".split-nav-text { font-size: 25px; font-weight: bold; color: white; }"
            b".split-save-text { font-size: 25px; font-weight: bold; color: white; }"
            b".split-nav-btn, .split-save-btn, .split-guide-btn, .split-del-btn"
            b" { margin: 0; box-shadow: none; }"
        )
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), theme_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.content.add(main_layout)

    # --- 이벤트 핸들러 ---
    def activate(self):
        # 가이드 화면에서 돌아온 경우는 입력값 유지
        if self._from_guide:
            self._from_guide = False
            return
        self.entry.set_text("")
        self._masked = False
        self._check_registered()   # 이미 등록된 ID가 있으면 ****** 표시

    def _check_registered(self):
        try:
            self._screen._ws.send_method(
                "printer.objects.query",
                {"objects": {TELEGRAM_VARS_OBJECT: None}},
                self._on_registered_result,
            )
        except Exception as e:
            logging.info(f"Telegram registered check failed: {e}")

    def _on_registered_result(self, result, *args):
        try:
            data = result.get("result", result)
            val = data["status"][TELEGRAM_VARS_OBJECT][TELEGRAM_VARS_KEY]
        except Exception:
            logging.info(f"Telegram registered check: unexpected result {result}")
            return
        if str(val).strip().strip("\"'").lower() in TELEGRAM_UNSET_VALUES:
            return
        GLib.idle_add(self._show_mask)

    def _show_mask(self):
        # 이미 숫자를 입력하기 시작했다면 덮어쓰지 않음
        if self.entry.get_text() == "":
            self.entry.set_text(MASK_TEXT)
            self._masked = True
        return False

    def _on_num_clicked(self, widget, num_char):
        if self._masked:           # ****** 표시 중이면 지우고 새 ID 입력 시작
            self.entry.set_text("")
            self._masked = False
        current_text = self.entry.get_text()
        self.entry.set_text(current_text + num_char)

    def _on_clear_clicked(self, widget):
        if self._masked:
            self.entry.set_text("")
            self._masked = False
            return
        current_text = self.entry.get_text()
        if current_text:
            self.entry.set_text(current_text[:-1])

    def _on_reset_clicked(self, widget):
        self._masked = False
        self.entry.set_text("")

    def _on_confirm(self, widget):
        # ****** 표시 그대로면 새로 입력한 게 없으므로 기존 ID 유지
        user_id = "" if self._masked else self.entry.get_text().strip()
        if user_id:
            logging.info(f"Telegram SplitPanel - 입력된 ID: {user_id}")
            gcode_cmd = f"SET_TELEGRAM_ID_SCREEN VALUE={user_id}"
            self._screen._ws.send_method("printer.gcode.script", {"script": gcode_cmd})

            if hasattr(self._screen, "show_popup_message"):
                self._screen.show_popup_message(f"텔레그램 ID {user_id} 등록 완료!", level=1)
                GLib.timeout_add(800, self._close_popup)   # mm초 뒤 닫기

        self._back_to_main()

    def _on_delete_id(self, widget):
        """등록된 텔레그램 ID 삭제 (알림 끄기)"""
        logging.info("Telegram SplitPanel - ID 삭제 (CLEAR_TELEGRAM_ID)")
        self._screen._ws.send_method("printer.gcode.script", {"script": "CLEAR_TELEGRAM_ID"})

        if hasattr(self._screen, "show_popup_message"):
            self._screen.show_popup_message("텔레그램 알림 해제 완료!", level=1)
            GLib.timeout_add(800, self._close_popup)

        self._back_to_main()

    def _close_popup(self):
        if hasattr(self._screen, "close_popup_message"):
            self._screen.close_popup_message()
        return False

    def _on_next_panel(self, widget=None):
        self._from_guide = True       # 추가: 돌아오면 입력값 유지
        self._screen.show_panel(NEXT_PANEL, NEXT_TITLE)

    def _on_cancel(self, widget):
        self._back_to_main()

    def _back_to_main(self):
        self._masked = False
        self.entry.set_text("")      # 추가: 나갈 때 입력값 초기화
        if self._screen._cur_panels and self._screen._cur_panels[-1] == "my_telegram":
            self._screen._menu_go_back()