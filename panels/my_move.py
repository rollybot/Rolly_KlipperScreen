import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel

# 원형 버튼용 CSS
CIRCLE_CSS = b"""
.circle_btn {
    border-radius: 9999px;
    padding: 0;
}
.circle_btn label {
    font-size: 1.4em;
    font-weight: bold;
}
.circle_ring {
    border-radius: 9999px;
    border: 2px solid alpha(@theme_fg_color, 0.25);
}
button.my_gray_btn { background: #5a5a5a; background-image: none; border: 2px solid #9a9a9a; border-radius: 10px; }
button.my_gray_btn:active { background: #7a7a7a; background-image: none; }
"""


class Panel(ScreenPanel):
    distances = [".1", "1", "10"]
    distance = "1"  # 기본값 1mm

    def __init__(self, screen, title):
        title = title or _("Move")
        super().__init__(screen, title)

        # CSS 등록
        provider = Gtk.CssProvider()
        provider.load_from_data(CIRCLE_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.buttons = {
            "x+": self._gtk.Button("arrow-right", None, "color1"),
            "x-": self._gtk.Button("arrow-left", None, "color1"),
            "y+": self._gtk.Button(label="+Y", style="color2"),
            "y-": self._gtk.Button(label="-Y", style="color2"),
            "home": self._gtk.Button("home", None, "color4"),
            "z+": self._gtk.Button("arrow-up", "Z+", "color1"),
            "z-": self._gtk.Button("arrow-down", "Z-", "color1"),
        }

        for key in ("x+", "x-", "y+", "y-", "home"):
            self.buttons[key].get_style_context().add_class("circle_btn")
            self.buttons[key].set_hexpand(True)
            self.buttons[key].set_vexpand(True)

        for key in ("z+", "z-"):
            self.buttons[key].get_style_context().add_class("my_gray_btn")

        self.buttons["x+"].connect("clicked", self.move, "X", "+")
        self.buttons["x-"].connect("clicked", self.move, "X", "-")
        self.buttons["y+"].connect("clicked", self.move, "Y", "+")
        self.buttons["y-"].connect("clicked", self.move, "Y", "-")
        self.buttons["z+"].connect("clicked", self.move, "Z", "+")
        self.buttons["z-"].connect("clicked", self.move, "Z", "-")
        self.buttons["home"].connect("clicked", self.home)

        # ---- XY 원형 패드 (십자 배치) ----
        xy_pad = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        xy_pad.set_row_spacing(6)
        xy_pad.set_column_spacing(6)
        xy_pad.attach(self.buttons["y+"], 1, 0, 1, 1)    # 위 (+Y)
        xy_pad.attach(self.buttons["x-"], 0, 1, 1, 1)    # 좌
        xy_pad.attach(self.buttons["home"], 1, 1, 1, 1)  # 중앙
        xy_pad.attach(self.buttons["x+"], 2, 1, 1, 1)    # 우
        xy_pad.attach(self.buttons["y-"], 1, 2, 1, 1)    # 아래 (-Y)

        ring = Gtk.Frame()
        ring.get_style_context().add_class("circle_ring")
        ring.set_shadow_type(Gtk.ShadowType.NONE)
        ring.add(xy_pad)
        ring.set_hexpand(True)
        ring.set_vexpand(True)

        # ---- Z 컬럼 ----
        z_col = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        z_col.set_row_spacing(6)
        z_col.set_vexpand(True)
        z_col.attach(self.buttons["z+"], 0, 0, 1, 1)
        z_col.attach(self.buttons["z-"], 0, 1, 1, 1)

        # ---- 위치 표시 ----
        for p in ("pos_x", "pos_y", "pos_z"):
            self.labels[p] = Gtk.Label()
        pos_grid = Gtk.Grid(column_homogeneous=True)
        pos_grid.attach(self.labels["pos_x"], 0, 0, 1, 1)
        pos_grid.attach(self.labels["pos_y"], 1, 0, 1, 1)
        pos_grid.attach(self.labels["pos_z"], 2, 0, 1, 1)

        # ---- 이동 거리 선택 (0.1 / 1 / 10) ----
        self.labels["move_dist"] = Gtk.Label(label=_("Move Distance (mm)"))
        distgrid = Gtk.Grid()
        distgrid.set_column_homogeneous(True)
        for j, i in enumerate(self.distances):
            self.labels[i] = self._gtk.Button(label=i)
            self.labels[i].set_direction(Gtk.TextDirection.LTR)
            self.labels[i].connect("clicked", self.change_distance, i)
            ctx = self.labels[i].get_style_context()
            ctx.add_class("horizontal_togglebuttons")
            if i == self.distance:
                ctx.add_class("horizontal_togglebuttons_active")
            distgrid.attach(self.labels[i], j, 0, 1, 1)

        # ---- 오른쪽 컬럼: Z 버튼 + 그 아래 거리 선택 ----
        self.labels["move_dist"].set_margin_top(12)     # Z 버튼과 간격 (키우면 더 내려감)
        self.labels["move_dist"].set_margin_bottom(0)   # 숫자 버튼 쪽은 붙임

        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_col.set_size_request(220, -1)  # 줄이면 XY 패드가 더 커짐
        right_col.set_hexpand(False)
        right_col.set_margin_bottom(10)
        right_col.pack_start(z_col, True, True, 0)
        right_col.pack_start(self.labels["move_dist"], False, False, 0)
        right_col.pack_start(distgrid, False, False, 0)

        # ---- 전체 레이아웃 ----
        main = Gtk.Grid()
        main.set_column_spacing(8)
        main.set_row_spacing(6)
        main.attach(pos_grid, 0, 0, 2, 1)
        main.attach(ring, 0, 1, 1, 1)
        main.attach(right_col, 1, 1, 1, 1)

        self.content.add(main)

        # 속도 기본값용 최대 속도
        printer_cfg = self._printer.get_config_section("printer")
        max_velocity = max(int(float(printer_cfg["max_velocity"])), 2)
        if "max_z_velocity" in printer_cfg:
            self.max_z_velocity = max(int(float(printer_cfg["max_z_velocity"])), 2)
        else:
            self.max_z_velocity = max_velocity

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        if "gcode_move" in data or ("toolhead" in data and "homed_axes" in data["toolhead"]):
            homed_axes = self._printer.get_stat("toolhead", "homed_axes")
            for i, axis in enumerate(("x", "y", "z")):
                if axis not in homed_axes:
                    self.labels[f"pos_{axis}"].set_label(f"{axis.upper()}: ?")
                elif "gcode_move" in data and "gcode_position" in data["gcode_move"]:
                    self.labels[f"pos_{axis}"].set_label(
                        f"{axis.upper()}: {data['gcode_move']['gcode_position'][i]:.2f}"
                    )

    def activate(self):
        self.process_update("notify_status_update", self._printer.data)

    def change_distance(self, widget, distance):
        logging.info(f"### my_move: distance {distance}")
        self.labels[f"{self.distance}"].get_style_context().remove_class(
            "horizontal_togglebuttons_active"
        )
        self.labels[f"{distance}"].get_style_context().add_class(
            "horizontal_togglebuttons_active"
        )
        self.distance = distance

    def move(self, widget, axis, direction):
        axis = axis.lower()
        logging.info(f"### my_move: move {axis}{direction} dist={self.distance}")
        if self._config.get_config()["main"].getboolean(f"invert_{axis}", False) and axis != "z":
            direction = "-" if direction == "+" else "+"

        dist = f"{direction}{self.distance}"
        config_key = "move_speed_z" if axis == "z" else "move_speed_xy"
        speed = (
            None if self.ks_printer_cfg is None else self.ks_printer_cfg.getint(config_key, None)
        )
        if speed is None:
            speed = self._config.get_config()["main"].getint(config_key, self.max_z_velocity)
        speed = 60 * max(1, speed)
        script = f"{KlippyGcodes.MOVE_RELATIVE}\nG0 {axis}{dist} F{speed}"
        self._screen._send_action(widget, "printer.gcode.script", {"script": script})
        if self._printer.get_stat("gcode_move", "absolute_coordinates"):
            self._screen._send_action(widget, "printer.gcode.script", {"script": "G90"})

    def home(self, widget):
        logging.info("### my_move: home clicked")
        # delta 는 바로 G28, 그 외는 homing 메뉴를 연다
        if "delta" in self._printer.get_config_section("printer")["kinematics"]:
            self._screen._send_action(widget, "printer.gcode.script", {"script": "G28"})
            return
        name = "homing"
        disname = self._screen._config.get_menu_name("move", name)
        menuitems = self._screen._config.get_menu_items("move", name)
        self._screen.show_panel("menu", disname, items=menuitems)
