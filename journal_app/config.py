# journal_app/config.py

import os

# --- DeepSeek API ---
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-v4-flash"

# --- IEEE Xplore API ---
# Register at https://developer.ieee.org to get a free API key
IEEE_API_KEY = os.environ.get("IEEE_API_KEY", "")

# --- Browser takeover (connect to existing Chrome) ---
# Set to e.g. "127.0.0.1:9222" to reuse your normal Chrome.
# Start Chrome with: chrome.exe --remote-debugging-port=9222
BROWSER_ADDRESS = os.environ.get("BROWSER_ADDRESS", "")

# --- App Config ---
SECRET_KEY = os.environ.get("JOURNAL_APP_SECRET", "dev-secret-change-in-production")
DEBUG_MODE = os.environ.get("JOURNAL_APP_DEBUG", "false").lower() == "true"
DATABASE_PATH = os.environ.get(
    "JOURNAL_APP_DB",
    os.path.join(os.path.dirname(__file__), "journal_data.db"),
)
