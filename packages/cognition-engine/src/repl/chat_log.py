"""Chat log with plain-text buffer for copy and selection."""

from __future__ import annotations

import re

from textual.geometry import Size
from textual.widgets import RichLog

_MARKUP_RE = re.compile(r"\[/?[^\]]+\]")


def strip_markup(text: str) -> str:
    return _MARKUP_RE.sub("", text).replace("\\[", "[")


class ChatRichLog(RichLog):
    """RichLog that keeps plain text for clipboard and drag-select."""

    ALLOW_SELECT = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.plain_lines: list[str] = []
        self._merge_stream_plain: bool = False
        self._stream_frame_line_count: int = 0
        self._stream_frame_start_line: int | None = None
        self._stream_plain_index: int | None = None

    def start_stream_frame(self) -> None:
        """Following update_stream_frame() calls replace one visible live response block."""
        self._merge_stream_plain = False
        self._stream_frame_line_count = 0
        self._stream_frame_start_line = None
        self._stream_plain_index = len(self.plain_lines)
        self.plain_lines.append("")

    def end_stream_frame(self) -> None:
        self._merge_stream_plain = False
        self._stream_frame_line_count = 0
        self._stream_frame_start_line = None
        self._stream_plain_index = None

    def start_stream_plain_merge(self) -> None:
        self.start_stream_frame()

    def end_stream_plain_merge(self) -> None:
        self.end_stream_frame()

    def update_stream_frame(self, content: str, plain: str, *, scroll_end: bool = True) -> None:
        """Replace the visible streaming block without stacking one line per token."""
        if self._stream_frame_line_count and self._stream_frame_start_line is not None:
            start = self._stream_frame_start_line
            end = start + self._stream_frame_line_count
            del self.lines[start:end]
            self._line_cache.clear()
            self._stream_frame_line_count = 0
            self._stream_frame_start_line = None
            self.virtual_size = Size(self._widest_line_width, len(self.lines))
        if self._stream_plain_index is None:
            self._stream_plain_index = len(self.plain_lines)
            self.plain_lines.append("")
        self.plain_lines[self._stream_plain_index] = plain
        before = len(self.lines)
        RichLog.write(self, content, expand=True, scroll_end=scroll_end)
        self._stream_frame_start_line = before
        self._stream_frame_line_count = max(0, len(self.lines) - before)

    def write(self, content, *args, **kwargs):
        result = super().write(content, *args, **kwargs)
        if isinstance(content, str):
            p = strip_markup(content)
            if self._merge_stream_plain and self.plain_lines:
                self.plain_lines[-1] += p
            else:
                self.plain_lines.append(p)
        return result

    def clear(self):
        self.plain_lines.clear()
        self._merge_stream_plain = False
        self._stream_frame_line_count = 0
        self._stream_frame_start_line = None
        self._stream_plain_index = None
        return super().clear()

    def plain_text(self) -> str:
        return "\n".join(self.plain_lines)

    def get_selection(self, selection):  # type: ignore[no-untyped-def]
        text = self.plain_text()
        if not text:
            return None
        extracted = selection.extract(text)
        if extracted is None:
            return None
        return extracted, "\n"
