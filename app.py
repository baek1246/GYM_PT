import calendar
import json
import os
from datetime import date, datetime
from html import escape

import pandas as pd
import streamlit as st


st.set_page_config(page_title="GYM PT ㅣ 운동 추천", page_icon="💪", layout="wide")

DATA_PATH = "dataset.csv"
STATE_PATH = "fitness_state.json"


def load_exercises() -> pd.DataFrame:
    """Read the supplied CSV without depending on its display encoding."""
    frame = pd.read_csv(DATA_PATH)
    frame = frame.iloc[:, :6].copy()
    frame.columns = ["body_part", "name", "level", "method", "effect", "caution"]
    return frame.dropna(subset=["name"]).fillna("")


def default_state() -> dict:
    return {
        "profile": {"name": "", "height": None, "weight": None, "age": None,
                    "gender": "선택 안 함", "goal": "건강 관리", "preferred_parts": [], "memo": ""},
        "favorites": [],
        "workouts": [],
        "routine_completions": [],
        "daily_notes": {},
        "attendance": [],
    }


def load_state() -> dict:
    state = default_state()
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as file:
                saved = json.load(file)
            for key in state:
                if key in saved:
                    state[key] = saved[key]
            state["profile"] = {**default_state()["profile"], **state["profile"]}
        except (OSError, json.JSONDecodeError):
            pass
    return state


def save_state() -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as file:
        json.dump(st.session_state.app_state, file, ensure_ascii=False, indent=2)


def initialize() -> None:
    if "app_state" not in st.session_state:
        st.session_state.app_state = load_state()
    # Keep already-open sessions compatible when new profile/stat fields are added.
    defaults = default_state()
    for key, value in defaults.items():
        st.session_state.app_state.setdefault(key, value)
    for key, value in defaults["profile"].items():
        st.session_state.app_state["profile"].setdefault(key, value)


def body_parts(value: str) -> list[str]:
    return [part.strip() for part in str(value).replace(",", "/").split("/") if part.strip()]


def level_rank(level: str) -> int:
    """Return a comparable difficulty score even when the data uses Korean labels."""
    text = str(level)
    if "초" in text:
        return 1
    if "고" in text:
        return 3
    return 2


TITLE_LEVELS = [("입문", 0), ("초급", 5), ("중급", 15), ("고급", 30), ("숙련", 60), ("전문", 100)]


def current_title() -> tuple[str, int | None]:
    total = len(set(st.session_state.app_state["routine_completions"]))
    title = "입문"
    next_goal = None
    for index, (name, requirement) in enumerate(TITLE_LEVELS):
        if total >= requirement:
            title = name
            next_goal = TITLE_LEVELS[index + 1][1] if index + 1 < len(TITLE_LEVELS) else None
    return title, next_goal


def level_badge(level: str) -> str:
    rank = level_rank(level)
    return f"<span class='level-badge level-{rank}'><span class='level-dot'></span>{escape(str(level))}</span>"


def complete_routine() -> bool:
    today_key = date.today().isoformat()
    completed = st.session_state.app_state["routine_completions"]
    if today_key in completed:
        return False
    completed.append(today_key)
    if today_key not in st.session_state.app_state["attendance"]:
        st.session_state.app_state["attendance"].append(today_key)
    save_state()
    return True


def profile_recommendations(exercises: pd.DataFrame, profile: dict, focus_parts: list[str] | None = None) -> tuple[pd.DataFrame, list[str], str]:
    """Rank exercises from the saved profile and explain the applied criteria."""
    frame = exercises.copy()
    reasons: list[str] = []
    goal = profile.get("goal", "건강 관리")
    goal_keywords = {
        "체중 감량": ["지구력", "전신", "유산소", "칼로리", "체지방"],
        "근력 향상": ["근력", "강화", "파워", "힘"],
        "근육량 증가": ["근비대", "근육", "발달", "매스"],
        "체력 증진": ["지구력", "심폐", "전신", "체력"],
        "건강 관리": ["기초", "전신", "가동성", "균형"],
    }
    keywords = goal_keywords.get(goal, goal_keywords["건강 관리"])
    frame["recommendation_score"] = 0
    searchable = (frame["effect"] + " " + frame["method"] + " " + frame["body_part"]).str.lower()
    for keyword in keywords:
        frame["recommendation_score"] += searchable.str.contains(keyword.lower(), na=False).astype(int) * 12
    reasons.append(f"목표 ‘{goal}’에 맞는 운동 효과를 우선 반영했습니다.")

    preferred = focus_parts if focus_parts is not None else profile.get("preferred_parts", [])
    if preferred:
        frame["recommendation_score"] += frame["body_part"].apply(
            lambda value: 30 if any(part in str(value) for part in preferred) else 0
        )
        reasons.append(f"선호 부위({', '.join(preferred)})를 우선 배치했습니다.")

    height, weight = profile.get("height"), profile.get("weight")
    bmi = None
    if height and weight:
        bmi = float(weight) / (float(height) / 100) ** 2
        if bmi >= 25:
            frame["recommendation_score"] += (frame["level"].apply(level_rank) == 1).astype(int) * 8
            reasons.append(f"BMI {bmi:.1f} 기준으로 관절 부담이 적은 초급 운동 비중을 높였습니다.")
        elif bmi < 18.5:
            frame["recommendation_score"] += searchable.str.contains("근력|근육|기초", na=False).astype(int) * 6
            reasons.append(f"BMI {bmi:.1f} 기준으로 기초 근력 운동을 우선했습니다.")

    age = profile.get("age")
    if age and int(age) >= 60:
        frame["recommendation_score"] += (frame["level"].apply(level_rank) == 1).astype(int) * 15
        reasons.append("연령 정보를 반영해 초급·기초 동작을 우선했습니다.")
    elif age and int(age) < 20:
        frame["recommendation_score"] += (frame["level"].apply(level_rank) <= 2).astype(int) * 6
        reasons.append("연령 정보를 반영해 무리하지 않는 난이도를 우선했습니다.")

    memo = str(profile.get("memo", ""))
    caution_words = [word for word in ["무릎", "허리", "어깨", "목", "손목"] if word in memo]
    if caution_words:
        caution_text = (frame["caution"] + " " + frame["method"]).str.lower()
        for word in caution_words:
            frame["recommendation_score"] -= caution_text.str.contains(word, na=False).astype(int) * 30
        reasons.append(f"추가 사항의 주의 부위({', '.join(caution_words)})가 언급된 동작은 뒤로 배치했습니다.")

    completed = {log["exercise"] for log in st.session_state.app_state["workouts"]}
    frame["recommendation_score"] -= frame["name"].isin(completed).astype(int) * 2
    return frame.sort_values(["recommendation_score", "name"], ascending=[False, True]), reasons, (f"BMI {bmi:.1f}" if bmi else "신체 정보 미입력")


def add_workout(exercise: str) -> None:
    day = date.today().isoformat()
    st.session_state.app_state["workouts"].append({
        "date": day, "exercise": exercise, "completed_at": datetime.now().strftime("%H:%M")
    })
    if day not in st.session_state.app_state["attendance"]:
        st.session_state.app_state["attendance"].append(day)
    save_state()


def toggle_favorite(exercise: str) -> None:
    favorites = st.session_state.app_state["favorites"]
    if exercise in favorites:
        favorites.remove(exercise)
    else:
        favorites.append(exercise)
    save_state()


def workout_count(day: str | None = None) -> int:
    logs = st.session_state.app_state["workouts"]
    return sum(1 for log in logs if day is None or log["date"] == day)


def render_profile_popover() -> None:
    profile = st.session_state.app_state["profile"]
    label = f"👤 {profile['name']}님의 프로필" if profile["name"] else "👤 프로필 설정"
    with st.popover(label, use_container_width=True):
        st.subheader("내 프로필")
        with st.form("profile_form"):
            name = st.text_input("이름", value=profile["name"], placeholder="예: 김운동")
            col1, col2, col3 = st.columns(3)
            with col1:
                height = st.number_input("키 (cm)", 0.0, 250.0, value=float(profile["height"] or 0), step=0.1)
            with col2:
                weight = st.number_input("몸무게 (kg)", 0.0, 300.0, value=float(profile["weight"] or 0), step=0.1)
            with col3:
                age = st.number_input("나이", 0, 120, value=int(profile["age"] or 0))
            gender = st.selectbox("성별", ["선택 안 함", "여성", "남성", "기타"],
                                  index=["선택 안 함", "여성", "남성", "기타"].index(profile["gender"]))
            goal = st.selectbox("운동 목표", ["건강 관리", "체중 감량", "근력 향상", "근육량 증가", "체력 증진"],
                                index=["건강 관리", "체중 감량", "근력 향상", "근육량 증가", "체력 증진"].index(profile["goal"]))
            preferred_parts = st.multiselect("집중하고 싶은 부위", all_parts, default=profile.get("preferred_parts", []))
            memo = st.text_area("추가 사항", value=profile["memo"], placeholder="부상 이력, 선호 운동, 주의할 점 등을 적어주세요.")
            if st.form_submit_button("프로필 저장", use_container_width=True):
                st.session_state.app_state["profile"] = {
                    "name": name.strip(), "height": height or None, "weight": weight or None,
                    "age": age or None, "gender": gender, "goal": goal,
                    "preferred_parts": preferred_parts, "memo": memo.strip(),
                }
                save_state()
                st.success("프로필을 저장했습니다.")
                st.rerun()


def render_card(row: pd.Series, key: str, show_plan: bool = False) -> None:
    name = row["name"]
    with st.container(border=True):
        st.markdown(f"### 💪 {name}")
        st.markdown(
            f"{level_badge(row['level'])} <span class='body-part-label'>{escape(str(row['body_part']))}</span>",
            unsafe_allow_html=True,
        )
        st.write(row["method"])
        if show_plan:
            st.info("권장 수행: 3세트 × 8~12회")
        with st.expander("운동 효과 및 주의사항"):
            st.markdown(f"**효과**  \n{row['effect']}")
            st.markdown(f"**주의사항**  \n{row['caution']}")
        left, right = st.columns(2)
        favorite = name in st.session_state.app_state["favorites"]
        with left:
            if st.button("★ 저장됨" if favorite else "☆ 즐겨찾기", key=f"fav_{key}", use_container_width=True):
                toggle_favorite(name)
                st.rerun()
        with right:
            if st.button("✓ 운동 완료", key=f"done_{key}", type="primary", use_container_width=True):
                add_workout(name)
                st.toast(f"{name} 완료! 누적 완료 횟수가 1회 늘었습니다.")


def render_grid(frame: pd.DataFrame, prefix: str, columns: int = 3, show_plan: bool = False) -> None:
    if frame.empty:
        st.info("조건에 맞는 운동이 없습니다.")
        return
    cols = st.columns(columns)
    for index, (_, row) in enumerate(frame.iterrows()):
        with cols[index % columns]:
            render_card(row, f"{prefix}_{index}_{row['name']}", show_plan)


def calendar_html(year: int, month: int, records: dict[str, dict]) -> str:
    weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)
    headings = ["일", "월", "화", "수", "목", "금", "토"]
    html = "<table class='calendar'><thead><tr>" + "".join(f"<th>{d}</th>" for d in headings) + "</tr></thead><tbody>"
    for week in weeks:
        html += "<tr>"
        for day in week:
            key = day.isoformat()
            info = records.get(key, {})
            classes = "other-month" if day.month != month else ("attended" if info.get("attendance") else "")
            items = []
            if info.get("attendance"):
                items.append("<span class='attendance-dot'>출석</span>")
            if info.get("workouts"):
                preview = ", ".join(info["workouts"][:2])
                suffix = " 외" if len(info["workouts"]) > 2 else ""
                items.append(f"<div class='cal-workout'>💪 {escape(preview)}{suffix}</div>")
            if info.get("note"):
                items.append(f"<div class='cal-note'>📝 {escape(info['note'][:18])}</div>")
            html += f"<td class='{classes}'><strong>{day.day}</strong>{''.join(items)}</td>"
        html += "</tr>"
    return html + "</tbody></table>"


initialize()
exercises = load_exercises()
all_parts = sorted({part for value in exercises["body_part"] for part in body_parts(value)})

st.markdown("""
<style>
.main .block-container { padding-top: 1.7rem; padding-bottom: 3rem; }
div[data-testid='stMetric'] { background: #fff; border: 1px solid #e7eaf0; border-radius: 12px; padding: 14px; }
.level-badge { display:inline-flex; align-items:center; gap:6px; padding:3px 9px; border-radius:999px; font-size:.82rem; font-weight:700; margin:0 6px 8px 0; }
.level-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.level-1 { background:#ecfdf5; color:#166534; border:1px solid #86efac; }.level-1 .level-dot { background:#22c55e; }
.level-2 { background:#fefce8; color:#854d0e; border:1px solid #fde047; }.level-2 .level-dot { background:#eab308; }
.level-3 { background:#fef2f2; color:#991b1b; border:1px solid #fca5a5; }.level-3 .level-dot { background:#ef4444; }
.body-part-label { display:inline-block; padding:3px 9px; border-radius:999px; color:#475569; background:#f8fafc; border:1px solid #e2e8f0; font-size:.82rem; }
.title-panel { border:1px solid #c4b5fd; background:linear-gradient(135deg,#faf5ff,#eef2ff); border-radius:14px; padding:14px 18px; margin:8px 0 18px; }
.calendar { width:100%; border-collapse:separate; border-spacing:5px; table-layout:fixed; }
.calendar th { color:#6b7280; font-size:.85rem; padding:5px; text-align:left; }
.calendar td { height:105px; vertical-align:top; padding:8px; border:1px solid #e5e7eb; border-radius:9px; background:#fff; overflow:hidden; font-size:.77rem; }
.calendar td.attended { background:#f0fdf4; border-color:#86efac; }
.calendar td.other-month { opacity:.35; }
.attendance-dot { display:inline-block; margin-left:5px; padding:2px 5px; border-radius:9px; background:#dcfce7; color:#166534; font-size:.65rem; }
.cal-workout { color:#155e75; margin-top:5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cal-note { color:#7c3aed; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
</style>
""", unsafe_allow_html=True)

head, profile_col = st.columns([4, 1])
with head:
    st.title("💪 GYM PT")
    st.caption("나에게 맞는 운동을 찾고, 완료 기록과 출석을 한 곳에서 관리하세요.")
with profile_col:
    render_profile_popover()

today = date.today().isoformat()
profile = st.session_state.app_state["profile"]
title_name, next_title_goal = current_title()
routine_total = len(set(st.session_state.app_state["routine_completions"]))
metrics = st.columns(5)
metrics[0].metric("누적 운동 완료", f"{workout_count()}회")
metrics[1].metric("오늘 완료", f"{workout_count(today)}회")
metrics[2].metric("출석 일수", f"{len(set(st.session_state.app_state['attendance']))}일")
metrics[3].metric("루틴 완료", f"{routine_total}일")
metrics[4].metric("현재 칭호", title_name)
next_message = "최고 칭호 ‘전문’을 달성했습니다!" if next_title_goal is None else f"다음 칭호까지 {next_title_goal - routine_total}회 남았습니다."
st.markdown(f"<div class='title-panel'>🏅 <b>{title_name}</b> 칭호 보유 · 루틴 누적 완료 <b>{routine_total}일</b><br><span>{next_message}</span></div>", unsafe_allow_html=True)
if profile["name"]:
    st.success(f"{profile['name']}님, 목표는 **{profile['goal']}**입니다. 오늘도 한 걸음씩 해봐요!")

tab_find, tab_recommend, tab_routine, tab_favorites, tab_records = st.tabs(
    ["운동 찾기", "맞춤 추천", "오늘의 루틴", "★ 즐겨찾기", "프로필 · 기록 캘린더"]
)

with tab_find:
    filters = st.columns([2, 2, 2])
    with filters[0]:
        selected_parts = st.multiselect("운동 부위", all_parts)
    with filters[1]:
        selected_levels = st.multiselect("난이도", sorted(exercises["level"].unique()))
    with filters[2]:
        search = st.text_input("운동 이름 검색")
    filtered = exercises.copy()
    if selected_parts:
        filtered = filtered[filtered["body_part"].apply(lambda x: any(p in str(x) for p in selected_parts))]
    if selected_levels:
        filtered = filtered[filtered["level"].isin(selected_levels)]
    if search:
        filtered = filtered[filtered["name"].str.contains(search, case=False, na=False)]
    st.subheader(f"검색 결과 {len(filtered)}개")
    render_grid(filtered, "find")

with tab_recommend:
    st.subheader("프로필 맞춤 운동 추천")
    saved_parts = profile.get("preferred_parts", [])
    choices = st.multiselect("이번 추천에서 집중할 부위", all_parts, default=saved_parts, key="recommend_focus")
    recommended, recommendation_reasons, body_summary = profile_recommendations(exercises, profile, choices)
    if not profile["height"] or not profile["weight"] or not profile["age"]:
        st.info("더 정교한 추천을 위해 프로필에서 키·몸무게·나이와 집중 부위를 입력해 주세요.")
    st.markdown(f"**추천 기준:** {body_summary}")
    for reason in recommendation_reasons:
        st.caption(f"• {reason}")
    render_grid(recommended.head(9), "recommend", show_plan=True)

with tab_routine:
    st.subheader("오늘의 운동 루틴")
    count = st.slider("루틴 운동 개수", 3, 8, 5)
    routine_parts = st.multiselect("루틴 부위", all_parts, default=profile.get("preferred_parts", []), key="routine_parts")
    routine, _, _ = profile_recommendations(exercises, profile, routine_parts)
    routine = routine.head(count)
    st.caption("프로필의 목표·신체 정보·주의 사항을 반영한 루틴입니다. 카드에서 ‘운동 완료’를 누르면 완료 횟수와 오늘 출석에 즉시 반영됩니다.")
    already_completed = today in st.session_state.app_state["routine_completions"]
    if st.button("🏁 오늘 루틴 전체 완료", type="primary", disabled=already_completed):
        if complete_routine():
            st.balloons()
            st.toast("오늘의 루틴 완료! 칭호 누적 횟수가 증가했습니다.")
            st.rerun()
    if already_completed:
        st.success("오늘의 루틴은 이미 완료 처리되었습니다.")
    st.caption("칭호: 입문(0) · 초급(5) · 중급(15) · 고급(30) · 숙련(60) · 전문(100)")
    render_grid(routine, "routine", show_plan=True)

with tab_favorites:
    favorite_names = st.session_state.app_state["favorites"]
    favorite_exercises = exercises[exercises["name"].isin(favorite_names)]
    st.subheader(f"즐겨찾기한 운동 {len(favorite_exercises)}개")
    st.caption("자주 하는 운동을 모아 보고, 여기서도 바로 운동 완료 기록을 남길 수 있습니다.")
    if favorite_exercises.empty:
        st.info("아직 즐겨찾기한 운동이 없습니다. 운동 카드의 ‘☆ 즐겨찾기’ 버튼을 눌러 추가해 보세요.")
    else:
        render_grid(favorite_exercises, "favorite", show_plan=True)

with tab_records:
    st.subheader("운동 기록 캘린더")
    st.caption("출석, 완료한 운동, 그리고 그날의 메모를 월간 화면에서 함께 확인할 수 있습니다.")
    record_controls = st.columns([1, 1, 2])
    with record_controls[0]:
        target_date = st.date_input("기록할 날짜", value=date.today())
    target_key = target_date.isoformat()
    state = st.session_state.app_state
    with record_controls[1]:
        attended = st.checkbox("출석으로 표시", value=target_key in state["attendance"])
        if attended != (target_key in state["attendance"]):
            if attended:
                state["attendance"].append(target_key)
            else:
                state["attendance"].remove(target_key)
            save_state()
            st.rerun()
    with record_controls[2]:
        note = st.text_input("오늘의 메모", value=state["daily_notes"].get(target_key, ""), placeholder="예: 하체 운동 완료, 컨디션 좋음")
        if st.button("메모 저장"):
            if note.strip():
                state["daily_notes"][target_key] = note.strip()
            else:
                state["daily_notes"].pop(target_key, None)
            save_state()
            st.success("메모를 저장했습니다.")
            st.rerun()

    month_col, detail_col = st.columns([3, 1])
    with month_col:
        calendar_month = st.date_input("조회할 월", value=target_date, key="calendar_month")
        records = {}
        for log in state["workouts"]:
            records.setdefault(log["date"], {"attendance": False, "workouts": [], "note": ""})["workouts"].append(log["exercise"])
        for day in state["attendance"]:
            records.setdefault(day, {"attendance": False, "workouts": [], "note": ""})["attendance"] = True
        for day, day_note in state["daily_notes"].items():
            records.setdefault(day, {"attendance": False, "workouts": [], "note": ""})["note"] = day_note
        st.markdown(calendar_html(calendar_month.year, calendar_month.month, records), unsafe_allow_html=True)
    with detail_col:
        st.markdown(f"#### {target_date.strftime('%m월 %d일')} 상세")
        day_logs = [log for log in state["workouts"] if log["date"] == target_key]
        st.write("출석 완료" if target_key in state["attendance"] else "출석 기록 없음")
        if day_logs:
            st.markdown("**완료한 운동**")
            for log in day_logs:
                st.write(f"• {log['exercise']} ({log['completed_at']})")
        else:
            st.caption("완료한 운동이 없습니다.")
        if state["daily_notes"].get(target_key):
            st.markdown("**메모**")
            st.write(state["daily_notes"][target_key])
