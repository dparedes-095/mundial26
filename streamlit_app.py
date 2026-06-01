import os
import html
import calendar

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from zoneinfo import ZoneInfo


st.set_page_config(
    page_title="World Cup 2026 Calendar",
    page_icon="🏆",
    layout="wide"
)

BASE_URL = "https://v3.football.api-sports.io"

WORLD_CUP_LEAGUE_ID = 1
WORLD_CUP_SEASON = 2026
LOCAL_TIMEZONE = "America/New_York"


def get_api_key():
    try:
        key = st.secrets.get("API_FOOTBALL_KEY")
    except Exception:
        key = None

    return key or os.getenv("API_FOOTBALL_KEY")


API_KEY = get_api_key()


@st.cache_data(ttl=60 * 30)
def fetch_world_cup_fixtures():
    url = f"{BASE_URL}/fixtures"

    params = {
        "league": WORLD_CUP_LEAGUE_ID,
        "season": WORLD_CUP_SEASON
    }

    headers = {
        "x-apisports-key": API_KEY
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=20
    )

    response.raise_for_status()
    return response.json()


def safe_text(value, fallback=""):
    if pd.isna(value):
        return fallback

    text = str(value).strip()

    if not text or text.lower() == "nan":
        return fallback

    return text


def normalize_fixtures(api_result):
    fixtures = api_result.get("response", [])
    rows = []

    local_tz = ZoneInfo(LOCAL_TIMEZONE)

    for item in fixtures:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})

        fixture_date = fixture.get("date")

        if not fixture_date:
            continue

        kickoff_utc = pd.to_datetime(fixture_date, utc=True)
        kickoff_local = kickoff_utc.tz_convert(local_tz)

        home = teams.get("home", {}) or {}
        away = teams.get("away", {}) or {}
        status = fixture.get("status", {}) or {}
        venue = fixture.get("venue", {}) or {}

        rows.append({
            "fixture_id": fixture.get("id"),
            "date": kickoff_local.date(),
            "time": kickoff_local.strftime("%I:%M %p").lstrip("0"),
            "datetime_local": kickoff_local,

            "round": safe_text(league.get("round"), "Round TBD"),

            "home_team": safe_text(home.get("name"), "TBD"),
            "away_team": safe_text(away.get("name"), "TBD"),
            "home_logo": home.get("logo"),
            "away_logo": away.get("logo"),

            "home_goals": goals.get("home"),
            "away_goals": goals.get("away"),

            "status_short": safe_text(status.get("short")),
            "status_long": safe_text(status.get("long"), "Scheduled"),

            "venue": safe_text(venue.get("name")),
            "city": safe_text(venue.get("city")),
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("datetime_local")

    return df


def build_match_title(row):
    home_team = safe_text(row.get("home_team"), "TBD")
    away_team = safe_text(row.get("away_team"), "TBD")

    home_goals = row.get("home_goals")
    away_goals = row.get("away_goals")

    if pd.notna(home_goals) and pd.notna(away_goals):
        return f"{home_team} {int(home_goals)} - {int(away_goals)} {away_team}"

    return f"{home_team} vs {away_team}"


def get_game_bucket(row):
    status = safe_text(row.get("status_short"))

    live_statuses = {"1H", "HT", "2H", "ET", "P", "LIVE"}
    complete_statuses = {"FT", "AET", "PEN"}

    if status in live_statuses:
        return "Live"
    elif status in complete_statuses:
        return "Results"
    else:
        return "Upcoming"


def build_location(row):
    location_parts = []

    venue = safe_text(row.get("venue"))
    city = safe_text(row.get("city"))

    if venue:
        location_parts.append(venue)

    if city:
        location_parts.append(city)

    return ", ".join(location_parts) if location_parts else "Venue TBD"


def apply_filters(fixtures_df, selected_date_range, selected_team, selected_round, selected_bucket):
    filtered_df = fixtures_df.copy()

    if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
        filtered_df = filtered_df[
            (filtered_df["date"] >= start_date)
            & (filtered_df["date"] <= end_date)
        ]

    if selected_team != "All teams":
        filtered_df = filtered_df[
            (filtered_df["home_team"] == selected_team)
            | (filtered_df["away_team"] == selected_team)
        ]

    if selected_round != "All rounds":
        filtered_df = filtered_df[filtered_df["round"] == selected_round]

    if selected_bucket != "All":
        filtered_df = filtered_df[filtered_df["bucket"] == selected_bucket]

    return filtered_df


def render_match_list(filtered_df):
    st.subheader("📅 Match Calendar")

    if filtered_df.empty:
        st.warning("No matches match your filters.")
        return

    for match_date, day_df in filtered_df.groupby("date"):
        pretty_date = pd.to_datetime(match_date).strftime("%A, %B %d, %Y")
        st.markdown(f"### {pretty_date}")

        for _, row in day_df.iterrows():
            match_title = build_match_title(row)
            location = build_location(row)

            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1.2, 2])

                with col1:
                    logo_col1, text_col, logo_col2 = st.columns([0.4, 2.5, 0.4])

                    with logo_col1:
                        home_logo = row.get("home_logo")
                        if pd.notna(home_logo) and home_logo:
                            st.image(home_logo, width=36)

                    with text_col:
                        st.markdown(f"**{match_title}**")
                        st.caption(safe_text(row.get("round"), "Round TBD"))

                    with logo_col2:
                        away_logo = row.get("away_logo")
                        if pd.notna(away_logo) and away_logo:
                            st.image(away_logo, width=36)

                with col2:
                    st.markdown(f"**{safe_text(row.get('time'), 'Time TBD')}**")
                    st.caption(LOCAL_TIMEZONE)

                with col3:
                    st.markdown(location)
                    st.caption(
                        safe_text(row.get("status_long"))
                        or safe_text(row.get("status_short"))
                        or "Scheduled"
                    )


def get_grid_filtered_df(fixtures_df):
    available_months = (
        fixtures_df[["date"]]
        .assign(month=lambda x: pd.to_datetime(x["date"]).dt.to_period("M").astype(str))
        ["month"]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    if not available_months:
        return None, None, None

    col1, col2 = st.columns([1, 2])

    with col1:
        selected_month = st.selectbox(
            "Month",
            options=available_months,
            format_func=lambda x: pd.to_datetime(x + "-01").strftime("%B %Y")
        )

    with col2:
        calendar_team_options = sorted(
            set(fixtures_df["home_team"].dropna().tolist())
            | set(fixtures_df["away_team"].dropna().tolist())
        )

        calendar_team = st.selectbox(
            "Team filter",
            options=["All teams"] + calendar_team_options
        )

    calendar_df = fixtures_df.copy()

    if calendar_team != "All teams":
        calendar_df = calendar_df[
            (calendar_df["home_team"] == calendar_team)
            | (calendar_df["away_team"] == calendar_team)
        ]

    month_df = calendar_df[
        pd.to_datetime(calendar_df["date"]).dt.to_period("M").astype(str) == selected_month
    ]

    return selected_month, calendar_team, month_df


def render_matchday_mobile_list(month_df):
    if month_df.empty:
        st.warning("No matches for this month/team filter.")
        return

    for match_date, day_df in month_df.groupby("date"):
        pretty_date = pd.to_datetime(match_date).strftime("%A, %B %d")
        st.markdown(f"### {pretty_date}")

        for _, row in day_df.sort_values("datetime_local").iterrows():
            match_title = build_match_title(row)
            location = build_location(row)

            with st.container(border=True):
                c1, c2 = st.columns([1, 4])

                with c1:
                    st.markdown(f"**{safe_text(row.get('time'), 'Time TBD')}**")

                with c2:
                    st.markdown(f"**{match_title}**")
                    st.caption(f"{safe_text(row.get('round'), 'Round TBD')} · {location}")


def render_matchday_grid(month_df, selected_month):
    if month_df.empty:
        st.warning("No matches for this month/team filter.")
        return

    selected_year, selected_month_num = map(int, selected_month.split("-"))

    matches_by_date = {
        match_date: day_df.sort_values("datetime_local")
        for match_date, day_df in month_df.groupby("date")
    }

    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdatescalendar(selected_year, selected_month_num)

    day_headers = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    calendar_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {
                margin: 0;
                font-family: Arial, Helvetica, sans-serif;
                color: #f5f5f5;
                background: transparent;
            }

            .wc-calendar-grid {
                display: grid;
                grid-template-columns: repeat(7, minmax(0, 1fr));
                gap: 8px;
                width: 100%;
                box-sizing: border-box;
            }

            .wc-calendar-header {
                font-weight: 700;
                text-align: center;
                padding: 8px;
                border-radius: 8px;
                background: rgba(128, 128, 128, 0.22);
                box-sizing: border-box;
            }

            .wc-calendar-day {
                min-height: 170px;
                padding: 8px;
                border: 1px solid rgba(128, 128, 128, 0.35);
                border-radius: 10px;
                background: rgba(128, 128, 128, 0.08);
                box-sizing: border-box;
                overflow: hidden;
            }

            .wc-calendar-day-muted {
                opacity: 0.35;
            }

            .wc-calendar-date {
                font-weight: 700;
                font-size: 0.95rem;
                margin-bottom: 6px;
            }

            .wc-match-pill {
                font-size: 0.76rem;
                line-height: 1.25;
                padding: 6px;
                margin-bottom: 6px;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.12);
                box-sizing: border-box;
                cursor: pointer;
                transition: transform 0.08s ease, background 0.15s ease, border 0.15s ease;
            }

            .wc-match-pill:hover {
                transform: scale(1.01);
                border: 1px solid rgba(255, 255, 255, 0.35);
            }

            .wc-match-pill.watch-red {
                background: rgba(220, 38, 38, 0.78);
                border: 1px solid rgba(248, 113, 113, 0.95);
            }

            .wc-match-pill.watch-yellow {
                background: rgba(202, 138, 4, 0.82);
                border: 1px solid rgba(250, 204, 21, 0.95);
                color: #111827;
            }

            .wc-match-pill.watch-blue {
                background: rgba(37, 99, 235, 0.80);
                border: 1px solid rgba(96, 165, 250, 0.95);
            }

            .wc-watch-label {
                display: inline-block;
                margin-top: 4px;
                padding: 2px 5px;
                border-radius: 999px;
                font-size: 0.62rem;
                font-weight: 700;
                background: rgba(0, 0, 0, 0.28);
                color: #ffffff;
            }

            .watch-yellow .wc-watch-label {
                background: rgba(255, 255, 255, 0.45);
                color: #111827;
            }

            .wc-match-time {
                font-weight: 700;
                margin-bottom: 2px;
            }

            .wc-match-round {
                opacity: 0.75;
                font-size: 0.68rem;
                margin-top: 3px;
            }

            .wc-priority-help {
                margin-bottom: 10px;
                font-size: 0.82rem;
                opacity: 0.85;
            }

            @media (max-width: 900px) {
                .wc-calendar-grid {
                    grid-template-columns: 1fr;
                }

                .wc-calendar-header {
                    display: none;
                }

                .wc-calendar-day-muted {
                    display: none;
                }

                .wc-calendar-day {
                    min-height: auto;
                }
            }
        </style>
    </head>
    <body>
        <div class="wc-priority-help">
            Click a match to mark priority:
            Red = 1, Yellow = 2, Blue = 3, next click clears.
        </div>

        <div class="wc-calendar-grid">
    """

    for day_name in day_headers:
        calendar_html += f'<div class="wc-calendar-header">{day_name}</div>'

    for week in weeks:
        for current_day in week:
            muted_class = ""
            if current_day.month != selected_month_num:
                muted_class = " wc-calendar-day-muted"

            calendar_html += f'<div class="wc-calendar-day{muted_class}">'
            calendar_html += f'<div class="wc-calendar-date">{current_day.day}</div>'

            day_matches = matches_by_date.get(current_day)

            if day_matches is not None and not day_matches.empty:
                for _, row in day_matches.iterrows():
                    fixture_id = html.escape(str(row.get("fixture_id")))
                    match_title = html.escape(build_match_title(row))
                    match_time = html.escape(safe_text(row.get("time"), "Time TBD"))
                    match_round = html.escape(safe_text(row.get("round"), "Round TBD"))
                    city = html.escape(safe_text(row.get("city"), ""))

                    location_line = f"<br>{city}" if city else ""

                    calendar_html += f"""
                        <div class="wc-match-pill" data-fixture-id="{fixture_id}" onclick="cycleWatch(this)">
                            <div class="wc-match-time">{match_time}</div>
                            <div>{match_title}</div>
                            <div class="wc-match-round">{match_round}{location_line}</div>
                            <div class="wc-watch-label" style="display:none;"></div>
                        </div>
                    """

            calendar_html += "</div>"

    calendar_html += """
        </div>

        <script>
            const WATCH_STORAGE_PREFIX = "wc2026_watch_";

            function applyWatchState(card, state) {
                card.classList.remove("watch-red", "watch-yellow", "watch-blue");

                const label = card.querySelector(".wc-watch-label");

                if (!label) {
                    return;
                }

                if (state === "1") {
                    card.classList.add("watch-red");
                    label.innerText = "RED 1";
                    label.style.display = "inline-block";
                } else if (state === "2") {
                    card.classList.add("watch-yellow");
                    label.innerText = "YELLOW 2";
                    label.style.display = "inline-block";
                } else if (state === "3") {
                    card.classList.add("watch-blue");
                    label.innerText = "BLUE 3";
                    label.style.display = "inline-block";
                } else {
                    label.innerText = "";
                    label.style.display = "none";
                }
            }

            function cycleWatch(card) {
                const fixtureId = card.dataset.fixtureId;
                const storageKey = WATCH_STORAGE_PREFIX + fixtureId;

                const currentState = localStorage.getItem(storageKey);

                let nextState = "1";

                if (currentState === "1") {
                    nextState = "2";
                } else if (currentState === "2") {
                    nextState = "3";
                } else if (currentState === "3") {
                    nextState = "";
                }

                if (nextState) {
                    localStorage.setItem(storageKey, nextState);
                } else {
                    localStorage.removeItem(storageKey);
                }

                applyWatchState(card, nextState);
            }

            function loadSavedWatchStates() {
                const cards = document.querySelectorAll(".wc-match-pill");

                cards.forEach(card => {
                    const fixtureId = card.dataset.fixtureId;
                    const storageKey = WATCH_STORAGE_PREFIX + fixtureId;
                    const savedState = localStorage.getItem(storageKey);

                    applyWatchState(card, savedState);
                });
            }

            loadSavedWatchStates();
        </script>
    </body>
    </html>
    """

    component_height = max(1500, len(weeks) * 300 + 200)

    components.html(
        calendar_html,
        height=component_height,
        scrolling=False
    )


def render_matchday_view(fixtures_df):
    st.subheader("🗓️ Matchday Grid")

    selected_month, calendar_team, month_df = get_grid_filtered_df(fixtures_df)

    if selected_month is None:
        st.warning("No months available.")
        return

    view_mode = st.segmented_control(
        "View style",
        options=["Grid", "Mobile List"],
        default="Grid"
    )

    if view_mode == "Grid":
        render_matchday_grid(month_df, selected_month)
    else:
        render_matchday_mobile_list(month_df)


st.title("🏆 World Cup 2026 Calendar")
st.caption("Calendar view of teams, kickoff times, venues, and match status.")

if not API_KEY:
    st.error("Missing API_FOOTBALL_KEY. Add it to Streamlit Cloud secrets.")
    st.stop()

try:
    api_result = fetch_world_cup_fixtures()

except requests.HTTPError as e:
    st.error(f"API request failed: {e}")
    st.stop()

except Exception as e:
    st.error(f"Something went wrong: {e}")
    st.stop()


errors = api_result.get("errors", {})
results = api_result.get("results", 0)

if errors:
    st.error("API returned an error:")
    st.json(errors)
    st.stop()

fixtures_df = normalize_fixtures(api_result)

if fixtures_df.empty:
    st.warning("No fixtures found.")
    with st.expander("Raw API response"):
        st.json(api_result)
    st.stop()


fixtures_df["bucket"] = fixtures_df.apply(get_game_bucket, axis=1)

top1, top2, top3 = st.columns(3)

top1.metric("Fixtures Loaded", len(fixtures_df))

teams_loaded = len(
    set(fixtures_df["home_team"].dropna())
    | set(fixtures_df["away_team"].dropna())
)
top2.metric("Teams", teams_loaded)

top3.metric("API Results", results)

st.divider()

tab1, tab2 = st.tabs(["📋 Match List", "🗓️ Matchday Grid"])


with tab1:
    filter1, filter2, filter3, filter4 = st.columns([1.5, 1.5, 1.5, 1])

    with filter1:
        min_date = fixtures_df["date"].min()
        max_date = fixtures_df["date"].max()

        selected_date_range = st.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

    with filter2:
        teams = sorted(
            set(fixtures_df["home_team"].dropna().tolist())
            | set(fixtures_df["away_team"].dropna().tolist())
        )

        selected_team = st.selectbox(
            "Team",
            options=["All teams"] + teams
        )

    with filter3:
        rounds = sorted(fixtures_df["round"].dropna().unique().tolist())

        selected_round = st.selectbox(
            "Round",
            options=["All rounds"] + rounds
        )

    with filter4:
        selected_bucket = st.selectbox(
            "View",
            options=["All", "Upcoming", "Live", "Results"]
        )

    filtered_df = apply_filters(
        fixtures_df,
        selected_date_range,
        selected_team,
        selected_round,
        selected_bucket
    )

    render_match_list(filtered_df)


with tab2:
    render_matchday_view(fixtures_df)


with st.expander("Raw API response"):
    st.json(api_result)