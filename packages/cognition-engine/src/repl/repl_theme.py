"""Cognition Engine REPL visual theme."""

from textual.widgets import Static
from textual.containers import VerticalScroll


class ChromeStatic(Static):
    """Headers, hints, and rail labels — excluded from cross-pane mouse selection."""

    ALLOW_SELECT = False


class PaneScroll(VerticalScroll):
    """Scroll container — does not participate in text selection (child RichLog still can)."""

    ALLOW_SELECT = False


CE_BRAND_MARKUP = """[bold #58a6ff]COGNITION[/]
[bold white]ENGINE[/]"""

CE_APP_CSS = """
Screen {
    background: #0a0e14;
}

Header {
    background: #111820;
    color: #e6edf3;
    border-bottom: solid #2d3a4f;
    text-style: bold;
}

Footer {
    background: #111820;
    border-top: solid #2d3a4f;
}

#workspace {
    height: 1fr;
    width: 100%;
}

#left-rail {
    width: 28;
    min-width: 26;
    max-width: 32;
    height: 1fr;
    background: #0d1117;
    border-right: solid #30363d;
    scrollbar-background: #0d1117;
    scrollbar-color: #484f58 #0d1117;
}

#left-rail-inner {
    width: 100%;
    height: auto;
    padding: 1 1;
}

#sidebar-status {
    width: 100%;
    height: auto;
    padding: 1;
    margin-bottom: 1;
    border: solid #30363d;
    background: #161b22;
}

.rail-section-title {
    color: #58a6ff;
    text-style: bold;
    margin: 1 0 0 0;
    padding: 0;
}

#command-buttons {
    height: auto;
    margin: 0 0 1 0;
}

#command-buttons Button {
    width: 100%;
    height: 3;
    margin-bottom: 1;
    background: #21262d;
    border: solid #30363d;
    color: #e6edf3;
    padding: 0 1;
}

#command-buttons Button:hover {
    background: #30363d;
    border: solid #58a6ff;
}

#command-buttons Button.-primary {
    background: #1f3d5c;
    border: solid #58a6ff;
    color: #ffffff;
}

#command-buttons Button.-danger {
    background: #3d1f1f;
    border: solid #da3633;
}

#command-hints {
    color: #768390;
    padding: 1 0;
    border-top: solid #30363d;
    height: auto;
}

#chat-column {
    width: 1fr;
    min-width: 0;
    height: 1fr;
}

/* ── Area 1: single model + project header (no duplicate boxes) ── */
#header-strip {
    height: 3;
    min-height: 3;
    max-height: 3;
    background: #161b22;
    border: solid #388bfd;
    padding: 0 1;
    margin: 0 0 1 0;
}

#header-model-line {
    width: auto;
    min-width: 8;
    max-width: 32;
    color: #adbac7;
    content-align: left middle;
    text-align: left;
    text-overflow: ellipsis;
}

#header-strip #model-select {
    width: 1fr;
    min-width: 22;
    max-width: 100%;
    border: solid #388bfd;
    background: #0d1117;
    margin: 0 1;
    color: #ffffff;
}

#header-strip #model-select:focus {
    border: solid #79c0ff;
}

#header-meta {
    width: auto;
    min-width: 14;
    max-width: 50%;
    color: #adbac7;
    content-align: right middle;
    text-align: right;
    padding: 0 1;
}

/* ── Area 2: chat fills space; progress strip hidden until agent runs ── */
#chat-scroll {
    height: 1fr;
    min-height: 10;
    border: none;
    background: #070b10;
    scrollbar-background: #070b10;
    scrollbar-color: #484f58 #070b10;
    margin: 0;
}

#log {
    padding: 1 2;
    width: 100%;
}

#thinking-box {
    display: none;
    height: 0;
    min-height: 0;
    max-height: 0;
    overflow: hidden;
    border: none;
    margin: 0;
    padding: 0;
}

#thinking-box.visible {
    display: block;
    height: auto;
    min-height: 0;
    max-height: 9;
    overflow: hidden auto;
    border: solid #388bfd;
    background: #0d1117;
    margin: 0 0 1 0;
    padding: 0 1;
}

#thinking-head {
    height: 1;
}

#think-spinner {
    width: 3;
    min-width: 3;
    height: 1;
}

#chat-thinking {
    display: none;
}

#task-list {
    height: auto;
    max-height: 5;
    padding: 0;
}

#thinking-detail {
    height: auto;
    max-height: 3;
    color: #6cb6ff;
    padding: 0;
}

/* ── Area 3: slim prompt dock ── */
#composer-stack {
    height: auto;
    min-height: 3;
    max-height: 12;
}

#composer {
    height: 3;
    min-height: 3;
    max-height: 3;
    border-top: solid #30363d;
    background: #010409;
    padding: 0 1;
    margin: 0;
}

#composer.-busy {
    border-top: solid #e3b341;
}

#composer.-busy #input {
    opacity: 0.6;
}

#prompt-glyph {
    width: 2;
    min-width: 2;
    color: #58a6ff;
    text-style: bold;
    content-align: center middle;
}

#input {
    width: 1fr;
    height: 1;
    min-height: 1;
    max-height: 1;
    border: none;
    background: transparent;
    padding: 0 1;
    color: #e6edf3;
}

#input:focus {
    border: none;
    background: #0d1117;
}

#slash-suggest {
    height: auto;
    max-height: 6;
    padding: 0 2 0 4;
    color: #8b949e;
    background: #010409;
    border-top: solid #21262d;
}

#slash-suggest.hidden {
    display: none;
    height: 0;
    max-height: 0;
    padding: 0;
    border: none;
}

#trace-rail {
    width: 46;
    min-width: 40;
    max-width: 52;
    height: 1fr;
    background: #080c10;
    border-left: solid #30363d;
    padding: 0 1;
}

#trace-hint {
    height: auto;
    max-height: 2;
    color: #768390;
    padding: 0 0 1 0;
}

#activity-scroll {
    height: 1fr;
    min-height: 8;
    border: solid #2d3a4f;
    background: #0a0e14;
    scrollbar-background: #0a0e14;
    scrollbar-color: #484f58 #0a0e14;
}

#activity-log {
    width: 100%;
    padding: 0 1;
}

#log, #activity-log, #thinking-detail {
    text-style: none;
}

#tips-bar {
    height: 3;
    min-height: 3;
    max-height: 3;
    background: #0a0e14;
    border-top: solid #2d3a4f;
    padding: 0 1;
    color: #768390;
}

ModelPickerScreen {
    align: center middle;
}

#picker-frame {
    width: 92;
    max-width: 110;
    height: 85%;
    background: #111820;
    border: solid #6cb6ff;
    padding: 1 2;
}

#picker-search {
    margin-bottom: 1;
    border: solid #3d5a80;
    background: #0a0e14;
}

#picker-list {
    height: 1fr;
    border: solid #2d3a4f;
    background: #070b10;
}

#picker-footer {
    color: #768390;
    margin-top: 1;
}

.picker-item-current {
    color: #3fb950;
    text-style: bold;
}

AgentPermissionScreen {
    align: center middle;
}

#perm-frame {
    width: 72;
    background: #111820;
    border: solid #e3b341;
    padding: 1 2;
}

#perm-actions Button {
    margin-right: 1;
}

ConfirmQuitScreen {
    align: center middle;
}

#quit-frame {
    width: 56;
    background: #111820;
    border: solid #da3633;
    padding: 1 2;
}

#quit-actions Button {
    margin-right: 1;
}
"""
