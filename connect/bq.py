import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

gcp_sa_path = st.secrets["GOOGLE_APPLICATION_CREDENTIALS"]
# print(credentials)


@st.cache_resource
def init_connection():
    """
    Creates a BigQuery client using the JSON key file path.
    """
    # Create credentials object from the file path
    credentials = service_account.Credentials.from_service_account_file(
        gcp_sa_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )

    # Initialize client with these credentials
    client = bigquery.Client(
        credentials=credentials,
        project=credentials.project_id,
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
