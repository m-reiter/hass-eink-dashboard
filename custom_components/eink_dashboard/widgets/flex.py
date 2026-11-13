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

"""Flex widget context builder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import (
    COLOR_BLACK,
    COLOR_GRAY,
    COLOR_WHITE,
    DEFAULT_CARD_STYLE,
    DEFAULT_ROW_H,
    PADDING,
    DisplayConfig,
    FontWeight,
    color_to_hex,
)
from ._helpers import (
    _card_insets,
    _color_context,
    _icon_stroke_width,
    _metrics_context,
    _resolve_entity,
    _resolve_icon_style,
    _resolve_icon_svg,
    _widget_dim,
)

if TYPE_CHECKING:
    from ..widget_config import FlexElement, FlexWidget


def _resolve_text(
    element: FlexElement,
    entity: object,
) -> str:
    """Resolve the display text for a text element.

    Args:
        element: Flex element dict.
        entity: Resolved entity (from ``_resolve_entity``).
        config: Display config.

    Returns:
        The resolved text string (may contain ``\\n`` for
        multi-line).
    """
    source = element.get("source", "state")
    if source == "static":
        return str(element.get("static_text", ""))
    attrs = getattr(entity, "attrs", {}) or {}
    if source == "attribute":
        attr_name = element.get("attribute", "")
        return str(attrs.get(attr_name, ""))
    if source.startswith("attribute:"):
        attr_name = source.split(":", 1)[1].strip()
        return str(attrs.get(attr_name, ""))
    # Default: state
    state_val = getattr(entity, "state_val", None)
    return str(state_val) if state_val is not None else ""


def _build_flex_context(
    widget: FlexWidget,
    config: DisplayConfig,
) -> dict[str, object]:
    """Build Jinja2 template context for the flex widget.

    Renders freely positioned icon and text elements on a card.
    Each element's position, size, and style are configurable.

    Args:
        widget: Widget config dict.  Recognised keys:
            ``entity`` (HA entity ID, required),
            ``elements`` (list of FlexElement dicts),
            ``card_style``, ``x``, ``w``, ``h``.
        config: Display config with ``states``, ``display_levels``.

    Returns:
        Template context dict consumed by ``flex.svg.j2``.
    """
    from ..render import (
        _compute_metrics,
        _font_weight_svg,
    )

    x = widget.get("x", PADDING)
    svg_w = _widget_dim(widget, "w", config["width"] - x)

    entity_id = widget.get("entity", "")
    entity = _resolve_entity(widget, config)

    empty_ctx: dict[str, object] = {
        "w": svg_w,
        "h": _widget_dim(widget, "h", DEFAULT_ROW_H * 2),
        "has_entity": False,
        "elements": [],
        **_color_context(),
    }
    if entity is None:
        return empty_ctx

    elements: list[FlexElement] = widget.get("elements", [])
    if not elements:
        return empty_ctx

    card_style = widget.get("card_style", DEFAULT_CARD_STYLE)
    display_levels = config.get("display_levels", 16)

    m = _compute_metrics(DEFAULT_ROW_H)
    x_off, r_inset, bar_width = _card_insets(m, card_style, display_levels)
    lpad = m.padding if x_off == 0 else 0
    rpad = m.padding if r_inset == 0 else 0

    default_font_size = widget.get("default_font_size", m.font_primary)
    default_icon_size = widget.get("default_icon_size", m.icon_inner)

    # Resolve each element.
    resolved: list[dict[str, object]] = []
    for el in elements:
        el_type = el.get("type", "text")
        el_x = el.get("x", 0)
        el_y = el.get("y", 0)

        if el_type == "icon":
            icon_size = el.get("icon_size", default_icon_size)
            icon_style = el.get("icon_style", "none")
            icon_outline, icon_no_circle = _resolve_icon_style(
                icon_style, display_levels=display_levels
            )
            icon_stroke_w = _icon_stroke_width(m.border, display_levels)

            icon_override = el.get("icon")
            domain = entity_id.split(".")[0] if entity_id else ""
            icon_svg, letter = _resolve_icon_svg(
                icon_override,
                entity.attrs,
                str(entity.state_val or ""),
                domain,
                icon_size,
                entity_id=entity_id,
            )

            resolved.append(
                {
                    "type": "icon",
                    "x": el_x,
                    "y": el_y,
                    "icon_svg": icon_svg,
                    "icon_size": icon_size,
                    "icon_outline": icon_outline,
                    "icon_no_circle": icon_no_circle,
                    "icon_stroke_w": icon_stroke_w,
                    "letter": letter,
                    "letter_font_sz": icon_size,
                }
            )

        elif el_type == "text":
            font_size = el.get("font_size", default_font_size)
            weight_str = el.get("weight", "regular")
            weight = (
                FontWeight[weight_str.upper()]
                if weight_str.upper() in FontWeight.__members__
                else FontWeight.REGULAR
            )
            text = _resolve_text(el, entity)
            lines = text.split("\\n") if text else [""]
            line_height = el.get("line_height", round(font_size * 1.2))

            align = el.get("align", "left")
            anchor = {"left": "start", "center": "middle", "right": "end"}.get(
                align, "start"
            )

            color_str = el.get("color", "black")
            if color_str == "gray":
                text_color = color_to_hex(COLOR_GRAY)
            elif color_str == "white":
                text_color = color_to_hex(COLOR_WHITE)
            else:
                text_color = color_to_hex(COLOR_BLACK)

            valign = el.get("valign", "top")
            dominant_baseline = {"top": "hanging", "middle": "middle", "bottom": "auto"}.get(
                valign, "hanging"
            )
            line_span = (len(lines) - 1) * line_height
            if valign == "top":
                y_offset = 0
            elif valign == "middle":
                y_offset = -line_span // 2
            else:  # bottom
                y_offset = -line_span

            resolved.append(
                {
                    "type": "text",
                    "x": el_x,
                    "y": el_y + y_offset,
                    "lines": lines,
                    "font_size": font_size,
                    "weight": _font_weight_svg(weight),
                    "color": text_color,
                    "align": align,
                    "anchor": anchor,
                    "dominant_baseline": dominant_baseline,
                    "line_height": line_height,
                }
            )

    svg_h = _widget_dim(widget, "h", DEFAULT_ROW_H * 2)

    return {
        "w": svg_w,
        "h": svg_h,
        "has_entity": True,
        "card_style": card_style,
        "bar_width": bar_width,
        **_metrics_context(m),
        **_color_context(),
        "x_off": x_off,
        "r_inset": r_inset,
        "lpad": lpad,
        "rpad": rpad,
        "elements": resolved,
    }
