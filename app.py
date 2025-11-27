import os

import streamlit as st

from pages.pages import (  # page_geo_analysis,; page_overview,; page_source_comparison,; page_temporal_trends,; page_topic_analysis,
    BQ_TABLE_REF,
    page_competition,
    page_emerging_trends,
    page_geo_hotspots,
    page_product_features,
    page_root_cause,
)
from utils.db import list_tables_debug

# import altair as alt
# import pandas as pd


# Define the base URI of the API
#   - Potential sources are in `.streamlit/secrets.toml` or in the Secrets section
#     on Streamlit Cloud
#   - The source selected is based on the shell variable passend when launching streamlit
#     (shortcuts are included in Makefile). By default it takes the cloud API url
if "API_URI" in os.environ:
    BASE_URI = st.secrets[os.environ.get("API_URI")]
else:
    BASE_URI = st.secrets["cloud_api_uri"]

# Add a '/' at the end if it's not there
BASE_URI = BASE_URI if BASE_URI.endswith("/") else BASE_URI + "/"

# Define the url to be used by requests.get to get a prediction (adapt if needed)
url = BASE_URI + "predict"

# Just displaying the source for the API. Remove this in your final version.
# st.markdown(f"Working with {url}")

# st.markdown("Welcome to **VoiceLens** APP.")

GCP_PROJECT = st.secrets["GCP_PROJECT"]

# --- Configuration (Update these BigQuery values) ---
# The BigQuery connection is automatically configured by Streamlit's st.connection()
# based on credentials defined in the Streamlit secrets file (secrets.toml).

### OPTIMISATIONS ###
st.set_page_config(
    page_title="Review Insights Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Main Application Logic ---
# Use a dictionary to map page names to functions
PAGES = {
    # "1. Overview & Sentiment": page_overview,
    # "2. Temporal Trends": page_temporal_trends,
    # "3. Topic Analysis": page_topic_analysis,
    # "4. Geographical Analysis": page_geo_analysis,
    # "5. Source Comparison": page_source_comparison,
    "1. Root Cause Analysis": page_root_cause,
    "2. Geo Hotspots": page_geo_hotspots,
    "3. Product Features": page_product_features,
    "4. Emerging Trends": page_emerging_trends,
    "5. Competitive Intel": page_competition,
}

# Sidebar Navigation
with st.sidebar:
    st.image(
        "https://placehold.co/150x50/1e293b/ffffff?text=REVIEW+INSIGHTS",
        use_column_width=False,
    )
    st.header("Navigation")
    selection = st.selectbox("Go to...", list(PAGES.keys()))

    st.markdown("---")
    st.info(
        "Data is sourced from BigQuery table: **" + BQ_TABLE_REF.replace("`", "") + "**"
    )

# DEBUGGING BQ Tables
# list_tables_debug()

# Run the selected page function
PAGES[selection]()

# TODO: Add some titles, introduction, ...


# TODO: Request user input


# TODO: Call the API using the user's input
#   - url is already defined above
#   - create a params dict based on the user's input
#   - finally call your API using the requests package


# TODO: retrieve the results
#   - add a little check if you got an ok response (status code 200) or something else
#   - retrieve the prediction from the JSON


# TODO: display the prediction in some fancy way to the user


# TODO: [OPTIONAL] maybe you can add some other pages?
#   - some statistical data you collected in graphs
#   - description of your product
#   - a 'Who are we?'-page
