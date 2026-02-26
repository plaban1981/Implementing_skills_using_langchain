"""
app.py

Streamlit UI for the LangChain Skills Agent.
Integrates three modes in one app:

  Tab 1 — 💬 Chat
      Standard skill-aware chat. Queries are routed to the best available skill
      and executed using the LangGraph pipeline.

  Tab 2 — 🛠️ Create Skill
      Describe a new skill in plain English. The app calls create_skill_programmatic()
      to generate SKILL.md + implementation script, write the folder to disk,
      register the @tool stub in skill_agent.py, and immediately make the skill
      available in the chat — no restart needed.

  Tab 3 — 📦 Skill Library
      Browse every loaded skill: name, description, SKILL.md preview, and
      the generated script.

Run with:
    streamlit run app.py
"""

import os
import sys
import time
import importlib
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="LangChain Skills Agent",
    page_icon="🧠",
    layout="wide",
)

# ── Lazy imports after path setup ─────────────────────────────────────────────
from skills_registry import get_registry
from skill_agent     import run_agent, reload_tools
from create_skill    import create_skill_programmatic


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _init_session():
    defaults = {
        "chat_messages":        [],   # [{role, content, skill, tools}]
        "skill_creation_log":   [],   # progress lines shown during creation
        "last_created_skill":   None, # name of most recently created skill
        "creation_result":      None, # full result dict from create_skill_programmatic
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_session()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("⚙️ Configuration")

    api_key = st.text_input(
        "Google API Key",
        value=os.environ.get("GOOGLE_API_KEY", ""),
        type="password",
        help="Get your key from https://aistudio.google.com/",
    )
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key

    st.divider()
    st.subheader("📦 Loaded Skills")

    registry = get_registry()
    if registry:
        for name, skill in registry.items():
            badge = "🆕 " if name == st.session_state.get("last_created_skill") else "🔧 "
            with st.expander(f"{badge}{name}"):
                st.caption(skill["description"])
    else:
        st.warning("No skills loaded. Create one in the 🛠️ tab.")

    st.divider()
    st.caption(f"**{len(registry)}** skill(s) loaded")

    if st.button("🔄 Refresh Registry"):
        registry = get_registry()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════

tab_chat, tab_create, tab_library = st.tabs([
    "💬 Chat",
    "🛠️ Create Skill",
    "📦 Skill Library",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — CHAT
# ══════════════════════════════════════════════════════════════════════════════

with tab_chat:
    st.header("💬 Skill-Aware Chat")
    st.caption(
        "Ask anything. YouTube URLs, PDF tasks, or any request matching a "
        "loaded skill will be routed and executed automatically."
    )

    with st.expander("ℹ️ How the pipeline works"):
        st.markdown("""
        1. **Skill Discovery** — all `skills/*/SKILL.md` descriptions injected into the LLM system prompt  
        2. **Skill Routing** — Gemini matches your query to the best skill  
        3. **Skill Reading** — agent calls `read_skill_instructions` to load the full SKILL.md  
        4. **Skill Execution** — LLM follows the documented workflow, calling Python tools  
        5. **Response** — tool outputs synthesised into a final answer  
        """)

    # ── Quick example buttons ─────────────────────────────────────────────────
    st.markdown("**Quick examples:**")
    example_cols = st.columns(2)
    examples = [
        ("📝 Transcript",    "Get the transcript for: https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("📋 Summary",       "Summarize this video: https://youtu.be/dQw4w9WgXcQ"),
        ("⏱️ Timestamps",   "Get the timestamped transcript for video ID: dQw4w9WgXcQ"),
        ("📦 List skills",   "What skills do you have available?"),
    ]
    for idx, (label, query) in enumerate(examples):
        col = example_cols[idx % 2]
        if col.button(label, key=f"ex_{idx}", use_container_width=True):
            st.session_state["prefill_query"] = query

    st.divider()

    # ── Render chat history ───────────────────────────────────────────────────
    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("skill"):
                cols = st.columns([1, 1, 4])
                cols[0].caption(f"🔧 Skill: `{msg['skill']}`")
                if msg.get("tools"):
                    cols[1].caption(f"🛠️ Tools: `{', '.join(msg['tools'])}`")

    # ── Chat input ────────────────────────────────────────────────────────────
    prefill     = st.session_state.pop("prefill_query", "")
    user_input  = st.chat_input(
        "Ask anything... (YouTube URLs trigger skills automatically)"
    )
    if prefill and not user_input:
        user_input = prefill

    if user_input:
        if not os.environ.get("GOOGLE_API_KEY"):
            st.error("⚠️ Please enter your Google API Key in the sidebar first.")
            st.stop()

        # Show the user message immediately
        st.session_state["chat_messages"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Run the agent with a fresh registry (picks up any just-created skill)
        with st.chat_message("assistant"):
            with st.spinner("🔍 Routing and executing skill..."):
                try:
                    fresh_registry = get_registry()
                    result = run_agent(user_input, verbose=False, registry=fresh_registry)
                    raw_response   = result["response"]
                    selected_skill = result.get("selected_skill")
                    tools_called   = result.get("tools_called", [])

                    # Normalise: Gemini can return a list of content blocks
                    if isinstance(raw_response, list):
                        parts = []
                        for block in raw_response:
                            if isinstance(block, dict):
                                parts.append(block.get("text") or block.get("content") or "")
                            elif isinstance(block, str):
                                parts.append(block)
                        response = "\n".join(p for p in parts if p).strip()
                    else:
                        response = str(raw_response).strip()

                    st.markdown(response)

                    if selected_skill:
                        info_cols = st.columns([1, 1, 4])
                        info_cols[0].caption(f"🔧 Skill: `{selected_skill}`")
                        if tools_called:
                            info_cols[1].caption(f"🛠️ `{', '.join(tools_called)}`")

                    st.session_state["chat_messages"].append({
                        "role":    "assistant",
                        "content": response,
                        "skill":   selected_skill,
                        "tools":   tools_called,
                    })

                except Exception as e:
                    err = (
                        f"❌ **Error:** {str(e)}\n\n"
                        "Make sure your Google API Key is valid and required "
                        "libraries are installed."
                    )
                    st.error(err)
                    st.session_state["chat_messages"].append(
                        {"role": "assistant", "content": err}
                    )

    # Clear chat button
    if st.session_state["chat_messages"]:
        if st.button("🗑️ Clear chat", key="clear_chat"):
            st.session_state["chat_messages"] = []
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CREATE SKILL
# ══════════════════════════════════════════════════════════════════════════════

with tab_create:
    st.header("🛠️ Create a New Skill")
    st.markdown(
        "Describe what you want the skill to do in plain English. "
        "The system will generate the `SKILL.md`, implementation script, "
        "and `@tool` wrapper — then make it immediately available in the Chat tab."
    )

    with st.expander("ℹ️ What happens when you create a skill"):
        st.markdown("""
        The creation pipeline runs these steps (mirroring Claude Code's skill-creator):

        | Step | What happens |
        |------|-------------|
        | 1 | LLM extracts a structured brief (name, triggers, I/O, libraries) |
        | 2 | LLM generates `SKILL.md` with full workflow instructions |
        | 3 | LLM generates a working Python implementation script |
        | 4 | LLM generates a `@tool` wrapper function |
        | 5 | Skill folder written to `skills/<name>/` on disk |
        | 6 | `@tool` stub injected into `skill_agent.py` |
        | 7 | Routing self-test — verifies the skill would be triggered correctly |
        | 8 | New skill immediately available in the Chat tab (no restart) |
        """)

    st.divider()

    # ── Input form ────────────────────────────────────────────────────────────
    with st.form("skill_creation_form"):
        skill_description = st.text_area(
            "Describe your skill",
            placeholder=(
                "e.g. 'Extract and summarise text from PDF files'\n"
                "e.g. 'Scrape a webpage and return its main content'\n"
                "e.g. 'Translate any text to a target language using a free API'"
            ),
            height=120,
        )
        col1, col2 = st.columns([1, 3])
        submitted = col1.form_submit_button(
            "🚀 Create Skill", use_container_width=True, type="primary"
        )
        col2.markdown(
            "<small style='color:grey'>Generation takes ~30-60 seconds</small>",
            unsafe_allow_html=True,
        )

    # ── Run creation pipeline ─────────────────────────────────────────────────
    if submitted:
        if not os.environ.get("GOOGLE_API_KEY"):
            st.error("⚠️ Please enter your Google API Key in the sidebar first.")
            st.stop()

        if not skill_description.strip():
            st.warning("Please describe the skill you want to create.")
            st.stop()

        st.session_state["skill_creation_log"]   = []
        st.session_state["last_created_skill"]   = None
        st.session_state["creation_result"]      = None

        log_placeholder = st.empty()
        log_lines: list[str] = []

        def ui_log(msg: str):
            log_lines.append(msg)
            log_placeholder.markdown("\n\n".join(log_lines))

        with st.spinner("Running skill creation pipeline..."):
            try:
                result = create_skill_programmatic(
                    skill_description.strip(),
                    log=ui_log,
                )
                st.session_state["creation_result"]    = result
                st.session_state["last_created_skill"] = result["skill_name"]

                # Hot-reload tools so the new skill is live in chat immediately
                try:
                    reload_tools()
                    ui_log("🔄  Tools reloaded — new skill is live in Chat tab.")
                except Exception as reload_err:
                    ui_log(f"⚠️  Could not hot-reload tools ({reload_err}). "
                           "Restart the app for the new @tool to be active.")

            except Exception as e:
                st.error(f"❌ Skill creation failed: {e}")
                st.stop()

    # ── Show result ───────────────────────────────────────────────────────────
    result = st.session_state.get("creation_result")
    if result:
        st.success(f"✅ Skill **{result['skill_name']}** created successfully!")

        skill_dir = result["skill_dir"]

        r_col1, r_col2 = st.columns(2)

        with r_col1:
            st.subheader("📄 Generated SKILL.md")
            st.code(result["skill_md"], language="markdown")

        with r_col2:
            st.subheader("🐍 Generated Script")
            st.code(result["script_code"], language="python")

        st.subheader("🔧 @tool Stub (added to skill_agent.py)")
        st.code(result["tool_stub"], language="python")

        st.subheader("📁 Files on disk")
        skill_path = Path(skill_dir)
        for f in sorted(skill_path.rglob("*")):
            if f.is_file():
                rel = f.relative_to(skill_path.parent.parent)
                st.caption(f"📄 `{rel}`")

        # Routing test result
        if result.get("test_passed"):
            st.success(f"🧪 Routing test passed — {result.get('test_reason', '')}")
        else:
            st.warning(
                f"⚠️ Routing test: {result.get('test_reason', '')}\n\n"
                "Consider editing the SKILL.md description in the Skill Library tab "
                "to add stronger trigger keywords."
            )

        if result.get("python_libraries"):
            st.info(
                "📦 Don't forget to install the skill's dependencies:\n"
                f"```\npip install {' '.join(result.get('python_libraries', []))}\n```"
            )

        st.info(
            "💬 The new skill is now available in the **Chat** tab. "
            "Try the suggested test query:\n\n"
            f"> {st.session_state.get('creation_result', {}).get('suggested_test_query', '')}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — SKILL LIBRARY
# ══════════════════════════════════════════════════════════════════════════════

with tab_library:
    st.header("📦 Skill Library")
    st.caption("Browse all skills currently loaded from the `skills/` directory.")

    lib_registry = get_registry()

    if not lib_registry:
        st.warning(
            "No skills found. Create your first skill in the 🛠️ Create Skill tab."
        )
    else:
        search = st.text_input("🔍 Filter skills", placeholder="Type to filter by name or description")

        for name, skill in lib_registry.items():
            if search and search.lower() not in name.lower() \
                      and search.lower() not in skill["description"].lower():
                continue

            badge = "🆕 " if name == st.session_state.get("last_created_skill") else ""
            with st.expander(f"{badge}🔧 {name}", expanded=(name == st.session_state.get("last_created_skill"))):

                st.markdown(f"**Description:** {skill['description']}")

                lib_col1, lib_col2 = st.columns(2)

                # SKILL.md
                with lib_col1:
                    st.markdown("**📄 SKILL.md**")
                    md_path = skill.get("skill_md_path")
                    if md_path and Path(md_path).exists():
                        content = Path(md_path).read_text(encoding="utf-8")
                        st.code(content, language="markdown")
                    else:
                        st.caption("SKILL.md not found on disk.")

                # Script files
                with lib_col2:
                    scripts_dir = skill.get("scripts_dir")
                    if scripts_dir and Path(scripts_dir).exists():
                        scripts = list(Path(scripts_dir).glob("*.py"))
                        if scripts:
                            st.markdown(f"**🐍 Scripts ({len(scripts)})**")
                            for s in scripts:
                                st.caption(f"`{s.name}`")
                                st.code(s.read_text(encoding="utf-8"), language="python")
                        else:
                            st.caption("No Python scripts found in scripts/.")
                    else:
                        st.caption("No scripts/ directory.")

                # Quick test button
                test_q = f"Help me use the {name} skill"
                if st.button(f"💬 Test in chat: \"{test_q[:45]}...\"",
                             key=f"test_{name}"):
                    st.session_state["prefill_query"] = test_q
                    # Switch to chat tab by re-running (user sees message pre-filled)
                    st.info("Query pre-filled — switch to the 💬 Chat tab to run it.")
