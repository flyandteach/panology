import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_PATH = Path("data/topics.json")

st.set_page_config(
    page_title="Aviation Futures Intelligence Agent",
    page_icon="🛩️",
    layout="wide",
)

DEFAULT_TOPICS = [
    {
        "topic": "eVTOL certification progress",
        "category": "AAM / eVTOL",
        "signal_strength": 4,
        "time_horizon": "Near term",
        "confidence": 3,
        "notes": "Track certification milestones, flight-test evidence, and regulatory filings separately from promotional claims.",
        "watch_items": "FAA certification phases; type certification basis; conformity aircraft; production certification",
        "last_updated": str(date.today()),
    },
    {
        "topic": "Airport electrification and charging infrastructure",
        "category": "Airport Infrastructure",
        "signal_strength": 3,
        "time_horizon": "Near to mid term",
        "confidence": 4,
        "notes": "Monitor utility capacity, charging standards, grid constraints, and airport capital planning integration.",
        "watch_items": "utility studies; charger deployments; battery storage; airport master plans",
        "last_updated": str(date.today()),
    },
    {
        "topic": "Drone delivery hub land-use regulation",
        "category": "Drone Logistics",
        "signal_strength": 4,
        "time_horizon": "Near term",
        "confidence": 4,
        "notes": "Track local ordinances, setbacks, community opposition, FAA environmental review, and operational scale.",
        "watch_items": "local zoning cases; hub approvals; noise complaints; state preemption",
        "last_updated": str(date.today()),
    },
]


def load_topics():
    if DATA_PATH.exists():
        with open(DATA_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    return DEFAULT_TOPICS


def save_topics(topics):
    DATA_PATH.parent.mkdir(exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as file:
        json.dump(topics, file, indent=2)


def score_topic(topic):
    strength = int(topic.get("signal_strength", 0))
    confidence = int(topic.get("confidence", 0))
    return round((strength * 0.65 + confidence * 0.35) * 20, 1)


def classify_priority(score):
    if score >= 80:
        return "High"
    if score >= 60:
        return "Medium"
    return "Low"


if "topics" not in st.session_state:
    st.session_state.topics = load_topics()

st.title("Aviation Futures Intelligence Agent")
st.caption("A simple public-facing watchlist tool for aviation technology, infrastructure, policy, and market signals.")

st.sidebar.header("Add Intelligence Item")
with st.sidebar.form("add_topic"):
    topic = st.text_input("Topic or signal")
    category = st.selectbox(
        "Category",
        [
            "AAM / eVTOL",
            "Airport Infrastructure",
            "Drone Logistics",
            "AI / Automation",
            "Energy / Sustainability",
            "Safety / Regulation",
            "Market / Finance",
            "Other",
        ],
    )
    signal_strength = st.slider("Signal strength", 1, 5, 3)
    confidence = st.slider("Confidence", 1, 5, 3)
    time_horizon = st.selectbox("Time horizon", ["Near term", "Near to mid term", "Mid term", "Long term"])
    notes = st.text_area("Notes")
    watch_items = st.text_area("Watch items")
    submitted = st.form_submit_button("Add item")

if submitted and topic.strip():
    st.session_state.topics.append(
        {
            "topic": topic.strip(),
            "category": category,
            "signal_strength": signal_strength,
            "confidence": confidence,
            "time_horizon": time_horizon,
            "notes": notes.strip(),
            "watch_items": watch_items.strip(),
            "last_updated": str(date.today()),
        }
    )
    save_topics(st.session_state.topics)
    st.sidebar.success("Item added.")

rows = []
for item in st.session_state.topics:
    score = score_topic(item)
    rows.append(
        {
            "Topic": item["topic"],
            "Category": item["category"],
            "Time Horizon": item["time_horizon"],
            "Signal Strength": item["signal_strength"],
            "Confidence": item["confidence"],
            "Priority Score": score,
            "Priority": classify_priority(score),
            "Last Updated": item["last_updated"],
        }
    )

st.subheader("Intelligence Watchlist")
df = pd.DataFrame(rows).sort_values(by="Priority Score", ascending=False)
st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader("Priority Summary")
col1, col2, col3 = st.columns(3)
col1.metric("High Priority", int((df["Priority"] == "High").sum()))
col2.metric("Medium Priority", int((df["Priority"] == "Medium").sum()))
col3.metric("Low Priority", int((df["Priority"] == "Low").sum()))

st.subheader("Detailed Notes")
for item in sorted(st.session_state.topics, key=score_topic, reverse=True):
    score = score_topic(item)
    with st.expander(f"{item['topic']} — {classify_priority(score)} priority"):
        st.write(f"**Category:** {item['category']}")
        st.write(f"**Priority score:** {score}")
        st.write(f"**Time horizon:** {item['time_horizon']}")
        st.write(f"**Notes:** {item['notes'] or 'No notes entered.'}")
        st.write(f"**Watch items:** {item['watch_items'] or 'No watch items entered.'}")
        st.write(f"**Last updated:** {item['last_updated']}")

st.subheader("Export")
report_lines = ["# Aviation Futures Intelligence Report", ""]
report_lines.append(f"Generated: {date.today()}")
report_lines.append("")
for item in sorted(st.session_state.topics, key=score_topic, reverse=True):
    score = score_topic(item)
    report_lines.append(f"## {item['topic']}")
    report_lines.append(f"- Category: {item['category']}")
    report_lines.append(f"- Priority: {classify_priority(score)}")
    report_lines.append(f"- Priority score: {score}")
    report_lines.append(f"- Time horizon: {item['time_horizon']}")
    report_lines.append(f"- Notes: {item['notes'] or 'None'}")
    report_lines.append(f"- Watch items: {item['watch_items'] or 'None'}")
    report_lines.append("")

report_text = "\n".join(report_lines)
st.download_button(
    "Download Markdown Report",
    data=report_text,
    file_name="aviation_futures_intelligence_report.md",
    mime="text/markdown",
)

st.info(
    "This MVP uses manual entries only. It does not automatically verify facts, browse the web, or monitor live data sources."
)
