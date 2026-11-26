import logging
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

# (printer 객체 이름, 표시 이름, 아이콘 이름)
TEMP_ITEMS = (
    ("extruder", "프린터노즐", "extruder"),
    ("heater_bed", "출력베드", "bed"),
)

# 텔레그램 알림 카드
TELEGRAM_TITLE = "텔레그램"
TELEGRAM_ICON = "info"
TELEGRAM_STATE_OBJECT = "gcode_macro TELEGRAM_VARS"
TELEGRAM_STATE_VAR = "user_id"
TELEGRAM_UNSET_VALUES = ("", "0", "none")

# 업데이트 알림 카드 (표시 전용)
UPDATE_TARGETS = ("mainsail", "KlipperScreen")
UPDATE_TITLE = "업데이트"
UPDATE_ICON = "complete"

LIGHT_FAN = "output_pin Light"
LIGHT_MACRO = "TOGGLE_FAN_LIGHT"

ICON_ON = "light_on"
ICON_OFF = "light"

# 모양
RADIUS = 18
CARD_HEIGHT = 56
BORDER_COLOR = "#6b7280"
ON_BG, ON_FG = "#f5c542", "#222222"
OFF_BG, OFF_FG = "#4a4f57", "#ffffff"

_CSS = f"""
box.temp-card {{
    border: 2px solid {BORDER_COLOR};
    border-radius: {RADIUS}px;
    padding: 8px 14px;
}}
box.notice-card {{
    border: 2px solid {BORDER_COLOR};
    border-radius: {RADIUS}px;
    padding: 4px 8px;
}}
box.notice-card.update-on {{
    border: 2px solid {BORDER_COLOR};
}}
button.light-btn {{
    border-radius: {RADIUS}px;
    border: none;
    box-shadow: none;
    background-image: none;
    padding: 8px 20px;
}}
button.light-on {{ background-color: {ON_BG}; }}
button.light-on label {{ color: {ON_FG}; }}
button.light-off {{ background-color: {OFF_BG}; }}
button.light-off label {{ color: {OFF_FG}; }}
"""

_css_loaded = False


def _load_css():
    global _css_loaded
    if _css_loaded:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(_CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _css_loaded = True


class LeftPanel:
    def __init__(self, panel):
        self.panel = panel
        self.temp_labels = {}
        self.light_on = False
        self._shown_state = None
        self._ignore_until = 0
        self._tg_value = None
        self._tg_last_query = 0
        self._tg_pending = False

        # 업데이트 조회 상태 변수
        self._has_update = False
        self._upd_last_query = 0
        self._upd_pending = False

        _load_css()

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.set_homogeneous(True)
        self.box.set_valign(Gtk.Align.FILL)
        self.box.set_vexpand(True)
        self.box.set_halign(Gtk.Align.FILL)
        self.box.set_hexpand(True)
        self.box.set_margin_start(10)
        self.box.set_margin_end(10)
        self.box.set_margin_top(6)
        self.box.set_margin_bottom(6)

        for key, title, icon in TEMP_ITEMS:
            self.box.pack_start(self._build_temp_card(key, title, icon), True, True, 0)

        self._build_notice_row()
        self._build_light_button()

        self.box.show_all()
        self._set_light_state(False)
        self.update()

    # ---------------- 공통 ----------------
    def _load_pixbuf(self, name):
        try:
            img = self.panel._gtk.Image(name)
            if img is not None:
                return img.get_pixbuf()
        except Exception as e:
            logging.info(f"Icon load failed ({name}): {e}")
        return None

    # ---------------- 온도 카드 ----------------
    def _build_temp_card(self, key, title, icon_name):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        card.get_style_context().add_class("temp-card")
        card.set_size_request(-1, CARD_HEIGHT)

        pix = self._load_pixbuf(icon_name)
        if pix is not None:
            icon = Gtk.Image()
            icon.set_from_pixbuf(pix)
            card.pack_start(icon, False, False, 0)

        name = Gtk.Label()
        name.set_markup(f"<span size='large' weight='bold'>{title}</span>")
        name.set_halign(Gtk.Align.START)
        card.pack_start(name, True, True, 0)

        temp = Gtk.Label()
        temp.set_halign(Gtk.Align.END)
        card.pack_end(temp, False, False, 0)

        self.temp_labels[key] = temp
        return card

    # ---------------- 알림 줄: 텔레그램(좌) | 업데이트(우) ----------------
    def _make_notice_half(self, title, icon_name):
        # 세로 2줄: (아이콘 + 제목) / 상태
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.get_style_context().add_class("notice-card")
        card.set_size_request(1, CARD_HEIGHT)  # 최소 폭을 1로 해서 줄 폭을 키우지 않음

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        top.set_halign(Gtk.Align.CENTER)

        pix = self._load_pixbuf(icon_name)
        if pix is not None:
            icon = Gtk.Image()
            if pix.get_width() > 30:
                pix = pix.scale_simple(30, 30, 2)
            icon.set_from_pixbuf(pix)
            top.pack_start(icon, False, False, 0)

        name = Gtk.Label()
        name.set_markup(f"<span size='large' weight='bold' foreground='#95a5a6'>{title}</span>")
        top.pack_start(name, False, False, 0)

        state = Gtk.Label()
        state.set_halign(Gtk.Align.CENTER)

        card.pack_start(top, True, True, 0)
        card.pack_start(state, True, True, 0)
        return card, state

    def _build_notice_row(self):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_homogeneous(True)
        row.set_size_request(1, -1)

        tg_card, self.telegram_label = self._make_notice_half(TELEGRAM_TITLE, TELEGRAM_ICON)
        self.update_card, self.update_label = self._make_notice_half(UPDATE_TITLE, UPDATE_ICON)

        row.pack_start(tg_card, True, True, 0)
        row.pack_start(self.update_card, True, True, 0)
        self.box.pack_start(row, True, True, 0)
        self._set_update_state(False)

    # ---------------- 텔레그램 ----------------
    def _query_telegram(self):
        now = time.time()
        if now - self._tg_last_query < 3:
            return
        if self._tg_pending and now - self._tg_last_query < 10:
            return
        self._tg_last_query = now
        self._tg_pending = True
        try:
            self.panel._screen._ws.send_method(
                "printer.objects.query",
                {"objects": {TELEGRAM_STATE_OBJECT: None}},
                self._on_telegram_query,
            )
        except Exception as e:
            self._tg_pending = False
            logging.info(f"Telegram query failed: {e}")

    def _on_telegram_query(self, result, *args):
        self._tg_pending = False
        try:
            data = result.get("result", result)
            val = data["status"][TELEGRAM_STATE_OBJECT][TELEGRAM_STATE_VAR]
        except Exception:
            return
        self._tg_value = val
        GLib.idle_add(self._apply_telegram)

    def _apply_telegram(self):
        self._set_telegram_state(self._telegram_enabled(self.panel._printer))
        return False

    def _telegram_enabled(self, printer):
        val = self._tg_value
        if val is None and printer:
            try:
                val = printer.get_stat(TELEGRAM_STATE_OBJECT, TELEGRAM_STATE_VAR)
            except Exception:
                val = None
        if val is None:
            return None
        return str(val).strip().strip("\"'").lower() not in TELEGRAM_UNSET_VALUES

    def _set_telegram_state(self, enabled):
        if enabled is None:
            markup = "<span foreground='#95a5a6'>--</span>"
        elif enabled:
            markup = "<span size='large' weight='bold' foreground='#2ecc71'>[ 알림 O ]</span>"
        else:
            markup = "<span size='large' weight='bold' foreground='#95a5a6'>[ 알림 X ]</span>"
        self.telegram_label.set_markup(markup)

    # ---------------- 업데이트 알림 (표시 전용) ----------------
    def _set_update_state(self, has_update):
        ctx = self.update_card.get_style_context()
        if has_update:
            ctx.add_class("update-on")
            self.update_label.set_markup(
                "<span size='large' weight='bold' foreground='#2ecc71'>[ New버전 ]</span>"
            )
        else:
            ctx.remove_class("update-on")
            self.update_label.set_markup(
                "<span size='large' weight='bold' foreground='#95a5a6'>[ 최신상태 ] </span>"
            )

    def _query_update(self):
        """Moonraker 캐시에서 업데이트 여부를 가볍게 조회 (15초에 한 번)"""
        now = time.time()
        if now - self._upd_last_query < 15:
            return
        if self._upd_pending and now - self._upd_last_query < 30:
            return
        self._upd_last_query = now
        self._upd_pending = True
        try:
            self.panel._screen._ws.send_method(
                "machine.update.status",
                {"refresh": False},
                self._on_update_query,
            )
        except Exception as e:
            self._upd_pending = False
            logging.info(f"Update query failed: {e}")

    def _on_update_query(self, result, *args):
        self._upd_pending = False
        if not result or "result" not in result:
            return
        info = result["result"].get("version_info", {})
        has_update = False
        for name in UPDATE_TARGETS:
            v = info.get(name)
            if not v:
                continue
            behind = v.get("commits_behind") or []
            remote = v.get("remote_version")
            if behind or (remote and v.get("version") != remote):
                has_update = True
                break
        self._has_update = has_update
        GLib.idle_add(self._apply_update_state)

    def _apply_update_state(self):
        self._set_update_state(self._has_update)
        return False

    # ---------------- 조명 버튼 ----------------
    def _build_light_button(self):
        # 이미지 위젯은 하나만 두고, 상태에 따라 그림만 교체
        self._pix = {True: self._load_pixbuf(ICON_ON), False: self._load_pixbuf(ICON_OFF)}
        self.icon = Gtk.Image()

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        inner.set_halign(Gtk.Align.CENTER)
        inner.add(self.icon)

        self.light_btn = Gtk.Button()
        self.light_btn.add(inner)
        self.light_btn.set_size_request(-1, CARD_HEIGHT)
        self.light_btn.get_style_context().add_class("light-btn")
        self.light_btn.connect("clicked", self.toggle_light)
        self.box.pack_start(self.light_btn, True, True, 0)

    def toggle_light(self, widget):
        self.light_on = not self.light_on
        self._pending_state = self.light_on      # 내가 원하는 목표 상태를 기록
        self._ignore_until = time.time() + 10    # 최대 10초(홈 이동 시간 등) 동안 안전장치
        self.panel._screen._send_action(
            widget, "printer.gcode.script", {"script": LIGHT_MACRO}
        )
        self._set_light_state(self.light_on)

    def _set_light_state(self, on):
        if self._shown_state == on:
            return
        self._shown_state = on
        logging.info(f"Light button state -> {'ON' if on else 'OFF'}")

        pix = self._pix.get(on)
        if pix is not None:
            self.icon.set_from_pixbuf(pix)
        else:
            self.icon.set_from_icon_name(ICON_ON if on else ICON_OFF, Gtk.IconSize.DIALOG)

        ctx = self.light_btn.get_style_context()
        ctx.remove_class("light-off" if on else "light-on")
        ctx.add_class("light-on" if on else "light-off")

    # ---------------- 상태 갱신 ----------------
    def update(self):
        printer = self.panel._printer
        if not printer:
            return
        for key, lbl in self.temp_labels.items():
            temp = printer.get_stat(key, "temperature")
            if temp is None:
                lbl.set_markup("<span size='x-large'>--</span>")
                continue
            try:
                lbl.set_markup(f"<span size='x-large' weight='bold'>{float(temp):.0f}°C</span>")
            except (TypeError, ValueError):
                lbl.set_markup("<span size='x-large'>--</span>")

        self._query_telegram()
        self._set_telegram_state(self._telegram_enabled(printer))
        self._query_update()

        # 실제 팬 속도를 읽을 수 있으면 그 값으로 상태 동기화
        # (버튼 누른 직후 2초는 이전 값이 남아 있을 수 있어 무시)
        if time.time() >= self._ignore_until:
            val = printer.get_stat(LIGHT_FAN, "value")
            try:
                actual_on = float(val) > 0
                pending = getattr(self, "_pending_state", None)

                if pending is not None:
                    # 프린터가 내가 누른 목표 상태에 도달했거나, 최대 대기 시간(15초)이 지났을 때만 동기화 재개
                    if actual_on == pending or time.time() >= self._ignore_until:
                        self._pending_state = None
                        self.light_on = actual_on
                        self._set_light_state(self.light_on)
                else:
                    # 평소(웹 UI 등에서 조명을 켰을 때 등)에는 즉시 동기화
                    self.light_on = actual_on
                    self._set_light_state(self.light_on)
            except (TypeError, ValueError):
                pass