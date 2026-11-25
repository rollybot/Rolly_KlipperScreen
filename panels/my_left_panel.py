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
TELEGRAM_TITLE = "텔레그램 알림"
TELEGRAM_ICON = "info"
# 알림 켜짐/꺼짐을 읽어올 Klipper 매크로 변수 (printer.cfg 의 TELEGRAM_VARS)
TELEGRAM_STATE_OBJECT = "gcode_macro TELEGRAM_VARS"
TELEGRAM_STATE_VAR = "user_id"
TELEGRAM_UNSET_VALUES = ("", "0", "none")   # 이 값이면 미등록(꺼짐)

LIGHT_FAN = "fan_generic Light"   # printer.cfg 의 [fan_generic Light] 이름과 일치
LIGHT_MACRO = "TOGGLE_FAN_LIGHT"  # 토글 매크로 이름

ICON_ON = "light_on"    # 켜졌을 때 아이콘
ICON_OFF = "light"      # 꺼졌을 때 아이콘

# 모양
RADIUS = 18                     # 모서리 둥글기(px)
CARD_HEIGHT = 56                # 카드/버튼 최소 높이 (남는 공간은 똑같이 나눠 가짐)
BORDER_COLOR = "#6b7280"        # 온도 카드 테두리 색
ON_BG, ON_FG = "#f5c542", "#222222"    # 조명 켜짐
OFF_BG, OFF_FG = "#4a4f57", "#ffffff"  # 조명 꺼짐

_CSS = f"""
box.temp-card {{
    border: 2px solid {BORDER_COLOR};
    border-radius: {RADIUS}px;
    padding: 8px 20px;
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
        self._shown_state = None      # 마지막으로 화면에 표시한 상태
        self._ignore_until = 0        # 버튼 누른 직후 잠깐 팬 값 무시
        self._tg_value = None         # Moonraker 에 직접 물어본 텔레그램 ID 값
        self._tg_last_query = 0
        self._tg_pending = False
        _load_css()

        # 모든 카드/버튼이 같은 높이로 위에서 아래로 나란히 (공간이 모자라도 같이 줄어듦)
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

        self._build_telegram_card()
        self._build_light_button()

        self.box.show_all()
        self._set_light_state(False)
        self.update()

    # ---------------- 공통 ----------------
    def _load_pixbuf(self, name):
        """KlipperScreen 테마 아이콘을 pixbuf로 읽기 (실패하면 None)"""
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

    # ---------------- 텔레그램 알림 카드 ----------------
    def _build_telegram_card(self):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        card.get_style_context().add_class("temp-card")
        card.set_size_request(-1, CARD_HEIGHT)

        pix = self._load_pixbuf(TELEGRAM_ICON)
        if pix is not None:
            icon = Gtk.Image()
            icon.set_from_pixbuf(pix)
            card.pack_start(icon, False, False, 0)

        name = Gtk.Label()
        name.set_markup(f"<span size='large' weight='bold'>{TELEGRAM_TITLE}</span>")
        name.set_halign(Gtk.Align.START)
        card.pack_start(name, True, True, 0)

        self.telegram_label = Gtk.Label()
        self.telegram_label.set_halign(Gtk.Align.END)
        card.pack_end(self.telegram_label, False, False, 0)

        self.box.pack_start(card, True, True, 0)
        logging.info("Telegram card added")

    def _query_telegram(self):
        """Moonraker 에 TELEGRAM_VARS 값을 직접 물어봄 (3초에 한 번까지)"""
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
            # 응답이 {"result": {"status": ...}} 로 한 겹 더 싸여 올 수도 있음
            data = result.get("result", result)
            val = data["status"][TELEGRAM_STATE_OBJECT][TELEGRAM_STATE_VAR]
        except Exception:
            logging.info(f"Telegram query: unexpected result {result}")
            return
        if val != self._tg_value:
            logging.info(
                "Telegram ID -> "
                + ("unset" if str(val).strip("\"' ") in TELEGRAM_UNSET_VALUES else "registered")
            )
        self._tg_value = val
        GLib.idle_add(self._apply_telegram)

    def _apply_telegram(self):
        self._set_telegram_state(self._telegram_enabled(self.panel._printer))
        return False

    def _telegram_enabled(self, printer):
        """ID 등록됨=True(켜짐), 미등록=False(꺼짐), 읽을 수 없음=None"""
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
            markup = "<span size='x-large' foreground='#95a5a6'>--</span>"
        elif enabled:
            markup = "<span size='x-large' weight='bold' foreground='#2ecc71'>켜짐</span>"
        else:
            markup = "<span size='x-large' weight='bold' foreground='#95a5a6'>꺼짐</span>"
        self.telegram_label.set_markup(markup)

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
        self._ignore_until = time.time() + 2   # 팬 상태가 갱신될 때까지 대기
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
            lbl.set_markup(f"<span size='x-large' weight='bold'>{temp:.0f}°C</span>")

        self._query_telegram()
        self._set_telegram_state(self._telegram_enabled(printer))

        # 실제 팬 속도를 읽을 수 있으면 그 값으로 상태 동기화
        # (버튼 누른 직후 2초는 이전 값이 남아 있을 수 있어 무시)
        if time.time() >= self._ignore_until:
            speed = printer.get_stat(LIGHT_FAN, "speed")
            if speed is not None:
                self.light_on = speed > 0
                self._set_light_state(self.light_on)