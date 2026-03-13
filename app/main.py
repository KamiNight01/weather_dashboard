from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
import altair as alt
from streamlit_autorefresh import st_autorefresh


@st.cache_data(ttl=600)
def fetch_json(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, timeout=12)
    if r.status_code == 401:
        raise RuntimeError(f"Unauthorized (401): {r.text}")
    r.raise_for_status()
    return r.json()


def get_api_key() -> Optional[str]:
    try:
        key = st.secrets.get("OPENWEATHER_API_KEY")
        if key:
            return str(key).strip()
    except Exception:
        pass
    key = os.getenv("OPENWEATHER_API_KEY")
    return key.strip() if key else None


def geocode_city(city: str, api_key: str) -> Optional[Tuple[float, float, str, str]]:
    url = "https://api.openweathermap.org/geo/1.0/direct"
    data = fetch_json(url, {"q": city, "limit": 1, "appid": api_key})
    if not data:
        return None
    d = data[0]
    return float(d["lat"]), float(d["lon"]), d.get("name", city), d.get("country", "")


def get_current(lat: float, lon: float, units: str, api_key: str) -> dict:
    url = "https://api.openweathermap.org/data/2.5/weather"
    return fetch_json(url, {"lat": lat, "lon": lon, "appid": api_key, "units": units})


def get_forecast(lat: float, lon: float, units: str, api_key: str) -> dict:
    url = "https://api.openweathermap.org/data/2.5/forecast"

    return fetch_json(
        url,
        {
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": units,
        },
    )

def forecast_to_df(forecast_json: dict) -> tuple[pd.DataFrame, int]:

    tz_offset = int((forecast_json.get("city") or {}).get("timezone", 0))
    rows = []

    for item in forecast_json.get("list", []):

        main = item.get("main", {}) or {}
        wind = item.get("wind", {}) or {}
        rain_3h = float(((item.get("rain") or {}).get("3h", 0.0)) or 0.0)
        snow_3h = float(((item.get("snow") or {}).get("3h", 0.0)) or 0.0)
        weather = (item.get("weather") or [{}])[0] or {}

        dt_utc = pd.to_datetime(item.get("dt_txt"), utc=True)
        dt_local = dt_utc + pd.to_timedelta(tz_offset, unit="s")

        rows.append(
            {
                "time_utc": dt_utc,
                "time_local": dt_local,
                "date_local": dt_local.date(),
                "hour_local": dt_local.hour,
                "temp": main.get("temp"),
                "feels_like": main.get("feels_like"),
                "temp_min": main.get("temp_min"),
                "temp_max": main.get("temp_max"),
                "humidity": main.get("humidity"),
                "wind": wind.get("speed"),
                "rain_mm": rain_3h,
                "snow_mm": snow_3h,
                "precip_mm": rain_3h + snow_3h,
                "condition": weather.get("main"),
                "description": weather.get("description"),
                "icon": weather.get("icon"),
            }
        )

    df = pd.DataFrame(rows)

    if df.empty:
        return df, tz_offset

    return df.sort_values("time_utc"), tz_offset
    

def inject_css():
    st.markdown(
        """
        <style>
          .block-container { padding-top: 1.05rem; padding-bottom: 1.6rem; max-width: 1350px; }
          h1 { font-size: 2.05rem; margin-bottom: 0.1rem; }
          .stMarkdown p { margin-bottom: 0.25rem; }

          /* Card look */
          div[data-testid="stContainer"][data-border="true"]{
            border: 1px solid rgba(49, 51, 63, 0.12);
            border-radius: 14px;
            padding: 0.85rem 0.9rem 0.75rem 0.9rem;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
            background: rgba(255,255,255,0.6);
          }

          /* Metrics */
          div[data-testid="stMetric"] { padding: 0.05rem 0.05rem; }
          div[data-testid="stMetricLabel"] { opacity: 0.75; }
          div[data-testid="stMetricValue"] { font-size: 1.5rem; }

          /* Dataframe corners */
          div[data-testid="stDataFrame"]{ border-radius: 12px; overflow: hidden; }

          /* Tighten tabs a bit */
          button[role="tab"] { padding-top: 0.25rem; padding-bottom: 0.25rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def style_forecast_table(df_day: pd.DataFrame, units: str):
    unit_temp = "°F" if units == "imperial" else "°C"
    unit_wind = "mph" if units == "imperial" else "m/s"

    show = df_day.copy()
    show["time"] = pd.to_datetime(show["time_base"]).dt.strftime("%a %I:%M %p")
    show = show[
        ["time", "temp", "feels_like", "humidity", "wind", "precip_mm", "condition", "description"]
    ].rename(
        columns={
            "temp": f"temp ({unit_temp})",
            "feels_like": f"feels ({unit_temp})",
            "humidity": "humidity (%)",
            "wind": f"wind ({unit_wind})",
            "precip_mm": "precip (mm)",
        }
    )

    return (
        show.style
        .background_gradient(subset=[f"temp ({unit_temp})", f"feels ({unit_temp})"], cmap="RdYlBu_r")
        .background_gradient(subset=["humidity (%)"], cmap="YlGnBu")
        .background_gradient(subset=[f"wind ({unit_wind})"], cmap="PuBu")
        .bar(subset=["precip (mm)"], color="#9ecae1")
        .format(precision=1)
    )


def utc_window_for_local_day(local_day: Any, tz_offset_seconds: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    Convert a base city's *local day* (date) into a [start_utc, end_utc) 24h window.
    local_day is a datetime.date.
    """
    start_local_naive = pd.Timestamp(local_day)  # midnight local (naive)
    start_utc = (start_local_naive - pd.to_timedelta(tz_offset_seconds, unit="s")).tz_localize("UTC")
    end_utc = start_utc + pd.Timedelta(hours=24)
    return start_utc, end_utc


# Main app
def run():
    st_autorefresh(interval=60000, key="weather_refresh")
    st.set_page_config(page_title="Weather Dashboard", page_icon="🌤️", layout="wide")
    inject_css()

    api_key = get_api_key()
    if not api_key:
        st.error("Missing OPENWEATHER_API_KEY (set env var or .streamlit/secrets.toml).")
        st.stop()

    # Session defaults
    if "searched" not in st.session_state:
        st.session_state.searched = False
    if "collapse_settings" not in st.session_state:
        st.session_state.collapse_settings = False
    if "city" not in st.session_state:
        st.session_state.city = "Columbus, OH"
    if "selected_date" not in st.session_state:
        st.session_state.selected_date = None
    if "compare_enabled" not in st.session_state:
        st.session_state.compare_enabled = False
    if "compare_city" not in st.session_state:
        st.session_state.compare_city = ""

    st.title("🌤️ Weather Dashboard")
    st.caption("Search a location for weather updates.")

    
    top1, top2 = st.columns([3, 1], gap="medium")
    with top1:
        city = st.text_input("Location", value=st.session_state.city, placeholder="Start typing a city…")
    with top2:
        search_clicked = st.button("Search", use_container_width=True)

    if search_clicked:
        st.session_state.city = city.strip() if city.strip() else st.session_state.city
        st.session_state.searched = True
        st.session_state.collapse_settings = True  

  
    with st.expander("Settings", expanded=not st.session_state.collapse_settings):
        s1, s2, s3 = st.columns([1, 1, 2], gap="medium")
        with s2:
            st.session_state.compare_enabled = st.checkbox("Enable compare", value=st.session_state.compare_enabled)
        with s3:
            st.session_state.compare_city = st.text_input(
                "Compare city",
                value=st.session_state.compare_city,
                placeholder="e.g., Seattle, WA",
                disabled=not st.session_state.compare_enabled,
            )
            


    # If user hasn't searched yet, still proceed with the default city 
    city = st.session_state.city
    units = "imperial"


    # Fetch base city
    geo = geocode_city(city, api_key)
    if not geo:
        st.warning("City not found. Try a different spelling.", icon="⚠️")
        st.stop()

    lat, lon, name, country = geo
    current = get_current(lat, lon, units, api_key)
    forecast = get_forecast(lat, lon, units, api_key)
    df, base_tz_offset = forecast_to_df(forecast)

    if df.empty:
        st.warning("No forecast data returned.")
        st.stop()

    available_dates = sorted(df["date_local"].unique().tolist())
    if st.session_state.selected_date is None or st.session_state.selected_date not in available_dates:
        st.session_state.selected_date = available_dates[0]

    # Date picker stays in the info area (not in settings) so it’s easy, but still compact
    dcol1, dcol2, dcol3 = st.columns([1.2, 1.2, 2.6], gap="medium")
    with dcol1:
        selected_date = st.selectbox(
            "Forecast day (local)",
            available_dates,
            index=available_dates.index(st.session_state.selected_date),
            format_func=lambda d: pd.to_datetime(d).strftime("%a, %b %d"),
        )
    with dcol2:
        st.write("") 
        st.caption(f"**{name}, {country}**")
    with dcol3:
        st.write("")  
        st.caption(current["weather"][0]["description"].title())

    st.session_state.selected_date = selected_date

    # Build a 24h window and base-day slice 
    start_utc, end_utc = utc_window_for_local_day(selected_date, base_tz_offset)

    base_24h = df[(df["time_utc"] >= start_utc) & (df["time_utc"] < end_utc)].copy()
    if base_24h.empty:
        st.warning("No forecast points for that day (try another date).")
        st.stop()

    # “time_base” = UTC converted to the base city's local time for a consistent x-axis
    base_24h["time_base"] = base_24h["time_utc"] + pd.to_timedelta(base_tz_offset, unit="s")

    unit_temp = "°F" if units == "imperial" else "°C"
    unit_wind = "mph" if units == "imperial" else "m/s"


    # Metrics row 

    m0, m1, m2, m3, m4 = st.columns(5, gap="medium")
    m0.metric("Current Temp", f"{current['main']['temp']:.1f} {unit_temp}")
    m1.metric("Max Temp", f"{base_24h['temp_max'].max():.1f} {unit_temp}")
    m2.metric("Min Temp", f"{base_24h['temp_min'].min():.1f} {unit_temp}")
    m3.metric("Precip", f"{base_24h['precip_mm'].sum():.1f} mm")
    m4.metric("Wind", f"{base_24h['wind'].mean():.1f} {unit_wind}")


    compare_24h = None
    if st.session_state.compare_enabled and st.session_state.compare_city.strip():
        g2 = geocode_city(st.session_state.compare_city.strip(), api_key)
        if g2:
            la, lo, n2, c2 = g2
            f2 = get_forecast(la, lo, units, api_key)
            d2, _tz2 = forecast_to_df(f2)

            d2_utc = d2[(d2["time_utc"] >= start_utc) & (d2["time_utc"] < end_utc)].copy()
            if not d2_utc.empty:
                d2_utc["time_base"] = d2_utc["time_utc"] + pd.to_timedelta(base_tz_offset, unit="s")
                d2_utc["series"] = f"{n2}, {c2}"
                compare_24h = d2_utc

    base_24h["series"] = f"{name}, {country}"


    tab_charts, tab_breakdown, tab_table = st.tabs(["Charts", "Breakdown", "Table"])

    CHART_H = 200

    with tab_charts:
        # Temperature: range + line
        temp_base = base_24h.dropna(subset=["time_base", "temp", "temp_min", "temp_max"]).copy()

        temp_range = (
            alt.Chart(temp_base)
            .mark_rule()
            .encode(
                x=alt.X("time_base:T", title="time"),
                y=alt.Y("temp_min:Q", title=f"temp ({unit_temp})"),
                y2="temp_max:Q",
                tooltip=[
                    alt.Tooltip("time_base:T", title="time"),
                    alt.Tooltip("temp:Q", title="temp"),
                    alt.Tooltip("feels_like:Q", title="feels"),
                    alt.Tooltip("temp_min:Q", title="min"),
                    alt.Tooltip("temp_max:Q", title="max"),
                    alt.Tooltip("description:N", title="weather"),
                ],
            )
            .properties(height=CHART_H)
        )
        temp_line = (
            alt.Chart(temp_base)
            .mark_line()
            .encode(
                x="time_base:T",
                y="temp:Q",
                tooltip=["time_base:T", "temp:Q", "feels_like:Q", "description:N"],
            )
            .properties(height=CHART_H)
        )
        temp_chart = (temp_range + temp_line).interactive()

        # Wind
        wind_chart = (
            alt.Chart(base_24h.dropna(subset=["time_base", "wind"]))
            .mark_line()
            .encode(
                x=alt.X("time_base:T", title="time"),
                y=alt.Y("wind:Q", title=f"wind ({unit_wind})"),
                tooltip=["time_base:T", "wind:Q"],
            )
            .properties(height=CHART_H)
            .interactive()
        )

        # Humidity
        humid_chart = (
            alt.Chart(base_24h.dropna(subset=["time_base", "humidity"]))
            .mark_line()
            .encode(
                x=alt.X("time_base:T", title="time"),
                y=alt.Y("humidity:Q", title="humidity (%)"),
                tooltip=["time_base:T", "humidity:Q"],
            )
            .properties(height=CHART_H)
            .interactive()
        )

        # Precipitation
        p = base_24h.copy()
        p["label"] = pd.to_datetime(p["time_base"]).dt.strftime("%I %p")
        precip_chart = (
            alt.Chart(p)
            .mark_bar()
            .encode(
                x=alt.X("label:N", title="time"),
                y=alt.Y("precip_mm:Q", title="precip (mm)"),
                tooltip=["time_base:T", "rain_mm:Q", "snow_mm:Q", "precip_mm:Q"],
            )
            .properties(height=CHART_H)
        )

        r1c1, r1c2 = st.columns(2, gap="medium")
        with r1c1:
            with st.container(border=True):
                st.markdown("#### Temperature")
                st.altair_chart(temp_chart, use_container_width=True)
        with r1c2:
            with st.container(border=True):
                st.markdown("#### Wind")
                st.altair_chart(wind_chart, use_container_width=True)

        r2c1, r2c2 = st.columns(2, gap="medium")
        with r2c1:
            with st.container(border=True):
                st.markdown("#### Humidity")
                st.altair_chart(humid_chart, use_container_width=True)
        with r2c2:
            with st.container(border=True):
                st.markdown("#### Precipitation")
                st.altair_chart(precip_chart, use_container_width=True)

        if compare_24h is not None:
            overlay = pd.concat([base_24h, compare_24h], ignore_index=True)

            with st.container(border=True):
                st.markdown("#### Compare: Temperature overlay")
                overlay_chart = (
                    alt.Chart(overlay.dropna(subset=["time_base", "temp"]))
                    .mark_line()
                    .encode(
                        x=alt.X("time_base:T", title="time"),
                        y=alt.Y("temp:Q", title=f"temp ({unit_temp})"),
                        color=alt.Color("series:N", scale=alt.Scale(scheme="tableau10")),
                        tooltip=["series:N", "time_base:T", "temp:Q", "description:N"],
                    )
                    .properties(height=240)
                    .interactive()
                )
                st.altair_chart(overlay_chart, use_container_width=True)
        elif st.session_state.compare_enabled and st.session_state.compare_city.strip():
            st.info("Compare is enabled, but there were no matching forecast points in the selected 24-hour window.")

    # --- Breakdown tab ---
    with tab_breakdown:
        b1, b2 = st.columns([1, 1], gap="medium")

        with b1:
            with st.container(border=True):
                st.markdown("#### Weather distribution")
                dist = (
                    base_24h.dropna(subset=["condition"])
                    .groupby("condition")
                    .size()
                    .reset_index(name="count")
                    .sort_values("count", ascending=False)
                )
                pie = (
                    alt.Chart(dist)
                    .mark_arc()
                    .encode(
                        theta="count:Q",
                        color=alt.Color("condition:N", scale=alt.Scale(scheme="tableau10")),
                        tooltip=["condition:N", "count:Q"],
                    )
                    .properties(height=260)
                )
                st.altair_chart(pie, use_container_width=True)

        with b2:
            with st.container(border=True):
                st.markdown("#### Quick statistics:")
                most_common = (
                    base_24h["condition"].dropna().value_counts().idxmax()
                    if base_24h["condition"].notna().any()
                    else "—"
                )
                st.write(f"**Most common:** {most_common}")
                st.write(f"**Peak wind:** {base_24h['wind'].max():.1f} {unit_wind}")
                st.write(f"**Max humidity:** {base_24h['humidity'].max():.0f}%")
                st.write(f"**Total precip:** {base_24h['precip_mm'].sum():.1f} mm")

    # --- Table tab ---
    with tab_table:
        with st.container(border=True):
            st.markdown("#### Forecast table")
            st.dataframe(style_forecast_table(base_24h, units), use_container_width=True, hide_index=True)

