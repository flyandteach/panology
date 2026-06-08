"""
Streamlit Web UI for the Recursive Editorial Book Agent.
"""

import os
import sys
import json

# Ensure the book_agent directory is on the path for relative imports
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Book Agent",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Lazy imports — agents & utils are imported after path is set
# ---------------------------------------------------------------------------
from agents.architect import ArchitectAgent
from agents.drafter import DrafterAgent
from agents.line_editor import LineEditorAgent
from agents.repetition_checker import RepetitionCheckerAgent
from agents.audience_critic import AudienceCriticAgent
from agents.quality_gate import QualityGateAgent
from utils.memory import ProjectMemory
from utils.metrics import TextMetrics
from utils.export import export_manuscript, save_draft
import config

import pandas as pd

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
DEFAULTS = {
    "project_memory": None,
    "current_draft": "",
    "current_scores": {},
    "gate_result": None,
    "revision_cycle": 0,
    "pipeline_running": False,
    "pipeline_issues": [],
    "last_section": None,
}
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ---------------------------------------------------------------------------
# Helper: LLM mode indicator
# ---------------------------------------------------------------------------
def llm_mode_badge() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "🟢 Claude API connected"
    if os.environ.get("OPENAI_API_KEY"):
        return "🟡 OpenAI API connected"
    return "🔴 Mock mode (no API key)"


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.title("Book Agent")
st.sidebar.caption(llm_mode_badge())
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["Setup", "Outline", "Write", "Memory", "Export"],
    index=0,
)

# Show project title in sidebar if loaded
pm: ProjectMemory | None = st.session_state["project_memory"]
if pm is not None:
    proj = pm.project
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Project:** {proj.get('title', 'Untitled')}")
    st.sidebar.markdown(f"Genre: {proj.get('genre', '—')}")
    approved_count = len(pm.get_approved_sections())
    outline_count = len(pm.get_outline())
    st.sidebar.markdown(f"Sections: {approved_count}/{outline_count} approved")
else:
    if page != "Setup":
        st.sidebar.warning("No project loaded. Go to Setup first.")


# ===========================================================================
# PAGE: Setup
# ===========================================================================
if page == "Setup":
    st.title("Project Setup")

    tab_new, tab_load = st.tabs(["Create New Project", "Load Existing Project"])

    # --- Create New ---
    with tab_new:
        st.subheader("Create a New Project")
        with st.form("new_project_form"):
            title = st.text_input("Title", placeholder="The Art of Thinking Clearly")
            genre = st.text_input("Genre", placeholder="narrative nonfiction")
            audience = st.text_input(
                "Target Audience", placeholder="Educated general readers, 25-45"
            )
            tone = st.text_input("Tone", placeholder="incisive, conversational, intellectually rigorous")
            style_profile = st.text_area(
                "Style Profile",
                placeholder="Short declarative sentences. No jargon. Concrete examples before abstractions.",
                height=100,
            )
            project_dir = st.text_input(
                "Project Directory (will be created if absent)",
                placeholder="/home/user/my_book_project",
            )
            submitted = st.form_submit_button("Create Project")

        if submitted:
            if not title.strip():
                st.error("Title is required.")
            elif not project_dir.strip():
                st.error("Project directory is required.")
            else:
                try:
                    os.makedirs(project_dir, exist_ok=True)
                    new_pm = ProjectMemory.load(project_dir)
                    new_pm.create_new(
                        title=title.strip(),
                        genre=genre.strip(),
                        audience=audience.strip(),
                        tone=tone.strip(),
                        style_profile=style_profile.strip(),
                    )
                    new_pm.save()
                    st.session_state["project_memory"] = new_pm
                    # Reset pipeline state
                    st.session_state["current_draft"] = ""
                    st.session_state["current_scores"] = {}
                    st.session_state["gate_result"] = None
                    st.session_state["revision_cycle"] = 0
                    st.session_state["pipeline_issues"] = []
                    st.session_state["last_section"] = None
                    st.success(f"Project '{title}' created at {project_dir}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to create project: {exc}")

    # --- Load Existing ---
    with tab_load:
        st.subheader("Load an Existing Project")
        load_dir = st.text_input(
            "Project Directory Path",
            placeholder="/home/user/my_book_project",
            key="load_dir_input",
        )
        if st.button("Load Project"):
            if not load_dir.strip():
                st.error("Enter a project directory path.")
            elif not os.path.isdir(load_dir.strip()):
                st.error(f"Directory not found: {load_dir.strip()}")
            else:
                try:
                    loaded_pm = ProjectMemory.load(load_dir.strip())
                    st.session_state["project_memory"] = loaded_pm
                    st.session_state["current_draft"] = ""
                    st.session_state["current_scores"] = {}
                    st.session_state["gate_result"] = None
                    st.session_state["revision_cycle"] = 0
                    st.session_state["pipeline_issues"] = []
                    st.session_state["last_section"] = None
                    st.success(
                        f"Loaded project: {loaded_pm.project.get('title', 'Untitled')}"
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to load project: {exc}")

    # --- Current project status ---
    if st.session_state["project_memory"] is not None:
        pm_now: ProjectMemory = st.session_state["project_memory"]
        st.markdown("---")
        st.subheader("Current Project Status")
        proj = pm_now.project
        col1, col2, col3 = st.columns(3)
        col1.metric("Title", proj.get("title", "—"))
        col2.metric("Genre", proj.get("genre", "—"))
        col3.metric("Status", proj.get("status", "—"))
        col4, col5 = st.columns(2)
        col4.metric("Approved Sections", len(pm_now.get_approved_sections()))
        col5.metric("Total Sections", len(pm_now.get_outline()))


# ===========================================================================
# PAGE: Outline
# ===========================================================================
elif page == "Outline":
    st.title("Outline")

    if st.session_state["project_memory"] is None:
        st.warning("No project loaded. Go to Setup first.")
        st.stop()

    pm_now: ProjectMemory = st.session_state["project_memory"]
    outline = pm_now.get_outline()

    if not outline:
        st.info("No outline yet. Generate one below.")
        if st.button("Generate Outline"):
            with st.spinner("Generating outline..."):
                agent = ArchitectAgent()
                new_outline_data = agent.create_outline(pm_now, "Create a comprehensive book outline.")
                sections = new_outline_data.get("sections", [])
                if sections:
                    pm_now.set_outline(sections)
                else:
                    # some responses wrap sections at top level
                    pm_now.set_outline([new_outline_data] if new_outline_data else [])
                pm_now.save()
            st.success("Outline generated.")
            st.rerun()
    else:
        # Display outline
        st.subheader(f"Outline — {pm_now.project.get('title', 'Untitled')}")
        for section in outline:
            sid = section.get("id", "?")
            title_s = section.get("title", "Untitled Section")
            status = section.get("status", "pending")
            stype = section.get("type", "")
            target_wc = section.get("target_word_count", "?")

            status_emoji = {"approved": "✅", "in_progress": "🔄", "pending": "⬜"}.get(
                status, "⬜"
            )
            label = f"{status_emoji} [{sid}] {title_s}"
            if stype:
                label += f" — *{stype}*"

            with st.expander(label):
                col_a, col_b = st.columns([2, 1])
                col_a.markdown(f"**Purpose/Brief:** {section.get('brief', '—')}")
                col_b.markdown(f"**Target word count:** {target_wc}")
                col_b.markdown(f"**Status:** `{status}`")

        st.markdown("---")
        st.subheader("Refine Outline")
        feedback = st.text_area(
            "Feedback for refinement",
            placeholder="Add a chapter on case studies. Make the conclusion more forward-looking.",
            height=80,
        )
        if st.button("Regenerate / Refine Outline"):
            if not feedback.strip():
                st.warning("Enter feedback before refining.")
            else:
                with st.spinner("Refining outline..."):
                    agent = ArchitectAgent()
                    new_outline_data = agent.refine_outline(pm_now, feedback)
                    sections = new_outline_data.get("sections", [])
                    if sections:
                        pm_now.set_outline(sections)
                    pm_now.save()
                st.success("Outline refined.")
                st.rerun()


# ===========================================================================
# PAGE: Write
# ===========================================================================
elif page == "Write":
    st.title("Write Section")

    if st.session_state["project_memory"] is None:
        st.warning("No project loaded. Go to Setup first.")
        st.stop()

    pm_now: ProjectMemory = st.session_state["project_memory"]
    outline = pm_now.get_outline()

    if not outline:
        st.warning("No outline found. Go to the Outline page and generate one first.")
        st.stop()

    next_section = pm_now.get_next_unstarted_section()

    col_left, col_right = st.columns([1, 2])

    # -------------------------------------------------------------------
    # Left column: controls
    # -------------------------------------------------------------------
    with col_left:
        st.subheader("Controls")

        if next_section is None:
            st.success("All sections have been started or approved.")
        else:
            st.markdown(f"**Next section:** `{next_section.get('id')}`")
            st.markdown(f"**Title:** {next_section.get('title', '—')}")
            st.markdown(f"**Target words:** {next_section.get('target_word_count', '?')}")
            st.markdown(f"**Brief:** {next_section.get('brief', '—')}")

        st.markdown("---")

        # Revision notes input (shown always, used when "Request Revision" was clicked)
        revision_notes = st.text_area(
            "Revision notes (optional — used when re-running pipeline)",
            height=80,
            key="revision_notes",
        )

        run_disabled = (
            next_section is None or st.session_state["pipeline_running"]
        )

        if st.button(
            "Draft & Review Section",
            disabled=run_disabled,
            type="primary",
        ):
            st.session_state["pipeline_running"] = True
            st.session_state["revision_cycle"] = 0
            st.session_state["current_draft"] = ""
            st.session_state["current_scores"] = {}
            st.session_state["gate_result"] = None
            st.session_state["pipeline_issues"] = []
            st.session_state["last_section"] = next_section
            st.rerun()

        # Show cycle info
        if st.session_state["revision_cycle"] > 0:
            st.info(
                f"Revision cycle: {st.session_state['revision_cycle']} / {config.MAX_REVISION_CYCLES}"
            )

    # -------------------------------------------------------------------
    # Pipeline execution
    # -------------------------------------------------------------------
    if st.session_state["pipeline_running"] and st.session_state["last_section"] is not None:
        section = st.session_state["last_section"]
        max_cycles = config.MAX_REVISION_CYCLES
        cycle = st.session_state["revision_cycle"]

        with st.status(
            f"Running pipeline for '{section.get('title', section.get('id'))}' — cycle {cycle + 1}/{max_cycles}",
            expanded=True,
            state="running",
        ) as status_box:

            # Mark section as in-progress
            pm_now.mark_section_status(section.get("id"), "in_progress")

            # Step 1: Draft
            st.write("Step 1/6: Drafting...")
            drafter = DrafterAgent()
            draft_text = drafter.draft_section(
                pm_now,
                section,
                {"revision_notes": revision_notes} if revision_notes.strip() else {},
            )
            st.write(f"  Draft: {len(draft_text.split())} words")

            # Step 2: Metrics
            st.write("Step 2/6: Computing metrics...")
            metrics_obj = TextMetrics()
            metrics = metrics_obj.analyze(draft_text)

            # Step 3: Line edit
            st.write("Step 3/6: Line editing...")
            line_agent = LineEditorAgent()
            line_result = line_agent.review(draft_text, pm_now, metrics)
            if line_result.get("revised_draft", "").strip():
                draft_text = line_result["revised_draft"]

            # Step 4: Repetition check
            st.write("Step 4/6: Checking repetition...")
            rep_agent = RepetitionCheckerAgent()
            rep_result = rep_agent.review(draft_text, pm_now, metrics)
            if rep_result.get("revised_draft", "").strip():
                draft_text = rep_result["revised_draft"]

            # Step 5: Audience critique
            st.write("Step 5/6: Audience critique...")
            aud_agent = AudienceCriticAgent()
            section_brief_str = section.get("brief", section.get("title", ""))
            aud_result = aud_agent.review(draft_text, pm_now, section_brief_str)

            # Step 6: Quality gate
            st.write("Step 6/6: Quality gate...")
            scores = {
                "line_edit": line_result.get("score", 0.0),
                "repetition": rep_result.get("score", 0.0),
                "continuity": rep_result.get("score", 0.0),  # proxy — no dedicated continuity agent
                "critical_audience": aud_result.get("score", 0.0),
            }
            all_issues = (
                line_result.get("issues", [])
                + rep_result.get("issues", [])
                + aud_result.get("issues", [])
            )
            gate_agent = QualityGateAgent()
            gate_result = gate_agent.evaluate(scores, all_issues)

            # Store in session
            st.session_state["current_draft"] = draft_text
            st.session_state["current_scores"] = scores
            st.session_state["gate_result"] = gate_result
            st.session_state["pipeline_issues"] = all_issues

            if gate_result["pass"]:
                st.write("Quality gate: PASSED")
                status_box.update(label="Pipeline complete — PASSED", state="complete")
            else:
                st.write(
                    f"Quality gate: FAILED ({len(gate_result['failed_thresholds'])} threshold(s) missed)"
                )
                new_cycle = cycle + 1
                if new_cycle < max_cycles:
                    st.write(f"  Will revise (cycle {new_cycle + 1}/{max_cycles})...")
                    st.session_state["revision_cycle"] = new_cycle
                    status_box.update(label=f"Cycle {new_cycle} — revising...", state="running")
                    # Rerun to trigger next cycle
                    st.rerun()
                else:
                    status_box.update(
                        label=f"Pipeline complete — FAILED after {max_cycles} cycles",
                        state="error",
                    )

        st.session_state["pipeline_running"] = False

    # -------------------------------------------------------------------
    # Right column: output
    # -------------------------------------------------------------------
    with col_right:
        st.subheader("Output")

        draft = st.session_state.get("current_draft", "")
        gate_result = st.session_state.get("gate_result")
        scores = st.session_state.get("current_scores", {})

        if not draft:
            st.info("No draft yet. Click 'Draft & Review Section' to begin.")
        else:
            # Draft text area
            st.markdown("**Current Draft**")
            st.text_area("Draft", value=draft, height=300, key="draft_display", disabled=True)
            st.caption(f"Word count: {len(draft.split())}")

            if gate_result:
                st.markdown("---")
                st.markdown("**Scorecard**")

                # Build pandas DataFrame for scorecard
                scorecard = gate_result.get("scorecard", {})
                rows = []
                for dim, data in scorecard.items():
                    rows.append(
                        {
                            "Dimension": data.get("label", dim),
                            "Score": data["score"],
                            "Threshold": data["threshold"],
                            "Status": "PASS" if data["passed"] else "FAIL",
                        }
                    )
                # Add overall row
                overall = gate_result.get("overall_score", 0.0)
                avg_threshold = config.THRESHOLDS["min_average"]
                rows.append(
                    {
                        "Dimension": "Overall Average",
                        "Score": overall,
                        "Threshold": avg_threshold,
                        "Status": "PASS" if overall >= avg_threshold else "FAIL",
                    }
                )

                df = pd.DataFrame(rows)

                def _color_status(val):
                    color = "green" if val == "PASS" else "red"
                    return f"color: {color}; font-weight: bold"

                styled = df.style.applymap(_color_status, subset=["Status"])
                st.dataframe(styled, use_container_width=True, hide_index=True)

                # Verdict
                if gate_result.get("pass"):
                    st.success("VERDICT: ALL THRESHOLDS MET")
                else:
                    cycles_done = st.session_state.get("revision_cycle", 0)
                    if cycles_done >= config.MAX_REVISION_CYCLES:
                        st.error(
                            f"VERDICT: FAILED after {config.MAX_REVISION_CYCLES} revision cycles — showing best draft"
                        )
                        failed_dims = [
                            f"{f['dimension']} (needs +{f['gap']:.1f})"
                            for f in gate_result.get("failed_thresholds", [])
                        ]
                        st.markdown("**Failed thresholds:** " + ", ".join(failed_dims))
                    else:
                        st.warning("VERDICT: FAILED — revisions in progress")

                # Issues list
                issues = st.session_state.get("pipeline_issues", [])
                if issues:
                    with st.expander(f"Issues ({len(issues)})"):
                        for issue in issues:
                            st.markdown(f"- {issue}")

                # Action buttons — only show if gate passed or all cycles exhausted
                cycles_done = st.session_state.get("revision_cycle", 0)
                show_actions = gate_result.get("pass") or cycles_done >= config.MAX_REVISION_CYCLES

                if show_actions:
                    section_info = st.session_state.get("last_section", {})
                    section_id = section_info.get("id", "unknown")
                    section_title = section_info.get("title", "Section")

                    st.markdown("---")
                    st.markdown("**Actions**")
                    act_col1, act_col2, act_col3 = st.columns(3)

                    with act_col1:
                        if st.button("Approve", type="primary"):
                            # Save draft file
                            drafts_approved = os.path.join(
                                os.path.dirname(pm_now.path), config.DRAFTS_APPROVED_DIR
                            )
                            save_draft(draft, section_id, drafts_approved)
                            # Update memory
                            summary = draft[:200].strip() + "..."
                            pm_now.add_approved_section(
                                section_id=section_id,
                                title=section_title,
                                summary=summary,
                                content=draft,
                            )
                            pm_now.add_revision_history(
                                {
                                    "section_id": section_id,
                                    "action": "approved",
                                    "cycles": cycles_done,
                                    "overall_score": gate_result.get("overall_score"),
                                }
                            )
                            pm_now.save()
                            # Clear pipeline state
                            st.session_state["current_draft"] = ""
                            st.session_state["gate_result"] = None
                            st.session_state["current_scores"] = {}
                            st.session_state["revision_cycle"] = 0
                            st.session_state["last_section"] = None
                            st.success(f"Section '{section_title}' approved.")
                            st.rerun()

                    with act_col2:
                        if st.button("Request Revision"):
                            # Re-trigger pipeline with revision notes
                            st.session_state["pipeline_running"] = True
                            st.session_state["revision_cycle"] = 0
                            st.session_state["gate_result"] = None
                            st.rerun()

                    with act_col3:
                        if st.button("Reject"):
                            # Save to rejected dir
                            drafts_rejected = os.path.join(
                                os.path.dirname(pm_now.path), config.DRAFTS_REJECTED_DIR
                            )
                            save_draft(draft, section_id + "_rejected", drafts_rejected)
                            pm_now.mark_section_status(section_id, "pending")
                            pm_now.add_revision_history(
                                {
                                    "section_id": section_id,
                                    "action": "rejected",
                                    "cycles": cycles_done,
                                }
                            )
                            pm_now.save()
                            st.session_state["current_draft"] = ""
                            st.session_state["gate_result"] = None
                            st.session_state["current_scores"] = {}
                            st.session_state["revision_cycle"] = 0
                            st.session_state["last_section"] = None
                            st.warning(f"Section '{section_title}' rejected. Marked as pending.")
                            st.rerun()


# ===========================================================================
# PAGE: Memory & History
# ===========================================================================
elif page == "Memory":
    st.title("Memory & History")

    if st.session_state["project_memory"] is None:
        st.warning("No project loaded. Go to Setup first.")
        st.stop()

    pm_now: ProjectMemory = st.session_state["project_memory"]
    mem = pm_now.data.get("memory", {})

    # --- Full memory JSON ---
    with st.expander("Full Project Memory (JSON)", expanded=False):
        st.json(pm_now.data)

    # --- Approved sections ---
    st.subheader("Approved Sections")
    approved = pm_now.get_approved_sections()
    if approved:
        df_approved = pd.DataFrame(
            [
                {
                    "ID": s["id"],
                    "Title": s["title"],
                    "Word Count": s.get("word_count", "?"),
                    "Approved At": s.get("approved_at", "—"),
                    "Summary": s.get("summary", "—")[:120] + "..." if len(s.get("summary", "")) > 120 else s.get("summary", "—"),
                }
                for s in approved
            ]
        )
        st.dataframe(df_approved, use_container_width=True, hide_index=True)
    else:
        st.info("No approved sections yet.")

    # --- Revision history ---
    st.subheader("Revision History")
    history = pm_now.data.get("revision_history", [])
    if history:
        df_hist = pd.DataFrame(history)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.info("No revision history yet.")

    # --- Phrases to avoid ---
    st.subheader("Phrases to Avoid")
    phrases = mem.get("phrases_to_avoid", [])
    if phrases:
        for p in phrases:
            st.markdown(f"- `{p}`")
    else:
        st.info("No phrases flagged yet.")

    # --- Used metaphors ---
    st.subheader("Used Metaphors")
    metaphors = mem.get("used_metaphors", [])
    if metaphors:
        for m in metaphors:
            st.markdown(f"- {m}")
    else:
        st.info("No metaphors recorded yet.")

    # --- Key terms ---
    st.subheader("Key Terms")
    key_terms = mem.get("key_terms", {})
    if key_terms:
        df_terms = pd.DataFrame(
            [{"Term": k, "Definition": v} for k, v in key_terms.items()]
        )
        st.dataframe(df_terms, use_container_width=True, hide_index=True)
    else:
        st.info("No key terms defined yet.")


# ===========================================================================
# PAGE: Export
# ===========================================================================
elif page == "Export":
    st.title("Export Manuscript")

    if st.session_state["project_memory"] is None:
        st.warning("No project loaded. Go to Setup first.")
        st.stop()

    pm_now: ProjectMemory = st.session_state["project_memory"]
    approved = pm_now.get_approved_sections()

    if not approved:
        st.warning("No approved sections to export yet.")
        st.stop()

    st.info(f"{len(approved)} approved section(s) ready for export.")

    export_path = os.path.join(os.path.dirname(pm_now.path), config.EXPORTS_DIR)

    if st.button("Export Full Manuscript as Markdown", type="primary"):
        with st.spinner("Assembling manuscript..."):
            try:
                filepath = export_manuscript(pm_now, export_path)
                with open(filepath, "r", encoding="utf-8") as fh:
                    content = fh.read()
                st.session_state["_export_content"] = content
                st.session_state["_export_filename"] = os.path.basename(filepath)
                st.success(f"Exported to: {filepath}")
            except Exception as exc:
                st.error(f"Export failed: {exc}")

    content = st.session_state.get("_export_content", "")
    filename = st.session_state.get("_export_filename", "manuscript.md")

    if content:
        st.markdown("---")
        st.subheader("Manuscript Preview")
        st.text_area("Preview", value=content, height=400, disabled=True)

        st.download_button(
            label="Download Manuscript (.md)",
            data=content,
            file_name=filename,
            mime="text/markdown",
        )
