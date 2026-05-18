"""Cognition Engine REPL visual theme."""

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
    width: 34;
    min-width: 30;
    max-width: 38;
    background: #111820;
    border-right: solid #2d3a4f;
    padding: 0 1;
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

#command-hints {
    color: #768390;
    padding: 0 0 1 0;
    border-top: solid #2d3a4f;
}

#main-column {
    width: 1fr;
}

#top-bar {
    height: 3;
    background: linear-gradient(90deg, #111820 0%, #15202b 100%);
    border: solid #2d3a4f;
    padding: 0 2;
    content-align: left middle;
}

#chat-scroll {
    height: 1fr;
    border: solid #2d3a4f;
    background: #070b10;
    margin: 1 0 0 0;
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
"""
