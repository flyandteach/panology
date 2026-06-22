from __future__ import annotations

from pathlib import Path
import json
import tempfile

import streamlit as st

from travel_agent import TravelFormAgent, TravelIntake

BASE = Path(__file__).resolve().parent

st.set_page_config(page_title="Travel Form Agent", layout="wide")
st.title("Travel Form Agent")
st.write("Upload or paste a travel-intake JSON file to generate a completed travel request PDF and travel expense voucher XLSX.")

with st.expander("Expected JSON shape", expanded=False):
    st.code((BASE / "examples" / "bfi_travel_intake.json").read_text(encoding="utf-8"), language="json")

uploaded = st.file_uploader("Travel intake JSON", type=["json"])
text = st.text_area("Or paste travel intake JSON", height=260)

travel_request_template = st.file_uploader("Travel request PDF template", type=["pdf"])
expense_template = st.file_uploader("133-103 XLSX template", type=["xlsx"])

if st.button("Generate forms"):
    try:
        if uploaded is not None:
            payload = json.loads(uploaded.read().decode("utf-8"))
        elif text.strip():
            payload = json.loads(text)
        else:
            st.error("Provide a travel-intake JSON file or paste JSON.")
            st.stop()

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            request_template_path = td_path / "travel_request_template.pdf"
            expense_template_path = td_path / "133-103_template.xlsx"
            if travel_request_template is not None:
                request_template_path.write_bytes(travel_request_template.read())
            else:
                request_template_path.write_bytes((BASE / "templates" / "travel_request_template.pdf").read_bytes())
            if expense_template is not None:
                expense_template_path.write_bytes(expense_template.read())
            else:
                expense_template_path.write_bytes((BASE / "templates" / "133-103_template.xlsx").read_bytes())

            intake = TravelIntake.from_dict(payload)
            agent = TravelFormAgent(request_template_path, expense_template_path, td_path / "outputs")
            outputs = agent.run(intake)
            request_bytes = outputs["travel_request_pdf"].read_bytes()
            expense_bytes = outputs["expense_voucher_xlsx"].read_bytes()

        st.success("Forms generated.")
        st.download_button("Download travel request PDF", request_bytes, "travel_request.pdf", mime="application/pdf")
        st.download_button(
            "Download travel expense voucher XLSX",
            expense_bytes,
            "travel_expense_voucher.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.error(str(e))
