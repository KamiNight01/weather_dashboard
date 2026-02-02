import streamlit as st

st.set_page_config(
    page_title="Weather Dashboard",
    page_icon="🌤️",
    layout="wide",
)

st.title("🌤️ Weather Dashboard")
st.caption("Search a location from your database and view live weather + insights.")

left, right = st.columns([1, 2], gap="large")

with left:
    st.subheader("Search")
    st.text_input("Location", placeholder="Start typing a city…")
    st.info("Next: connect this search to your SQLite locations table.")

with right:
    st.subheader("Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Max Temp", "— °C")
    c2.metric("Min Temp", "— °C")
    c3.metric("Precipitation", "— mm")
    c4.metric("Wind", "— m/s")

    st.divider()
    st.subheader("Charts")
    st.write("Next: temperature / wind / precipitation charts once we pull data.")
