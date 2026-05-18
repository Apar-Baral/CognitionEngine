"""Cognition Engine REPL visual theme."""

CE_BRAND_MARKUP = """[bold #58a6ff]╭──────────────╮[/]
[bold #58a6ff]│[/] [bold white]COGNITION[/] [bold #58a6ff]│[/]
[bold #58a6ff]│[/] [bold #6cb6ff]ENGINE[/]    [bold #58a6ff]│[/]
[bold #58a6ff]╰──────────────╯[/]"""

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
}

#left-rail {
    width: 26;
    min-width: 24;
    max-width: 28;
    height: 1fr;
    background: #111820;
    border-right: solid #2d3a4f;
    scrollbar-background: #111820;
    scrollbar-color: #3d5a80;
    scrollbar-gutter: stable;
}

#left-rail-inner {
    width: 100%;
    height: auto;
    padding: 0 1;
}

#ce-brand {
    width: 100%;
    height: auto;
    min-height: 5;
    text-align: center;
    padding: 1 0;
    margin-bottom: 1;
    border: solid #3d5a80;
    background: #070d14;
    content-align: center middle;
}

.rail-section-title {
    color: #6cb6ff;
    text-style: bold;
    margin: 1 0 0 0;
    padding: 0 0;
}

#model-select {
    margin: 0 0 1 0;
    width: 100%;
    border: solid #3d5a80;
    background: #0d1520;
}

#model-select:focus {
    border: solid #6cb6ff;
}

#setup-panel {
    color: #adbac7;
    padding: 0 0 1 0;
    border-bottom: solid #2d3a4f;
    margin-bottom: 1;
}

#command-buttons {
    height: auto;
    margin: 0 0 1 0;
}

#command-buttons Button {
    width: 100%;
    margin-bottom: 1;
    background: #1c2430;
    border: solid #3d5a80;
    color: #e6edf3;
}

#command-buttons Button:hover {
    background: #253040;
    border: solid #6cb6ff;
}

#command-buttons Button.-primary {
    background: #1f3d5c;
    border: solid #6cb6ff;
    color: #ffffff;
    text-style: bold;
}

#command-buttons Button.-danger {
    background: #3d1f1f;
    border: solid #da3633;
    color: #ffdede;
}

#command-buttons Button.-danger:hover {
    background: #5c2525;
    border: solid #f85149;
}

#command-hints {
    color: #768390;
    padding: 0 0 1 0;
    border-top: solid #2d3a4f;
}

#chat-column {
    width: 1fr;
    min-width: 40;
}

#trace-rail {
    width: 34;
    min-width: 30;
    max-width: 38;
    height: 1fr;
    background: #080c10;
    border-left: solid #2d3a4f;
    padding: 0 1;
}

#trace-hint {
    height: auto;
    color: #768390;
    padding: 0 0 1 0;
    text-align: center;
}

#prompt-display {
    height: auto;
    min-height: 2;
    max-height: 6;
    padding: 1 2;
    margin-bottom: 1;
    background: #152238;
    border: tall #6cb6ff;
    color: #e6edf3;
}

#top-bar {
    height: 2;
    background: #131a24;
    border: solid #2d3a4f;
    padding: 0 2;
    content-align: left middle;
}

#token-bar {
    height: 2;
    min-height: 2;
    background: #131a24;
    border: solid #3d5a80;
    border-top: solid #2d3a4f;
    padding: 0 2;
    color: #e6edf3;
    content-align: left middle;
    margin: 0;
}

#tips-bar {
    height: 2;
    background: #0a0e14;
    border-top: solid #2d3a4f;
    padding: 0 1;
    color: #768390;
    text-style: italic;
}

#thinking-box {
    display: none;
    height: auto;
    min-height: 1;
    max-height: 12;
    border: solid #6cb6ff;
    background: #0d1520;
    margin: 1 0;
    padding: 0 1;
}

#thinking-box.visible {
    display: block;
}

#thinking-head {
    height: 1;
    min-height: 1;
}

#think-spinner {
    width: 3;
    min-width: 3;
    height: 1;
    content-align: center middle;
}

#chat-thinking {
    display: none;
}

#thinking-detail {
    width: 100%;
    height: auto;
    padding: 0 0 1 0;
    color: #6cb6ff;
}

#tracker-panel {
    height: auto;
    max-height: 3;
    display: none;
    background: #0d1520;
    border: solid #2d3a4f;
    padding: 0 2;
    margin-bottom: 1;
}

#activity-scroll {
    height: 1fr;
    border: solid #2d3a4f;
    background: #0a0e14;
    margin-bottom: 1;
    overflow-x: hidden;
}

#activity-log {
    padding: 0 1;
    width: 100%;
}

#chat-scroll {
    height: 1fr;
    border: solid #2d3a4f;
    background: #070b10;
    margin: 1 0 0 0;
    scrollbar-background: #070b10;
    scrollbar-color: #3d5a80;
}

#log {
    padding: 1 2;
}

#composer {
    height: auto;
    margin-top: 1;
    border-top: solid #2d3a4f;
    padding-top: 1;
}

#composer.-busy #input {
    opacity: 0.55;
}

#prompt-glyph {
    width: 3;
    content-align: center middle;
    color: #6cb6ff;
    text-style: bold;
}

#input {
    border: tall #3d5a80;
    background: #0d1520;
    padding: 0 1;
}

#input:focus {
    border: tall #6cb6ff;
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

#picker-search:focus {
    border: solid #6cb6ff;
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
    max-width: 90;
    background: #111820;
    border: solid #e3b341;
    padding: 1 2;
}

#perm-detail {
    margin: 1 0;
    color: #c9d1d9;
}

#perm-actions {
    height: auto;
    margin-top: 1;
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

#quit-actions {
    height: auto;
    margin-top: 1;
}

#quit-actions Button {
    margin-right: 1;
}
"""
