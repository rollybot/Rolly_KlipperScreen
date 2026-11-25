import logging
import re

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    z_deltas = ["0.01", "0.05"]
    z_delta = z_deltas[-1]
    speed = 100
    z_offset = 0.0

    # 출력속도 프리셋 (%) -- 숫자는 원하는 대로 수정하세요
    SPEED_PRESETS = [60, 80, 100, 120]

    def __init__(self, screen, title):
        title = title or _("Fine Tuning")
        super().__init__(screen, title)

        # ---- 박스 테두리 CSS ----
        css = Gtk.CssProvider()
        css.load_from_data(
            b""".my_box { border: 2px solid #8a8a8a; border-radius: 10px; padding: 8px; }
                .my_box_title { font-weight: bold; font-size: 22px; }
                button.my_gray_btn { background: #5a5a5a; background-image: none; border: 2px solid #9a9a9a; border-radius: 10px; }
                button.my_gray_btn:active { background: #7a7a7a; background-image: none; }
                button.my_gray_btn.my_selected { background: #2e7d32; background-image: none; border: 2px solid #a5d6a7; }"""
        )
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )

        if self.ks_printer_cfg is not None:
            bs = self.ks_printer_cfg.get("z_babystep_values", "")
            if re.match(r"^[0-9,\.\s]+$", bs):
                bs = [str(i.strip()) for i in bs.split(",")]
                if 1 < len(bs) < 3:
                    self.z_deltas = bs
                    self.z_delta = self.z_deltas[-1]

        # ---- Z 단위 선택 ----
        zgrid = Gtk.Grid()
        for j, i in enumerate(self.z_deltas):
            self.labels[f"zdelta{i}"] = self._gtk.Button(label=i)
            self.labels[f"zdelta{i}"].connect(
                "clicked", self.change_percent_delta, "z_offset", float(i)
            )
            ctx = self.labels[f"zdelta{i}"].get_style_context()
            ctx.add_class("horizontal_togglebuttons")
            if i == self.z_delta:
                ctx.add_class("horizontal_togglebuttons_active")
            zgrid.attach(self.labels[f"zdelta{i}"], j, 0, 1, 1)

        # ---- 속도 프리셋 버튼 ----
        self.speed_buttons = {}
        presetgrid = Gtk.Grid(column_homogeneous=True, row_homogeneous=True)
        presetgrid.set_row_spacing(5)
        presetgrid.set_halign(Gtk.Align.CENTER)   # 박스 가운데로 모으기
        presetgrid.set_hexpand(False)
        for j, value in enumerate(self.SPEED_PRESETS):
            btn = self._gtk.Button(None, f"{_('출력속도')} {value}%", "color3")
            btn.connect("clicked", self.set_speed_preset, value)
            btn.get_style_context().add_class("my_gray_btn")
            btn.set_size_request(330, -1)         # 버튼 폭(px), 원하는 값으로 조절
            self.speed_buttons[value] = btn
            presetgrid.attach(btn, 0, j, 1, 1)

        # ---- Z 버튼 ----
        self.labels["z+"] = self._gtk.Button("z-farther", "Z+", "color1")
        self.labels["z-"] = self._gtk.Button("z-closer", "Z-", "color1")
        self.labels["zoffset"] = self._gtk.Button(
            "refresh", "  0.00" + _("mm"), "color1", self.bts, Gtk.PositionType.LEFT, 1
        )

        # ---- Z-offset 박스 ----
        zlabel_narrow = Gtk.Label(label="간극 좁히기")
        zlabel_wide = Gtk.Label(label="간극 넓히기")
        zlabel_narrow.set_vexpand(False)
        zlabel_wide.set_vexpand(False)

        zinner = Gtk.Grid(column_homogeneous=True)
        zinner.set_row_spacing(5)
        zinner.set_column_spacing(5)

        self.labels["zoffset"].set_vexpand(False)
        self.labels["z-"].get_style_context().add_class("my_gray_btn")
        self.labels["z+"].get_style_context().add_class("my_gray_btn")
        self.labels["z-"].set_vexpand(False)
        self.labels["z+"].set_vexpand(False)
        self.labels["z-"].set_size_request(-1, 200)   # 버튼 높이(px), 원하는 값으로 조절
        self.labels["z+"].set_size_request(-1, 200)
        zgrid.set_vexpand(False)

        zinner.attach(self.labels["zoffset"], 0, 0, 2, 1)  # 위: 현재값
        zinner.attach(self.labels["z-"], 0, 1, 1, 1)       # 큰 버튼 (남는 높이 모두 사용)
        zinner.attach(self.labels["z+"], 1, 1, 1, 1)
        zinner.attach(zlabel_narrow, 0, 2, 1, 1)           # 버튼 아래 설명
        zinner.attach(zlabel_wide, 1, 2, 1, 1)
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        zinner.attach(spacer, 0, 3, 2, 1)   # 남는 높이를 차지하는 빈 행
        zinner.attach(zgrid, 0, 4, 2, 1)    # 아래: 단위 선택 (원래 크기)
        zframe, _unused = self.make_box("Z-offset", zinner)

        # ---- 출력속도 박스 ----
        self.speed_frame, self.speed_title = self.make_box("출력속도", presetgrid)
        self.update_speed_title()

        # ---- 두 박스를 나란히 ----
        grid = Gtk.Grid(column_homogeneous=True, row_homogeneous=True)
        grid.set_column_spacing(15)
        if self._screen.vertical_mode:
            grid.attach(zframe, 0, 0, 1, 1)
            grid.attach(self.speed_frame, 0, 1, 1, 1)
        else:
            grid.attach(zframe, 0, 0, 1, 1)
            grid.attach(self.speed_frame, 1, 0, 1, 1)

        self.labels["z+"].connect("clicked", self.change_babystepping, "+")
        self.labels["zoffset"].connect("clicked", self.change_babystepping, "reset")
        self.labels["z-"].connect("clicked", self.change_babystepping, "-")

        self.content.add(grid)
        self.update_speed_selection()  # 시작 시 100% 강조

    def make_box(self, title, content):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("my_box")
        label = Gtk.Label(label=title)
        label.get_style_context().add_class("my_box_title")
        label.set_vexpand(False)
        box.pack_start(label, False, False, 0)
        box.pack_start(content, True, True, 0)
        return box, label

    def activate(self):
        # 패널이 열릴 때 프린터의 실제 속도 배율을 반영
        factor = self._printer.get_stat("gcode_move", "speed_factor")
        if factor is not None:
            self.speed = round(float(factor) * 100)
        self.update_speed_title()
        self.update_speed_selection()

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        if "gcode_move" in data:
            if "homing_origin" in data["gcode_move"]:
                self.labels["zoffset"].set_label(
                    f"  {data['gcode_move']['homing_origin'][2]:.3f}mm"
                )
                self.z_offset = float(data["gcode_move"]["homing_origin"][2])
            if "speed_factor" in data["gcode_move"]:
                self.speed = round(float(data["gcode_move"]["speed_factor"]) * 100)
                self.update_speed_title()
                self.update_speed_selection()

    def set_speed_preset(self, widget, value):
        logging.info(f"### Speed preset {value}%")
        self.speed = value
        self.update_speed_title()
        self.update_speed_selection()
        self._screen._send_action(
            widget, "printer.gcode.script", {"script": KlippyGcodes.set_speed_rate(self.speed)}
        )

    def update_speed_title(self):
        self.speed_title.set_text(f"출력속도 (현재 {self.speed}%)")

    def update_speed_selection(self):
        # 현재 속도와 일치하는 프리셋 버튼만 강조
        for value, btn in self.speed_buttons.items():
            ctx = btn.get_style_context()
            if value == self.speed:
                ctx.add_class("my_selected")
            else:
                ctx.remove_class("my_selected")

    def change_babystepping(self, widget, direction):
        if direction == "reset":
            self.labels["zoffset"].set_label("  0.00mm")
            self._screen._send_action(
                widget, "printer.gcode.script", {"script": "SET_GCODE_OFFSET Z=0 MOVE=1"}
            )
            return
        elif direction == "+":
            self.z_offset += float(self.z_delta)
        elif direction == "-":
            self.z_offset -= float(self.z_delta)
        self.labels["zoffset"].set_label(f"  {self.z_offset:.3f}mm")
        self._screen._send_action(
            widget,
            "printer.gcode.script",
            {"script": f"SET_GCODE_OFFSET Z_ADJUST={direction}{self.z_delta} MOVE=1"},
        )

    def change_percent_delta(self, widget, array, delta):
        logging.info(f"### Delta {delta}")
        if array == "z_offset":
            self.labels[f"zdelta{self.z_delta}"].get_style_context().remove_class(
                "horizontal_togglebuttons_active"
            )
            self.z_delta = delta
        widget.get_style_context().add_class("horizontal_togglebuttons_active")
