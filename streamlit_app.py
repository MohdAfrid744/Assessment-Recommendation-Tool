"""
streamlit_app.py — Self-Contained Streamlit App for Streamlit Cloud Deployment

This app calls the agent logic directly (not via HTTP), so it works on
Streamlit Cloud without needing a separate FastAPI server.

Environment variables are loaded from Streamlit Secrets (st.secrets) when
running on Streamlit Cloud, and from a local .env file when running locally.
"""

import os
import sys
import time
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Page Config — MUST be the very first Streamlit command
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Assessment Recommendation Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Bootstrap: inject Streamlit secrets into os.environ ──────────────────────
# Only access st.secrets if secrets.toml actually exists (avoids Streamlit's
# built-in "No secrets found" UI warning when running locally with .env).
import pathlib
_secrets_paths = [
    pathlib.Path.home() / ".streamlit" / "secrets.toml",
    pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml",
]
if any(p.exists() for p in _secrets_paths):
    try:
        for key, value in st.secrets.items():
            if isinstance(value, str):
                os.environ.setdefault(key, value)
    except Exception:
        pass
# Local dev: keys are loaded from .env by agent.py via python-dotenv

# ── Add project root to sys.path so app.* imports work ───────────────────────
sys.path.insert(0, os.path.dirname(__file__))

# ── Now safe to import agent (it calls os.getenv internally) ─────────────────
from app import agent
from app.schemas import Message

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS — Premium Dark Theme
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Dark gradient background */
.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    min-height: 100vh;
}

/* Main header */
.main-header {
    background: linear-gradient(90deg, #6c63ff, #a855f7, #ec4899);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-size: 2.4rem;
    font-weight: 700;
    letter-spacing: -0.5px;
    margin-bottom: 0.2rem;
}

.sub-header {
    color: #94a3b8;
    font-size: 1rem;
    font-weight: 400;
    margin-bottom: 1.5rem;
}

/* Chat messages */
.stChatMessage {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 16px !important;
    backdrop-filter: blur(12px);
    margin-bottom: 0.75rem !important;
}

/* User message distinct style */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: rgba(108, 99, 255, 0.12) !important;
    border-color: rgba(108, 99, 255, 0.25) !important;
}

/* Recommendation card */
.rec-card {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(108,99,255,0.3);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.2s ease;
}
.rec-card:hover {
    border-color: rgba(168,85,247,0.6);
}
.rec-card h4 {
    color: #c4b5fd;
    margin: 0 0 0.4rem 0;
    font-size: 1rem;
    font-weight: 600;
}
.rec-card .badge {
    display: inline-block;
    background: rgba(108,99,255,0.25);
    color: #a5b4fc;
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 0.75rem;
    font-weight: 500;
    margin-right: 6px;
    margin-bottom: 4px;
}
.rec-card .reason {
    color: #94a3b8;
    font-size: 0.875rem;
    margin-top: 0.5rem;
    line-height: 1.5;
}
.rec-card a {
    color: #818cf8;
    text-decoration: none;
    font-size: 0.875rem;
    font-weight: 500;
}
.rec-card a:hover { color: #a5b4fc; }

/* Sidebar styling */
[data-testid="stSidebar"] {
    background: rgba(15, 12, 41, 0.85) !important;
    border-right: 1px solid rgba(255,255,255,0.07) !important;
}
[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}

/* Input box */
[data-testid="stChatInput"] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(108,99,255,0.4) !important;
    border-radius: 999px !important;
    color: white !important;
}

/* Turn counter badge */
.turn-badge {
    background: rgba(168,85,247,0.2);
    border: 1px solid rgba(168,85,247,0.4);
    border-radius: 999px;
    padding: 4px 14px;
    font-size: 0.8rem;
    color: #c4b5fd;
    display: inline-block;
    margin-bottom: 1rem;
}

/* Status pills */
.pill-green {
    background: rgba(16,185,129,0.15);
    border: 1px solid rgba(16,185,129,0.4);
    border-radius: 999px;
    padding: 3px 12px;
    color: #6ee7b7;
    font-size: 0.78rem;
    font-weight: 500;
}
.pill-red {
    background: rgba(239,68,68,0.15);
    border: 1px solid rgba(239,68,68,0.4);
    border-radius: 999px;
    padding: 3px 12px;
    color: #fca5a5;
    font-size: 0.78rem;
    font-weight: 500;
}

/* Expander overrides */
[data-testid="stExpander"] {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 12px !important;
}

/* Divider */
hr { border-color: rgba(255,255,255,0.08) !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(108,99,255,0.4); border-radius: 3px; }

/* Quick Start template buttons — styled as cards */
div[data-testid="stHorizontalBlock"] button {
    background: rgba(108,99,255,0.10) !important;
    border: 1px solid rgba(108,99,255,0.28) !important;
    border-radius: 14px !important;
    padding: 1.1rem 0.5rem !important;
    height: auto !important;
    min-height: 100px !important;
    color: #c4b5fd !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    line-height: 1.5 !important;
    white-space: pre-line !important;
    transition: background 0.18s, border-color 0.18s, transform 0.15s !important;
    box-shadow: none !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.25rem !important;
}

div[data-testid="stHorizontalBlock"] button * {
    white-space: pre-line !important;
    text-align: center !important;
}

div[data-testid="stHorizontalBlock"] button:hover {
    background: rgba(108,99,255,0.22) !important;
    border-color: rgba(168,85,247,0.65) !important;
    transform: translateY(-2px) !important;
    color: #e9d5ff !important;
}

</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: streaming word-by-word writer
# ─────────────────────────────────────────────────────────────────────────────
def stream_data(text: str):
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.025)


def render_recommendations(recs: list):
    """Render recommendation cards with rich formatting."""
    if not recs:
        return
    st.markdown("---")
    st.markdown("#### 🎯 Recommended Assessments")
    for i, r in enumerate(recs, 1):
        name = r.get("name", "Unknown")
        url = r.get("url", "")
        test_type = r.get("test_type", "")
        job_levels = r.get("job_levels") or []
        languages = r.get("languages") or []
        reason = r.get("reason", "")

        badges_html = ""
        if test_type:
            badges_html += f'<span class="badge">🏷 {test_type}</span>'
        for lvl in (job_levels if isinstance(job_levels, list) else []):
            badges_html += f'<span class="badge">👤 {lvl}</span>'
        if isinstance(languages, list) and languages:
            badges_html += f'<span class="badge">🌐 {len(languages)} lang</span>'

        url_html = f'<a href="{url}" target="_blank">🔗 View Assessment →</a>' if url else ""

        st.markdown(f"""
        <div class="rec-card">
            <h4>{i}. {name}</h4>
            {badges_html}
            <div class="reason">{reason}</div>
            <div style="margin-top:0.6rem">{url_html}</div>
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# API key validation
# ─────────────────────────────────────────────────────────────────────────────
gemini_key = os.environ.get("GEMINI_API_KEY", "")
groq_key = os.environ.get("GROQ_API_KEY", "")

if not gemini_key and not groq_key:
    st.error("⚠️ **No API keys configured.** Please add `GEMINI_API_KEY` (and optionally `GROQ_API_KEY`) to your Streamlit Secrets or `.env` file.")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Session State
# ─────────────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_recs" not in st.session_state:
    st.session_state.last_recs = []
if "conversation_ended" not in st.session_state:
    st.session_state.conversation_ended = False


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 Assessment Recommendation Tool")
    st.markdown("<hr/>", unsafe_allow_html=True)

    # Status indicators
    st.markdown("**API Status**")
    col1, col2 = st.columns(2)
    with col1:
        label = "● Gemini" if gemini_key else "✕ Gemini"
        cls = "pill-green" if gemini_key else "pill-red"
        st.markdown(f'<span class="{cls}">{label}</span>', unsafe_allow_html=True)
    with col2:
        label = "● Groq" if groq_key else "✕ Groq"
        cls = "pill-green" if groq_key else "pill-red"
        st.markdown(f'<span class="{cls}">{label}</span>', unsafe_allow_html=True)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # Conversation turn counter
    turns = len(st.session_state.messages)
    max_turns = 8
    st.markdown(f'<div class="turn-badge">💬 Turn {turns // 2} of {max_turns // 2}</div>', unsafe_allow_html=True)
    st.progress(min(turns / max_turns, 1.0))

    st.markdown("<hr/>", unsafe_allow_html=True)

    # Stateless payload inspector
    with st.expander("🔍 Stateless Payload Inspector", expanded=False):
        st.caption("Every request sends the full conversation history.")
        st.json({"messages": st.session_state.messages}, expanded=False)

    # Last API response
    if st.session_state.last_recs:
        with st.expander("📦 Last Recommendations (Raw)", expanded=False):
            recs_data = []
            for r in st.session_state.last_recs:
                if hasattr(r, "dict"):
                    recs_data.append(r.dict())
                elif hasattr(r, "model_dump"):
                    recs_data.append(r.model_dump())
                else:
                    recs_data.append(r)
            st.json(recs_data)

    st.markdown("<hr/>", unsafe_allow_html=True)

    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_recs = []
        st.session_state.conversation_ended = False
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Main Area — Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="main-header">Assessment Recommendation Tool</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">AI-powered guidance to find the right assessment for any role — powered by Gemini & Groq</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Quick Start Templates — shown only on the welcome screen
# ─────────────────────────────────────────────────────────────────────────────
TEMPLATES = [
    {"icon": "☕", "label": "Java Developer",   "hint": "Mid-level backend",       "prompt": "I need to hire a mid-level Java developer for backend systems"},
    {"icon": "📞", "label": "Sales Rep",         "hint": "Entry-level retail",       "prompt": "Looking for entry-level sales representatives for our retail team"},
    {"icon": "👥", "label": "HR Manager",        "hint": "Senior talent acquisition", "prompt": "Hiring a senior HR manager to lead talent acquisition"},
    {"icon": "📊", "label": "Data Analyst",      "hint": "Junior-to-mid level",      "prompt": "We need a data analyst for a junior-to-mid level position"},
    {"icon": "📋", "label": "Project Manager",   "hint": "Senior delivery PM",       "prompt": "Looking for an experienced project manager for software delivery"},
    {"icon": "🐍", "label": "Python Developer",  "hint": "Senior IC engineer",       "prompt": "Hiring a senior Python developer for data engineering work"},
]

if not st.session_state.messages and not st.session_state.conversation_ended:
    st.markdown("**⚡ Quick Start — pick a role template:**")
    cols = st.columns(len(TEMPLATES))
    for col, tpl in zip(cols, TEMPLATES):
        with col:
            if st.button(
                f"{tpl['icon']}\n{tpl['label']}",
                key=f"main_tpl_{tpl['label']}",
                use_container_width=True,
                help=tpl["hint"],
            ):
                st.session_state._inject_prompt = tpl["prompt"]
                st.rerun()
    st.markdown("")
    st.info("👋 **Or type below:** Describe the role you're hiring for and I'll guide you to the best assessments.")

# ─────────────────────────────────────────────────────────────────────────────
# Render Conversation History
# ─────────────────────────────────────────────────────────────────────────────
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # Re-render the last assistant recommendations
        if msg["role"] == "assistant" and i == len(st.session_state.messages) - 1:
            render_recommendations(
                [r.model_dump() if hasattr(r, "model_dump") else (r.dict() if hasattr(r, "dict") else r)
                 for r in st.session_state.last_recs]
            )

if st.session_state.conversation_ended:
    st.success("✅ Conversation complete! Click **Clear Conversation** in the sidebar to start a new session.")


# ─────────────────────────────────────────────────────────────────────────────
# Handle template injection (from main page buttons)
# ─────────────────────────────────────────────────────────────────────────────
injected = getattr(st.session_state, "_inject_prompt", None)
if injected:
    del st.session_state._inject_prompt
    user_input = injected
else:
    user_input = None


# ─────────────────────────────────────────────────────────────────────────────
# Chat Input
# ─────────────────────────────────────────────────────────────────────────────
if not st.session_state.conversation_ended:
    chat_input = st.chat_input("Describe the role you're hiring for…", key="chat_input")
    if chat_input:
        user_input = chat_input

if user_input:
    # Append user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Build Message objects for the agent
    message_objs = [Message(role=m["role"], content=m["content"]) for m in st.session_state.messages]

    # Call agent directly (no HTTP)
    with st.chat_message("assistant"):
        with st.spinner("🤔 Consulting the assessment catalog…"):
            try:
                reply, recs, end_of_conversation = agent.respond(message_objs)
            except Exception as e:
                reply = f"⚠️ An error occurred: `{e}`\n\nPlease check your API keys in Streamlit Secrets."
                recs = []
                end_of_conversation = False

        # Stream the reply
        st.write_stream(stream_data(reply))

        # Render recommendation cards
        render_recommendations(
            [r.model_dump() if hasattr(r, "model_dump") else (r.dict() if hasattr(r, "dict") else r)
             for r in recs]
        )

        if end_of_conversation:
            st.success("✅ The agent has finalised its recommendations. You may start a new session.")

    # Update session state
    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.session_state.last_recs = recs
    st.session_state.conversation_ended = end_of_conversation
    st.rerun()
