# Copyright 2026 Andreas Schneider
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

"""Tests for the departures widget (public transport departures)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from custom_components.eink_dashboard.const import (
    COLOR_GRAY,
    DEFAULT_ROW_H,
)
from custom_components.eink_dashboard.render import (
    _compute_metrics,
    render_dashboard,
)
from custom_components.eink_dashboard.svg_render import render_widget_svg
from custom_components.eink_dashboard.widgets._helpers import (
    _resolve_icon_svg,
)
from tests.helpers import (
    assert_card_border,
    assert_has_gray_pixels,
    assert_vertically_centered,
    make_config,
    render_to_image,
)

_NOW = datetime(2026, 11, 22, 10, 0, 0, tzinfo=timezone(timedelta(hours=1)))

_M43_TIMES = [
    {
        "planned": "2026-11-22T10:00:00+01:00",
        "estimated": "2026-11-22T10:00:00+01:00",
        "delay": 0,
        "cancelled": False,
        "head_sign": "Frankfurt (Main) Bergen Ost",
        "alerts": False,
    },
    {
        "planned": "2026-11-22T10:29:00+01:00",
        "estimated": "2026-11-22T10:31:00+01:00",
        "delay": 2,
        "cancelled": False,
        "head_sign": "Frankfurt (Main) Bergen Ost",
        "alerts": True,
    },
    {
        "planned": "2026-11-22T11:05:00+01:00",
        "estimated": "2026-11-22T11:05:00+01:00",
        "delay": None,
        "cancelled": False,
        "head_sign": "Frankfurt (Main) Enkheim",
        "alerts": False,
    },
    {
        "planned": "2026-11-22T11:43:00+01:00",
        "estimated": "2026-11-22T11:43:00+01:00",
        "delay": 63,
        "cancelled": False,
        "head_sign": "Frankfurt (Main) Enkheim",
        "alerts": False,
    },
    {
        "planned": "2026-11-22T12:00:00+01:00",
        "estimated": "2026-11-22T12:00:00+01:00",
        "delay": None,
        "cancelled": True,
        "head_sign": "Frankfurt (Main) Enkheim",
        "alerts": False,
    },
]

_M43 = {
    "state": "2026-11-22T10:00:00+00:00",
    "attributes": {
        "line_name": "M43",
        "transport": "BUS",
        "direction": "Frankfurt (Main) Bergen Ost",
        "icon": "mdi:bus",
        "times": _M43_TIMES,
        "friendly_name": "Weidenbornstraße M43",
    },
}

_U4_TIMES = [
    {
        "planned": "2026-11-22T10:00:00+01:00",
        "estimated": "2026-11-22T10:00:00+01:00",
        "delay": 1,
        "cancelled": False,
        "head_sign": "Frankfurt (Main) Enkheim",
        "alerts": False,
    },
    {
        "planned": "2026-11-22T12:00:00+01:00",
        "estimated": "2026-11-22T12:00:00+01:00",
        "delay": 0,
        "cancelled": False,
        "head_sign": "Frankfurt (Main) Enkheim",
        "alerts": False,
    },
]

_U4 = {
    "state": "2026-11-22T10:00:00+00:00",
    "attributes": {
        "line_name": "U4",
        "transport": "SUBWAY",
        "direction": "Frankfurt (Main) Enkheim",
        "icon": "mdi:subway",
        "times": _U4_TIMES,
        "friendly_name": "Weidenbornstraße U4",
    },
}

_STATES = {"sensor.m43": _M43, "sensor.u4": _U4}

# The pinned "now" freezes the departure timeline for every test.
_CONFIG = {
    "width": 800,
    "height": 480,
    "states": _STATES,
    "now": _NOW.isoformat(),
}


def _render(widget: dict, config: dict | None = None) -> str:
    """Render the departures widget with the pinned timeline."""
    cfg = dict(config or _CONFIG)
    cfg.setdefault("now", _NOW.isoformat())
    return render_widget_svg(widget, cfg)


def _widget(**overrides: object) -> dict:
    """Build a departures widget config with defaults."""
    return {"type": "departures", "x": 0, "y": 0, "w": 400, **overrides}


class TestDeparturesWidget:
    """departures.svg.j2 renders one row per departure sensor."""

    def test_no_entities_renders_empty_widget(self) -> None:
        # Without entities the widget renders nothing (no text, no
        # card) per spec.
        svg = _render(_widget(entities=[]))
        assert "<text" not in svg
        assert "<rect" not in svg

    def test_absolute_times_and_line_rows(self) -> None:
        # Default time_format renders HH:MM for each departure; two
        # sensors produce two rows with their line names.
        svg = _render(_widget(entities=["sensor.m43", "sensor.u4"]))
        assert ">M43<" in svg
        assert ">U4<" in svg
        assert ">10:00<" in svg
        assert ">10:31<" in svg  # estimated (planned + delay 2)
        assert ">11:05<" in svg

    def test_cancelled_and_past_are_skipped(self) -> None:
        # Cancelled departures never show; the 12:00 trip is marked
        # cancelled in _M43_TIMES.
        svg = _render(_widget(entities=["sensor.m43"]))
        assert ">12:00<" not in svg

    def test_min_minutes_drops_immediate_departures(self) -> None:
        # min_minutes=10 drops the 10:00 departure (0 min away).
        svg = _render(_widget(entities=["sensor.m43"], min_minutes=10))
        assert ">10:00<" not in svg
        assert ">10:31<" in svg

    def test_max_times_limits_cells(self) -> None:
        # max_times=2 shows only the first two (non-cancelled)
        # departures.
        svg = _render(_widget(entities=["sensor.m43"], max_times=2))
        assert ">10:00<" in svg
        assert ">10:31<" in svg
        assert ">11:05<" not in svg

    def test_relative_format(self) -> None:
        # Relative mode shows whole minutes until the (estimated)
        # departure.
        svg = _render(
            _widget(
                entities=["sensor.m43"],
                time_format="relative",
                max_times=4,
            )
        )
        assert ">0m<" in svg
        assert ">31m<" in svg

    def test_relative_over_an_hour_uses_hm_format(self) -> None:
        # 103 minutes away read as "1h43m", not "103 min".
        svg = _render(
            _widget(
                entities=["sensor.m43"],
                time_format="relative",
                max_times=4,
            )
        )
        assert ">1h43m<" in svg

    def test_auto_switches_at_one_hour(self) -> None:
        # Auto shows relative times up to 59 minutes, then absolute.
        svg = _render(_widget(entities=["sensor.m43"], time_format="auto"))
        assert ">0m<" in svg
        assert ">31m<" in svg
        assert ">11:05<" in svg  # 65 min away -> absolute

    def test_head_sign_strip_prefix(self) -> None:
        # The shared city prefix is stripped from every destination.
        svg = _render(
            _widget(
                entities=["sensor.m43"],
                w=560,
                head_sign_strip_prefix="Frankfurt (Main) ",
            )
        )
        assert "Bergen Ost" in svg
        assert "Frankfurt (Main)" not in svg

    def test_destination_falls_back_to_direction(self) -> None:
        # A sensor without times shows the direction attribute.
        states = {
            "sensor.empty": {
                "state": "2026-11-22T10:00:00+00:00",
                "attributes": {
                    "line_name": "X1",
                    "direction": "Irgendwo",
                    "times": [],
                },
            }
        }
        svg = _render(
            _widget(entities=["sensor.empty"]),
            {"width": 800, "height": 480, "states": states},
        )
        assert ">Irgendwo<" in svg

    def test_missing_entity_is_skipped(self) -> None:
        # An entity absent from the states produces no row instead
        # of an error.
        svg = _render(_widget(entities=["sensor.m43", "sensor.missing"]))
        assert svg.count(">M43<") == 1

    def test_delay_first_only_shows_next_departure(self) -> None:
        # Default ("first"): only each row's next departure shows a
        # chip — U4's 10:00 (delay 1), not M43's 10:31 (delay 2).
        svg = _render(_widget(entities=["sensor.m43", "sensor.u4"]))
        assert ">+1<" in svg
        assert ">+2<" not in svg

    def test_delay_all_shows_every_delayed(self) -> None:
        # "all": every delayed departure gets a chip.
        svg = _render(
            _widget(
                entities=["sensor.m43", "sensor.u4"],
                delay_style="all",
            )
        )
        assert ">+1<" in svg
        assert ">+2<" in svg

    def test_delay_none_hides_delay(self) -> None:
        # delay_style "none" never shows delay information.
        svg = _render(_widget(entities=["sensor.m43"], delay_style="none"))
        assert "+2" not in svg

    def test_line_style_text_renders_bold_text(self) -> None:
        # line_style "text" renders the line name as bold text
        # (no badge chip).
        svg = _render(_widget(entities=["sensor.m43"], line_style="text"))
        assert ">M43<" in svg

    def test_alert_icon_on_alerted_departure(self) -> None:
        # The second departure has alerts=true; the row shows the
        # gray alert triangle when alert_style is "triangle".
        svg = _render(_widget(entities=["sensor.m43"]))
        assert 'style="color: #787878"' in svg

    def test_alert_icon_mode_swaps_row_icon(self) -> None:
        # alert_style "icon" resolves the row icon's alert variant
        # (bus -> bus-alert) instead of drawing the triangle.
        captured: list[object] = []

        def _capture(icon_override, *args, **kwargs):
            captured.append(icon_override)
            return _resolve_icon_svg(icon_override, *args, **kwargs)

        with patch(
            "custom_components.eink_dashboard.widgets.departures"
            "._resolve_icon_svg",
            side_effect=_capture,
        ):
            svg = _render(
                _widget(
                    entities=["sensor.m43"],
                    alert_style="icon",
                )
            )
        assert "mdi:bus-alert" in captured
        assert 'style="color: #787878"' not in svg

    def test_alert_icon_mode_falls_back_to_triangle(self) -> None:
        # An icon without an alert variant (bus-stop) keeps the
        # triangle marker.
        states = {
            "sensor.x9": {
                "state": "2026-11-22T10:00:00+00:00",
                "attributes": {
                    "line_name": "X9",
                    "direction": "Frankfurt (Main) Hauptbahnhof",
                    "icon": "mdi:bus-stop",
                    "times": [
                        {
                            "planned": "2026-11-22T10:29:00+01:00",
                            "estimated": "2026-11-22T10:29:00+01:00",
                            "delay": 0,
                            "cancelled": False,
                            "head_sign": "Hauptbahnhof",
                            "alerts": True,
                        }
                    ],
                },
            }
        }
        svg = _render(
            _widget(entities=["sensor.x9"]),
            {"width": 800, "height": 480, "states": states},
        )
        assert 'style="color: #787878"' in svg

    def test_alert_none_hides_alert(self) -> None:
        svg = _render(_widget(entities=["sensor.m43"], alert_style="none"))
        assert 'style="color: #787878"' not in svg

    def test_header_icon_bus_clock_top_right(self) -> None:
        # Default header_icon draws the bus-clock icon top right
        # on the header row, same size as the row icons.
        svg = _render(
            _widget(entities=["sensor.m43"], list_header="ÖPNV", h=112)
        )
        # Widget w=400: icon_dia 36 sits at x = 400 - 12 - 36 = 352.
        assert "translate(352" in svg

    def test_header_icon_disabled_when_empty(self) -> None:
        svg = _render(
            _widget(
                entities=["sensor.m43"],
                list_header="ÖPNV",
                header_icon="",
                h=112,
            )
        )
        assert "translate(352" not in svg

    def test_times_ordered_earliest_leftmost(self) -> None:
        # Cells render left to right in departure order: the
        # earliest time's anchor is left of the latest's.
        svg = _render(_widget(entities=["sensor.m43"]))
        xs = [
            int(x)
            for x in re.findall(
                r'  x="(\d+)" y="\d+"\n'
                r'  font-family[^\n]+\n  font-size="\d+"\n'
                r'  font-weight="400"\n'
                r'  text-anchor="end"',
                svg,
            )
        ]
        assert len(xs) == 3
        assert xs[0] < xs[1] < xs[2]

    def test_list_header_renders_extra_row(self) -> None:
        svg = _render(_widget(entities=["sensor.m43"], list_header="ÖPNV"))
        assert ">ÖPNV<" in svg

    def test_line_badges_centered_on_shared_axis(self) -> None:
        # Badges keep their text-fitting widths but are centered
        # within a shared column: all badge centers share one
        # vertical axis.
        svg = _render(_widget(entities=["sensor.m43", "sensor.u4"]))
        rects = re.findall(
            r'<rect\n  x="(\d+)" y="\d+"\n  width="(\d+)"'
            r' height="\d+"\n  rx="6"',
            svg,
        )
        assert len(rects) == 2
        centers = [int(x) + int(w) / 2 for x, w in rects]
        assert abs(centers[0] - centers[1]) <= 1

    def test_destinations_share_start_x(self) -> None:
        # All destination texts start at the same x (after the
        # shared badge column).
        svg = _render(_widget(entities=["sensor.m43", "sensor.u4"]))
        # Both destination texts use the same larger font size and
        # start at identical x positions.
        xs = re.findall(
            r'<text\n  x="(\d+)" y="\d+"\n'
            r'  font-family[^\n]+\n  font-size="\d+"\n'
            r'  font-weight="400"\n'
            r'  text-anchor="start"',
            svg,
        )
        assert len(xs) == 2
        assert xs[0] == xs[1]

    def test_destinations_share_start_x_in_text_mode(self) -> None:
        # line_style "text" also aligns destinations: they start
        # after the widest line name, not after each own name.
        svg = _render(
            _widget(
                entities=["sensor.m43", "sensor.u4"],
                line_style="text",
            )
        )
        xs = re.findall(
            r'<text\n  x="(\d+)" y="\d+"\n'
            r'  font-family[^\n]+\n  font-size="\d+"\n'
            r'  font-weight="400"\n'
            r'  text-anchor="start"',
            svg,
        )
        assert len(xs) == 2
        assert xs[0] == xs[1]

    def test_times_right_aligned(self) -> None:
        # Every departure time is right-anchored (columns grow
        # leftward from the shared right edge).
        svg = _render(_widget(entities=["sensor.m43", "sensor.u4"]))
        # M43 shows 3 times, U4 has 2 departures.
        assert svg.count('text-anchor="end"') == 5

    def test_delay_chips_left_aligned_in_column(self) -> None:
        # All chips of one column start at the same x (the
        # column's chip sub-area is left-aligned).
        svg = _render(
            _widget(
                entities=["sensor.m43", "sensor.u4"],
                delay_style="all",
            )
        )
        chip_xs = re.findall(
            r'<rect\n  x="(\d+)" y="\d+"\n  width="\d+" height="\d+"'
            r'\n  rx="4"',
            svg,
        )
        assert len(chip_xs) == 2
        assert chip_xs[0] == chip_xs[1]

    def test_delay_chip_vertically_centered_with_time(self) -> None:
        # The chip's vertical center matches the time text's
        # center (both on the row center).
        svg = _render(
            _widget(
                entities=["sensor.m43", "sensor.u4"],
                delay_style="all",
            )
        )
        rect_y = re.search(
            r'<rect\n  x="\d+" y="(\d+)"\n  width="\d+" height="(\d+)"'
            r'\n  rx="4"',
            svg,
        )
        assert rect_y is not None
        chip_center = int(rect_y.group(1)) + int(rect_y.group(2)) / 2
        # Row center of the first row = row_h / 2 = 28.
        assert abs(chip_center - 28) <= 1

    def test_delay_chip_height_digit_only(self) -> None:
        # A digit-only chip ("+2") is exactly chip_font_sz tall
        # (m.font_secondary = 14 at row_h 56).
        svg = _render(_widget(entities=["sensor.m43"], delay_style="all"))
        heights = re.findall(
            r'<rect\n  x="\d+" y="\d+"\n  width="\d+" height="(\d+)"'
            r'\n  rx="4"',
            svg,
        )
        assert heights == ["14"]

    def test_delay_hours_format_and_chip_height(self) -> None:
        # A 63-minute delay reads "1h3" (no leading zero, no plus)
        # and its chip is 2 px taller than a digit-only chip.
        svg = _render(
            _widget(
                entities=["sensor.m43"],
                delay_style="all",
                max_times=4,
            )
        )
        assert ">+1h3<" in svg
        assert ">1h3<" not in svg
        heights = re.findall(
            r'<rect\n  x="\d+" y="\d+"\n  width="\d+" height="(\d+)"'
            r'\n  rx="4"',
            svg,
        )
        # Two chips, both at bare font size (14).
        assert sorted(heights) == ["14", "14"]

    def test_delay_does_not_shift_times(self) -> None:
        # A delay chip widens its column leftward, but the times
        # inside a column keep their right-aligned positions: the
        # delayed column's times (M43 10:31, U4 10:00) sit at the
        # same x as without chips.
        svg_none = _render(
            _widget(entities=["sensor.m43", "sensor.u4"], delay_style="none")
        )
        svg_all = _render(
            _widget(entities=["sensor.m43", "sensor.u4"], delay_style="all")
        )
        xs_none = re.findall(
            r'  x="(\d+)" y="\d+"\n'
            r'  font-family[^\n]+\n  font-size="\d+"\n'
            r'  font-weight="400"\n'
            r'  text-anchor="end"',
            svg_none,
        )
        xs_all = re.findall(
            r'  x="(\d+)" y="\d+"\n'
            r'  font-family[^\n]+\n  font-size="\d+"\n'
            r'  font-weight="400"\n'
            r'  text-anchor="end"',
            svg_all,
        )
        assert len(xs_all) == 5
        # DOM order: M43 (col 0..2), then U4 (col 1..2).  Within a
        # column, times align (col 1: M43 10:31 + U4 10:00; col 2:
        # 11:05 + 12:00); the chip-less col 2 keeps its position,
        # col 1 grows with the chips and pushes col 0 leftward.
        assert xs_all[1] == xs_all[3]
        assert xs_all[2] == xs_all[4]
        assert xs_all[2] == xs_none[2]
        assert int(xs_all[0]) < int(xs_all[1]) < int(xs_all[2])


class TestDeparturesStructure:
    """Structural/geometry tests per the widget-test skill."""

    def _config(self, **overrides: object) -> dict:
        return make_config(
            {"width": 800, "height": 480, "states": _STATES},
            **overrides,
        )

    def test_card_style_none_is_default(self) -> None:
        # Omitting card_style must produce byte-identical output to
        # card_style="none".
        base = _widget(entities=["sensor.m43"])
        with_none = render_dashboard(
            [{**base, "card_style": "none"}], self._config()
        )
        without = render_dashboard([base], self._config())
        assert with_none == without

    def test_card_border_draws_four_edges(self) -> None:
        # card_style="border" strokes the full widget frame.
        m = _compute_metrics(56)
        widget = _widget(
            entities=["sensor.m43"],
            card_style="border",
            h=56,
        )
        img = render_to_image([widget], self._config())
        assert_card_border(img, 400, 56, m)

    def test_row_divider_between_rows(self) -> None:
        # A gray divider runs along the boundary between the two
        # entity rows.
        m = _compute_metrics(56)
        widget = _widget(entities=["sensor.m43", "sensor.u4"], h=112)
        img = render_to_image([widget], self._config())
        assert_has_gray_pixels(
            img,
            24,
            56 - m.divider,
            376,
            56 + m.divider,
            low=COLOR_GRAY - 20,
            high=COLOR_GRAY + 20,
        )

    def test_icon_and_dest_vertically_centered(self) -> None:
        # Icon circle and the destination text of the same row
        # share the vertical center.
        widget = _widget(entities=["sensor.m43"], h=56)
        img = render_to_image([widget], self._config())
        assert_vertically_centered(
            img,
            (12, 12, 48, 44),
            (116, 12, 150, 44),
        )

    def test_auto_height_single_row(self) -> None:
        # Without explicit h, one row produces height DEFAULT_ROW_H.
        svg = _render(_widget(entities=["sensor.m43"]))
        m_h = re.search(r'height="(\d+)"', svg)
        assert m_h is not None
        assert int(m_h.group(1)) == DEFAULT_ROW_H

    def test_auto_height_header_plus_rows(self) -> None:
        # Without explicit h, header + one row produce twice the
        # default row height.
        svg = _render(_widget(entities=["sensor.m43"], list_header="ÖPNV"))
        m_h = re.search(r'height="(\d+)"', svg)
        assert m_h is not None
        assert int(m_h.group(1)) == 2 * DEFAULT_ROW_H

    def test_explicit_h_preserved(self) -> None:
        # An explicit h overrides auto-sizing.
        svg = _render(_widget(entities=["sensor.m43"], h=200))
        m_h = re.search(r'height="(\d+)"', svg)
        assert m_h is not None
        assert int(m_h.group(1)) == 200
