import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 정밀 보안 설정 (사이드바 자동 열림 + 화살표 보호)
# ==========================================
st.set_page_config(
    page_title="2026 미술하기 생각하기", 
    page_icon="🎨", 
    layout="wide",
    initial_sidebar_state="expanded" # 접속 시 주차 메뉴가 자동으로 펼쳐짐
)

# [수정] 화살표 버튼은 남겨두고, 우측의 깃허브/배포/메뉴만 쏙 가리는 CSS
hide_style = """
    <style>
    /* 1. 우측 상단 햄버거 메뉴(점 3개) 숨기기 */
    #MainMenu {visibility: hidden;}
    
    /* 2. 하단 푸터(Made with Streamlit) 숨기기 */
    footer {visibility: hidden;}
    
    /* 3. 상단 툴바에서 깃허브, 뷰 소스 아이콘 등만 가리기 */
    /* 화살표(Sidebar Toggle)를 살리기 위해 전체 가리기 대신 요소를 투명하게 처리합니다 */
    [data-testid="stToolbar"] {visibility: hidden;}
    .stAppDeployButton {display: none;}
    
    /* 4. 사이드바 화살표(Collapse/Expand) 버튼은 다시 보이게 강제 설정 */
    button[data-testid="stSidebarCollapseButton"] {
        visibility: visible !important;
        color: #31333F; /* 버튼 색상을 명확하게 설정 */
    }
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# ==========================================
# 2. 시간 및 시스템 설정
# ==========================================
now = datetime.now()
weekday = now.weekday()  # 수(2) ~ 일(6) 제출 가능
is_open = 2 <= weekday <= 6

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    @st.cache_resource
    def get_model():
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for p in ['models/gemini-3-flash', 'models/gemini-1.5-flash-latest']:
            if p in available: return p
        return available[0]
    
    active_model = get_model()
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"⚠️ 시스템 초기화 오류: {e}")
    st.stop()

# ==========================================
# 3. 사이드바 (주차 선택 및 관리)
# ==========================================
with st.sidebar:
    st.title("📅 주차 선택")
    selected_week = st.selectbox(
        "제출할 주차를 선택하세요", 
        [f"Week{i:02d}" for i in range(1, 13)]
    )
    st.divider()
    admin_pw = st.text_input("관리자 인증", type="password")
    is_admin = (admin_pw == "1234")

# ==========================================
# 4. 현황판 표시
# ==========================================
try:
    df = conn.read(worksheet=selected_week, ttl=0)
except:
    df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])

st.title("🎨 2026 미술하기 생각하기 에세이")
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

# ==========================================
# 5. 제출 폼 및 로직
# ==========================================
if not is_open:
    st.warning("⚠️ 지금은 제출 기간이 아닙니다. (매주 수요일 ~ 일요일 제출 가능)")
    st.info(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")
else:
    st.success(f"✅ {selected_week} 제출 가능 (마감: 이번 주 일요일 23:59)")
    with st.form("essay_form", clear_on_submit=True):
        cid, cname = st.columns(2)
        with cid: sid = st.text_input("학번 (숫자만)")
        with cname: sname = st.text_input("이름")
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
                        prompt = f"미술에 대한 참신성 평가(Pass/Fail 및 1문장 요약):\n\n{content}"
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
                        st.success("✅ 제출 성공!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 오류 발생: {e}")

# ==========================================
# 6. 명단 확인 및 관리 도구
# ==========================================
if not df.empty:
    with st.expander("📋 제출 확인 명단"):
        st.dataframe(df[['학번', '이름', '제출시간']].iloc[::-1], use_container_width=True)

if is_admin:
    st.sidebar.divider()
    if st.sidebar.button(f"🔥 {selected_week} 초기화"):
        empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])
        conn.update(worksheet=selected_week, data=empty_df)
        st.sidebar.success("초기화 완료")
        st.rerun()
