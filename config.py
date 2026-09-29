import os
import sys
from pathlib import Path

# Paths
BASE_DIR = Path("/root/YT_JackVsAI")
REPO_DIR = BASE_DIR
CATALOG_FILE = BASE_DIR / "catalog.json"
STATE_FILE = BASE_DIR / "state.json"
WORK_DIR = Path("/tmp/yt_jackvsai_work")
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
LOG_FILE = Path("/var/log/yt_jackvsai.log")

# Channel Information
CHANNEL_ID = "UCKBj5HPTd64zoQmkGNseKUw"
CHANNEL_NAME = "Jack Vs. AI"
CHANNEL_HANDLE = "@JackVsAI"
CHANNEL_URL = "https://www.youtube.com/@JackVsAI"
RSS_FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
CHANNEL_DOMAIN = "Intelligence Artificielle, Vid?os IA, VFX, Animation 3D, Cin?ma IA, Seedance, Kling, Midjourney, Wan, Nano Banana, Workflows Cr?atifs"

# Models
GEMINI_MODEL = "gemini-3.5-flash-lite"
WHISPER_MODEL = "large-v3-turbo"
MODEL_SIGNATURE = f"whisper-v3-large-turbo+{GEMINI_MODEL}"

# API Keys & Network
GEMINI_KEYS_FILE = Path("/root/yt_batch_2026-09-25/.gemini_keys")
PROXY = "socks5://127.0.0.1:4001"
PLAYER_CLIENT = "android"

# Processing parameters
BATCH_SIZE = 5
MAX_BLOCK_DURATION = 32.0
MIN_BLOCK_DURATION = 18.0
FRAME_DIFF_THRESHOLD = 15.0
FRAME_MAX_WIDTH = 1280

# Ensure directories exist
BASE_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)

