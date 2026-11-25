import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel

# 순서 중요: KlipperScreen은 설치 후 재시작되므로 항상 마지막
TARGETS = ["mainsail", "KlipperScreen"]

MSG = {
    "mainsail": "웹 화면(PC·스마트폰)의 새 기능이 준비되었습니다.\n업데이트 후 웹 화면을 다시 열어 주세요.",
    "KlipperScreen": "프린터 화면의 새 기능이 준비되었습니다.\n업데이트 중 화면이 잠시 꺼졌다 켜집니다.",
    "both": "프린터 화면과 웹 화면의 새 기능이 준비되었습니다.\n업데이트 중 화면이 잠시 꺼졌다 켜지며,\n완료 후 웹 화면을 다시 열어 주세요.",
    "none": "최신 상태입니다.",
    "fail": "업데이트를 확인하지 못했습니다.\n인터넷 연결을 확인해 주세요.",
    "wait": "확인하는 중입니다...",
    "running": "업데이트 중입니다.\n완료될 때까지 전원을 끄지 마세요.",
}

BTN_CSS = b"""
button.rolly-round-btn {
    border-radius: 18px;
    padding: 10px 24px;
}
"""


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.can_update = []
        self.queue = []
        self.is_updating = False

        self.status = Gtk.Label(label=MSG["wait"], wrap=True)
        self.status.set_justify(Gtk.Justification.CENTER)
        self.status.set_vexpand(True)

        self.btn_update = self._gtk.Button("complete", "업데이트", "color3")
        self.btn_update.connect("clicked", self.confirm)
        self.btn_update.set_sensitive(False)

        # 둥근 사각 버튼 스타일
        self.btn_update.set_size_request(260, 70)
        ctx = self.btn_update.get_style_context()
        ctx.add_class("rolly-round-btn")
        css = Gtk.CssProvider()
        css.load_from_data(BTN_CSS)
        ctx.add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.add(self.status)
        box.add(self.btn_update)
        self.content.add(box)

        # 패널 생성 시 백그라운드에서 미리 한 번 최신 정보 조회
        self.check_update(force_refresh=True, silent=True)

    def activate(self):
        if self.is_updating:
            return
        # 1단계: Moonraker 캐시에서 즉시(0.1초 내) 결과 가져와 화면에 바로 표시
        self.check_update(force_refresh=False, silent=bool(self.can_update))
        # 2단계: 뒤에서 조용히 GitHub 최신 상태 다시 확인
        self.check_update(force_refresh=True, silent=True)

    def check_update(self, force_refresh=False, silent=False):
        if not silent:
            self.status.set_text(MSG["wait"])
            self.btn_update.set_sensitive(False)
        self._screen._ws.send_method(
            "machine.update.status",
            {"refresh": force_refresh},
            self.on_status,
        )

    def on_status(self, result, method, params):
        if self.is_updating:
            return
        if not result or "result" not in result:
            # 이미 캐시로 업데이트 가능 상태를 띄워둔 상태라면 실패 메시지로 덮어쓰지 않음
            if not self.can_update:
                self.status.set_text(MSG["fail"])
            return

        info = result["result"].get("version_info", {})

        self.can_update = []
        for name in TARGETS:
            v = info.get(name)
            if not v:
                continue
            behind = v.get("commits_behind") or []
            remote = v.get("remote_version")
            if behind or (remote and v.get("version") != remote):
                self.can_update.append(name)

        if len(self.can_update) == 2:
            self.status.set_text(MSG["both"])
        elif self.can_update:
            self.status.set_text(MSG[self.can_update[0]])
        else:
            self.status.set_text(MSG["none"])
        self.btn_update.set_sensitive(bool(self.can_update))

    def confirm(self, widget):
        if self._printer.state in ("printing", "paused"):
            self._screen.show_popup_message(
                "출력 중에는 사용할 수 없습니다.\n출력이 끝난 후 다시 시도해 주세요."
            )
            return
        self.queue = list(self.can_update)
        if not self.queue:
            return
        self.is_updating = True
        self._screen._confirm_send_action(
            widget,
            "업데이트를 시작합니다.\n완료될 때까지 전원을 끄지 마세요.",
            "machine.update.client",
            {"name": self.queue.pop(0)},
        )
        self.status.set_text(MSG["running"])
        self.btn_update.set_sensitive(False)

    def process_update(self, action, data):
        if action != "notify_update_response":
            return
        if data.get("complete"):
            if self.queue:
                try:
                    self._screen._ws.send_method(
                        "machine.update.client", {"name": self.queue.pop(0)}
                    )
                except Exception:
                    logging.exception("rolly update: next item failed")
                    self.is_updating = False
            else:
                # 모든 업데이트 완료 후 화면 상태 갱신
                self.is_updating = False
                self.can_update = []
                self.check_update(force_refresh=False, silent=False)
