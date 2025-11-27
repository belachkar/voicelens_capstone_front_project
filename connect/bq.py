import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account


@st.cache_resource
def init_connection():
    """
    Creates a BigQuery client using the JSON key file path.
    """
    # # Create credentials object from the file path
    # credentials = service_account.Credentials.from_service_account_file(
    #     gcp_sa_path,
    #     scopes=["https://www.googleapis.com/auth/cloud-platform"],
    # )

    project_id = None
    credentials = None
    # Streamlit Cloud case: secrets contain the JSON as a dict
    if "gcp_service_account" in st.secrets:
        service_account_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

        project_id = service_account_info["project_id"]

    else:
        # Local development case: secrets contain only a file path
        gcp_sa_path = st.secrets["GOOGLE_APPLICATION_CREDENTIALS"]

        credentials = service_account.Credentials.from_service_account_file(
            gcp_sa_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

        project_id = credentials.project_id


    # Initialize client with these credentials
    client = bigquery.Client(
        credentials=credentials,
        project=project_id,
        location="europe-west1",
    )
    return client


# --- Data Loading Function (Caches results for performance) ---
@st.cache_data(ttl=600)
def load_data_from_bq(query):
    """
    Runs the SQL query and returns a Pandas DataFrame.
    """
    try:
        client = init_connection()

        # Execute the query
        query_job = client.query(query)

        # Convert directly to DataFrame (most efficient method)
        df = query_job.to_dataframe()
        return df

    except Exception as e:
        st.error(f"Error connecting to BigQuery: {e}")
        st.stop()
