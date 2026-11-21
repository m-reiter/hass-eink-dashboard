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

"""List widget context builder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import (
    COLOR_BLACK,
    DEFAULT_CARD_STYLE,
    DEFAULT_ROW_H,
    PADDING,
    DisplayConfig,
    FontWeight,
    color_to_hex,
)
from ._helpers import (
    CardRow,
    _auto_row_height,
    _card_insets,
    _color_context,
    _divider_stroke_width,
    _icon_stroke_width,
    _list_row_height,
    _max_row_height,
    _metrics_context,
    _resolve_entity,
    _resolve_icon_style,
    _resolve_icon_svg,
    _row_context,
    _widget_dim,
)

if TYPE_CHECKING:
    from ..widget_config import ListWidget


def _build_list_context(
    widget: ListWidget,
    config: DisplayConfig,
) -> dict[str, object]:
    """Build Jinja2 template context for the list widget.

    Renders a header (entity state or override) in medium weight and
    a list of text items read from an entity attribute, each as a
    ``card_row``.

    Args:
        widget: Widget config dict.  Recognised keys:
            ``entity``, ``source`` (attribute name),
            ``separator`` (default ``, ``), ``max_items``,
            ``hide_icon``, ``name`` (header override),
            ``card_style``, ``x``, ``w``, ``h``.
        config: Display config with ``states``, ``display_levels``,
            and ``font_scale``.

    Returns:
        Template context dict consumed by ``list.svg.j2``.
        Returns ``{"w": …, "h": …, "has_rows": False}`` when the
        entity is absent or no items are found.
    """
    from ..render import (
        _compute_metrics,
        _font_weight_svg,
        resolve_font,
    )

    x = widget.get("x", PADDING)
    svg_w = _widget_dim(widget, "w", config["width"] - x)

    entity_id = widget.get("entity", "")
    entity = _resolve_entity(widget, config)

    empty_ctx: dict[str, object] = {
        "w": svg_w,
        "h": _widget_dim(widget, "h", DEFAULT_ROW_H),
        "has_rows": False,
        **_color_context(),
    }
    if entity is None:
        return empty_ctx

    card_style = widget.get("card_style", DEFAULT_CARD_STYLE)
    display_levels = config.get("display_levels", 16)
    font_scale: float = config.get("font_scale", 1.0)
    max_row_h = _max_row_height(widget, config)
    hide_icon = bool(widget.get("hide_icon", False))

    # Header: entity state or override.
    header: str = widget.get("name") or str(entity.state_val or "")

    # Source attribute.
    source_attr = widget.get("source", "")
    attrs = entity.attrs
    if not source_attr:
        for key in attrs:
            if key not in ("friendly_name", "icon", "unit_of_measurement"):
                source_attr = key
                break

    separator = widget.get("separator", ", ")
    raw_value = str(attrs.get(source_attr, ""))
    items = [
        item.strip() for item in raw_value.split(separator) if item.strip()
    ]

    max_items = widget.get("max_items")
    overflow = 0
    if max_items and len(items) > max_items:
        visible_items = items[: max_items - 1]
        overflow = len(items) - (max_items - 1)
    else:
        visible_items = items

    if not visible_items and overflow == 0:
        return empty_ctx

    # Number of rows: header + items + overflow.
    num_display_rows = (
        len(visible_items) + (1 if header else 0) + (1 if overflow > 0 else 0)
    )
    if num_display_rows < 1:
        num_display_rows = 1

    svg_h = _widget_dim(
        widget,
        "h",
        _auto_row_height("", num_display_rows, max_row_h),
    )

    content_h = svg_h
    row_h = _list_row_height(content_h, num_display_rows, max_row_h)
    # The card frame wraps the rows only, not any unused space
    # below them.
    content_h = row_h * num_display_rows

    m = _compute_metrics(row_h)

    x_off, r_inset, bar_width = _card_insets(m, card_style, display_levels)
    lpad = m.padding if x_off == 0 else 0
    rpad = m.padding if r_inset == 0 else 0

    # Header font (medium weight).
    header_font_sz = m.font_primary
    header_weight = FontWeight.MEDIUM
    if header:
        header_font_sz, header_weight = resolve_font(
            widget,
            "title",
            header_font_sz,
            FontWeight.MEDIUM,
            scale=font_scale,
        )

    # Per-row font.
    primary_font_sz, primary_weight = resolve_font(
        widget,
        "primary",
        m.font_primary,
        FontWeight.REGULAR,
        scale=font_scale,
    )
    secondary_font_sz, secondary_weight = resolve_font(
        widget,
        "secondary",
        m.font_secondary,
        FontWeight.REGULAR,
        scale=font_scale,
    )
    value_font_sz, value_weight = resolve_font(
        widget,
        "value",
        m.font_secondary,
        FontWeight.REGULAR,
        scale=font_scale,
    )

    icon_stroke_w = _icon_stroke_width(m.border, display_levels)
    divider_stroke_w = _divider_stroke_width(widget)
    divider_y_off = (divider_stroke_w % 2) / 2

    # Icon resolution for the header row.
    icon_svg = ""
    icon_letter = ""
    icon_outline = False
    icon_no_circle = hide_icon
    if not hide_icon:
        icon_override = widget.get("icon")
        domain = entity_id.split(".")[0] if entity_id else ""
        icon_outline, icon_no_circle = _resolve_icon_style(
            widget.get("icon_style"), display_levels=display_levels
        )
        # Without a circle the glyph is scaled to the full icon
        # diameter so it appears the same size as with a circle.
        icon_inner_sz = m.icon_dia if icon_no_circle else m.icon_inner
        icon_svg, icon_letter = _resolve_icon_svg(
            icon_override,
            attrs,
            str(entity.state_val or ""),
            domain,
            icon_inner_sz,
            entity_id=entity_id,
        )

    rows: list[dict[str, object]] = []
    row_idx = 0

    # Header row (with icon, medium weight).
    if header:
        row_ctx = _row_context(
            CardRow(
                y=row_idx * row_h,
                primary=header,
                icon_svg=icon_svg,
                icon_outline=icon_outline,
                icon_no_circle=icon_no_circle or hide_icon,
                letter=icon_letter,
                icon_fill=color_to_hex(COLOR_BLACK),
            )
        )
        row_ctx["primary_font_sz"] = header_font_sz
        row_ctx["primary_weight"] = _font_weight_svg(header_weight)
        row_ctx["row_hide_icon"] = hide_icon
        row_ctx["icon_inner_sz"] = (
            icon_inner_sz if not hide_icon else m.icon_inner
        )
        rows.append(row_ctx)
        row_idx += 1

    # Item rows (no icon, regular weight).
    for item in visible_items:
        row_ctx = _row_context(
            CardRow(
                y=row_idx * row_h,
                primary=item,
                icon_svg="",
                icon_outline=True,
                icon_no_circle=True,
                letter="",
                icon_fill=color_to_hex(COLOR_BLACK),
            )
        )
        row_ctx["primary_font_sz"] = primary_font_sz
        row_ctx["primary_weight"] = _font_weight_svg(primary_weight)
        row_ctx["row_hide_icon"] = True
        row_ctx["icon_inner_sz"] = m.icon_inner
        rows.append(row_ctx)
        row_idx += 1

    # Overflow row.
    if overflow > 0:
        overflow_text = (
            f"+{overflow} weiteres"
            if overflow == 1
            else f"+{overflow} weitere"
        )
        row_ctx = _row_context(
            CardRow(
                y=row_idx * row_h,
                primary=overflow_text,
                icon_svg="",
                icon_outline=True,
                icon_no_circle=True,
                letter="",
                icon_fill=color_to_hex(COLOR_BLACK),
            )
        )
        row_ctx["primary_font_sz"] = primary_font_sz
        row_ctx["primary_weight"] = _font_weight_svg(primary_weight)
        rows.append(row_ctx)
        row_idx += 1

    return {
        "w": svg_w,
        "h": svg_h,
        "has_rows": True,
        "header": header,
        "header_font_sz": header_font_sz,
        "header_weight": _font_weight_svg(header_weight),
        "card_style": card_style,
        "bar_width": bar_width,
        **_metrics_context(m),
        **_color_context(),
        "row_h": row_h,
        "rows": rows,
        "x_off": x_off,
        "r_inset": r_inset,
        "lpad": lpad,
        "rpad": rpad,
        "icon_stroke_w": icon_stroke_w,
        "divider_stroke_w": divider_stroke_w,
        "divider_y_off": divider_y_off,
        "hide_icon": hide_icon,
        "primary_font_sz": primary_font_sz,
        "primary_weight": _font_weight_svg(primary_weight),
        "secondary_font_sz": secondary_font_sz,
        "secondary_weight": _font_weight_svg(secondary_weight),
        "value_font_sz": value_font_sz,
        "value_weight": _font_weight_svg(value_weight),
    }
