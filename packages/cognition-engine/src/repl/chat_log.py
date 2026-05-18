"""Chat log with plain-text buffer for copy and selection."""

from __future__ import annotations

import re

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

    def start_stream_plain_merge(self) -> None:
        """Following write() chunks merge into the last plain_lines entry (streaming body)."""
        self._merge_stream_plain = True

    def end_stream_plain_merge(self) -> None:
        self._merge_stream_plain = False

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
