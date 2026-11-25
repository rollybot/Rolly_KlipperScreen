import logging
import math
import re
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from ks_includes.screen_panel import ScreenPanel

PANEL_NAME = "my_leveling"      # 파일명, 메뉴의 panel: 값과 동일하게
MACRO_NAME = "BED_LEVELING"     # 실행할 gcode_macro 이름
NEXT_PANEL = "my_Bguides"       # 열고 싶은 다른 오버레이 패널 (파일명)
NEXT_TITLE = "내 옵션"          # 그 패널에 넘길 제목
MARKER_DONE = "BED_LEVEL_DONE"  # 매크로 끝에서 RESPOND로 보낼 문자열
MAX_LINES = 200                 # 콘솔에 유지할 최대 줄 수

# ---- 원형 베드 설정 ----
BED_RADIUS = 100.0              # 베드 반지름 (mm)
CENTER_X = 0.0                  # 베드 중심 X (델타면 0)
CENTER_Y = 0.0                  # 베드 중심 Y (델타면 0)
PROBE_OFFSET_X = 0.0            # [probe]의 x_offset
PROBE_OFFSET_Y = 0.0            # [probe]의 y_offset
MAP_SIZE = 260                  # 베드 맵 최대 크기 (px)
POLL_MS = 100                   # 위치 갱신 주기 (ms)

# ---- 측정점 감지 설정 ----
USE_Z_DETECT = True             # Z 하강/상승으로 측정점 감지
Z_TRIGGER_MAX = 5.0             # 이 높이(mm) 이하까지 내려갔을 때만 측정으로 인정

PROBE_RE = re.compile(
    r"probe at\s*[(\[]?\s*(-?\d+\.?\d*)\s*[, ]\s*(-?\d+\.?\d*)",
    re.IGNORECASE,
)

# 레벨링을 실행 중인 Panel 인스턴스 (show_panel이 인스턴스를 새로 만들기 때문)
_OWNER = None

CSS = b"""
.bed_overlay { background-color: rgba(0, 0, 0, 0.8); }
.bed_overlay label { color: #f5f5f5; }
.bed_overlay button { background-image: none; background-color: #000000; border: 1px solid #aaaaaa; min-height: 60px; }
.bed_overlay separator { background-color: #888888; min-height: 2px; }
.bed_overlay textview, .bed_overlay textview text { background-color: rgba(0, 0, 0, 0.6); color: #e0e0e0; }
"""


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.title_text = title
        self.overlay_widget = None

        # 레벨링 진행(콘솔) 상태
        self.running = False
        self.console_buf = None
        self.console_view = None
        self.status_label = None

        # 베드 맵 상태
        self.map_area = None
        self.cur_pos = None          # (x, y) 현재 프로브 위치
        self.probed = []             # [(x, y), ...] 측정 완료 지점
        self.poll_id = None
        self.last_z = None
        self.z_going_down = False
        self.z_min = None            # 하강 중 가장 낮았던 Z
        self.min_pos = None          # 그 순간의 (x, y)

        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # ------------------------------------------------------------------
    # 패널 진입
    # ------------------------------------------------------------------
    def activate(self):
        if _OWNER is not None:      # 레벨링 진행 중 재진입이면 확인창을 띄우지 않음
            return
        GLib.idle_add(self._show_overlay)

    # ------------------------------------------------------------------
    # 1단계: 확인 오버레이
    # ------------------------------------------------------------------
    def _show_overlay(self):
        if self._screen._cur_panels and self._screen._cur_panels[-1] == PANEL_NAME:
            self._screen._menu_go_back()

        self._remove_overlay()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(30)
        box.set_margin_end(30)
        box.set_margin_top(20)
        box.set_margin_bottom(20)

        title_label = Gtk.Label(hexpand=True, halign=Gtk.Align.CENTER)
        title_label.set_markup(
            f'<span size="xx-large" weight="bold">{self.title_text}</span>'
        )
        box.pack_start(title_label, False, False, 0)
        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        info_label = Gtk.Label(vexpand=True, hexpand=True)
        info_label.set_markup(
            '<span size="x-large" weight="bold">베드 레벨링을 시작하시겠습니까?</span>\n\n'
            '<span size="large">프로브를 장착하세요.</span>\n'
            '<span size="large">완료후 프린터가 재시작됩니다!</span>'
        )
        info_label.set_justify(Gtk.Justification.CENTER)
        info_label.set_line_wrap(True)
        box.pack_start(info_label, True, True, 0)

        btn_row = Gtk.Box(spacing=15, homogeneous=True)
        btn_row.add(self._make_button("레벨링 실행", self._on_macro))
        btn_row.add(self._make_button("가이드", self._on_next_panel))
        btn_row.add(self._make_button("닫기", self._on_close))
        box.pack_end(btn_row, False, False, 0)

        self._attach_overlay(box)
        return False

    def _make_button(self, text, callback):
        btn = Gtk.Button(hexpand=True)
        label = Gtk.Label()
        label.set_markup(f'<span size="x-large">{text}</span>')
        btn.add(label)
        btn.connect("clicked", callback)
        return btn

    def _attach_overlay(self, box):
        event_box = Gtk.EventBox()
        event_box.get_style_context().add_class("bed_overlay")
        event_box.add(box)

        self._screen.overlay.add_overlay(event_box)
        event_box.show_all()
        self.overlay_widget = event_box

    # ------------------------------------------------------------------
    # 2단계: 레벨링 실행 + 콘솔/베드맵 오버레이
    # ------------------------------------------------------------------
    def _on_macro(self, widget=None):
        global _OWNER
        logging.info("my_leveling: 레벨링 시작")
        _OWNER = self
        self._remove_overlay()
        self.running = True
        self.probed = []
        self.last_z = None
        self.z_going_down = False
        self.z_min = None
        self.min_pos = None
        self.cur_pos = self._read_toolhead_pos()

        self._screen.show_panel(PANEL_NAME, self.title_text)
        self._show_console()

        try:
            self._screen._send_action(
                widget, "printer.gcode.script", {"script": MACRO_NAME}
            )
        except Exception as e:
            logging.exception("my_leveling: 매크로 전송 실패")
            self._screen.show_popup_message(f"실행 실패: {e}")
            self._finish()

    def _show_console(self):
        self._remove_overlay()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        box.set_margin_start(30)
        box.set_margin_end(30)
        box.set_margin_top(20)
        box.set_margin_bottom(20)

        # 상태 표시 + 구분선
        self.status_label = Gtk.Label(hexpand=True, halign=Gtk.Align.CENTER)
        self._set_status("베드 레벨링 진행 중...")
        box.pack_start(self.status_label, False, False, 0)
        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # 본문: 왼쪽 베드 맵 + 오른쪽 콘솔
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)

        screen_h = getattr(self._screen, "height", 480)
        size = min(MAP_SIZE, int(screen_h * 0.6))
        self.map_area = Gtk.DrawingArea()
        self.map_area.set_size_request(size, size)
        self.map_area.set_valign(Gtk.Align.CENTER)
        self.map_area.set_halign(Gtk.Align.CENTER)
        self.map_area.connect("draw", self._on_draw_map)
        body.pack_start(self.map_area, False, False, 0)

        self.console_buf = Gtk.TextBuffer()
        self.console_view = Gtk.TextView(buffer=self.console_buf)
        self.console_view.set_editable(False)
        self.console_view.set_cursor_visible(False)
        self.console_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.console_view.set_left_margin(8)
        self.console_view.set_right_margin(8)

        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.console_view)
        body.pack_start(scroll, True, True, 0)

        box.pack_start(body, True, True, 0)

        # 비상용 닫기 버튼
        box.pack_end(self._make_button("닫기", self._on_force_close), False, False, 0)

        self._attach_overlay(box)

        # 위치 폴링 시작
        if self.poll_id:
            GLib.source_remove(self.poll_id)
        self.poll_id = GLib.timeout_add(POLL_MS, self._poll_pos)

        # 콘솔 첫 줄 메시지
        self._append("베드 온도 올리는 중...")

    def _set_status(self, text):
        if self.status_label:
            self.status_label.set_markup(
                f'<span size="xx-large" weight="bold">{text}</span>'
            )

    def _append(self, line):
        if self.console_buf is None or self.console_view is None:
            return
        self.console_buf.insert(self.console_buf.get_end_iter(), line + "\n")

        extra = self.console_buf.get_line_count() - MAX_LINES
        if extra > 0:
            self.console_buf.delete(
                self.console_buf.get_start_iter(),
                self.console_buf.get_iter_at_line(extra),
            )

        mark = self.console_buf.create_mark(None, self.console_buf.get_end_iter(), False)
        self.console_view.scroll_mark_onscreen(mark)
        self.console_buf.delete_mark(mark)

    # ------------------------------------------------------------------
    # 위치 읽기 / 폴링 / 측정 지점 기록
    # ------------------------------------------------------------------
    def _get_printer(self):
        return getattr(self, "_printer", None) or self._screen.printer

    def _read_toolhead_pos(self):
        try:
            pos = self._get_printer().data["toolhead"]["position"]
            return self._to_probe_xy(pos[0], pos[1])
        except Exception:
            logging.exception("my_leveling: toolhead 위치 읽기 실패")
            return None

    @staticmethod
    def _to_probe_xy(x, y):
        return (x + PROBE_OFFSET_X, y + PROBE_OFFSET_Y)

    def _add_probed(self, pt, authoritative=False):
        """측정 지점 기록.
        같은 위치(2mm 이내)가 이미 있으면 중복 기록하지 않되,
        authoritative=True(Klipper 응답 파싱 좌표)이면 기존 점을 정확한 좌표로 교체한다.
        """
        for i, p in enumerate(self.probed):
            if abs(pt[0] - p[0]) < 2 and abs(pt[1] - p[1]) < 2:
                if authoritative:
                    self.probed[i] = pt
                return
        self.probed.append(pt)
        logging.info(f"my_leveling: 점 추가 {pt} (총 {len(self.probed)}개)")

    def _poll_pos(self):
        if not self.running:
            self.poll_id = None
            return False
        try:
            pos = self._get_printer().data["toolhead"]["position"]
            x, y, z = pos[0], pos[1], pos[2]
            self.cur_pos = self._to_probe_xy(x, y)

            if USE_Z_DETECT and self.last_z is not None:
                # 하강 시작 감지
                if z < self.last_z - 0.05 and not self.z_going_down:
                    self.z_going_down = True
                    self.z_min = z
                    self.min_pos = self.cur_pos

                if self.z_going_down:
                    if z <= self.z_min:
                        # 가장 낮은 지점 갱신 (프로브가 닿는 순간의 위치)
                        self.z_min = z
                        self.min_pos = self.cur_pos
                    elif z > self.z_min + 0.05:
                        # 상승 시작 = 측정 1회 완료
                        self.z_going_down = False
                        if self.z_min <= Z_TRIGGER_MAX and self.min_pos is not None:
                            self._add_probed(self.min_pos)
                        else:
                            logging.info(
                                f"my_leveling: 무시된 하강 z_min={self.z_min:.2f} "
                                f"(Z_TRIGGER_MAX={Z_TRIGGER_MAX})"
                            )
                        self.z_min = None
                        self.min_pos = None
            self.last_z = z
        except Exception:
            logging.exception("my_leveling: 위치 폴링 실패")
        if self.map_area:
            self.map_area.queue_draw()
        return True

    # ------------------------------------------------------------------
    # 베드 맵 그리기
    # ------------------------------------------------------------------
    def _bed_to_px(self, x, y, cx, cy, r_px):
        px = cx + (x - CENTER_X) / BED_RADIUS * r_px
        py = cy - (y - CENTER_Y) / BED_RADIUS * r_px   # Y축은 위쪽이 +
        return px, py

    def _on_draw_map(self, widget, cr):
        try:
            return self._draw_map_inner(widget, cr)
        except Exception:
            logging.exception("my_leveling: draw 실패")
            return False

    def _draw_map_inner(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        cx, cy = w / 2.0, h / 2.0
        r_px = min(w, h) / 2.0 - 8

        # 베드 원
        cr.set_source_rgba(0.15, 0.15, 0.15, 1)
        cr.arc(cx, cy, r_px, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgba(0.7, 0.7, 0.7, 1)
        cr.set_line_width(2)
        cr.stroke()

        # 중심 십자선
        cr.set_source_rgba(0.25, 0.25, 0.25, 1)
        cr.set_line_width(1)
        cr.move_to(cx - r_px, cy)
        cr.line_to(cx + r_px, cy)
        cr.move_to(cx, cy - r_px)
        cr.line_to(cx, cy + r_px)
        cr.stroke()

        # 측정 완료 지점 (회색)
        cr.set_source_rgba(0.6, 0.6, 0.6, 1)
        for (x, y) in self.probed:
            px, py = self._bed_to_px(x, y, cx, cy, r_px)
            cr.arc(px, py, 5, 0, 2 * math.pi)
            cr.fill()

        # 현재 위치 (빨강)
        if self.cur_pos is not None:
            px, py = self._bed_to_px(self.cur_pos[0], self.cur_pos[1], cx, cy, r_px)
            cr.set_source_rgba(1, 0.2, 0.2, 0.35)       # 바깥 후광
            cr.arc(px, py, 12, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(1, 0.2, 0.2, 1)
            cr.arc(px, py, 6, 0, 2 * math.pi)
            cr.fill()
        return False

    # ------------------------------------------------------------------
    # Klipper 응답 수신
    # ------------------------------------------------------------------
    def process_update(self, action, data):
        # show_panel이 만든 새 인스턴스가 받은 업데이트를 실제 소유자에게 전달
        if _OWNER is not None and _OWNER is not self:
            return _OWNER.process_update(action, data)

        if action != "notify_status_update":      # 상태 업데이트는 너무 잦아서 로그 제외
            logging.info(f"my_leveling: {action} {str(data)[:300]}")

        if not self.running:
            return

        if action == "notify_gcode_response":
            for line in str(data).splitlines():
                if MARKER_DONE in line:
                    self._set_status("레벨링 완료")
                    GLib.timeout_add(1500, self._finish)
                    continue

                # 응답에 좌표가 있으면 그 좌표를 우선 사용 (있는 경우에만 동작)
                m = PROBE_RE.search(line)
                if m:
                    pt = (float(m.group(1)), float(m.group(2)))
                    logging.info(f"my_leveling: probe 파싱 {pt}")
                    self._add_probed(pt, authoritative=True)
                    if self.map_area:
                        self.map_area.queue_draw()

                self._append(line)
                if line.startswith("!!"):
                    self._set_status("오류 발생 - 닫기를 누르세요")

        elif action == "notify_klippy_ready":
            self._finish()

    # ------------------------------------------------------------------
    # 종료 처리
    # ------------------------------------------------------------------
    def _on_force_close(self, widget=None):
        self._finish()

    def _finish(self):
        global _OWNER
        if not self.running:
            return False
        self.running = False
        _OWNER = None
        if self.poll_id:
            GLib.source_remove(self.poll_id)
            self.poll_id = None
        self._remove_overlay()
        self.console_buf = None
        self.console_view = None
        self.status_label = None
        self.map_area = None
        if self._screen._cur_panels and self._screen._cur_panels[-1] == PANEL_NAME:
            self._screen._menu_go_back()
        return False

    # ------------------------------------------------------------------
    # 기타 버튼 동작
    # ------------------------------------------------------------------
    def _on_next_panel(self, widget=None):
        self._remove_overlay()
        self._screen.show_panel(NEXT_PANEL, NEXT_TITLE)

    def _on_close(self, widget=None):
        self._remove_overlay()

    def _remove_overlay(self):
        if self.overlay_widget is not None:
            self._screen.overlay.remove(self.overlay_widget)
            self.overlay_widget = None
