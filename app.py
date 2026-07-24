"""개인 맞춤 운동 추천 및 루틴 기록 앱."""

from __future__ import annotations

import calendar
import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="나만의 운동 루틴", page_icon="💪", layout="wide")

DATA_PATH = Path("dataset.csv")
SAVE_PATH = Path("user_data.json")
REQUIRED_COLUMNS = ["신체부위", "운동 이름", "난이도", "운동방법", "효과", "주의사항"]
TITLES = [(0, "입문"), (10, "초급"), (30, "중급"), (60, "고급"), (100, "숙련"), (200, "전문")]
MOTIVATION_WORDS = {
    "다이어트": ["전신", "지구력", "하체", "코어"],
    "근육량 증가": ["근력", "볼륨", "발달", "강화"],
    "습관 기르기": ["기초", "전신", "코어"],
    "치료": ["자세", "교정", "가동성", "균형"],
}


def default_data() -> dict:
    return {
        "profile": {
            "이름": "", "성별": "선택 안 함", "나이": 20, "키": 170, "몸무게": 60,
            "운동 동기": "습관 기르기", "주당 운동 횟수": 3, "집중 부위": [],
            "운동 장소": "집", "불편한 부위": "없음", "운동 기간": "3개월",
            "최장 규칙 운동 기간": "없음",
        },
        "routine": [],
        "completed": {},  # {YYYY-MM-DD: [운동 이름, ...]}
        "notes": {},      # {YYYY-MM-DD: 메모}
        "attendance": {}, # {YYYY-MM-DD: True} - 사이트 방문 출석
        "routine_completed_days": {},  # {YYYY-MM-DD: True} - 하루 루틴 전체 완료
    }


def load_user_data() -> dict:
    if not SAVE_PATH.exists():
        return default_data()
    try:
        saved = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
        result = default_data()
        result.update(saved)
        result["profile"] = {**default_data()["profile"], **saved.get("profile", {})}
        return result
    except (json.JSONDecodeError, OSError):
        return default_data()


def save_user_data(user_data: dict) -> None:
    SAVE_PATH.write_text(json.dumps(user_data, ensure_ascii=False, indent=2), encoding="utf-8")


@st.cache_data
def load_exercises() -> pd.DataFrame:
    exercises = pd.read_csv(DATA_PATH, encoding="utf-8-sig").fillna("")
    missing = [column for column in REQUIRED_COLUMNS if column not in exercises.columns]
    if missing:
        raise ValueError(f"dataset.csv에 필요한 컬럼이 없습니다: {', '.join(missing)}")
    return exercises


def split_parts(value: str) -> list[str]:
    return [part.strip() for part in str(value).replace(",", "/").split("/") if part.strip()]


def get_title(total_count: int) -> tuple[str, int | None]:
    current, next_threshold = "입문", None
    for threshold, title in TITLES:
        if total_count >= threshold:
            current = title
        elif next_threshold is None:
            next_threshold = threshold
    return current, next_threshold


def routine_completed_day_count(user_data: dict) -> int:
    """칭호는 운동 개수가 아닌 '하루 루틴 전체 완료' 일수로 계산한다."""
    return len(user_data["routine_completed_days"])


def make_recommendations(exercises: pd.DataFrame, profile: dict) -> pd.DataFrame:
    focus_parts = set(profile.get("집중 부위", []))
    keywords = MOTIVATION_WORDS[profile["운동 동기"]]
    discomfort = profile.get("불편한 부위", "없음").strip()
    beginner = profile.get("최장 규칙 운동 기간") in ("없음", "1개월 미만")

    def score(row: pd.Series) -> int:
        text = f"{row['운동방법']} {row['효과']} {row['주의사항']}"
        score_value = 0
        if focus_parts.intersection(split_parts(row["신체부위"])):
            score_value += 50
        score_value += sum(10 for keyword in keywords if keyword in text)
        if beginner and row["난이도"] == "초급":
            score_value += 15
        if discomfort and discomfort != "없음" and discomfort in text:
            score_value -= 25
        return score_value

    result = exercises.copy()
    result["추천 점수"] = result.apply(score, axis=1)
    return result.sort_values(["추천 점수", "난이도", "운동 이름"], ascending=[False, True, True])


def profile_summary(user_data: dict) -> None:
    profile = user_data["profile"]
    total = routine_completed_day_count(user_data)
    title, next_threshold = get_title(total)
    st.markdown("### 👤 내 프로필")
    st.write(f"**{profile['이름'] or '운동가'}** · {title}")
    st.caption(f"{profile['성별']} · {profile['나이']}세 · {profile['키']}cm · {profile['몸무게']}kg")
    st.metric("루틴 완료 일수", f"{total}일")
    if next_threshold:
        st.progress(total / next_threshold, text=f"다음 칭호까지 {next_threshold - total}회")
    else:
        st.success("최고 칭호 '전문'을 달성했습니다!")


def render_profile_page(user_data: dict, exercises: pd.DataFrame) -> None:
    st.title("프로필 설정")
    st.caption("입력 내용은 추천 운동과 루틴 설계에 반영됩니다.")
    profile = user_data["profile"]
    parts = sorted({part for value in exercises["신체부위"] for part in split_parts(value)})
    genders = ["선택 안 함", "여성", "남성", "기타"]
    locations = ["집", "헬스장", "공원/야외", "학교/회사", "기타"]
    periods = ["1개월", "3개월", "6개월", "1년 이상"]
    histories = ["없음", "1개월 미만", "1~3개월", "3~6개월", "6개월 이상"]

    with st.form("profile_form"):
        left, right = st.columns(2)
        with left:
            name = st.text_input("이름", profile["이름"])
            gender = st.selectbox("성별", genders, index=genders.index(profile["성별"]))
            age = st.number_input("나이", 10, 100, int(profile["나이"]))
            height = st.number_input("키 (cm)", 100, 230, int(profile["키"]))
            weight = st.number_input("몸무게 (kg)", 25, 250, int(profile["몸무게"]))
        with right:
            motivation = st.selectbox("운동 동기", list(MOTIVATION_WORDS), index=list(MOTIVATION_WORDS).index(profile["운동 동기"]))
            frequency = st.slider("주 몇 회 운동할까요?", 1, 7, int(profile["주당 운동 횟수"]))
            focus = st.multiselect("초점을 맞출 신체 부위", parts, default=profile["집중 부위"])
            location = st.selectbox("운동 장소", locations, index=locations.index(profile["운동 장소"]))
            discomfort = st.text_input("불편한 부위", profile["불편한 부위"], placeholder="예: 무릎, 허리 / 없으면 '없음'")
            period = st.selectbox("운동을 수행할 기간", periods, index=periods.index(profile["운동 기간"]))
            history = st.selectbox("이전에 규칙적으로 운동한 최장 기간", histories, index=histories.index(profile["최장 규칙 운동 기간"]))
        submitted = st.form_submit_button("프로필 저장", width="stretch")

    if submitted:
        user_data["profile"] = {
            "이름": name, "성별": gender, "나이": age, "키": height, "몸무게": weight,
            "운동 동기": motivation, "주당 운동 횟수": frequency, "집중 부위": focus,
            "운동 장소": location, "불편한 부위": discomfort or "없음", "운동 기간": period,
            "최장 규칙 운동 기간": history,
        }
        save_user_data(user_data)
        st.success("프로필을 저장했습니다.")


def render_calendar_page(user_data: dict) -> None:
    st.title("운동 기록 캘린더")
    month_date = st.date_input("확인할 달 선택", date.today(), key="month_date")
    selected_date = st.session_state.get("selected_record_date", month_date)
    if not isinstance(selected_date, date):
        selected_date = month_date
    year, month = month_date.year, month_date.month
    if (selected_date.year, selected_date.month) != (year, month):
        selected_date = month_date
    st.caption(f"{year}년 {month}월 · ✅ 출석 완료 · 🏆 루틴 완료 · 📝 메모 기록됨")

    for week in calendar.monthcalendar(year, month):
        columns = st.columns(7)
        for column, day_number in zip(columns, week):
            if not day_number:
                continue
            day_key = date(year, month, day_number).isoformat()
            if column.button(str(day_number), key=f"calendar_{day_key}", width="stretch"):
                st.session_state.selected_record_date = date(year, month, day_number)
                st.rerun()
            status = []
            if user_data["attendance"].get(day_key):
                status.append("✅ 출석")
            if user_data["routine_completed_days"].get(day_key):
                status.append("🏆 완료")
            if user_data["notes"].get(day_key):
                status.append("📝 메모")
            column.caption(" · ".join(status) if status else "")

    day_key = selected_date.isoformat()
    exercises = user_data["completed"].get(day_key, [])
    left, right = st.columns([1, 1])
    with left:
        st.subheader(f"{day_key} 기록")
        st.write("출석 완료" if user_data["attendance"].get(day_key) else "출석 기록 없음")
        st.write("루틴 완료" if user_data["routine_completed_days"].get(day_key) else "루틴 미완료")
        st.write("완료한 운동: " + (", ".join(exercises) if exercises else "없음"))
    with right:
        note = st.text_area("그날의 피드백 메모", value=user_data["notes"].get(day_key, ""), placeholder="운동에서 느낀 점과 다음에 기록할 점을 적어 보세요.")
        if user_data["notes"].get(day_key):
            st.success("메모가 기록되어 있습니다.")
        if st.button("메모 저장"):
            if note.strip():
                user_data["notes"][day_key] = note.strip()
            else:
                user_data["notes"].pop(day_key, None)
            save_user_data(user_data)
            st.success("메모를 저장했습니다.")
            st.rerun()


def add_exercise_to_routine(user_data: dict, exercise_name: str) -> tuple[bool, str]:
    """중복 없이 원하는 수만큼 루틴에 운동을 추가한다."""
    if exercise_name in user_data["routine"]:
        return False, "이미 나의 루틴에 추가된 운동입니다."
    user_data["routine"].append(exercise_name)
    save_user_data(user_data)
    return True, f"{exercise_name}을(를) 루틴에 추가했습니다."


def render_my_routine_page(user_data: dict, exercises: pd.DataFrame) -> None:
    """현재 루틴을 한 화면에서 관리하고 검색으로 운동을 추가하는 페이지."""
    st.title("나의 루틴")
    st.caption("현재 루틴을 확인하고 운동을 직접 검색하여 원하는 수만큼 구성하세요.")

    today = date.today().isoformat()
    current_names = user_data["routine"]
    current = exercises[exercises["운동 이름"].isin(current_names)].copy()
    current["순서"] = current["운동 이름"].map({name: index for index, name in enumerate(current_names)})
    current = current.sort_values("순서")

    summary_left, summary_right = st.columns([1, 2])
    with summary_left:
        completed_today = user_data["completed"].get(today, [])
        done_count = len(set(current_names) & set(completed_today))
        st.metric("현재 루틴", f"{len(current_names)}개")
        st.metric("오늘 완료", f"{done_count}/{len(current_names)}개")
        if current_names:
            st.progress(done_count / len(current_names))
    with summary_right:
        if current.empty:
            st.info("아직 루틴이 없습니다. 아래에서 운동을 검색해 추가하세요.")
        else:
            st.subheader("한눈에 보는 오늘의 루틴")
            for order, (_, row) in enumerate(current.iterrows(), start=1):
                name = row["운동 이름"]
                done = name in completed_today
                item_left, item_right = st.columns([5, 1])
                item_left.markdown(f"**{order}. {name}** · {row['신체부위']} · {row['난이도']} {'✅' if done else ''}")
                if item_right.button("삭제", key=f"remove_{name}", width="stretch"):
                    user_data["routine"].remove(name)
                    save_user_data(user_data)
                    st.rerun()

    st.divider()
    st.subheader("운동 직접 검색 · 루틴 추가")
    keyword = st.text_input("검색어", placeholder="운동 이름, 효과, 운동방법을 입력하세요. 예: 스쿼트, 코어", key="routine_search")
    all_parts = sorted({part for value in exercises["신체부위"] for part in split_parts(value)})
    filter_left, filter_right = st.columns(2)
    selected_parts = filter_left.multiselect("신체 부위 선택", all_parts, key="routine_search_parts")
    selected_levels = filter_right.multiselect("난이도 선택", ["초급", "중급", "고급"], key="routine_search_levels")
    if keyword.strip() or selected_parts or selected_levels:
        searchable = exercises["운동 이름"] + " " + exercises["신체부위"] + " " + exercises["운동방법"] + " " + exercises["효과"]
        results = exercises.copy()
        if keyword.strip():
            results = results[searchable.str.contains(keyword.strip(), case=False, na=False)]
        if selected_parts:
            results = results[results["신체부위"].apply(lambda value: bool(set(split_parts(value)) & set(selected_parts)))]
        if selected_levels:
            results = results[results["난이도"].isin(selected_levels)]
        results = results.head(30)
        if results.empty:
            st.info("검색 결과가 없습니다.")
        else:
            st.caption(f"검색 결과 {len(results)}개")
            for row_index, row in results.iterrows():
                name = row["운동 이름"]
                result_left, result_middle, result_right = st.columns([4, 2, 1])
                result_left.markdown(f"**{name}**")
                result_middle.caption(f"{row['신체부위']} · {row['난이도']}")
                is_added = name in user_data["routine"]
                if result_right.button("추가됨" if is_added else "추가", key=f"routine_add_{row_index}", disabled=is_added, width="stretch"):
                    _, message = add_exercise_to_routine(user_data, name)
                    st.success(message)
                    st.rerun()
                with st.expander(f"{name} 운동 설명"):
                    st.markdown(f"**운동방법**  \n{row['운동방법']}")
                    st.markdown(f"**효과**  \n{row['효과']}")
                    st.markdown(f"**주의사항**  \n{row['주의사항']}")


def render_main_page(user_data: dict, exercises: pd.DataFrame) -> None:
    st.title("오늘의 맞춤 운동")
    st.caption("추천된 4개 운동을 선택하거나 직접 검색한 운동을 더해 원하는 수만큼 오늘의 루틴을 구성하세요.")
    left, right = st.columns([1, 2], gap="large")
    with left:
        profile_summary(user_data)
        st.caption("프로필 설정에서 정보를 수정하면 추천 결과가 달라집니다.")
    with right:
        recommended = make_recommendations(exercises, user_data["profile"]).head(4)
        st.subheader("맞춤 추천 4가지")
        options = recommended["운동 이름"].tolist()
        saved_options = [item for item in user_data["routine"] if item in options]
        chosen = st.multiselect("오늘의 루틴 선택", options, default=saved_options, placeholder="추천 운동 중 원하는 운동 선택")
        if st.button("선택한 운동으로 루틴 저장", disabled=not chosen, width="stretch"):
            # 검색을 통해 추가한 운동은 추천 목록에 없어도 보존한다.
            searched_items = [item for item in user_data["routine"] if item not in options]
            user_data["routine"] = list(dict.fromkeys(searched_items + chosen))
            save_user_data(user_data)
            st.success(f"오늘의 루틴 {len(user_data['routine'])}개를 저장했습니다.")
            st.rerun()
        for _, row in recommended.iterrows():
            st.markdown(f"**{row['운동 이름']}** · {row['신체부위']} · {row['난이도']}")
            st.caption(row["효과"])

        with st.expander("운동 검색으로 루틴에 추가"):
            search_word = st.text_input("운동 이름·효과·방법 검색", placeholder="예: 스쿼트, 코어", key="exercise_search")
            body_parts = sorted({part for value in exercises["신체부위"] for part in split_parts(value)})
            detail_left, detail_right = st.columns(2)
            searched_parts = detail_left.multiselect("신체 부위", body_parts, key="main_search_parts")
            searched_levels = detail_right.multiselect("난이도", ["초급", "중급", "고급"], key="main_search_levels")
            if search_word.strip() or searched_parts or searched_levels:
                searchable = exercises["운동 이름"] + " " + exercises["신체부위"] + " " + exercises["운동방법"] + " " + exercises["효과"]
                results = exercises.copy()
                if search_word.strip():
                    results = results[searchable.str.contains(search_word.strip(), case=False, na=False)]
                if searched_parts:
                    results = results[results["신체부위"].apply(lambda value: bool(set(split_parts(value)) & set(searched_parts)))]
                if searched_levels:
                    results = results[results["난이도"].isin(searched_levels)]
                results = results.head(20)
                if results.empty:
                    st.info("검색 결과가 없습니다.")
                for row_index, row in results.iterrows():
                    name = row["운동 이름"]
                    search_left, search_right = st.columns([4, 1])
                    search_left.write(f"**{name}** · {row['신체부위']} · {row['난이도']}")
                    already_added = name in user_data["routine"]
                    if search_right.button("추가됨" if already_added else "루틴 추가", key=f"add_{row_index}", disabled=already_added, width="stretch"):
                        _, message = add_exercise_to_routine(user_data, name)
                        st.success(message)
                        st.rerun()
                    with st.expander(f"{name} 운동 설명"):
                        st.markdown(f"**운동방법**  \n{row['운동방법']}")
                        st.markdown(f"**효과**  \n{row['효과']}")
                        st.markdown(f"**주의사항**  \n{row['주의사항']}")

    st.divider()
    st.subheader("오늘의 루틴 진행")
    today = date.today().isoformat()
    routine = exercises[exercises["운동 이름"].isin(user_data["routine"])]
    if routine.empty:
        st.info("추천 운동에서 1개 이상을 선택해 오늘의 루틴을 저장하세요.")
        return
    completed_today = user_data["completed"].get(today, [])
    for _, row in routine.iterrows():
        name = row["운동 이름"]
        with st.container(border=True):
            st.markdown(f"#### {name}")
            st.caption(f"{row['신체부위']} · {row['난이도']}")
            st.write(row["운동방법"])
            with st.expander("효과 및 주의사항"):
                st.markdown(f"**효과**  \n{row['효과']}")
                st.markdown(f"**주의사항**  \n{row['주의사항']}")
            already_done = name in completed_today
            if st.button("오늘 완료" if not already_done else "오늘 완료됨", key=f"complete_{name}", disabled=already_done, width="stretch"):
                user_data["completed"].setdefault(today, []).append(name)
                save_user_data(user_data)
                st.toast(f"{name} 완료! 같은 운동은 하루에 한 번만 기록됩니다.")
                st.rerun()

    done_count = len(set(user_data["routine"]) & set(completed_today))
    if done_count == len(user_data["routine"]):
        if not user_data["routine_completed_days"].get(today):
            user_data["routine_completed_days"][today] = True
            save_user_data(user_data)
        st.success("🎉 오늘의 루틴을 모두 완료했습니다. 출석이 기록되었습니다!")
    else:
        st.progress(done_count / len(user_data["routine"]), text=f"오늘 루틴 {done_count}/{len(user_data['routine'])}개 완료")


try:
    exercise_data = load_exercises()
except Exception as error:
    st.error(f"운동 데이터를 불러오지 못했습니다: {error}")
    st.stop()

if "page" not in st.session_state:
    st.session_state.page = "메인 페이지"
user_data = load_user_data()
today_key = date.today().isoformat()
# 사이트에 접속한 날은 자동 출석 처리한다. 이미 출석한 날은 다시 기록하지 않는다.
if not user_data["attendance"].get(today_key):
    user_data["attendance"][today_key] = True
    save_user_data(user_data)

st.sidebar.title("💪 나만의 운동")
st.sidebar.divider()
st.sidebar.caption("페이지 이동")
nav_pages = [
    ("🏠 메인", "메인 페이지"),
    ("📋 나의 루틴", "나의 루틴"),
    ("👤 프로필 설정", "프로필 설정"),
    ("📅 운동 기록", "운동 기록"),
]
for label, target_page in nav_pages:
    st.sidebar.button(
        label,
        key=f"nav_{target_page}",
        type="primary" if st.session_state.page == target_page else "secondary",
        on_click=lambda target=target_page: st.session_state.update(page=target),
        width="stretch",
    )
page = st.session_state.page

if page == "프로필 설정":
    render_profile_page(user_data, exercise_data)
elif page == "운동 기록":
    render_calendar_page(user_data)
elif page == "나의 루틴":
    render_my_routine_page(user_data, exercise_data)
else:
    render_main_page(user_data, exercise_data)
