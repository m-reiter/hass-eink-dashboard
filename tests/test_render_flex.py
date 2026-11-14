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
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from typing import ClassVar

from custom_components.eink_dashboard.svg_render import render_widget_svg
from custom_components.eink_dashboard.widgets.flex import (
    _build_flex_context,
)
from tests.helpers import (
    make_config,
)

MOCK_FLEX_STATES = {
    "sensor.muellabfuhr": {
        "state": "Restmuell",
        "attributes": {
            "friendly_name": "Muellabfuhr",
            "status": "Heute",
        },
    },
    "sensor.temperature": {
        "state": "22.5",
        "attributes": {
            "friendly_name": "Living Room",
            "unit_of_measurement": "°C",
        },
    },
}

_DEFAULTS: ClassVar[dict[str, object]] = {
    "width": 400,
    "height": 300,
    "states": MOCK_FLEX_STATES,
}


class TestRenderFlex:
    """Verify rendering of the flex widget."""

    _DEFAULTS: ClassVar[dict[str, object]] = {
        "width": 400,
        "height": 300,
        "states": MOCK_FLEX_STATES,
    }

    def _config(self, **overrides: object) -> dict[str, object]:
        return make_config(self._DEFAULTS, **overrides)

    def _widget(self, **overrides: object) -> dict[str, object]:
        w: dict[str, object] = {
            "type": "flex",
            "x": 0,
            "y": 0,
            "w": 216,
            "h": 116,
            "entity": "sensor.muellabfuhr",
            "card_style": "border",
            "elements": [
                {
                    "type": "icon",
                    "x": 8,
                    "y": 8,
                    "icon": "mdi:trash-can",
                    "icon_size": 32,
                    "icon_style": "none",
                },
                {
                    "type": "text",
                    "x": 48,
                    "y": 8,
                    "source": "state",
                    "font_size": 16,
                    "weight": "medium",
                    "color": "black",
                },
                {
                    "type": "text",
                    "x": 8,
                    "y": 48,
                    "source": "attribute:status",
                    "font_size": 14,
                    "weight": "regular",
                    "color": "gray",
                },
            ],
        }
        w.update(overrides)
        return w

    # ── Structural tests ──────────────────────────────

    def test_flex_renders_icon_and_text(self) -> None:
        # Basic rendering: icon + state text + attribute text.
        widget = self._widget()
        svg = render_widget_svg(widget, self._config())
        assert "Restmuell" in svg
        assert "Heute" in svg

    def test_flex_missing_entity(self) -> None:
        # Missing entity → empty context.
        widget = self._widget(entity="sensor.nonexistent")
        ctx = _build_flex_context(widget, self._config())
        assert ctx["has_entity"] is False
        assert ctx["elements"] == []

    def test_flex_empty_elements(self) -> None:
        # No elements → empty context.
        widget = self._widget(elements=[])
        ctx = _build_flex_context(widget, self._config())
        assert ctx["has_entity"] is False or ctx["elements"] == []

    def test_flex_card_border(self) -> None:
        # Border style draws a rounded rect.
        widget = self._widget(card_style="border")
        svg = render_widget_svg(widget, self._config())
        assert 'stroke-width="2"' in svg or 'stroke="#000000"' in svg

    # ── Data sources ──────────────────────────────────

    def test_flex_source_state(self) -> None:
        widget = self._widget(
            elements=[
                {
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "source": "state",
                    "font_size": 14,
                },
            ]
        )
        svg = render_widget_svg(widget, self._config())
        assert "Restmuell" in svg

    def test_flex_source_attribute(self) -> None:
        widget = self._widget(
            elements=[
                {
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "source": "attribute:status",
                    "font_size": 14,
                },
            ]
        )
        svg = render_widget_svg(widget, self._config())
        assert "Heute" in svg

    def test_flex_source_attribute_colon(self) -> None:
        widget = self._widget(
            elements=[
                {
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "source": "attribute: status",
                    "font_size": 14,
                },
            ]
        )
        svg = render_widget_svg(widget, self._config())
        assert "Heute" in svg

    def test_flex_source_static(self) -> None:
        widget = self._widget(
            elements=[
                {
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "source": "static",
                    "static_text": "Hello",
                    "font_size": 14,
                },
            ]
        )
        svg = render_widget_svg(widget, self._config())
        assert "Hello" in svg

    def test_flex_dynamic_icon(self) -> None:
        # Without icon override, icon is resolved from entity.
        widget = self._widget(
            elements=[
                {
                    "type": "icon",
                    "x": 0,
                    "y": 0,
                    "icon_size": 24,
                    "icon_style": "none",
                },
            ]
        )
        svg = render_widget_svg(widget, self._config())
        # Should render something (letter fallback or icon)
        assert len(svg) > 100

    # ── Multi-line & valign ──────────────────────────

    def test_flex_multiline_newline(self) -> None:
        widget = self._widget(
            elements=[
                {
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "source": "static",
                    "static_text": "Line1\nLine2",
                    "font_size": 14,
                },
            ]
        )
        svg = render_widget_svg(widget, self._config())
        assert "Line1" in svg
        assert "Line2" in svg

    def test_flex_multiline_escaped(self) -> None:
        widget = self._widget(
            elements=[
                {
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "source": "static",
                    "static_text": "Line1\\nLine2",
                    "font_size": 14,
                },
            ]
        )
        svg = render_widget_svg(widget, self._config())
        assert "Line1" in svg
        assert "Line2" in svg

    def test_flex_valign_top(self) -> None:
        widget = self._widget(
            elements=[
                {
                    "type": "text",
                    "x": 0,
                    "y": 50,
                    "source": "static",
                    "static_text": "Top",
                    "font_size": 14,
                    "valign": "top",
                },
            ]
        )
        svg = render_widget_svg(widget, self._config())
        assert 'y="50"' in svg or 'y="5' in svg

    # ── Edge cases ───────────────────────────────────

    def test_flex_no_entity(self) -> None:
        widget = self._widget(entity="")
        ctx = _build_flex_context(widget, self._config())
        assert ctx["has_entity"] is False

    def test_flex_default_sizes(self) -> None:
        # Elements without explicit sizes use defaults from metrics.
        widget = self._widget(
            elements=[
                {"type": "text", "x": 0, "y": 0, "source": "state"},
            ]
        )
        svg = render_widget_svg(widget, self._config())
        assert "Restmuell" in svg
