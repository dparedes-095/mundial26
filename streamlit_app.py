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

                        "home_team_id": home.get("id"),
            "away_team_id": away.get("id"),
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


def get_next_match(fixtures_df):
    now = pd.Timestamp.now(tz=ZoneInfo(LOCAL_TIMEZONE))

    upcoming_df = fixtures_df[
        fixtures_df["datetime_local"] >= now
    ].sort_values("datetime_local")

    if upcoming_df.empty:
        return None

    return upcoming_df.iloc[0]


def get_next_team_match(fixtures_df, team_name):
    now = pd.Timestamp.now(tz=ZoneInfo(LOCAL_TIMEZONE))

    team_df = fixtures_df[
        (
            (fixtures_df["home_team"] == team_name)
            | (fixtures_df["away_team"] == team_name)
        )
        & (fixtures_df["datetime_local"] >= now)
    ].sort_values("datetime_local")

    if team_df.empty:
        return None

    return team_df.iloc[0]


def format_short_match_value(row):
    if row is None:
        return "None found"

    match_title = build_match_title(row)
    match_date = pd.to_datetime(row["date"]).strftime("%b %d")
    match_time = safe_text(row.get("time"), "Time TBD")

    return f"{match_title} · {match_date}, {match_time}"


def render_dashboard_card(title, value, caption=None):
    with st.container(border=True):
        st.caption(title)
        st.markdown(f"**{value}**")

        if caption:
            st.caption(caption)


def render_tab1_hero_cards(fixtures_df):
    today = pd.Timestamp.now(tz=ZoneInfo(LOCAL_TIMEZONE)).date()

    today_df = fixtures_df[fixtures_df["date"] == today]
    next_match = get_next_match(fixtures_df)
    next_usa_match = get_next_team_match(fixtures_df, "USA")

    if today_df.empty:
        cities_today = "None today"
    else:
        cities = sorted(
            [
                safe_text(city)
                for city in today_df["city"].dropna().unique().tolist()
                if safe_text(city)
            ]
        )

        if not cities:
            cities_today = "Venue TBD"
        elif len(cities) <= 2:
            cities_today = ", ".join(cities)
        else:
            cities_today = ", ".join(cities[:2]) + f" +{len(cities) - 2} more"

    hero1, hero2, hero3, hero4 = st.columns(4)

    with hero1:
        render_dashboard_card(
            "Matches Today",
            len(today_df),
            today.strftime("%A, %b %d")
        )

    with hero2:
        render_dashboard_card(
            "Next Match",
            format_short_match_value(next_match)
        )

    with hero3:
        render_dashboard_card(
            "Next USA Match",
            format_short_match_value(next_usa_match)
        )

    with hero4:
        render_dashboard_card(
            "Host Cities Today",
            cities_today
        )


def render_quick_filters(fixtures_df):
    st.markdown("#### ⚡ Quick Filters")

    today = pd.Timestamp.now(tz=ZoneInfo(LOCAL_TIMEZONE)).date()
    tomorrow = today + pd.Timedelta(days=1)
    week_end = today + pd.Timedelta(days=7)

    if "quick_filter" not in st.session_state:
        st.session_state.quick_filter = "All"

    quick1, quick2, quick3, quick4, quick5, quick6, quick7 = st.columns(7)

    with quick1:
        if st.button("All", use_container_width=True):
            st.session_state.quick_filter = "All"

    with quick2:
        if st.button("Today", use_container_width=True):
            st.session_state.quick_filter = "Today"

    with quick3:
        if st.button("Tomorrow", use_container_width=True):
            st.session_state.quick_filter = "Tomorrow"

    with quick4:
        if st.button("This Week", use_container_width=True):
            st.session_state.quick_filter = "This Week"

    with quick5:
        if st.button("USA", use_container_width=True):
            st.session_state.quick_filter = "USA"

    with quick6:
        if st.button("Mexico", use_container_width=True):
            st.session_state.quick_filter = "Mexico"

    with quick7:
        if st.button("Live Now", use_container_width=True):
            st.session_state.quick_filter = "Live Now"

    quick_filter = st.session_state.quick_filter
    quick_df = fixtures_df.copy()

    if quick_filter == "Today":
        quick_df = quick_df[quick_df["date"] == today]

    elif quick_filter == "Tomorrow":
        quick_df = quick_df[quick_df["date"] == tomorrow]

    elif quick_filter == "This Week":
        quick_df = quick_df[
            (quick_df["date"] >= today)
            & (quick_df["date"] <= week_end)
        ]

    elif quick_filter == "USA":
        quick_df = quick_df[
            (quick_df["home_team"] == "USA")
            | (quick_df["away_team"] == "USA")
        ]

    elif quick_filter == "Mexico":
        quick_df = quick_df[
            (quick_df["home_team"] == "Mexico")
            | (quick_df["away_team"] == "Mexico")
        ]

    elif quick_filter == "Live Now":
        quick_df = quick_df[quick_df["bucket"] == "Live"]

    st.caption(f"Active quick filter: **{quick_filter}**")

    return quick_df


def get_round_sort_key(round_name):
    round_text = safe_text(round_name, "Round TBD").lower()

    if "group" in round_text:
        return 1
    if "round of 32" in round_text:
        return 2
    if "round of 16" in round_text:
        return 3
    if "quarter" in round_text:
        return 4
    if "semi" in round_text:
        return 5
    if "third" in round_text:
        return 6
    if "final" in round_text:
        return 7

    return 99


def render_round_progress(fixtures_df):
    st.markdown("#### 🧭 Tournament Progress")

    round_counts = (
        fixtures_df
        .groupby("round")
        .size()
        .reset_index(name="matches")
    )

    if round_counts.empty:
        st.info("No round data available yet.")
        return

    round_counts["sort_key"] = round_counts["round"].apply(get_round_sort_key)
    round_counts = round_counts.sort_values(["sort_key", "round"])

    total_matches = int(round_counts["matches"].sum())

    progress_cols = st.columns(min(len(round_counts), 4))

    for index, row in round_counts.iterrows():
        col = progress_cols[index % len(progress_cols)]

        with col:
            share = int(row["matches"]) / total_matches if total_matches else 0

            with st.container(border=True):
                st.caption(safe_text(row["round"], "Round TBD"))
                st.markdown(f"**{int(row['matches'])} matches**")
                st.progress(share)


def render_team_profile(fixtures_df, selected_team):
    if selected_team == "All teams":
        return

    team_df = fixtures_df[
        (fixtures_df["home_team"] == selected_team)
        | (fixtures_df["away_team"] == selected_team)
    ].sort_values("datetime_local")

    if team_df.empty:
        return

    first_match = team_df.iloc[0]
    next_match = get_next_team_match(fixtures_df, selected_team)

    cities = sorted(
        [
            safe_text(city)
            for city in team_df["city"].dropna().unique().tolist()
            if safe_text(city)
        ]
    )

    rounds = sorted(
        [
            safe_text(round_name)
            for round_name in team_df["round"].dropna().unique().tolist()
            if safe_text(round_name)
        ],
        key=get_round_sort_key
    )

    if not cities:
        city_value = "TBD"
    elif len(cities) <= 2:
        city_value = ", ".join(cities)
    else:
        city_value = ", ".join(cities[:2]) + f" +{len(cities) - 2} more"

    if not rounds:
        round_value = "TBD"
    elif len(rounds) <= 2:
        round_value = ", ".join(rounds)
    else:
        round_value = ", ".join(rounds[:2]) + f" +{len(rounds) - 2} more"

    st.markdown(f"#### 🧬 {selected_team} Snapshot")

    p1, p2, p3, p4 = st.columns(4)

    with p1:
        render_dashboard_card("Matches", len(team_df), round_value)

    with p2:
        render_dashboard_card("First Match", format_short_match_value(first_match))

    with p3:
        render_dashboard_card("Next Match", format_short_match_value(next_match))

    with p4:
        render_dashboard_card("Cities", city_value)

    with st.expander(f"{selected_team} full team schedule"):
        for _, row in team_df.iterrows():
            st.markdown(
                f"**{pd.to_datetime(row['date']).strftime('%A, %B %d')} · "
                f"{safe_text(row.get('time'), 'Time TBD')}** — "
                f"{build_match_title(row)}"
            )
            st.caption(
                f"{safe_text(row.get('round'), 'Round TBD')} · {build_location(row)}"
            )


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

    with st.expander("How to use this grid", expanded=False):
        st.markdown(
            """
            **What this tab is for**

            This is the visual calendar view of the World Cup schedule. Use it when you want to see matches laid out by month instead of scrolling through the full list.

            **Controls**

            - **Month** changes the calendar month.
            - **Team filter** shows only matches for one team, or all teams.
            - **View style** lets you switch between:
              - **Grid**: calendar-style layout for desktop/tablet.
              - **Mobile List**: easier vertical list for smaller screens.

            **Priority colors**

            In **Grid** view, click a match card to cycle your watch priority:

            - **Red 1** = must-watch
            - **Yellow 2** = interested
            - **Blue 3** = maybe / background watch
            - Click again after Blue to clear it.

            Your color choices are saved in this browser, so they should stick around when you refresh on the same device.
            """
        )

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



# -----------------------------
# Player API helpers
# -----------------------------

def get_first_stat(player_item):
    statistics = player_item.get("statistics", []) or []
    if not statistics:
        return {}

    return statistics[0] or {}


def nested_get(source, path, fallback=None):
    current = source

    for part in path:
        if not isinstance(current, dict):
            return fallback
        current = current.get(part)

    if current is None:
        return fallback

    return current


def to_int_or_none(value):
    try:
        if pd.isna(value):
            return None
        return int(value)
    except Exception:
        return None


@st.cache_data(ttl=60 * 30)
def fetch_top_players(endpoint):
    url = f"{BASE_URL}/{endpoint}"

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


@st.cache_data(ttl=60 * 30)
def fetch_players_search(search_text=None, team_id=None):
    url = f"{BASE_URL}/players"

    params = {
        "league": WORLD_CUP_LEAGUE_ID,
        "season": WORLD_CUP_SEASON
    }

    if search_text:
        params["search"] = search_text

    if team_id:
        params["team"] = team_id

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


@st.cache_data(ttl=60 * 10)
def fetch_fixture_player_stats(fixture_id):
    url = f"{BASE_URL}/fixtures/players"

    params = {
        "fixture": int(fixture_id)
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


def player_response_to_df(api_result):
    rows = []

    for item in api_result.get("response", []) or []:
        player = item.get("player", {}) or {}
        stat = get_first_stat(item)

        games = stat.get("games", {}) or {}
        team = stat.get("team", {}) or {}
        goals = stat.get("goals", {}) or {}
        cards = stat.get("cards", {}) or {}
        shots = stat.get("shots", {}) or {}
        passes = stat.get("passes", {}) or {}
        tackles = stat.get("tackles", {}) or {}
        duels = stat.get("duels", {}) or {}

        rows.append({
            "player_id": player.get("id"),
            "Player": safe_text(player.get("name"), "Unknown"),
            "Age": player.get("age"),
            "Team": safe_text(team.get("name"), "TBD"),
            "Position": safe_text(games.get("position"), "TBD"),
            "Appearances": games.get("appearences"),
            "Starts": games.get("lineups"),
            "Minutes": games.get("minutes"),
            "Rating": games.get("rating"),
            "Goals": goals.get("total"),
            "Assists": goals.get("assists"),
            "Shots": shots.get("total"),
            "Shots on Goal": shots.get("on"),
            "Passes": passes.get("total"),
            "Key Passes": passes.get("key"),
            "Tackles": tackles.get("total"),
            "Duels Won": duels.get("won"),
            "Yellow": cards.get("yellow"),
            "Red": cards.get("red"),
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        for col in ["Age", "Appearances", "Starts", "Minutes", "Goals", "Assists", "Shots", "Shots on Goal", "Passes", "Key Passes", "Tackles", "Duels Won", "Yellow", "Red"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce")
        df = df.sort_values(["Goals", "Assists", "Rating"], ascending=[False, False, False], na_position="last")

    return df


def fixture_players_to_df(api_result):
    rows = []

    for team_block in api_result.get("response", []) or []:
        team = team_block.get("team", {}) or {}
        team_name = safe_text(team.get("name"), "TBD")

        for player_item in team_block.get("players", []) or []:
            player = player_item.get("player", {}) or {}
            stat = player_item.get("statistics", [{}])[0] or {}

            games = stat.get("games", {}) or {}
            goals = stat.get("goals", {}) or {}
            shots = stat.get("shots", {}) or {}
            passes = stat.get("passes", {}) or {}
            tackles = stat.get("tackles", {}) or {}
            duels = stat.get("duels", {}) or {}
            cards = stat.get("cards", {}) or {}

            rows.append({
                "Team": team_name,
                "Player": safe_text(player.get("name"), "Unknown"),
                "Position": safe_text(games.get("position"), "TBD"),
                "Minutes": games.get("minutes"),
                "Rating": games.get("rating"),
                "Goals": goals.get("total"),
                "Assists": goals.get("assists"),
                "Shots": shots.get("total"),
                "Shots on Goal": shots.get("on"),
                "Passes": passes.get("total"),
                "Pass Accuracy": passes.get("accuracy"),
                "Tackles": tackles.get("total"),
                "Duels Won": duels.get("won"),
                "Yellow": cards.get("yellow"),
                "Red": cards.get("red"),
            })

    df = pd.DataFrame(rows)

    if not df.empty:
        number_cols = ["Minutes", "Rating", "Goals", "Assists", "Shots", "Shots on Goal", "Passes", "Tackles", "Duels Won", "Yellow", "Red"]
        for col in number_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.sort_values(["Rating", "Goals", "Assists"], ascending=[False, False, False], na_position="last")

    return df


def get_team_id_options(fixtures_df):
    team_rows = []

    home_rows = fixtures_df[["home_team", "home_team_id"]].rename(
        columns={"home_team": "team", "home_team_id": "team_id"}
    )
    away_rows = fixtures_df[["away_team", "away_team_id"]].rename(
        columns={"away_team": "team", "away_team_id": "team_id"}
    )

    team_df = pd.concat([home_rows, away_rows], ignore_index=True)
    team_df = team_df.dropna(subset=["team", "team_id"]).drop_duplicates()

    for _, row in team_df.sort_values("team").iterrows():
        team_rows.append((safe_text(row["team"]), int(row["team_id"])))

    return team_rows


def render_player_table(df, label):
    if df.empty:
        st.info(f"No {label.lower()} found yet. This may stay empty until squads/match stats are populated by the API.")
        return

    preferred_cols = [
        "Player", "Team", "Position", "Age", "Appearances", "Starts", "Minutes",
        "Rating", "Goals", "Assists", "Shots", "Shots on Goal", "Passes",
        "Key Passes", "Tackles", "Duels Won", "Yellow", "Red"
    ]

    display_cols = [col for col in preferred_cols if col in df.columns]
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True
    )


def render_fixture_player_table(df):
    if df.empty:
        st.info("No player stats found for this fixture yet. Pre-match fixtures often stay empty until lineups or full-time stats are available.")
        return

    display_cols = [
        "Team", "Player", "Position", "Minutes", "Rating", "Goals", "Assists",
        "Shots", "Shots on Goal", "Passes", "Pass Accuracy", "Tackles",
        "Duels Won", "Yellow", "Red"
    ]

    display_cols = [col for col in display_cols if col in df.columns]

    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True
    )


def render_player_tracker(fixtures_df):
    st.subheader("⭐ Player Tracker")
    st.caption("Search players, view tournament leaderboards, and inspect per-match player stats when the API has them.")

    with st.expander("How to use Player Tracker", expanded=False):
        st.markdown(
            """
            **What this tab does**

            - **Leaderboards** pulls API-Football player ranking endpoints for the World Cup season.
            - **Player Search** searches the `/players` endpoint by player name and optional team.
            - **Match Player Stats** uses `/fixtures/players` for one selected fixture.

            **Important**

            Some World Cup player endpoints may be empty before squads, lineups, or completed matches are available.
            Use the debug expanders to see the raw API response if something looks blank.
            """
        )

    team_options = get_team_id_options(fixtures_df)
    team_name_to_id = {name: team_id for name, team_id in team_options}

    board_tab, search_tab, match_tab = st.tabs(
        ["🏆 Leaderboards", "🔎 Player Search", "📌 Match Player Stats"]
    )

    with board_tab:
        st.markdown("#### Tournament leaderboards")

        leaderboard_map = {
            "Top Scorers": "players/topscorers",
            "Top Assists": "players/topassists",
            "Top Yellow Cards": "players/topyellowcards",
            "Top Red Cards": "players/topredcards",
        }

        board_choice = st.selectbox(
            "Leaderboard",
            options=list(leaderboard_map.keys())
        )

        endpoint = leaderboard_map[board_choice]

        try:
            board_result = fetch_top_players(endpoint)
            board_df = player_response_to_df(board_result)

            metric1, metric2, metric3 = st.columns(3)

            with metric1:
                st.metric("Rows returned", len(board_df))

            with metric2:
                st.metric("API results", board_result.get("results", 0))

            with metric3:
                st.metric("Endpoint", endpoint)

            render_player_table(board_df, board_choice)

            with st.expander("Raw leaderboard API response"):
                st.json(board_result)

        except requests.HTTPError as e:
            st.error(f"Leaderboard request failed: {e}")
        except Exception as e:
            st.error(f"Something went wrong loading the leaderboard: {e}")

    with search_tab:
        st.markdown("#### Search player stats")

        search_col1, search_col2 = st.columns([2, 1.3])

        with search_col1:
            search_text = st.text_input(
                "Player name",
                placeholder="Example: Messi, Pulisic, Mbappe"
            )

        with search_col2:
            selected_team_name = st.selectbox(
                "Optional team filter",
                options=["All teams"] + list(team_name_to_id.keys())
            )

        selected_team_id = None
        if selected_team_name != "All teams":
            selected_team_id = team_name_to_id.get(selected_team_name)

        run_search = st.button("Search players", use_container_width=True)

        if run_search:
            if not search_text and not selected_team_id:
                st.warning("Enter a player name or choose a team first.")
            else:
                try:
                    player_result = fetch_players_search(search_text=search_text, team_id=selected_team_id)
                    player_df = player_response_to_df(player_result)

                    result1, result2 = st.columns(2)
                    with result1:
                        st.metric("Rows returned", len(player_df))
                    with result2:
                        st.metric("API results", player_result.get("results", 0))

                    render_player_table(player_df, "players")

                    with st.expander("Raw player search API response"):
                        st.json(player_result)

                except requests.HTTPError as e:
                    st.error(f"Player search failed: {e}")
                except Exception as e:
                    st.error(f"Something went wrong searching players: {e}")

    with match_tab:
        st.markdown("#### Per-match player stats")

        fixture_options = fixtures_df.sort_values("datetime_local").copy()
        fixture_options["fixture_label"] = fixture_options.apply(
            lambda row: (
                f"{pd.to_datetime(row['date']).strftime('%b %d')} · "
                f"{safe_text(row.get('time'), 'Time TBD')} · "
                f"{build_match_title(row)}"
            ),
            axis=1
        )

        fixture_label_to_id = dict(
            zip(fixture_options["fixture_label"], fixture_options["fixture_id"])
        )

        selected_fixture_label = st.selectbox(
            "Fixture",
            options=fixture_options["fixture_label"].tolist()
        )

        selected_fixture_id = fixture_label_to_id.get(selected_fixture_label)

        if st.button("Load match player stats", use_container_width=True):
            try:
                fixture_player_result = fetch_fixture_player_stats(selected_fixture_id)
                fixture_player_df = fixture_players_to_df(fixture_player_result)

                stat1, stat2 = st.columns(2)
                with stat1:
                    st.metric("Players returned", len(fixture_player_df))
                with stat2:
                    st.metric("API results", fixture_player_result.get("results", 0))

                render_fixture_player_table(fixture_player_df)

                with st.expander("Raw fixture player API response"):
                    st.json(fixture_player_result)

            except requests.HTTPError as e:
                st.error(f"Fixture player stats request failed: {e}")
            except Exception as e:
                st.error(f"Something went wrong loading fixture player stats: {e}")

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


teams_loaded = len(
    set(fixtures_df["home_team"].dropna())
    | set(fixtures_df["away_team"].dropna())
)


st.divider()

tab1, tab2, tab3 = st.tabs(["📋 Match List", "🗓️ Matchday Grid", "⭐ Player Tracker"])


with tab1:
    render_tab1_hero_cards(fixtures_df)

    st.divider()

    quick_filtered_df = render_quick_filters(fixtures_df)

    st.divider()

    render_round_progress(fixtures_df)

    st.divider()

    if quick_filtered_df.empty:
        st.warning("No matches available for this quick filter.")
    else:
        filter1, filter2, filter3, filter4 = st.columns([1.5, 1.5, 1.5, 1])

        with filter1:
            min_date = quick_filtered_df["date"].min()
            max_date = quick_filtered_df["date"].max()

            selected_date_range = st.date_input(
                "Date range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )

        with filter2:
            teams = sorted(
                set(quick_filtered_df["home_team"].dropna().tolist())
                | set(quick_filtered_df["away_team"].dropna().tolist())
            )

            selected_team = st.selectbox(
                "Team",
                options=["All teams"] + teams
            )

        with filter3:
            rounds = sorted(
                quick_filtered_df["round"]
                .dropna()
                .unique()
                .tolist(),
                key=get_round_sort_key
            )

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
            quick_filtered_df,
            selected_date_range,
            selected_team,
            selected_round,
            selected_bucket
        )

        render_team_profile(quick_filtered_df, selected_team)

        st.divider()

        render_match_list(filtered_df)


with tab2:
    render_matchday_view(fixtures_df)


with tab3:
    render_player_tracker(fixtures_df)


with st.expander("Raw API response"):
    st.json(api_result)