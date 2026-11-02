"""Google Search / Gemini center panel (replaces Brave Search + Ask Leo)."""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

# Keep module name for existing imports; panel is now Google Search / Gemini.
GOOGLE_SEARCH_HTML = """
<html>
<head>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #ffffff;
            margin: 0;
        }
        .search-container {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            flex-direction: column;
            gap: 20px;
        }
        .search-box {
            width: 500px;
            max-width: 90vw;
            padding: 12px 16px;
            font-size: 16px;
            border: 2px solid #ddd;
            border-radius: 24px;
        }
        .search-box:focus { outline: none; border-color: #1a73e8; }
        .btn-row {
            display: flex;
            gap: 12px;
            align-items: center;
        }
        .search-btn {
            padding: 10px 30px;
            background: #1a73e8;
            color: white;
            border: none;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
        }
        .search-btn:hover { background: #1765cc; }
        .gemini-btn {
            padding: 10px 30px;
            background: #8e44ad;
            color: white;
            border: none;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
        }
        .gemini-btn:hover { background: #7d3c98; }
        .hint {
            color: #666;
            font-size: 12px;
            max-width: 480px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="search-container">
        <h1>Google Search</h1>
        <input type="text" class="search-box" id="searchInput" placeholder="Search...">
        <div class="btn-row">
            <button class="search-btn" onclick="search()">Search</button>
            <button class="gemini-btn" onclick="askGemini()">Gemini</button>
        </div>
        <p class="hint">Search opens Google. Gemini opens the Gemini web app (sign-in uses this WebEngine profile).</p>
    </div>
    <script>
        function search() {
            const query = document.getElementById('searchInput').value.trim();
            if (query) {
                window.location.href = 'https://www.google.com/search?q=' + encodeURIComponent(query);
            }
        }
        function askGemini() {
            // Gemini app has no stable ?q= prefill; open the app after optional Google search AI Mode.
            const query = document.getElementById('searchInput').value.trim();
            if (query) {
                window.location.href = 'https://www.google.com/search?q=' + encodeURIComponent(query) + '&udm=50';
            } else {
                window.location.href = 'https://gemini.google.com/app';
            }
        }
        document.getElementById('searchInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') search();
        });
    </script>
</body>
</html>
"""

# Back-compat alias for any leftover references.
BRAVE_SEARCH_HTML = GOOGLE_SEARCH_HTML


def build_brave_search_panel(theme: Optional[Dict[str, str]] = None) -> QWidget:
    """Center panel with Google Search + Gemini (QWebEngineView when available)."""
    del theme  # HTML is fixed light landing page
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        view.setHtml(GOOGLE_SEARCH_HTML)
        lay.addWidget(view)
        wrap._web_view = view  # type: ignore[attr-defined]
    except Exception as e:
        err = QLabel(
            f"Google Search needs Qt WebEngine.\n{e}\n\n"
            "Windows (DLL load / procedure not found):\n"
            "  Close all Spock windows, then either re-run Phase B\n"
            "  or: .venv\\Scripts\\python.exe -m pip install "
            "\"PyQt6>=6.6,<6.12\" \"PyQt6-WebEngine>=6.6,<6.12\"\n"
            "  (PyQt6 6.12+ breaks WebEngine until Riverbank ships a match.)\n\n"
            "Ubuntu/WSL:\n"
            "  sudo apt install -y libnspr4 libnss3\n"
            "  .venv/bin/pip install \"PyQt6-WebEngine>=6.6,<6.12\"\n\n"
            "Or open https://www.google.com/ / https://gemini.google.com/ in a browser."
        )
        err.setWordWrap(True)
        lay.addWidget(err)
    return wrap


# Preferred name going forward.
build_google_search_panel = build_brave_search_panel
