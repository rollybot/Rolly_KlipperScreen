import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from ks_includes.screen_panel import ScreenPanel

# (Moonraker 항목명, 버튼 문구, 업데이트 있을 때 설명)
ITEMS = [
    ("mainsail", "웹 화면 업데이트",
     "새 기능이 준비되었습니다.\n업데이트 후 웹 화면을 다시 열어 주세요."),
    ("KlipperScreen", "프린터 화면 업데이트",
     "새 기능이 준비되었습니다.\n업데이트 중 화면이 잠시 꺼졌다 켜집니다."),
]

MSG = {
    "none": "최신 상태입니다.",
    "wait": "확인하는 중입니다...",
    "fail": "확인하지 못했습니다.\n인터넷 연결을 확인해 주세요.",
    "running": "업데이트 중입니다.\n전원을 끄지 마세요.",
    "error": "업데이트에 실패했습니다.\n잠시 후 다시 시도해 주세요.",
    "done": "업데이트가 완료되었습니다.",
}

BTN_CSS = b"""
button.rolly-round-btn {
    border-radius: 18px;
    padding: 10px 24px;
    border: 2px solid #4a90d9;
    background-image: none;
    background-color: #2b6cb0;
    color: #ffffff;
}
button.rolly-round-btn:hover {
    background-color: #3b7fc6;
}
button.rolly-round-btn:active {
    background-color: #1f4f85;
}
button.rolly-round-btn:disabled {
    background-color: #3a3f47;
    border-color: #555b66;
    color: #8a909b;
}
"""

UPDATE_TIMEOUT = 300  # 초: 이 시간 동안 완료 알림이 없으면 실패 처리


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.is_updating = False
        self.current = None
        self.timeout_id = None
        self.rows = {}  # name -> (label, button)

        css = Gtk.CssProvider()
        css.load_from_data(BTN_CSS)

        # 세로로 항목을 쌓고, 각 항목은 [버튼 | 설명문] 가로 배치
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)

        for name, title_text, _desc in ITEMS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
            row.set_halign(Gtk.Align.CENTER)

            btn = self._gtk.Button("complete", title_text, "color3")
            btn.set_size_request(280, 70)
            btn.set_valign(Gtk.Align.CENTER)
            btn.set_sensitive(False)
            btn.connect("clicked", self.confirm, name)
            ctx = btn.get_style_context()
            ctx.add_class("rolly-round-btn")
            ctx.add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_USER)

            label = Gtk.Label(label=MSG["wait"], wrap=True)
            label.set_justify(Gtk.Justification.LEFT)
            label.set_xalign(0)
            label.set_valign(Gtk.Align.CENTER)
            label.set_size_request(300, -1)
            label.set_max_width_chars(28)

            row.add(btn)
            row.add(label)
            box.add(row)
            self.rows[name] = (label, btn)

        self.content.add(box)
        self.check_update(force_refresh=True)

    def activate(self):
        if self.is_updating:
            return
        # 캐시로 즉시 표시 후, 뒤에서 최신 상태 재확인
        self.check_update(force_refresh=False)
        self.check_update(force_refresh=True)

    # ---------- 상태 조회 ----------
    def check_update(self, force_refresh=False):
        # 업데이트 진행 중에는 조회 요청을 보내지 않음 (요청 겹침 방지)
        if self.is_updating:
            return
        self._screen._ws.send_method(
            "machine.update.status", {"refresh": force_refresh}, self.on_status
        )

    def on_status(self, result, method, params):
        if self.is_updating:
            return
        if not result or "result" not in result:
            for name, (label, btn) in self.rows.items():
                if not btn.get_sensitive():
                    label.set_text(MSG["fail"])
            return

        info = result["result"].get("version_info", {})
        for name, _title, desc in ITEMS:
            label, btn = self.rows[name]
            v = info.get(name) or {}
            behind = v.get("commits_behind") or []
            remote = v.get("remote_version")
            has_update = bool(behind or (remote and v.get("version") != remote))
            label.set_text(desc if has_update else MSG["none"])
            btn.set_sensitive(has_update)

    # ---------- 설치 ----------
    def confirm(self, widget, name):
        if self.is_updating:
            return
        if self._printer.state in ("printing", "paused"):
            self._screen.show_popup_message(
                "출력 중에는 사용할 수 없습니다.\n출력이 끝난 후 다시 시도해 주세요."
            )
            return
        self.current = name
        self._screen._confirm_send_action(
            widget,
            "업데이트를 시작합니다.\n완료될 때까지 전원을 끄지 마세요.",
            "machine.update.client",
            {"name": name},
        )
        self._begin(name)

    def _begin(self, name):
        self.is_updating = True
        for _n, (_label, btn) in self.rows.items():
            btn.set_sensitive(False)
        self.rows[name][0].set_text(MSG["running"])
        self._start_timeout()

    def _start_timeout(self):
        self._stop_timeout()
        self.timeout_id = GLib.timeout_add_seconds(UPDATE_TIMEOUT, self._on_timeout)

    def _stop_timeout(self):
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

    def _on_timeout(self):
        self.timeout_id = None
        logging.error("rolly update: timeout (%s)", self.current)
        self._fail()
        return False

    def _fail(self):
        # 실패 시 상태를 풀어 다시 시도할 수 있게 함
        self._stop_timeout()
        self.is_updating = False
        if self.current in self.rows:
            self.rows[self.current][0].set_text(MSG["error"])
        self.check_update(force_refresh=False)

    def process_update(self, action, data):
        if action != "notify_update_response" or not self.is_updating:
            return

        message = str(data.get("message", "")).lower()
        if data.get("status") == "error" or data.get("error") or (
            data.get("complete")
            and ("error" in message or "fail" in message or "timeout" in message)
        ):
            logging.error("rolly update failed: %s", data)
            self._fail()
            return

        if not data.get("complete"):
            self._start_timeout()  # 진행 중이면 타이머 연장
            return

        self._stop_timeout()
        self.is_updating = False
        if self.current in self.rows:
            self.rows[self.current][0].set_text(MSG["done"])
        GLib.timeout_add_seconds(3, self._after_done)

    def _after_done(self):
        self.check_update(force_refresh=True)
        return False