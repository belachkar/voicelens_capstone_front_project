import os

import altair as alt
import pandas as pd
import streamlit as st

from connect.bq import load_data_from_bq

# --- Setup & Config ---
if "API_URI" in os.environ:
    BASE_URI = st.secrets[os.environ.get("API_URI")]
else:
    BASE_URI = st.secrets.get("cloud_api_uri", "")

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
    *Select a specific time window below to analyze sentiment trends and identify the topics causing drops.*
    """
    )

    # 1. PRE-QUERY: Get dynamic Date Bounds from the database (Post-2021)
    # We run this small query first to know what range to show in the date picker.
    bounds_query = f"""
        SELECT
            MIN(DATE(review_date)) as min_date,
            MAX(DATE(review_date)) as max_date
        FROM {BQ_TABLE_REF}
        WHERE CAST(review_date AS DATE) >= '2021-01-01'
    """
    bounds_df = load_data_from_bq(bounds_query)

    # Set defaults. If DB is empty, fallback to today.
    if not bounds_df.empty and pd.notnull(bounds_df.iloc[0]["min_date"]):
        min_db_date = bounds_df.iloc[0]["min_date"]
        max_db_date = bounds_df.iloc[0]["max_date"]
    else:
        min_db_date = pd.to_datetime("2021-01-01").date()
        max_db_date = pd.to_datetime("today").date()

    # 2. Date Inputs (Dynamic Defaults)
    col1, col2 = st.columns(2)

    start_date = col1.date_input(
        "Start Date", value=min_db_date, min_value=min_db_date, max_value=max_db_date
    )
    end_date = col2.date_input(
        "End Date", value=max_db_date, min_value=min_db_date, max_value=max_db_date
    )

    if start_date > end_date:
        st.error("Error: End date must fall after start date.")
        return

    # 3. Time Series Chart (Dynamic Query)
    # Uses LOWER() for safety and filters >= 2021
    ts_query = f"""
        SELECT
            DATE(review_date) as date,
            COUNT(review_id) as volume,
            SAFE_DIVIDE(COUNTIF(LOWER(predicted_sentiment) = 'negative'), COUNT(review_id)) as negative_rate
        FROM {BQ_TABLE_REF}
        WHERE DATE(review_date) BETWEEN '{start_date}' AND '{end_date}'
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
                    title="Negative Sentiment Rate",
                    scale=alt.Scale(domain=[0, 1.1]),  # Adds 10% breathing room at top
                ),
                tooltip=["date", alt.Tooltip("negative_rate", format=".1%")],
            )
            .add_params(brush)
            .properties(height=300, title="Sentiment Trend over Selected Period")
        )

        st.altair_chart(line, use_container_width=True)

        # 4. Root Cause Topic Query
        st.subheader(f"Top Negative Topics ({start_date} to {end_date})")

        topic_query = f"""
            SELECT
                REPLACE(predicted_topic, 'Topic: ', '') as simple_topic,
                COUNT(review_id) as negative_mentions
            FROM {BQ_TABLE_REF}
            WHERE LOWER(predicted_sentiment) = 'negative'
            AND DATE(review_date) BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY 1
            ORDER BY 2 DESC
            LIMIT 4
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
    else:
        st.warning("No data found for this date range.")


# ==========================================
# 2. GEOGRAPHICAL HOTSPOTS (Location + Sentiment)
# ==========================================
def page_geo_hotspots():
    st.title("🌍 Geographical Hotspots")
    st.markdown("**Goal:** Identify regions with specific support or logistics issues.")

    # FIX: Rewrote SAFE_DIVIDE denominator to ensure non-NULL sentiment is counted.
    geo_query = f"""
        SELECT
            location,
            COUNT(review_id) as total_reviews,
            SAFE_DIVIDE(
                COUNTIF(LOWER(predicted_sentiment) = 'negative'),
                COUNTIF(predicted_sentiment IS NOT NULL)
            ) as negative_pct
        FROM {BQ_TABLE_REF}
        WHERE location IS NOT NULL
          AND LENGTH(location) = 2
          --AND REGEXP_CONTAINS(location, r'^[A-Z]{{2}}$')
          --AND CAST(review_date AS DATE) >= '2021-01-01'
        GROUP BY 1
        HAVING total_reviews > 0
        ORDER BY negative_pct DESC
        --LIMIT 20
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
                    scale=alt.Scale(domain=[0, 1.05]),
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

        # # Option A — Vertical Expansion + Scrollable Chart (Best UX in Streamlit)
        # # FIXED height chart (doesn’t expand)
        # chart = (
        #     alt.Chart(geo_df)
        #     .mark_bar()
        #     .encode(
        #         x=alt.X(
        #             "negative_pct",
        #             axis=alt.Axis(format="%"),
        #             title="% Negative Reviews",
        #             scale=alt.Scale(domain=[0, 1.05]),
        #         ),
        #         y=alt.Y("location:N", sort="-x", title="Location"),
        #         color=alt.Color("negative_pct:Q", scale=alt.Scale(scheme="reds")),
        #         tooltip=[
        #             "location",
        #             "total_reviews",
        #             alt.Tooltip("negative_pct:Q", format=".1%"),
        #         ],
        #     )
        #     .properties(width="container", height=2500)   # <— increased height
        # )

        # # scrollable container
        # st.markdown("""
        # <div style="height:700px; overflow-y: scroll; border:1px solid #ddd; padding:10px;">
        # """, unsafe_allow_html=True)

        # st.altair_chart(chart, use_container_width=True)
        # st.markdown("</div>", unsafe_allow_html=True)

        # # Option B — Switch to a Choropleth Map (Best visualization for many regions)
        # import altair as alt
        # from vega_datasets import data

        # countries = data.world_110m()
        # geojson = alt.topo_feature(countries, "countries")

        # df_geo = geo_df.rename(columns={"location": "id"})  # id must match ISO code

        # chart = alt.Chart(geojson).mark_geoshape().encode(
        #     color=alt.Color("negative_pct:Q", scale=alt.Scale(scheme="reds"), title="% Negative"),
        #     tooltip=["id:N", alt.Tooltip("negative_pct:Q", format=".1%"), "total_reviews:Q"]
        # ).transform_lookup(
        #     lookup="id",
        #     from_=alt.LookupData(df_geo, "id", ["negative_pct", "total_reviews"])
        # ).properties(
        #     width="container",
        #     height=550
        # ).project("naturalEarth1")

        # st.altair_chart(chart, use_container_width=True)

        # # Option C — Paginated Table + Sparkline (Super clean)
        # st.dataframe(
        #     geo_df.sort_values("negative_pct", ascending=False)
        #         .style.background_gradient(subset=["negative_pct"], cmap="Reds")
        # )

        # Worst Location Information
        worst_loc = geo_df.iloc[0]["location"]
        st.warning(
            f"📍 **Action Required:** **{worst_loc}** is showing the highest rate of customer dissatisfaction."
        )
    else:
        st.warning(
            "No valid location data found (looking for 2-letter country codes post-2021)."
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

    # --- UPDATED QUERY FOR NEW DATA FORMAT ---
    # New Format: [('text', 'LABEL'), ('text', 'LABEL')]
    # Method: Use REGEXP_EXTRACT_ALL to find the 'text' where the label is PRODUCT or METRIC.
    # Pattern explanation: \('([^']*)', '(?:PRODUCT|METRIC)'\)
    #   \('      -> matches literal ('
    #   ([^']*)  -> Capture Group 1: Matches the text (assuming no internal single quotes)
    #   ', '     -> matches literal ', '
    #   (?:...)  -> Non-capturing group for OR logic
    #   '\)      -> matches literal ')

    feature_query = f"""
        SELECT
            TRIM(LOWER(matches)) as feature,
            COUNT(*) as mentions,
            SAFE_DIVIDE(COUNTIF(predicted_sentiment = 'positive'), COUNT(*)) as positive_pct
        FROM {BQ_TABLE_REF},
        UNNEST(REGEXP_EXTRACT_ALL(extracted_entities, r"\('([^']*)', '(?:PRODUCT|METRIC)'\)")) as matches
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

        # 2. Display Best 3 and Lowest 3
        col1, col2 = st.columns(2)

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
            bottom_3 = df_sorted.tail(3).sort_values(by="positive_pct", ascending=True)
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

    # Using CAST(review_date as DATE) to be safe with DATETIME comparison
    trend_query = f"""
        WITH recent_stats AS (
            SELECT predicted_topic, COUNT(review_id) as vol_recent
            FROM {BQ_TABLE_REF}
            WHERE CAST(review_date AS DATE) >= '2024-09-01'
            GROUP BY 1
        ),
        past_stats AS (
            SELECT predicted_topic, COUNT(review_id) as vol_past
            FROM {BQ_TABLE_REF}
            WHERE CAST(review_date AS DATE) < '2024-09-01'
            GROUP BY 1
        )
        SELECT
            REPLACE(r.predicted_topic, 'Topic: ', '') as simple_topic,
            r.vol_recent,
            COALESCE(p.vol_past, 1) as vol_past,
            SAFE_DIVIDE((r.vol_recent - COALESCE(p.vol_past, 0)), COALESCE(p.vol_past, 1)) as growth_rate
        FROM recent_stats r
        LEFT JOIN past_stats p ON r.predicted_topic = p.predicted_topic
        WHERE r.vol_recent > 0
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

    # --- UPDATED QUERY FOR NEW DATA FORMAT ---
    # Pattern: \('([^']*)', '(?:ORG|TEAM|PRODUCT)'\)
    # Captures text where label is ORG, TEAM, or PRODUCT
    comp_query = f"""
        SELECT
            TRIM(matches) as competitor,
            COUNT(*) as mentions,
            SAFE_DIVIDE(COUNTIF(predicted_sentiment = 'negative'), COUNT(*)) as negative_association_pct
        FROM {BQ_TABLE_REF},
        UNNEST(REGEXP_EXTRACT_ALL(extracted_entities, r"\('([^']*)', '(?:ORG|TEAM|PRODUCT)'\)")) as matches
        WHERE LOWER(matches) NOT LIKE '%voicelens%'
        -- Exclude your own main product names if needed:
        AND LOWER(matches) NOT IN ('hotel marrakesh', 'product a')
        GROUP BY 1
        HAVING mentions > 0
        ORDER BY mentions DESC
        LIMIT 10
    """
    df = load_data_from_bq(comp_query)

    if not df.empty:
        st.subheader("Competitor/Entity Sentiment Association")

        # chart = (
        #     alt.Chart(df)
        #     .mark_circle()
        #     .encode(
        #         x=alt.X("mentions", title="Mention Volume"),
        #         y=alt.Y(
        #             "negative_association_pct",
        #             axis=alt.Axis(format="%"),
        #             title="% Negative Context",
        #         ),
        #         size=alt.value(200),
        #         color=alt.Color("competitor", legend=None),
        #         tooltip=[
        #             "competitor",
        #             "mentions",
        #             alt.Tooltip("negative_association_pct", format=".1%"),
        #         ],
        #     )
        #     .mark_text(align="left", dx=15)
        #     .encode(text="competitor")
        # )
        # st.altair_chart(chart, use_container_width=True)

        # # Chart: Option 1 — Bubble Chart With Non-Overlapping Labels (Tooltips Only)
        # chart = (
        #     alt.Chart(df)
        #     .mark_circle(opacity=0.7)
        #     .encode(
        #         x=alt.X("mentions", title="Mention Volume"),
        #         y=alt.Y("negative_association_pct", title="% Negative Context", axis=alt.Axis(format="%")),
        #         size=alt.Size("mentions", scale=alt.Scale(range=[100, 1500])),
        #         color=alt.Color("competitor:N", title="Competitor"),
        #         tooltip=[
        #             alt.Tooltip("competitor:N", title="Competitor"),
        #             alt.Tooltip("mentions:Q", title="Mentions"),
        #             alt.Tooltip("negative_association_pct:Q", title="Neg. %", format=".1%"),
        #         ],
        #     )
        # ).properties(height=450)

        # st.altair_chart(chart, use_container_width=True)

        # # Chart: Option 2 — Bubble Chart With Labels Inside Circles
        # base = alt.Chart(df).encode(
        #     x=alt.X("mentions", title="Mention Volume"),
        #     y=alt.Y("negative_association_pct", title="% Negative Context", axis=alt.Axis(format="%")),
        # )

        # circles = base.mark_circle(opacity=0.6).encode(
        #     size=alt.Size("mentions", scale=alt.Scale(range=[200, 1800])),
        #     color=alt.Color("competitor:N", legend=None),
        # )

        # labels = base.mark_text(
        #     dy=2,  # slight downward offset
        #     fontSize=10,
        #     fontWeight="bold",
        #     color="white",
        # ).encode(text="competitor:N")

        # chart = (circles + labels).properties(height=450)

        # st.altair_chart(chart, use_container_width=True)
        # Chart: Option 3 — Horizontal Bar Chart (Best readability if many competitors)
        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadius=4)
            .encode(
                y=alt.Y("competitor:N", sort="-x", title="Competitor"),
                x=alt.X("mentions:Q", title="Mention Volume"),
                color=alt.Color("negative_association_pct:Q", scale=alt.Scale(scheme="reds")),
                tooltip=[
                    "competitor",
                    "mentions",
                    alt.Tooltip("negative_association_pct", format=".1%"),
                ],
            )
        ).properties(height=450)

        st.altair_chart(chart, use_container_width=True)

        # Option 4 — Scatter Plot With Force-Directed Label Layout (Best but more code)
        base = alt.Chart(df).encode(
            x=alt.X("mentions", title="Mention Volume"),
            y=alt.Y("negative_association_pct", title="% Negative Context", axis=alt.Axis(format="%"))
        )

        points = base.mark_circle(size=250, opacity=0.6).encode(
            color="competitor:N",
            tooltip=["competitor", "mentions", alt.Tooltip("negative_association_pct", format=".1%")],
        )

        labels = base.mark_text(
            align="left",
            dx=10,
            dy=0,
            fontSize=10,
            fontWeight="bold",
        ).encode(text="competitor")

        chart = (points + labels).properties(height=450)

        st.altair_chart(chart, use_container_width=True)


    else:
        st.warning("No competitor mentions found in the current dataset.")
