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

"""Tests for the list widget's header override (list_header)."""

from __future__ import annotations

from custom_components.eink_dashboard.svg_render import render_widget_svg

_STATES = {
    "sensor.offene_fenster": {
        "state": "Keine offenen Fenster",
        "attributes": {
            "open_windows": "",
            "friendly_name": "Offene Fenster",
        },
    },
}

_CONFIG = {"width": 800, "height": 480, "states": _STATES}


class TestListHeaderOverride:
    """The list_header key overrides the entity-state fallback."""

    def test_list_header_renders_instead_of_entity_state(self) -> None:
        widget = {
            "type": "list",
            "x": 0,
            "y": 0,
            "w": 216,
            "entity": "sensor.offene_fenster",
            "list_header": "Wohnzimmer",
        }
        svg = render_widget_svg(widget, _CONFIG)
        assert "Wohnzimmer" in svg
        assert "Keine offenen Fenster" not in svg

    def test_entity_state_used_without_override(self) -> None:
        widget = {
            "type": "list",
            "x": 0,
            "y": 0,
            "w": 216,
            "entity": "sensor.offene_fenster",
        }
        svg = render_widget_svg(widget, _CONFIG)
        # The header text is truncated to the widget width, so
        # match a prefix rather than the full state string.
        assert "Keine offenen" in svg
