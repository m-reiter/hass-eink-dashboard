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

"""Departures widget context builder (public transport departures).

One row per departure sensor (e.g. from the "Public Transport
Departures" integration): entity icon, line badge, destination of
the next departure, and the next departure times.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from ..const import (
    AUTO_TIME_MAX_MIN,
    DEFAULT_ALERT_STYLE,
    DEFAULT_CARD_STYLE,
    DEFAULT_DELAY_STYLE,
    DEFAULT_HEADER_ICON,
    DEFAULT_LINE_STYLE,
    DEFAULT_MAX_TIMES,
    DEFAULT_MIN_MINUTES,
    DEFAULT_ROW_FONT_SCALE,
    DEFAULT_TIME_FORMAT,
    DEPARTURES_COLUMN_GAP_FACTOR,
    PADDING,
    DisplayConfig,
    FontWeight,
)
from ._helpers import (
    _auto_row_height,
    _card_insets,
    _color_context,
    _divider_stroke_width,
    _icon_stroke_width,
    _list_row_height,
    _max_row_height,
    _metrics_context,
    _resolve_icon_style,
    _resolve_icon_svg,
    _widget_dim,
)

if TYPE_CHECKING:
    from PIL import ImageFont

    from ..render import WidgetMetrics
    from ..widget_config import DeparturesWidget

    _PilFont = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _now() -> datetime:
    """Current local time, timezone-aware."""
    return datetime.now().astimezone()


def _parse_dt(value: object) -> datetime | None:
    """Parse an ISO timestamp; return None for absent/invalid values.

    Naive timestamps are assumed to be local time.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _wait_minutes(estimated: datetime, now: datetime) -> int:
    """Whole minutes from now until the departure."""
    return int((estimated - now).total_seconds() // 60)


def _format_time(
    estimated: datetime,
    wait_min: int,
    time_format: str,
) -> str:
    """Format one departure time per the widget's time_format."""
    if time_format == "relative" or (
        time_format == "auto" and wait_min <= AUTO_TIME_MAX_MIN
    ):
        if wait_min >= 60:
            # "103 min" reads worse than "1h43m"; minutes without
            # a leading zero ("1h4m").
            return f"{wait_min // 60}h{wait_min % 60}m"
        return f"{max(wait_min, 0)} min"
    return estimated.strftime("%H:%M")


# Alert-variant icons: transport icon -> alert variant.  Icons
# without a variant entry fall back to the triangle marker.
ALERT_ICON_MAP: dict[str, str] = {
    "mdi:bus": "mdi:bus-alert",
    "mdi:subway": "mdi:subway-alert-variant",
    "mdi:tram": "mdi:tram-alert",
    "mdi:train": "mdi:train-alert",
    "mdi:ferry": "mdi:ferry-alert",
}


def _strip_prefix(dest: str, prefix: str) -> str:
    """Remove a leading prefix from the destination text."""
    if prefix and dest.startswith(prefix):
        return dest[len(prefix) :].lstrip()
    return dest


def _collect_rows(
    config: DisplayConfig,
    entity_ids: list[str],
    now: datetime,
    time_format: str,
    max_times: int,
    min_minutes: int,
    strip_prefix: str,
) -> tuple[
    list[dict[str, object]],
    list[list[dict[str, object]]],
    list[tuple[str, dict]],
]:
    """Collect per-row departure data for every configured entity.

    Entities missing from the display states are skipped entirely.

    Args:
        config: Display config providing ``states``.
        entity_ids: Departure sensor IDs in display order.
        now: Reference time for the past/future filter.
        time_format: ``"absolute"``, ``"relative"`` or ``"auto"``.
        max_times: Departure times shown per row.
        min_minutes: Drop departures sooner than this many minutes.
        strip_prefix: Prefix removed from every destination.

    Returns:
        ``(raw_rows, row_cells, row_sources)``: per-row destination
        data, per-row time cells, and the (entity ID, attributes)
        pair per row for the later icon pass.
    """
    states = config.get("states", {})
    raw_rows: list[dict[str, object]] = []
    row_cells: list[list[dict[str, object]]] = []
    row_sources: list[tuple[str, dict]] = []
    for entity_id in entity_ids:
        state = states.get(entity_id)
        if state is None:
            continue
        attrs = state.get("attributes", {})
        line = str(attrs.get("line_name", "") or "")
        direction = str(attrs.get("direction", "") or "")

        dest = ""
        alert = False
        cells: list[dict[str, object]] = []
        for entry in attrs.get("times") or []:
            if not isinstance(entry, dict) or entry.get("cancelled"):
                continue
            planned = _parse_dt(entry.get("planned"))
            estimated = _parse_dt(entry.get("estimated")) or planned
            if estimated is None:
                continue
            wait_min = _wait_minutes(estimated, now)
            if wait_min < min_minutes:
                continue
            if not dest:
                dest = str(entry.get("head_sign") or "") or direction
            alert = alert or bool(entry.get("alerts"))
            raw_delay = entry.get("delay")
            delay = (
                int(raw_delay) if isinstance(raw_delay, (int, float)) else 0
            )
            cells.append(
                {
                    "text": _format_time(estimated, wait_min, time_format),
                    "delay": delay,
                }
            )
            if len(cells) >= max_times:
                break

        # Destination of the next departure; without any upcoming
        # departure fall back to the entity's direction attribute.
        if not dest:
            dest = direction

        raw_rows.append(
            {
                "line": line,
                "dest": _strip_prefix(dest, strip_prefix),
                "alert": alert,
            }
        )
        row_cells.append(cells)
        row_sources.append((entity_id, attrs))
    return raw_rows, row_cells, row_sources


def _alert_icon_swap(
    widget: DeparturesWidget,
    attrs: dict,
    entity_id: str,
    alert: bool,
    alert_style: str,
    hide_icon: bool,
    icon_inner_sz: int,
) -> str:
    """Resolve the alert-variant icon swap for a row.

    For ``alert_style == "icon"`` with an alert flag and a known
    variant (see ``ALERT_ICON_MAP``), returns the replacement icon
    SVG.  All other cases return "" — callers then fall back to
    the triangle marker so the alert stays visible.
    """
    if alert_style != "icon" or not alert or hide_icon:
        return ""
    variant = ALERT_ICON_MAP.get(str(attrs.get("icon", "") or ""))
    if variant is None:
        return ""
    icon_svg, _letter = _resolve_icon_svg(
        variant,
        attrs,
        "",
        entity_id.split(".")[0],
        icon_inner_sz,
        entity_id=entity_id,
    )
    return icon_svg


def _alert_triangle_ctx(
    alert: bool,
    alert_style: str,
    alert_sz: int,
    inner_gap: int,
) -> tuple[int, str]:
    """Resolve the triangle marker for one row.

    Args:
        alert: Whether any shown departure carries alerts.
        alert_style: ``"triangle"``, ``"icon"`` or ``"none"``;
            the marker is drawn only for ``"triangle"``.
        alert_sz: Triangle marker size in px.
        inner_gap: Shared inner gap in px.

    Returns:
        ``(alert_w, alert_svg)``: the extra width the marker
        reserves (0 = none) and the marker SVG ("" when not
        drawn).
    """
    if alert_style != "triangle" or not alert:
        return (0, "")
    from ..svg_render import _mdi_svg_filter

    return (alert_sz + inner_gap, _mdi_svg_filter("alert", alert_sz))


def _header_row_context(
    header: str,
    header_font_sz: int,
    header_icon: str,
    row_h: int,
    svg_w: int,
    r_inset: int,
    rpad: int,
    x_off: int,
    lpad: int,
    icon_dia: int,
) -> dict[str, object]:
    """Build the header row context with optional top-right icon.

    Args:
        header: Header text (non-empty here).
        header_font_sz: Header font size in px.
        header_icon: MDI icon name ("" disables the icon).
        row_h: Header row height in px.
        svg_w: Widget width in px.
        r_inset: Right inset from the card decoration.
        rpad: Right padding.
        x_off: Left inset from the card decoration.
        lpad: Left padding.
        icon_dia: Row icon diameter; the header icon matches it.

    Returns:
        Row context dict consumed by ``departures.svg.j2``.
    """
    header_icon_svg = ""
    header_icon_x = 0
    header_icon_y = 0
    if header_icon:
        from ..svg_render import _mdi_svg_filter

        # Same size as the row icons (icon_dia) so the header
        # icon reads as an equal peer.
        header_icon_svg = _mdi_svg_filter(
            header_icon.removeprefix("mdi:"), icon_dia
        )
        header_icon_x = svg_w - r_inset - rpad - icon_dia
        header_icon_y = row_h // 2 - icon_dia // 2
    return {
        "y": 0,
        "header": True,
        "header_x": x_off + lpad,
        "header_y": row_h // 2,
        "header_icon_svg": header_icon_svg,
        "header_icon_x": header_icon_x,
        "header_icon_y": header_icon_y,
    }


def _normalize_delay_style(value: str) -> str:
    """Validate the delay chip policy value.

    Args:
        value: Raw ``delay_style`` widget value.

    Returns:
        ``"all"``, ``"first"`` or ``"none"`` (default for unknown
        values).
    """
    if value in ("all", "first", "none"):
        return value
    return DEFAULT_DELAY_STYLE


def _resolve_alert_style(widget: DeparturesWidget) -> str:
    """Validate the alert display style value.

    Args:
        widget: Widget config dict.

    Returns:
        ``"triangle"``, ``"icon"`` or ``"none"`` (default for
        unknown values).
    """
    style = str(widget.get("alert_style", DEFAULT_ALERT_STYLE))
    if style in ("triangle", "icon", "none"):
        return style
    return DEFAULT_ALERT_STYLE


@dataclass(frozen=True)
class _DepartureFonts:
    """Resolved font sizes and weights for the departures widget
    roles."""

    header_font_sz: int
    """Header font size in px."""
    header_weight: FontWeight
    """Header font weight."""
    line_font_sz: int
    """Line badge/name font size in px."""
    line_weight: FontWeight
    """Line font weight."""
    dest_font_sz: int
    """Destination font size in px."""
    dest_weight: FontWeight
    """Destination font weight."""
    time_font_sz: int
    """Departure time font size in px."""
    time_weight: FontWeight
    """Time font weight."""


def _resolve_fonts(
    widget: DeparturesWidget,
    m: WidgetMetrics,
    font_scale: float,
    font_px_base: int,
) -> _DepartureFonts:
    """Resolve the departures font sizes and weights per role.

    Args:
        widget: Widget config dict (``fonts`` overrides).
        m: WidgetMetrics from _compute_metrics(row_h).
        font_scale: Display-level font scale.
        font_px_base: Metrics-derived base size, already scaled by
            the widget's row_font_scale.

    Returns:
        _DepartureFonts with all role sizes and weights.
    """
    from ..render import resolve_font

    header_font_sz, header_weight = resolve_font(
        widget,
        "title",
        font_px_base,
        FontWeight.MEDIUM,
        scale=font_scale,
    )
    line_font_sz, line_weight = resolve_font(
        widget,
        "line",
        font_px_base,
        FontWeight.BOLD,
        scale=font_scale,
    )
    dest_font_sz, dest_weight = resolve_font(
        widget,
        "destination",
        font_px_base,
        FontWeight.REGULAR,
        scale=font_scale,
    )
    time_font_sz, time_weight = resolve_font(
        widget,
        "time",
        font_px_base,
        FontWeight.REGULAR,
        scale=font_scale,
    )
    return _DepartureFonts(
        header_font_sz=header_font_sz,
        header_weight=header_weight,
        line_font_sz=line_font_sz,
        line_weight=line_weight,
        dest_font_sz=dest_font_sz,
        dest_weight=dest_weight,
        time_font_sz=time_font_sz,
        time_weight=time_weight,
    )


def _delay_text(delay: int) -> str:
    """Format the delay chip label.

    Args:
        delay: Delay in minutes (>= 1).

    Returns:
        Always with a leading ``"+"``: minutes as ``"+N"``, an
        hour or more compactly as ``"+1h"``, ``"+1h1"``, ``"+1h12"``.
    """
    if delay >= 60:
        hours, minutes = divmod(delay, 60)
        return f"+{hours}h" + (str(minutes) if minutes else "")
    return f"+{delay}"


def _column_layout(
    row_cells: list[list[dict[str, object]]],
    times_right: int,
    time_font: _PilFont,
    chip_font: _PilFont,
    chip_gap: int,
    col_gap: int,
    delay_style: str,
) -> tuple[list[int], list[int], int, int, bool]:
    """Lay out the departure time columns.

    Columns are laid out left to right in departure order and
    aligned from the shared right edge (a row with fewer cells
    aligns its last time at the right edge).  Each column is:
    [times right-aligned][chip_gap][chip sub-area, only when the
    column shows any delay; chips left-aligned within it].

    Args:
        row_cells: Per-row time cell dicts.
        times_right: Shared right edge x in px.
        time_font: PIL font for time text measurement.
        chip_font: PIL font for chip text measurement.
        chip_gap: Gap between time texts and the chip sub-area in
            px.
        col_gap: Gap between columns in px.
        delay_style: ``"all"``, ``"first"`` or ``"none"``.

    Returns:
        ``(col_time_right, col_chip_x, times_w, num_cols,
        any_cells)``: per-column right edge of the time texts,
        per-column left edge of the chip sub-area (0 = no chips),
        total times width, column count and whether any cell
        exists.
    """

    def _chip_w(delay: int) -> int:
        return round(chip_font.getlength(_delay_text(delay))) + 4

    def _cell_chip(delay: int, j: int) -> bool:
        # Chip is shown when the policy asks for it and the
        # departure is actually delayed; "first" restricts it to
        # the next departure (first cell) of the row.
        if delay <= 0 or delay_style == "none":
            return False
        return delay_style == "all" or j == 0

    num_cols = max((len(cells) for cells in row_cells), default=0)
    # Cells grouped per column as (j, cell) pairs, j = per-row
    # cell index.
    col_cells: list[list[tuple[int, dict]]] = [[] for _ in range(num_cols)]
    for cells in row_cells:
        n_cells = len(cells)
        for j, cell in enumerate(cells):
            col_cells[j + (num_cols - n_cells)].append((j, cell))

    # Measure and position the columns from the shared right edge
    # leftward.
    col_time_right: list[int] = []
    col_chip_x: list[int] = []
    col_right = times_right
    for cells_in_col in reversed(col_cells):
        chip_area = 0
        time_max = 0
        for j, cell in cells_in_col:
            delay = int(str(cell["delay"]))
            time_max = max(
                time_max,
                round(time_font.getlength(str(cell["display"]))),
            )
            if _cell_chip(delay, j):
                chip_area = max(chip_area, _chip_w(delay))
        if chip_area:
            chip_x = col_right - chip_area
            col_time_right.append(chip_x - chip_gap)
            col_chip_x.append(chip_x)
        else:
            col_time_right.append(col_right)
            col_chip_x.append(0)
        col_right -= time_max + chip_area + col_gap
    col_time_right.reverse()
    col_chip_x.reverse()
    any_cells = num_cols > 0
    times_w = times_right - col_right - col_gap if any_cells else 0
    return col_time_right, col_chip_x, times_w, num_cols, any_cells


def _build_departures_context(
    widget: DeparturesWidget,
    config: DisplayConfig,
) -> dict[str, object]:
    """Build Jinja2 template context for the departures widget.

    Renders one row per departure sensor: the entity icon, the line
    name (badge or bold text), the destination of the next upcoming
    departure (``head_sign``, falling back to the entity's
    ``direction`` attribute), an optional alert icon, and the next
    departure times.  A ``list_header`` above the rows is optional.

    Args:
        widget: Widget config dict.  Recognised keys:
            ``entities`` (one sensor per row, in display order),
            ``list_header``, ``header_icon``,
            ``head_sign_strip_prefix``,
            ``time_format`` (``"absolute"``/``"relative"``/
            ``"auto"``), ``max_times``, ``min_minutes``,
            ``delay_style`` (``"all"``/``"first"``/``"none"``),
            ``alert_style`` (``"triangle"``/``"icon"``/
            ``"none"``), ``line_style`` (``"badge"``/``"text"``),
            ``row_font_scale``, ``hide_icon``, ``icon``,
            ``icon_style``, ``card_style``, ``x``, ``w``, ``h``.
        config: Display config with ``states``, ``display_levels``,
            and ``font_scale``.

    Returns:
        Template context dict consumed by ``departures.svg.j2``.
        Returns ``{"w": …, "h": …, "has_rows": False}`` when no
        entities are configured (the widget renders nothing).
    """
    from ..render import (
        _compute_metrics,
        _font_weight_svg,
        _load_font,
    )
    from .graph.geometry import _truncate_to_width

    x = widget.get("x", PADDING)
    svg_w = _widget_dim(widget, "w", config["width"] - x)

    empty_ctx: dict[str, object] = {
        "w": svg_w,
        "h": _widget_dim(widget, "h", 56),
        "has_rows": False,
        **_color_context(),
    }

    entity_ids = [str(e) for e in widget.get("entities") or []]
    if not entity_ids:
        return empty_ctx

    card_style = widget.get("card_style", DEFAULT_CARD_STYLE)
    display_levels = config.get("display_levels", 16)
    font_scale: float = config.get("font_scale", 1.0)
    max_row_h = _max_row_height(widget, config)
    hide_icon = bool(widget.get("hide_icon", False))
    time_format = str(widget.get("time_format", DEFAULT_TIME_FORMAT))
    max_times = int(widget.get("max_times", DEFAULT_MAX_TIMES))
    min_minutes = int(widget.get("min_minutes", DEFAULT_MIN_MINUTES))
    # Delay chip display policy: "all" (every delayed departure),
    # "first" (only the next departure of each row) or "none".
    delay_style = _normalize_delay_style(
        str(widget.get("delay_style", DEFAULT_DELAY_STYLE))
    )
    line_style = str(widget.get("line_style", DEFAULT_LINE_STYLE))
    alert_style = _resolve_alert_style(widget)
    strip_prefix = str(widget.get("head_sign_strip_prefix", ""))
    header = str(widget.get("list_header") or "")
    header_icon = str(widget.get("header_icon", DEFAULT_HEADER_ICON))

    now = _now()

    raw_rows, row_cells, row_sources = _collect_rows(
        config,
        entity_ids,
        now,
        time_format,
        max_times,
        min_minutes,
        strip_prefix,
    )

    num_display_rows = len(raw_rows) + (1 if header else 0)
    if num_display_rows < 1:
        return empty_ctx

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

    times_right = svg_w - r_inset - rpad

    # Widget-level font scale on top of the metrics-derived
    # defaults (the display-level font_scale still multiplies on
    # top of this inside resolve_font).
    row_font_scale = float(
        widget.get("row_font_scale", DEFAULT_ROW_FONT_SCALE)
    )
    font_px_base = round(m.font_primary * row_font_scale)

    fonts = _resolve_fonts(widget, m, font_scale, font_px_base)
    header_font_sz = fonts.header_font_sz
    header_weight = fonts.header_weight
    line_font_sz = fonts.line_font_sz
    line_weight = fonts.line_weight
    dest_font_sz = fonts.dest_font_sz
    dest_weight = fonts.dest_weight
    time_font_sz = fonts.time_font_sz
    time_weight = fonts.time_weight

    def _measured_font(size: int, weight: FontWeight):
        return _load_font(
            int(size),
            medium=weight == FontWeight.MEDIUM,
            bold=weight == FontWeight.BOLD,
        )

    time_font = _measured_font(time_font_sz, time_weight)
    line_font = _measured_font(line_font_sz, line_weight)

    # Departure time display text: the chip carries the delay
    # separately, so the displayed time is just the formatted
    # estimate.
    for cells in row_cells:
        for cell in cells:
            cell["display"] = str(cell["text"])

    # Delay chip geometry: a small bold "+N" chip, drawn
    # left-aligned in a per-column chip sub-area, vertically
    # centered with the time text.  Chip height equals the chip
    # font size (works for digits and the "h" ascender alike).
    chip_gap = 2
    chip_font_sz = m.font_secondary
    chip_h = chip_font_sz
    chip_font = _measured_font(chip_font_sz, FontWeight.BOLD)

    def _chip_w(delay: int) -> int:
        return round(chip_font.getlength(_delay_text(delay))) + 4

    def _cell_chip(delay: int, j: int) -> bool:
        # Chip is shown when the policy asks for it and the
        # departure is actually delayed; "first" restricts it to
        # the next departure (first cell) of the row.
        if delay <= 0 or delay_style == "none":
            return False
        return delay_style == "all" or j == 0

    # Departure time columns, laid out left to right in departure
    # order and aligned from the shared right edge (a row with
    # fewer cells aligns its last time at the right edge).  Each
    # column is: [chip sub-area, only when the column shows any
    # delay, chips left-aligned][chip_gap][times right-aligned].
    # The gap between columns scales with the time font size.
    col_gap = round(time_font_sz * DEPARTURES_COLUMN_GAP_FACTOR)
    col_time_right, col_chip_x, times_w, num_cols, any_cells = _column_layout(
        row_cells,
        times_right,
        time_font,
        chip_font,
        chip_gap,
        col_gap,
        delay_style,
    )

    # Line badge chips: variable width per line name, but all
    # badges are centered within one shared badge column, so the
    # destinations after them still start at the same x.
    badge_texts: list[str] = []
    if line_style == "badge":
        badge_texts.extend(
            _truncate_to_width(str(raw["line"]), line_font, m.icon_dia * 2)
            for raw in raw_rows
        )
    badge_col_w = max(
        (round(line_font.getlength(text)) + m.padding for text in badge_texts),
        default=0,
    )

    # Text-mode line column: the widest line name over all rows,
    # so destinations start at the same x like in badge mode.
    line_col_w = 0
    if line_style != "badge":
        line_col_w = max(
            (round(line_font.getlength(str(raw["line"]))) for raw in raw_rows),
            default=0,
        )

    # Delay chip drawing helper: chips sit left-aligned in the
    # column's chip sub-area, vertically centered with the time
    # text.

    def _resolve_row_icon(
        attrs: dict,
        entity_id: str,
        alert: bool,
    ) -> tuple[str, bool, bool, int]:
        """Resolve the row icon with optional alert-variant swap.

        Args:
            attrs: Entity attributes (icon source).
            entity_id: Entity ID for icon resolution.
            alert: Whether any shown departure carries alerts.

        Returns:
            ``(icon_svg, icon_outline, icon_no_circle,
            icon_inner_sz)``.
        """
        domain = entity_id.split(".")[0] if entity_id else ""
        # Default to circle-free glyphs (icon_style "none")
        # unless the config asks for a circle.
        outline, no_circle = _resolve_icon_style(
            widget.get("icon_style", "none"),
            display_levels=display_levels,
        )
        # Without a circle the glyph is scaled to the full icon
        # diameter so it appears the same size as with a circle.
        inner_sz = m.icon_dia if no_circle else m.icon_inner
        if alert:
            swap = _alert_icon_swap(
                widget,
                attrs,
                entity_id,
                alert,
                alert_style,
                hide_icon,
                inner_sz,
            )
            if swap:
                return swap, outline, no_circle, inner_sz
        icon_svg, _letter = _resolve_icon_svg(
            widget.get("icon"),
            attrs,
            "",
            domain,
            inner_sz,
            entity_id=entity_id,
        )
        return icon_svg, outline, no_circle, inner_sz

    def _delay_badge(delay: int, chip_x: int, row_top: float) -> dict:
        text = _delay_text(delay)
        w_px = _chip_w(delay)
        # Symmetric, vertically centered with the time text (both
        # on the row center).
        y = row_top + row_h // 2 - chip_h // 2
        return {
            "text": text,
            "x": chip_x,
            "y": y,
            "w": w_px,
            "h": chip_h,
            "text_x": chip_x + w_px // 2,
            "text_y": row_top + row_h // 2,
            "font_sz": chip_font_sz,
        }

    def _cell_contexts(
        cells: list[dict[str, object]],
        row_top: int,
    ) -> list[dict[str, object]]:
        """Compute per-cell positions in the pre-laid-out columns:
        times right-aligned at the column's time edge, chips
        left-aligned in the chip sub-area to their right."""
        ctxs: list[dict[str, object]] = []
        n_cells = len(cells)
        for j, cell in enumerate(cells):
            col = j + (num_cols - n_cells)
            delay = int(str(cell["delay"]))
            chip = _cell_chip(delay, j)
            ctxs.append(
                {
                    "text": cell["display"],
                    "x": col_time_right[col],
                    "delay": delay,
                    "badge": (
                        _delay_badge(delay, col_chip_x[col], row_top)
                        if chip
                        else None
                    ),
                }
            )
        return ctxs

    icon_stroke_w = _icon_stroke_width(m.border, display_levels)
    divider_stroke_w = _divider_stroke_width(widget)
    divider_y_off = (divider_stroke_w % 2) / 2

    # Second pass: per-row geometry and icons (metrics are known
    # now).
    rows: list[dict[str, object]] = []
    row_idx = 0

    if header:
        rows.append(
            _header_row_context(
                header,
                header_font_sz,
                header_icon,
                row_h,
                svg_w,
                r_inset,
                rpad,
                x_off,
                lpad,
                m.icon_dia,
            )
        )
        row_idx += 1

    for row_i, (raw, cells, (entity_id, attrs)) in enumerate(
        zip(raw_rows, row_cells, row_sources, strict=True)
    ):
        row_top = row_idx * row_h
        icon_svg, icon_outline, icon_no_circle, icon_inner_sz = (
            _resolve_row_icon(attrs, entity_id, bool(raw["alert"]))
        )

        tx = x_off + lpad + (0 if hide_icon else m.icon_dia + m.inner_gap)

        # Line badge chip or bold text; either way the destination
        # starts after it.  The chip keeps its text-fitting width
        # but is centered within the shared badge column so all
        # destinations align.
        badge: dict[str, object] | None = None
        dest_x: float = tx
        if line_style == "badge" and raw["line"]:
            badge_text = badge_texts[row_i]
            badge_w_i = round(line_font.getlength(badge_text)) + m.padding
            badge_h = line_font_sz + max(2, round(row_h * 0.08))
            badge_x = tx + (badge_col_w - badge_w_i) // 2
            badge_y = row_top + (row_h - badge_h) // 2
            badge = {
                "text": badge_text,
                "x": badge_x,
                "y": badge_y,
                "w": badge_w_i,
                "h": badge_h,
                "text_x": badge_x + badge_w_i // 2,
                "text_y": row_top + row_h // 2,
            }
            dest_x = tx + badge_col_w + m.inner_gap
        else:
            dest_x = tx + line_col_w + m.inner_gap

        # Alert handling: "triangle" draws the gray marker between
        # destination and times; "icon" swaps the row icon for its
        # alert variant (handled in _resolve_row_icon); "none"
        # draws nothing.
        alert_sz = dest_font_sz + 2
        alert_w, alert_triangle = _alert_triangle_ctx(
            bool(raw["alert"]),
            alert_style,
            alert_sz,
            m.inner_gap,
        )

        times_left = times_right - (times_w if any_cells else 0) - alert_w
        dest_max = times_left - dest_x - m.inner_gap

        alert_x = times_left - alert_sz if alert_triangle else 0
        alert_y = row_top + row_h // 2 - alert_sz // 2 if alert_triangle else 0

        cell_ctxs = _cell_contexts(cells, row_top)

        row_ctx: dict[str, object] = {
            "y": row_top,
            "header": False,
            "line": raw["line"],
            "line_x": tx + line_col_w // 2 if badge is None else 0,
            "dest": _truncate_to_width(
                str(raw["dest"]),
                _measured_font(dest_font_sz, dest_weight),
                dest_max,
            ),
            "dest_x": dest_x,
            "alert": bool(alert_triangle),
            "alert_icon": alert_triangle,
            "alert_x": alert_x,
            "alert_y": alert_y,
            "line_badge": badge,
            "cells": cell_ctxs,
            "icon_svg": icon_svg,
            "icon_outline": icon_outline,
            "icon_no_circle": icon_no_circle or hide_icon,
            "icon_inner_sz": icon_inner_sz,
        }
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
        "line_font_sz": line_font_sz,
        "line_weight": _font_weight_svg(line_weight),
        "dest_font_sz": dest_font_sz,
        "dest_weight": _font_weight_svg(dest_weight),
        "time_font_sz": time_font_sz,
        "time_weight": _font_weight_svg(time_weight),
        "delay_style": delay_style,
        "line_style": line_style,
        "alert_style": alert_style,
    }
