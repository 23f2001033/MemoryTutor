"""Loads config from .env (local) or st.secrets (Streamlit Cloud) and wires
Gemini (via LiteLLM) into cognee's environment.

Must be imported before any other module imports `cognee`, because cognee
reads its LLM/embedding configuration from the environment at import/first use.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _get_secret(name: str, default: str = "") -> str:
    """.env / real env vars first (local + CLI scripts), falling back to
    Streamlit Cloud's st.secrets, which isn't exposed via os.environ."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st
    except ImportError:
        return default
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        return default
    except Exception as exc:
        # Anything other than "key not present" (e.g. malformed secrets.toml)
        # means secrets couldn't be read at all. Surface it loudly instead of
        # silently falling back to default and reporting a misleading
        # "not set" error later.
        raise RuntimeError(f"Could not read Streamlit secrets: {exc}") from exc


GEMINI_API_KEY = _get_secret("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    hint = ""
    try:
        import streamlit as st

        available = sorted(st.secrets.keys())
        hint = f" Streamlit secrets currently define these keys: {available or '(none)'}."
    except Exception:
        pass
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Copy .env.example to .env and add your "
        "Google AI Studio key (https://aistudio.google.com/apikey), or set it "
        "in Streamlit Cloud's app secrets (Manage app -> Settings -> Secrets), "
        "then reboot the app so the new secrets are picked up." + hint
    )

# NOTE: gemini-1.5-flash and text-embedding-004 (the models originally requested)
# have been fully retired by Google (confirmed via a live 404 from the Gemini API,
# not just a deprecation warning). Defaults below use gemini-flash-lite-latest:
# it has a much higher free-tier request quota than gemini-2.5-flash (which caps
# at ~20 requests/day on a free key) and, being a "-latest" alias, keeps tracking
# Google's current lite model instead of pointing at a fixed version that will
# eventually be retired too. Override via .env if you have a paid key and want
# gemini-2.5-flash's higher answer quality.
LLM_MODEL = _get_secret("LLM_MODEL", "gemini/gemini-flash-lite-latest")
EMBEDDING_MODEL = _get_secret("EMBEDDING_MODEL", "gemini/gemini-embedding-001")

os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ["LLM_MODEL"] = LLM_MODEL
os.environ["LLM_API_KEY"] = GEMINI_API_KEY

os.environ.setdefault("EMBEDDING_PROVIDER", "gemini")
os.environ["EMBEDDING_MODEL"] = EMBEDDING_MODEL
os.environ["EMBEDDING_API_KEY"] = GEMINI_API_KEY
os.environ.setdefault("EMBEDDING_DIMENSIONS", os.environ.get("EMBEDDING_DIMENSIONS", "3072"))

# Single-user local app: disable cognee's multi-tenant access control so
# add/cognify/search fall back to an auto-created default user with no auth setup.
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

NOTES_DATASET = "course_notes"
MEMORY_DATASET = "user_memory"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.path.join(PROJECT_ROOT, "uploads")
USER_MEMORY_PATH = os.path.join(PROJECT_ROOT, "user_memory.json")

os.makedirs(UPLOADS_DIR, exist_ok=True)

# By default cognee stores its databases inside its own package directory
# (site-packages/cognee/.cognee_system), which would wipe the "persistent"
# memory graph every time the venv is rebuilt. Pin storage to the project
# directory instead so it survives reinstalls.
os.environ.setdefault("DATA_ROOT_DIRECTORY", os.path.join(PROJECT_ROOT, ".data_storage"))
os.environ.setdefault("SYSTEM_ROOT_DIRECTORY", os.path.join(PROJECT_ROOT, ".cognee_system"))
