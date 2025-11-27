import os

import altair as alt
import pandas as pd
import streamlit as st

# import pandas as pd
# from datetime import datetime, timedelta
from connect.bq import load_data_from_bq

# --- Setup & Config ---
if "API_URI" in os.environ:
    BASE_URI = st.secrets[os.environ.get("API_URI")]
else:
    BASE_URI = st.secrets.get("cloud_api_uri", "")  # Added .get() for safety

BASE_URI = BASE_URI if BASE_URI.endswith("/") else BASE_URI + "/"
url = BASE_URI + "predict"

DEBUG = st.secrets.get("DEBUG", False)
GCP_PROJECT = st.secrets["GCP_PROJECT"]
DATASET = st.secrets["DATASET"]
MASTER_INSIGHT_TABLE = st.secrets["MASTER_INSIGHT_TABLE"]
DUMMY_INSIGHT_TABLE = st.secrets.get("DUMMY_INSIGHT_TABLE", MASTER_INSIGHT_TABLE)

# Select table based on debug mode
INSIGHT_TABLE = MASTER_INSIGHT_TABLE if not DEBUG else DUMMY_INSIGHT_TABLE
BQ_TABLE_REF = f"`{GCP_PROJECT}.{DATASET}.{INSIGHT_TABLE}`"


# --- Helper: Color Scales ---
# Green for positive, Red for negative
sentiment_scale = alt.Scale(
    domain=["positive", "neutral", "negative"], range=["#34d399", "#fbbf24", "#f87171"]
)


# ==========================================
# 1. ROOT CAUSE INSIGHT (Sentiment + Topic + Time)
# ==========================================
def page_root_cause():
    st.title("📉 Root Cause Analysis")
    st.markdown(
        """
    **Goal:** Diagnose sudden dips in sentiment.
    *Select a specific time window on the chart below to see which topics caused the drop.*
    """
    )

    # 1. Time Series Chart
    # Removed the date filter "INTERVAL 1 YEAR" to ensure dummy data from any date shows up
    ts_query = f"""
        SELECT
            DATE(review_date) as date,
            COUNT(review_id) as volume,
            SAFE_DIVIDE(COUNTIF(predicted_sentiment = 'negative'), COUNT(review_id)) as negative_rate
        FROM {BQ_TABLE_REF}
        WHERE review_date > '2020-01-01'
        GROUP BY 1
        ORDER BY 1
    """
    ts_df = load_data_from_bq(ts_query)

    if not ts_df.empty:
        # Interactive Selection Brush
        brush = alt.selection_interval(encodings=["x"], name="brush")

        base = alt.Chart(ts_df).encode(x="date:T")

        line = (
            base.mark_line(color="#f87171")
            .encode(
                y=alt.Y(
                    "negative_rate",
                    axis=alt.Axis(format="%"),
                    title="negative Sentiment Rate",
                ),
                tooltip=["date", alt.Tooltip("negative_rate", format=".1%")],
            )
            .add_params(brush)
            .properties(height=300, title="Select a date range here:")
        )

        st.altair_chart(line, use_container_width=True)

        # 2. Filter Inputs
        col1, col2 = st.columns(2)
        st.info("👇 **Drill Down:** Adjust these dates to match the dip you see above.")

        # Safe date handling for dummy data
        min_date = pd.to_datetime(ts_df["date"]).min().date()
        max_date = pd.to_datetime(ts_df["date"]).max().date()

        start_date = col1.date_input(
            "Start Date", min_date, min_value=min_date, max_value=max_date
        )
        end_date = col2.date_input(
            "End Date", max_date, min_value=min_date, max_value=max_date
        )

        # 3. Root Cause Query
        st.subheader(f"Top Negative Topics ({start_date} to {end_date})")

        # Cleaned 'predicted_topic' to remove "Topic: " prefix for cleaner charts
        topic_query = f"""
            SELECT
                REPLACE(predicted_topic, 'Topic: ', '') as simple_topic,
                COUNT(review_id) as negative_mentions
            FROM {BQ_TABLE_REF}
            WHERE predicted_sentiment = 'negative'
            AND DATE(review_date) BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY 1
            ORDER BY 2 DESC
            LIMIT 10
        """
        topic_df = load_data_from_bq(topic_query)

        if not topic_df.empty:
            chart = (
                alt.Chart(topic_df)
                .mark_bar(color="#f87171")
                .encode(
                    x=alt.X("negative_mentions", title="Negative Mentions"),
                    y=alt.Y("simple_topic", sort="-x", title="Topic"),
                    tooltip=["simple_topic", "negative_mentions"],
                )
            )
            st.altair_chart(chart, use_container_width=True)

            top_issue = topic_df.iloc[0]["simple_topic"]
            st.error(
                f"🚨 **Root Cause Identified:** The spike in negative sentiment is primarily driven by **'{top_issue}'**."
            )
        else:
            st.warning("No negative reviews found in this selected date range.")


# ==========================================
# 2. GEOGRAPHICAL HOTSPOTS (Location + Sentiment)
# ==========================================
def page_geo_hotspots():
    st.title("🌍 Geographical Hotspots")
    st.markdown("**Goal:** Identify regions with specific support or logistics issues.")

    # Lowered threshold to > 0 to ensure dummy data shows up
    geo_query = f"""
        SELECT
            location,
            COUNT(review_id) as total_reviews,
            SAFE_DIVIDE(COUNTIF(predicted_sentiment = 'negative'), COUNT(review_id)) as negative_pct
        FROM {BQ_TABLE_REF}
        WHERE location IS NOT NULL
          AND location != ''
          AND REGEXP_CONTAINS(TRIM(location), r'^[A-Za-z]{2}$')  -- only 2-letter alpha codes
        GROUP BY 1
        HAVING total_reviews > 0
        ORDER BY negative_pct DESC
        LIMIT 20
    """
    geo_df = load_data_from_bq(geo_query)

    if not geo_df.empty:
        st.subheader("Regions by Negative Sentiment Rate")

        chart = (
            alt.Chart(geo_df)
            .mark_bar()
            .encode(
                x=alt.X(
                    "negative_pct",
                    axis=alt.Axis(format="%"),
                    title="% Negative Reviews",
                ),
                y=alt.Y("location", sort="-x", title="Location"),
                color=alt.Color(
                    "negative_pct", scale=alt.Scale(scheme="reds"), title="Negativity"
                ),
                tooltip=[
                    "location",
                    "total_reviews",
                    alt.Tooltip("negative_pct", format=".1%"),
                ],
            )
            .properties(height=500)
        )

        st.altair_chart(chart, use_container_width=True)

        worst_loc = geo_df.iloc[0]["location"]
        st.warning(
            f"📍 **Action Required:** **{worst_loc}** is showing the highest rate of customer dissatisfaction."
        )


# ==========================================
# 3. PRODUCT FEATURE INSIGHT (Best & Worst)
# ==========================================
def page_product_features():
    st.title("🛠️ Product Feature Analysis")
    st.markdown(
        """
    **Goal:** Engineering directives. We extract specific product parts (Battery, Screen, Price)
    and analyze the sentiment specifically associated with them.
    """
    )

    # FIX: Included 'METRIC' label so "price" shows up
    # FIX: Lowered threshold to > 0
    feature_query = f"""
        SELECT
            TRIM(LOWER(JSON_EXTRACT_SCALAR(entity, '$.text'))) as feature,
            COUNT(*) as mentions,
            SAFE_DIVIDE(COUNTIF(predicted_sentiment = 'positive'), COUNT(*)) as positive_pct
        FROM {BQ_TABLE_REF},
        UNNEST(JSON_EXTRACT_ARRAY(extracted_entities)) as entity
        WHERE JSON_EXTRACT_SCALAR(entity, '$.label') IN ('PRODUCT', 'METRIC')
        GROUP BY 1
        HAVING mentions > 0
        ORDER BY mentions DESC
        LIMIT 20
    """

    df = load_data_from_bq(feature_query)

    if not df.empty:
        # 1. Display the Chart
        st.subheader("Sentiment by Component/Feature")
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X(
                    "positive_pct",
                    axis=alt.Axis(format="%"),
                    title="positive Sentiment %",
                ),
                y=alt.Y("feature", sort="-x", title="Product Feature"),
                color=alt.Color(
                    "positive_pct",
                    scale=alt.Scale(scheme="redyellowgreen", domain=[0, 1]),
                    title="Sentiment",
                ),
                tooltip=[
                    "feature",
                    "mentions",
                    alt.Tooltip("positive_pct", format=".1%"),
                ],
            )
        )
        st.altair_chart(chart, use_container_width=True)

        st.markdown("---")

        # 2. Display Best 3 and Lowest 3 (Requested Feature)
        col1, col2 = st.columns(2)

        # Sort by positive percentage
        df_sorted = df.sort_values(by="positive_pct", ascending=False)

        with col1:
            st.success("✅ **Top 3 Best Performing Features**")
            top_3 = df_sorted.head(3)
            for index, row in top_3.iterrows():
                st.metric(
                    label=row["feature"].title(),
                    value=f"{row['positive_pct']*100:.0f}% positive",
                    delta="Great",
                )

        with col2:
            st.error("⚠️ **Lowest 3 Performing Features**")
            bottom_3 = df_sorted.tail(3).sort_values(
                by="positive_pct", ascending=True
            )  # Sort worst to top
            for index, row in bottom_3.iterrows():
                st.metric(
                    label=row["feature"].title(),
                    value=f"{row['positive_pct']*100:.0f}% positive",
                    delta="- Critical",
                    delta_color="inverse",
                )


# ==========================================
# 4. EMERGING TRENDS (Topic + Growth)
# ==========================================
def page_emerging_trends():
    st.title("🚀 Emerging Trends & Requests")
    st.markdown("**Goal:** Identifies topics exploding in volume (Month-over-Month).")

    # FIX: Removed restrictive date filters for dummy data
    # Logic: Just compare two arbitrary windows or simple counts if data is sparse
    trend_query = f"""
        WITH recent_stats AS (
            SELECT predicted_topic, COUNT(review_id) as vol_recent
            FROM {BQ_TABLE_REF}
            -- Relaxed window for dummy data visibility
            WHERE review_date >= '2024-09-01'
            GROUP BY 1
        ),
        past_stats AS (
            SELECT predicted_topic, COUNT(review_id) as vol_past
            FROM {BQ_TABLE_REF}
            -- Relaxed window for dummy data visibility
            WHERE review_date < '2024-09-01'
            GROUP BY 1
        )
        SELECT
            REPLACE(r.predicted_topic, 'Topic: ', '') as simple_topic,
            r.vol_recent,
            COALESCE(p.vol_past, 1) as vol_past, -- Avoid division by zero
            SAFE_DIVIDE((r.vol_recent - COALESCE(p.vol_past, 0)), COALESCE(p.vol_past, 1)) as growth_rate
        FROM recent_stats r
        LEFT JOIN past_stats p ON r.predicted_topic = p.predicted_topic
        WHERE r.vol_recent > 0 -- Show everything
        ORDER BY growth_rate DESC
        LIMIT 10
    """
    df = load_data_from_bq(trend_query)

    if not df.empty:
        st.subheader("Fastest Growing Topics (Comparison)")

        chart = (
            alt.Chart(df)
            .mark_bar(color="#818cf8")
            .encode(
                x=alt.X("growth_rate", axis=alt.Axis(format="%"), title="Growth Rate"),
                y=alt.Y("simple_topic", sort="-x", title="Topic"),
                tooltip=[
                    "simple_topic",
                    alt.Tooltip("growth_rate", format=".1%"),
                    "vol_recent",
                ],
            )
        )
        st.altair_chart(chart, use_container_width=True)

        top_trend = df.iloc[0]["simple_topic"]
        st.info(
            f"📈 **Strategic Opportunity:** Users are suddenly talking about **'{top_trend}'**."
        )
    else:
        st.warning("Not enough data to calculate trends yet.")


# ==========================================
# 5. COMPETITIVE INTELLIGENCE (NER + Sentiment)
# ==========================================
def page_competition():
    st.title("⚔️ Competitive Intelligence")
    st.markdown("**Goal:** Analyze sentiment when customers mention competitors.")

    # FIX: Added 'TEAM' and 'PRODUCT' to labels because dummy data HAS NO 'ORG' tags.
    # In production, you would restrict this to 'ORG'.
    comp_query = f"""
        SELECT
            TRIM(JSON_EXTRACT_SCALAR(entity, '$.text')) as competitor,
            COUNT(*) as mentions,
            SAFE_DIVIDE(COUNTIF(predicted_sentiment = 'negative'), COUNT(*)) as negative_association_pct
        FROM {BQ_TABLE_REF},
        UNNEST(JSON_EXTRACT_ARRAY(extracted_entities)) as entity
        WHERE JSON_EXTRACT_SCALAR(entity, '$.label') IN ('ORG', 'TEAM', 'PRODUCT')
        AND LOWER(JSON_EXTRACT_SCALAR(entity, '$.text')) NOT LIKE '%voicelens%'
        -- Exclude your own main product names if needed:
        AND LOWER(JSON_EXTRACT_SCALAR(entity, '$.text')) NOT IN ('hotel marrakesh', 'product a')
        GROUP BY 1
        HAVING mentions > 0
        ORDER BY mentions DESC
        LIMIT 10
    """
    df = load_data_from_bq(comp_query)

    if not df.empty:
        st.subheader("Competitor/Entity Sentiment Association")

        chart = (
            alt.Chart(df)
            .mark_circle()
            .encode(
                x=alt.X("mentions", title="Mention Volume"),
                y=alt.Y(
                    "negative_association_pct",
                    axis=alt.Axis(format="%"),
                    title="% Negative Context",
                ),
                size=alt.value(200),
                color=alt.Color("competitor", legend=None),
                tooltip=[
                    "competitor",
                    "mentions",
                    alt.Tooltip("negative_association_pct", format=".1%"),
                ],
            )
            .mark_text(align="left", dx=15)
            .encode(text="competitor")
        )

        st.altair_chart(chart, use_container_width=True)
    else:
        st.warning("No competitor mentions found in the current dataset.")


# # --- Main App Navigation ---
# def main():
#     st.sidebar.title("VoiceLens 🧠")
#     st.sidebar.info("Diagnostic Analytics Dashboard")
#     st.sidebar.markdown("---")

#     # Navigation Menu
#     page = st.sidebar.radio(
#         "Select Insight:",
#         [
#             "1. Root Cause Analysis",
#             "2. Geo Hotspots",
#             "3. Product Features",
#             "4. Emerging Trends",
#             "5. Competitive Intel",
#         ],
#     )

#     if page == "1. Root Cause Analysis":
#         page_root_cause()
#     elif page == "2. Geo Hotspots":
#         page_geo_hotspots()
#     elif page == "3. Product Features":
#         page_product_features()
#     elif page == "4. Emerging Trends":
#         page_emerging_trends()
#     elif page == "5. Competitive Intel":
#         page_competition()


# if __name__ == "__main__":
#     main()
