"""Cognition Engine REPL visual theme."""

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

#model-bar {
    height: auto;
    min-height: 4;
    max-height: 5;
    background: #161b22;
    border: solid #58a6ff;
    padding: 0 1;
    margin: 0 0 1 0;
}

#model-bar-label {
    width: 8;
    min-width: 8;
    color: #58a6ff;
    text-style: bold;
    content-align: left middle;
}

#model-current {
    width: 1fr;
    min-width: 12;
    color: #ffffff;
    text-style: bold;
    content-align: left middle;
    padding: 0 1;
}

#model-bar #model-select {
    width: 22;
    min-width: 18;
    max-width: 28;
    border: solid #6cb6ff;
    background: #0d1117;
    margin: 0 1 0 0;
}

#status-bar {
    height: 2;
    min-height: 2;
    background: #131a24;
    border: solid #2d3a4f;
    padding: 0 2;
    color: #adbac7;
    margin: 0 0 1 0;
}

#token-bar {
    height: 2;
    min-height: 2;
    background: #131a24;
    border: solid #3d5a80;
    padding: 0 2;
    color: #e6edf3;
    margin: 0;
}

#tips-bar {
    height: 2;
    min-height: 2;
    background: #0a0e14;
    border-top: solid #2d3a4f;
    padding: 0 1;
    color: #768390;
}

#task-list {
    height: auto;
    max-height: 8;
    padding: 0 1;
}

#thinking-box {
    display: none;
    height: auto;
    max-height: 10;
    border: solid #6cb6ff;
    background: #0d1520;
    margin: 0 0 1 0;
    padding: 0 1;
}

#thinking-box.visible {
    display: block;
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

#thinking-detail {
    height: auto;
    color: #6cb6ff;
}

#prompt-display {
    height: 1;
    min-height: 1;
    max-height: 2;
    padding: 0 2;
    background: #0d1520;
    border: solid #2d3a4f;
    color: #8b949e;
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
    max-height: 3;
    color: #768390;
    padding: 0 0 1 0;
}

#activity-scroll {
    height: 1fr;
    min-height: 6;
    border: solid #2d3a4f;
    background: #0a0e14;
    scrollbar-background: #0a0e14;
    scrollbar-color: #484f58 #0a0e14;
}

#activity-log {
    width: 100%;
    padding: 0 1;
}

#chat-scroll {
    height: 1fr;
    min-height: 8;
    border: solid #2d3a4f;
    background: #070b10;
    scrollbar-background: #070b10;
    scrollbar-color: #484f58 #070b10;
}

#log {
    padding: 1 2;
    width: 100%;
}

#composer {
    height: auto;
    min-height: 3;
    max-height: 4;
    border-top: solid #2d3a4f;
    padding: 1 0 0 0;
}

#composer.-busy #input {
    opacity: 0.55;
}

#prompt-glyph {
    width: 3;
    color: #6cb6ff;
    text-style: bold;
}

#input {
    width: 1fr;
    min-height: 1;
    border: solid #3d5a80;
    background: #0d1520;
}

#input:focus {
    border: solid #6cb6ff;
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
