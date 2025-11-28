import os

import requests
import streamlit as st
from streamlit_extras.add_vertical_space import add_vertical_space
from streamlit_extras.colored_header import colored_header
from streamlit_extras.stylable_container import stylable_container

# -----------------------
# CONFIG
# -----------------------
if "API_URI" in os.environ:
    BASE_URI = st.secrets[os.environ.get("API_URI")]
else:
    BASE_URI = st.secrets.get("cloud_api_uri", "")

BASE_URI = BASE_URI if BASE_URI.endswith("/") else BASE_URI + "/"
API_URL = BASE_URI + "predict"

st.set_page_config(
    page_title="Voicelens Review Predictor",
    layout="centered",
)

# -----------------------
# PAGE HEADER
# -----------------------
colored_header(
    label="🔮 Voicelens Review IntelligenceBASE_URI",
    description="Upload or write multiple reviews and get automatic predictions for sentiment & entities.",
    color_name="blue-70",
)

add_vertical_space(2)

# -----------------------
# SESSION STATE FOR REVIEWS
# -----------------------
if "reviews" not in st.session_state:
    st.session_state.reviews = [""]  # Start with one input


def add_review():
    st.session_state.reviews.append("")


def remove_review(i):
    st.session_state.reviews.pop(i)


# -----------------------
# INPUT SECTION
# -----------------------
st.markdown("### ✍️ Enter Reviews")
st.write("API URL:", API_URL)

for i, text in enumerate(st.session_state.reviews):
    with stylable_container(
        key=f"review_card_{i}",
        css_styles="""
            {
                border-radius: 12px;
                padding: 18px;
                background-color: #F8F9FA;
                border: 1px solid #E0E0E0;
                box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
                margin-bottom: 10px;
            }
        """,
    ):
        cols = st.columns([0.9, 0.1])
        with cols[0]:
            st.session_state.reviews[i] = st.text_area(
                label=f"Review #{i+1}",
                value=st.session_state.reviews[i],
                key=f"text_{i}",
                placeholder="Write a customer review...",
                label_visibility="collapsed",
                height=80,
            )
        with cols[1]:
            if len(st.session_state.reviews) > 1:
                if st.button("🗑️", key=f"remove_{i}", help="Remove this review"):
                    remove_review(i)
                    st.rerun()

# Add Review Button
st.markdown("")
add_btn_col = st.columns([0.3, 0.4, 0.3])[1]
with add_btn_col:
    st.button("➕ Add another review", on_click=add_review)

add_vertical_space(2)

# -----------------------
# PREDICT BUTTON
# -----------------------
center_col = st.columns([0.25, 0.5, 0.25])[1]
with center_col:
    run_predict = st.button("🚀 Run Predictions", use_container_width=True)

# -----------------------
# RUN PREDICTION
# -----------------------
if run_predict:
    reviews_cleaned = [r.strip() for r in st.session_state.reviews if r.strip()]

    if not reviews_cleaned:
        st.error("Please enter at least one review.")
        st.stop()

    with st.spinner("Contacting AI model..."):
        try:
            response = requests.post(
                API_URL,
                json={"reviews": reviews_cleaned},
                timeout=20,
            )
            response.raise_for_status()
            predictions = response.json()

        except Exception as e:
            st.error(f"Error contacting API: {e}")
            st.stop()

    st.markdown("## 📊 Results")

    # DISPLAY RESULTS
    for i, pred in enumerate(predictions):
        with stylable_container(
            key=f"result_card_{i}",
            css_styles="""
                {
                    border-radius: 12px;
                    padding: 20px;
                    background-color: white;
                    border: 1px solid #D0D7DE;
                    box-shadow: 0px 3px 6px rgba(0,0,0,0.08);
                    margin-bottom: 16px;
                }
            """,
        ):
            st.markdown(f"### ✨ Review #{i+1}")
            st.markdown(f"**📝 Text:** {pred['text']}")
            st.markdown(f"**💬 Sentiment:** `{pred['sentiment']}`")

            if "entities" in pred:
                st.markdown("**🔍 Extracted Entities:**")
                if pred["entities"]:
                    for ent, label in pred["entities"]:
                        st.markdown(f"- **{ent}** — *{label}*")
                else:
                    st.write("No relevant entities found.")

    st.success("🎉 Predictions complete!")
