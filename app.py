"""통합 GYM PT 앱: 탐색·신체 맵·맞춤 추천·루틴·기록을 한 곳에서 제공합니다."""
from __future__ import annotations

import base64
import calendar
import json
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(page_title="GYM PT", page_icon="💪", layout="wide")
st.markdown(
    """
    <style>
    .calendar-status {
        min-height: 3.4rem; margin: .25rem 0 .6rem; padding: .55rem;
        border: 1px solid #94a3b8; border-radius: .55rem;
        background: #e8f0ff; color: #102a56; font-size: .84rem; line-height: 1.45;
        box-shadow: 0 1px 2px rgba(15, 23, 42, .12);
    }
    .calendar-status strong { color: #0f172a; font-weight: 800; }
    .calendar-status.empty { background: #f1f5f9; color: #64748b; }
    .calendar-note {
        margin-top: .4rem; padding: .45rem; border-left: 4px solid #d97706;
        border-radius: .3rem; background: #fff7d6; color: #713f12;
        font-size: .82rem; font-weight: 650; line-height: 1.4;
        overflow-wrap: anywhere;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "GYM_PT-wkrdjq"
DATA_PATH = SOURCE_DIR / "dataset.csv"
STATE_PATH = BASE_DIR / "app_state.json"
BODY_IMAGE_PATH = SOURCE_DIR / "body.png"
COMPONENT_DIR = SOURCE_DIR / "body_map_component"
REQUIRED_COLUMNS = ["신체부위", "운동 이름", "난이도", "운동방법", "효과", "주의사항"]
LEVEL_ORDER = {"초급": 1, "중급": 2, "고급": 3}
GOAL_KEYWORDS = {
    "다이어트": ["전신", "지구력", "유산소", "칼로리", "체지방"],
    "근력 향상": ["근력", "강화", "파워", "힘"],
    "근육량 증가": ["근비대", "근육", "발달", "매스"],
    "체력 증진": ["지구력", "심폐", "전신", "체력"],
    "습관 기르기": ["기초", "전신", "코어", "가동성"],
}
TITLES = [(0, "입문"), (10, "초급"), (30, "중급"), (60, "고급"), (100, "숙련"), (200, "전문")]


@st.cache_data
def load_exercises() -> pd.DataFrame:
    frame = pd.read_csv(DATA_PATH, encoding="utf-8-sig").fillna("")
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"운동 데이터에 필요한 컬럼이 없습니다: {', '.join(missing)}")
    frame = frame[REQUIRED_COLUMNS].copy()
    frame["난이도 점수"] = frame["난이도"].map(LEVEL_ORDER).fillna(2).astype(int)
    frame["검색 텍스트"] = frame.astype(str).agg(" ".join, axis=1).str.lower()
    return frame


def default_state() -> dict:
    return {
        "profile": {"이름": "", "성별": "선택 안 함", "나이": 20, "키": 170, "몸무게": 60,
                    "운동 동기": "습관 기르기", "주당 운동 횟수": 3, "집중 부위": [],
                    "운동 장소": "집", "불편한 부위": "없음", "운동 기간": "3개월",
                    "최장 규칙 운동 기간": "없음"},
        "routine": [], "favorites": [], "completed": {}, "notes": {},
        "attendance": {}, "routine_completed_days": {},
    }


def load_state() -> dict:
    state = default_state()
    if STATE_PATH.exists():
        try:
            saved = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            state.update({key: value for key, value in saved.items() if key in state})
            state["profile"] = {**default_state()["profile"], **saved.get("profile", {})}
        except (OSError, json.JSONDecodeError):
            pass
    return state


def save_state() -> None:
    STATE_PATH.write_text(json.dumps(st.session_state.data, ensure_ascii=False, indent=2), encoding="utf-8")


def parts(value: str) -> list[str]:
    return [item.strip() for item in str(value).replace(",", "/").split("/") if item.strip()]


def all_parts(exercises: pd.DataFrame) -> list[str]:
    return sorted({part for value in exercises["신체부위"] for part in parts(value)})


def matches_parts(value: str, selected: list[str]) -> bool:
    return not selected or bool(set(parts(value)) & set(selected))


def filtered_exercises(exercises: pd.DataFrame, selected: list[str], levels: list[str], query: str) -> pd.DataFrame:
    result = exercises.copy()
    if selected:
        result = result[result["신체부위"].apply(lambda value: matches_parts(value, selected))]
    if levels:
        result = result[result["난이도"].isin(levels)]
    if query.strip():
        result = result[result["검색 텍스트"].str.contains(query.strip().lower(), regex=False, na=False)]
    return result.sort_values(["난이도 점수", "신체부위", "운동 이름"])


def recommendation(exercises: pd.DataFrame, profile: dict, selected: list[str] | None = None) -> pd.DataFrame:
    focus = selected if selected is not None else profile.get("집중 부위", [])
    words = GOAL_KEYWORDS.get(profile.get("운동 동기"), GOAL_KEYWORDS["습관 기르기"])
    discomfort = str(profile.get("불편한 부위", "없음"))
    result = exercises.copy()
    result["추천 점수"] = 0
    if focus:
        result["추천 점수"] += result["신체부위"].apply(lambda value: 50 if matches_parts(value, focus) else 0)
    for word in words:
        result["추천 점수"] += result["검색 텍스트"].str.contains(word.lower(), regex=False).astype(int) * 10
    if profile.get("최장 규칙 운동 기간") in ("없음", "1개월 미만"):
        result["추천 점수"] += (result["난이도"] == "초급").astype(int) * 15
    if discomfort and discomfort != "없음":
        result["추천 점수"] -= result["검색 텍스트"].str.contains(discomfort.lower(), regex=False).astype(int) * 25
    return result.sort_values(["추천 점수", "난이도 점수", "운동 이름"], ascending=[False, True, True])


def toggle(collection: str, exercise: str) -> None:
    items = st.session_state.data[collection]
    if exercise in items:
        items.remove(exercise)
    else:
        items.append(exercise)
    save_state()


def add_to_routine(exercise: str) -> None:
    if exercise not in st.session_state.data["routine"]:
        st.session_state.data["routine"].append(exercise)
        save_state()
        st.toast(f"{exercise}을(를) 루틴에 추가했습니다.")


def complete_exercise(exercise: str) -> None:
    today = date.today().isoformat()
    done = st.session_state.data["completed"].setdefault(today, [])
    if exercise not in done:
        done.append(exercise)
        st.session_state.data["attendance"][today] = True
        save_state()
        st.toast(f"{exercise} 완료!")


def render_card(row: pd.Series, key: str, show_add: bool = True) -> None:
    name = row["운동 이름"]
    with st.container(border=True):
        st.markdown(f"#### {name}")
        st.caption(f"{row['신체부위']} · {row['난이도']}")
        st.write(row["운동방법"])
        with st.expander("효과 및 주의사항"):
            st.markdown(f"**효과**  \n{row['효과']}")
            st.markdown(f"**주의사항**  \n{row['주의사항']}")
        left, middle, right = st.columns(3)
        favorite = name in st.session_state.data["favorites"]
        if left.button("★ 즐겨찾기" if not favorite else "★ 해제", key=f"fav_{key}", width="stretch"):
            toggle("favorites", name); st.rerun()
        if show_add and middle.button("루틴 추가", key=f"add_{key}", disabled=name in st.session_state.data["routine"], width="stretch"):
            add_to_routine(name); st.rerun()
        if right.button("오늘 완료", key=f"done_{key}", width="stretch"):
            complete_exercise(name); st.rerun()


@st.cache_data
def body_image_url() -> str | None:
    if not BODY_IMAGE_PATH.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(BODY_IMAGE_PATH.read_bytes()).decode("ascii")


def render_body_map(exercises: pd.DataFrame) -> str | None:
    if not COMPONENT_DIR.exists() or not body_image_url():
        return None
    component = components.declare_component("body_map_merged", path=str(COMPONENT_DIR))
    specs = [("어깨", "shoulder", "40,18,20,10"), ("가슴", "chest", "44,27,12,11"),
             ("이두근", "biceps", "39,27,22,17"), ("삼두근", "triceps", "39,35,22,15"),
             ("전완근", "forearm", "39,46,22,14"), ("복부", "core", "45,38,10,15"),
             ("허벅지", "thigh", "42,53,16,19"), ("종아리", "calf", "45,72,10,19")]
    existing = set(all_parts(exercises)); hotspots = []
    for part, ident, box in specs:
        if part in existing:
            left, top, width, height = map(float, box.split(","))
            names = exercises[exercises["신체부위"].apply(lambda value: matches_parts(value, [part]))]["운동 이름"].head(3).tolist()
            hotspots.append({"part": part, "id": ident, "left": left, "top": top, "width": width, "height": height, "suggestions": names})
    return component(image_url=body_image_url(), hotspots=hotspots, default=None, key="body_map")


def profile_page(exercises: pd.DataFrame) -> None:
    st.title("프로필 설정")
    profile = st.session_state.data["profile"]
    genders = ["선택 안 함", "여성", "남성", "기타"]
    locations = ["집", "헬스장", "공원/야외", "학교/회사", "기타"]
    periods = ["1개월", "3개월", "6개월", "1년 이상"]
    histories = ["없음", "1개월 미만", "1~3개월", "3~6개월", "6개월 이상"]
    with st.form("profile"):
        a, b = st.columns(2)
        with a:
            name = st.text_input("이름", profile["이름"]); gender = st.selectbox("성별", genders, index=genders.index(profile["성별"]))
            age = st.number_input("나이", 10, 100, int(profile["나이"])); height = st.number_input("키 (cm)", 100, 230, int(profile["키"])); weight = st.number_input("몸무게 (kg)", 25, 250, int(profile["몸무게"]))
        with b:
            goal = st.selectbox("운동 동기", list(GOAL_KEYWORDS), index=list(GOAL_KEYWORDS).index(profile["운동 동기"]))
            frequency = st.slider("주당 운동 횟수", 1, 7, int(profile["주당 운동 횟수"])); focus = st.multiselect("집중 부위", all_parts(exercises), default=profile["집중 부위"])
            location = st.selectbox("운동 장소", locations, index=locations.index(profile["운동 장소"])); discomfort = st.text_input("불편한 부위", profile["불편한 부위"])
            period = st.selectbox("운동 기간", periods, index=periods.index(profile["운동 기간"])); history = st.selectbox("최장 규칙 운동 기간", histories, index=histories.index(profile["최장 규칙 운동 기간"]))
        submitted = st.form_submit_button("프로필 저장", width="stretch")
    if submitted:
        st.session_state.data["profile"] = {"이름": name, "성별": gender, "나이": age, "키": height, "몸무게": weight, "운동 동기": goal, "주당 운동 횟수": frequency, "집중 부위": focus, "운동 장소": location, "불편한 부위": discomfort or "없음", "운동 기간": period, "최장 규칙 운동 기간": history}
        save_state(); st.success("프로필을 저장했습니다.")


def calendar_page() -> None:
    st.title("운동 기록 캘린더")
    selected_month = st.date_input("확인할 달", date.today())
    data = st.session_state.data; year, month = selected_month.year, selected_month.month
    st.caption("✅ 출석 · 🏋 완료 운동 수 · 🏆 루틴 전체 완료 · 📝 메모")
    for week in calendar.monthcalendar(year, month):
        columns = st.columns(7)
        for column, day_number in zip(columns, week):
            if day_number:
                key = date(year, month, day_number).isoformat()
                workouts = data["completed"].get(key, [])
                markers = []
                if data["attendance"].get(key):
                    markers.append("✅ 출석")
                if workouts:
                    markers.append(f"🏋 {len(workouts)}개")
                if data["routine_completed_days"].get(key):
                    markers.append("🏆 완료")
                if data["notes"].get(key):
                    markers.append("📝 메모")
                if column.button(str(day_number), key=f"day_{key}", width="stretch"):
                    st.session_state.record_day = key
                status = " · ".join(markers) if markers else "기록 없음"
                status_class = "" if markers else " empty"
                column.markdown(
                    f"<div class='calendar-status{status_class}'><strong>{status}</strong></div>",
                    unsafe_allow_html=True,
                )
                saved_note = str(data["notes"].get(key, "")).strip()
                if saved_note:
                    preview = saved_note.replace("\n", " ")
                    if len(preview) > 70:
                        preview = preview[:70].rstrip() + "…"
                    column.markdown(
                        f"<div class='calendar-note'>📝 {escape(preview)}</div>",
                        unsafe_allow_html=True,
                    )
    key = st.session_state.get("record_day", selected_month.isoformat())
    if not key.startswith(f"{year:04d}-{month:02d}"):
        key = selected_month.isoformat()
        st.session_state.record_day = key

    st.divider()
    st.subheader(f"{key} 기록")
    attended = bool(data["attendance"].get(key))
    if st.button("출석 취소" if attended else "출석 완료", key=f"attendance_{key}"):
        if attended:
            data["attendance"].pop(key, None)
        else:
            data["attendance"][key] = True
        save_state()
        st.rerun()

    workouts = data["completed"].get(key, [])
    st.markdown("#### 당일 완료 운동")
    if workouts:
        for index, workout in enumerate(workouts, start=1):
            st.write(f"{index}. {workout}")
    else:
        st.info("이 날짜에 완료로 기록된 운동이 없습니다.")

    st.markdown("#### 메모")
    saved_note = data["notes"].get(key, "")
    if saved_note:
        st.success(saved_note)
    note = st.text_area("메모 작성 또는 수정", saved_note, key=f"note_{key}")
    if st.button("메모 저장", key=f"save_note_{key}"):
        if note.strip(): data["notes"][key] = note.strip()
        else: data["notes"].pop(key, None)
        save_state(); st.rerun()


def main_page(exercises: pd.DataFrame) -> None:
    data = st.session_state.data; profile = data["profile"]; total = len(data["routine_completed_days"])
    title = next(name for threshold, name in TITLES[::-1] if total >= threshold)
    st.title("💪 GYM PT")
    st.caption("운동 탐색, 신체 부위 선택, 맞춤 추천, 루틴과 기록을 한 곳에서 관리하세요.")
    a, b, c, d = st.columns(4); a.metric("전체 운동", len(exercises)); b.metric("즐겨찾기", len(data["favorites"])); c.metric("루틴 완료 일수", total); d.metric("현재 칭호", title)
    tab_find, tab_recommend, tab_routine, tab_favorite = st.tabs(["운동 찾기", "맞춤 추천", "내 루틴", "즐겨찾기"])
    with tab_find:
        clicked = render_body_map(exercises)
        if clicked: st.session_state.selected_part = clicked
        selected = st.multiselect("신체 부위", all_parts(exercises), default=[st.session_state.selected_part] if st.session_state.get("selected_part") else [])
        levels = st.multiselect("난이도", list(LEVEL_ORDER)); query = st.text_input("검색", placeholder="운동명, 효과, 방법, 주의사항")
        result = filtered_exercises(exercises, selected, levels, query)
        st.download_button("검색 결과 CSV", result[REQUIRED_COLUMNS].to_csv(index=False).encode("utf-8-sig"), "exercise_search_result.csv", "text/csv")
        columns = st.columns(3)
        for index, (_, row) in enumerate(result.iterrows()):
            with columns[index % 3]: render_card(row, f"search_{row.name}")
    with tab_recommend:
        focus = st.multiselect("이번 추천 집중 부위", all_parts(exercises), default=profile["집중 부위"])
        count = st.slider("추천 수", 3, 12, 6)
        result = recommendation(exercises, profile, focus).head(count)
        st.caption(f"목표: {profile['운동 동기']} · 프로필의 운동 경험과 불편 부위를 함께 반영합니다.")
        columns = st.columns(3)
        for index, (_, row) in enumerate(result.iterrows()):
            with columns[index % 3]: render_card(row, f"recommend_{row.name}")
    with tab_routine:
        routine = exercises[exercises["운동 이름"].isin(data["routine"])]
        today = date.today().isoformat(); done = data["completed"].get(today, [])
        st.metric("오늘 진행", f"{len(set(done) & set(data['routine']))}/{len(data['routine'])}")
        for _, row in routine.iterrows(): render_card(row, f"routine_{row.name}", show_add=False)
        if data["routine"] and set(data["routine"]).issubset(done):
            data["routine_completed_days"][today] = True; save_state(); st.success("오늘 루틴을 모두 완료했습니다! 🏆")
    with tab_favorite:
        favorite = exercises[exercises["운동 이름"].isin(data["favorites"])]
        if favorite.empty: st.info("즐겨찾기한 운동이 없습니다.")
        for _, row in favorite.iterrows(): render_card(row, f"favorite_{row.name}")


try:
    exercises = load_exercises()
except Exception as error:
    st.error(f"운동 데이터를 불러오지 못했습니다: {error}")
    st.stop()
if "data" not in st.session_state: st.session_state.data = load_state()
if "selected_part" not in st.session_state: st.session_state.selected_part = ""

page = st.sidebar.radio("메뉴", ["홈", "프로필 설정", "운동 기록 캘린더"])
if page == "프로필 설정": profile_page(exercises)
elif page == "운동 기록 캘린더": calendar_page()
else: main_page(exercises)
