import streamlit as st

from connect.bq import init_connection


# Add this temporarily to check table names
def list_tables_debug():
    client = init_connection()
    dataset_id = "wagon-bootcamp-2106.voicelens"  # Hardcoded for safety

    try:
        tables = client.list_tables(dataset_id)
        st.write(f"Tables found in {dataset_id}:")
        found_tables = []
        for table in tables:
            st.write(f"- `{table.table_id}`")
            found_tables.append(table.table_id)

        if not found_tables:
            st.error("❌ No tables found in this dataset!")

    except Exception as e:
        st.error(f"Error listing tables: {e}")
