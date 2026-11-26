import logging
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

LIGHT_FAN = "output_pin Light"
LIGHT_MACRO = "TOGGLE_FAN_LIGHT"
ICON_ON = "light_on"
ICON_OFF = "light"

RADIUS = 18
ON_BG, ON_FG = "#f5c542", "#222222"
OFF_BG, OFF_FG = "#4a4f57", "#ffffff"

_CSS = f"""
button.light-btn {{
    border-radius: {RADIUS}px;
    border: none;
    box-shadow: none;
    background-image: none;
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


class LightButton:
    """job_status 등 다른 패널에서 쓰는 조명 토글 버튼"""

    def __init__(self, panel, label="Light"):
        _load_css()
        self.panel = panel
        self.light_on = False
        self._shown = None
        self._pending = None
        self._ignore_until = 0

        # panel._gtk.Button으로 만들어 다른 버튼과 같은 크기/폰트를 유지
        self.button = panel._gtk.Button(ICON_OFF, label, None)
        self.button.get_style_context().add_class("light-btn")
        self.button.connect("clicked", self._toggle)
        self._set_state(False)

    def _toggle(self, widget):
        self.light_on = not self.light_on
        self._pending = self.light_on
        self._ignore_until = time.time() + 10
        self.panel._screen._ws.api.gcode_script(LIGHT_MACRO)
        self._set_state(self.light_on)

    def _set_state(self, on):
        if self._shown == on:
            return
        self._shown = on
        ctx = self.button.get_style_context()
        ctx.remove_class("light-off" if on else "light-on")
        ctx.add_class("light-on" if on else "light-off")
        # 아이콘 교체
        try:
            from ks_includes.KlippyGtk import find_widget
            img = find_widget(self.button, Gtk.Image)
            pix = self.panel._gtk.Image(ICON_ON if on else ICON_OFF)
            if img is not None and pix is not None:
                img.set_from_pixbuf(pix.get_pixbuf())
        except Exception as e:
            logging.info(f"Light icon update failed: {e}")

    def sync(self):
        """프린터 실제 상태와 동기화 (process_update에서 호출)"""
        if time.time() < self._ignore_until:
            return
        try:
            val = self.panel._printer.get_stat(LIGHT_FAN, "value")
            actual = float(val) > 0
        except (TypeError, ValueError):
            return
        self._pending = None
        self.light_on = actual
        self._set_state(actual)