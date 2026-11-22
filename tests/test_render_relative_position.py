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

"""Tests for relative widget positioning (relative_to_x/y).

Uses ``frame`` widgets because their border stroke is drawn fully
inward from the declared widget bounds, making the rendered position
of each frame directly observable via border pixels.
"""

from __future__ import annotations

from typing import ClassVar

from tests.helpers import (
    assert_all_white,
    assert_has_dark_pixels,
    content_bbox,
    render_to_image,
)


def _frame(
    x: int = 0,
    y: int = 0,
    w: int = 100,
    h: int = 50,
    **extra: object,
) -> dict[str, object]:
    """Build a frame widget config with sensible defaults."""
    return {"type": "frame", "x": x, "y": y, "w": w, "h": h, **extra}


_HIDDEN_CONDITION: ClassVar[list[dict[str, str]]] = [
    {"condition": "state", "entity": "input_boolean.show", "state": "on"},
]


class TestRelativePositioning:
    """render_dashboard resolves relative_to_x/relative_to_y anchors."""

    def _config(self) -> dict[str, object]:
        """Build a minimal render config with an off toggle state."""
        return {
            "width": 400,
            "height": 300,
            "states": {"input_boolean.show": {"state": "off"}},
        }

    def test_row_chain_resolves_right_edges(self) -> None:
        # Three frames chained via relative_to_x render side by side
        # at x = 0, 100, 200.  Frame borders grow inward from the
        # declared bounds, so each frame's left border starts exactly
        # at the resolved x.
        widgets = [
            _frame(x=0, y=0, label="one"),
            _frame(x=0, y=0, label="two", relative_to_x="one"),
            _frame(x=0, y=0, label="three", relative_to_x="two"),
        ]
        img = render_to_image(widgets, self._config())
        # Left borders of the three frames.
        assert_has_dark_pixels(img, 0, 20, 4, 30)
        assert_has_dark_pixels(img, 99, 20, 104, 30)
        assert_has_dark_pixels(img, 199, 20, 204, 30)
        # The gaps between frames stay empty (frame interiors are
        # transparent; borders are 2 px inward from each edge).
        assert_all_white(img, 6, 20, 94, 30)
        assert_all_white(img, 106, 20, 194, 30)

    def test_column_chain_resolves_bottom_edges(self) -> None:
        # Two frames chained via relative_to_y render stacked at
        # y = 0 and y = 50.
        widgets = [
            _frame(x=0, y=0, label="one"),
            _frame(x=0, y=0, label="two", relative_to_y="one"),
        ]
        img = render_to_image(widgets, self._config())
        assert_has_dark_pixels(img, 20, 0, 80, 4)
        assert_has_dark_pixels(img, 20, 49, 80, 54)
        assert_all_white(img, 20, 6, 80, 44)

    def test_hidden_spacer_passes_origin_through(self) -> None:
        # A hidden widget between two visible ones must not add its
        # own offset to the chain: the visible follower positions
        # itself from the hidden widget's origin (the anchor edge),
        # not origin + offset.  With a 4 px offset on both the hidden
        # spacer and the follower, the total gap stays 4 px.
        widgets = [
            _frame(x=0, y=0, label="one"),
            # Hidden spacer: origin = 50, offset 4 must NOT count.
            _frame(
                x=0,
                y=4,
                label="spacer",
                relative_to_y="one",
                visibility=_HIDDEN_CONDITION,
            ),
            _frame(x=0, y=4, label="three", relative_to_y="spacer"),
        ]
        img = render_to_image(widgets, self._config())
        # The third frame's top border sits at y = 50 + 4 = 54; its
        # bottom border is at 50 + 4 + 50 - 2 = 102.
        assert_has_dark_pixels(img, 20, 53, 80, 57)
        assert_has_dark_pixels(img, 20, 101, 80, 105)
        # Nothing between the first frame's bottom border and the
        # third frame's top border (old semantics placed the border
        # at 58, which this region excludes).
        assert_all_white(img, 20, 59, 80, 100)

    def test_unknown_reference_falls_back_to_absolute(self) -> None:
        # A reference label that no previous widget declares cannot
        # resolve; the widget then positions itself absolutely.
        widgets = [_frame(x=10, y=0, relative_to_x="ghost")]
        img = render_to_image(widgets, self._config())
        assert_has_dark_pixels(img, 9, 20, 14, 30)
        assert_all_white(img, 0, 20, 8, 30)

    def test_hidden_widget_without_label_is_skipped(self) -> None:
        # A hidden widget without a label contributes no anchor and
        # simply does not render.
        widgets = [
            _frame(
                x=0,
                y=0,
                visibility=_HIDDEN_CONDITION,
            ),
        ]
        img = render_to_image(widgets, self._config())
        assert_all_white(img, 0, 0, img.width, img.height)

    def test_forward_reference_ignores_later_widgets(self) -> None:
        # References resolve against previously rendered widgets only;
        # a widget may not anchor to one that comes after it.
        widgets = [
            _frame(x=0, y=0, relative_to_x="later"),
            _frame(x=150, y=0, label="later"),
        ]
        img = render_to_image(widgets, self._config())
        # The first frame's reference is unresolvable (the label only
        # exists on a later widget), so it falls back to x = 0 while
        # the second frame renders at its absolute x = 150.
        assert_has_dark_pixels(img, 0, 20, 4, 30)
        assert_has_dark_pixels(img, 149, 20, 154, 30)
        assert_all_white(img, 106, 20, 144, 30)

    def test_content_bbox_matches_resolved_row_positions(self) -> None:
        # Cross-check the row chain via tight content bounding boxes:
        # each 100 px frame contributes border content only within
        # its own resolved column.
        widgets = [
            _frame(x=0, y=0, label="one"),
            _frame(x=0, y=0, label="two", relative_to_x="one"),
        ]
        img = render_to_image(widgets, self._config())
        first = content_bbox(img, 0, 0, 99, img.height)
        second = content_bbox(img, 100, 0, img.width, img.height)
        assert first is not None
        assert second is not None
        assert first[0] == 0
        assert second[0] == 100
