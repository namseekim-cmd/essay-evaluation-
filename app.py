import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. 보안 및 기본 설정
st.set_page_config(page_title="2026 미술하기 생각하기", page_icon="🎨", layout="wide")

hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display: none;}
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# 2. 현재 시간 및 제출 가능 여부 체크
now = datetime.now()
weekday = now.weekday()  # 월(0), 화(1), 수(2), 목(3), 금(4), 토(5), 일(6)
is_open = 2 <= weekday <= 6  # 수요일(2) ~ 일요일(6)

# 3. AI 및 데이터베이스 연결
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    @st.cache_resource
    def get_active_model():
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for p in ['models/gemini-1.5-flash-latest', 'models/gemini-1.5-flash']:
            if p in available: return p
        return available[0]
    
    active_model = get_active_model()
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"⚠️ 시스템 초기화 오류: {e}")
    st.stop()

# 4. 사이드바 및 관리자 기능
with st.sidebar:
    st.title("📅 주차 관리")
    selected_week = st.selectbox("제출 주차 선택", [f"Week{i:02d}" for i in range(1, 13)])
    st.divider()
    admin_pw = st.text_input("시스템 관리자 인증", type="password")
    is_admin = (admin_pw == "1234")

# 5. 데이터 로드 및 현황판
try:
    df = conn.read(worksheet=selected_week, ttl=0)
except:
    df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])

st.title("📝 2026 미술하기 생각하기 에세이")
st.subheader(f"📊 {selected_week} 실시간 현황")

c1, c2, c3 = st.columns(3)
with c1: st.metric("총 제출 인원", f"{len(df)}명 / 125명")
with c2: 
    pass_cnt = df['AI의견'].str.contains("Pass").sum() if not df.empty else 0
    st.metric("참신성 통과", f"{pass_cnt}명")
with c3:
    avg_len = int(df['글자수'].astype(int).mean()) if not df.empty else 0
    st.metric("평균 글자수", f"{avg_len}자")

st.divider()

# 6. 제출 기간 안내 및 폼 제어
if not is_open:
    st.warning("⚠️ 지금은 제출 기간이 아닙니다. (매주 수요일 00:00 ~ 일요일 23:59 제출 가능)")
    st.info(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')} (월/화요일은 시스템 점검 및 휴무입니다.)")
else:
    st.success(f"✅ {selected_week} 과제 제출이 가능합니다. (마감: 이번 주 일요일 23:59)")
    
    with st.form("essay_form", clear_on_submit=True):
        col_id, col_name = st.columns(2)
        with col_id: sid = st.text_input("학번 (숫자만)")
        with col_name: sname = st.text_input("이름")
        content = st.text_area("에세이 내용 (1500자 이상)", height=500)
        submitted = st.form_submit_button(f"{selected_week} 과제 제출하기")

        if submitted:
            if not sid or not sname:
                st.warning("학번과 이름을 입력해 주세요.")
            elif len(content) < 1500:
                st.error(f"❌ 글자수 부족 (현재 {len(content)}자 / 최소 1500자 필요)")
            elif sid in df['학번'].astype(str).values:
                st.error(f"❌ 이미 제출된 학번입니다.")
            else:
                with st.spinner("AI 분석 및 저장 중..."):
                    try:
                        model = genai.GenerativeModel(active_model)
                        prompt = f"에세이 참신성 평가(Pass/Fail 및 1문장 요약):\n\n{content}"
                        response = model.generate_content(prompt)
                        ai_comment = response.text

                        new_data = pd.DataFrame([{
                            "학번": str(sid), "이름": str(sname), 
                            "글자수": len(content), "AI의견": str(ai_comment),
                            "제출시간": datetime.now().strftime('%Y-%m-%d %H:%M')
                        }])

                        updated_df = pd.concat([df, new_data], ignore_index=True).astype(str)
                        conn.update(worksheet=selected_week, data=updated_df)

                        st.balloons()
                        st.success("✅ 제출 완료!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 오류: {e}")

# 7. 하단 명단 및 관리 도구
if not df.empty:
    with st.expander("📋 제출 확인 명단"):
        st.dataframe(df[['학번', '이름', '제출시간']].iloc[::-1], use_container_width=True)

if is_admin:
    st.sidebar.divider()
    if st.sidebar.button(f"🔥 {selected_week} 데이터 초기화"):
        empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])
        conn.update(worksheet=selected_week, data=empty_df)
        st.sidebar.success("초기화 완료")
        st.rerun()
