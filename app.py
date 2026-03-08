import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 강력 보안 및 화살표 강제 노출 설정
# ==========================================
st.set_page_config(
    page_title="2026 미술하기 생각하기", 
    page_icon="🎨", 
    layout="wide",
    initial_sidebar_state="expanded" # 접속하자마자 메뉴가 열려 있게 함
)

# [최종 수정] 화살표 버튼은 절대 건드리지 않고, 우측 요소만 투명하게 가리는 CSS
st.markdown("""
    <style>
    /* 1. 우측 상단 메뉴, 깃허브, 배포 버튼만 정밀 타격해서 숨김 */
    #MainMenu {visibility: hidden;}
    .stAppDeployButton {display: none;}
    [data-testid="stToolbar"] {visibility: hidden;}
    footer {visibility: hidden;}

    /* 2. 왼쪽 상단 화살표(사이드바 버튼)를 강제로 화면 맨 위로 표시 */
    [data-testid="stSidebarCollapseButton"] {
        visibility: visible !important;
        display: block !important;
        position: fixed;
        top: 10px;
        left: 10px;
        z-index: 99999;
        background-color: #f0f2f6; /* 버튼이 잘 보이도록 배경색 추가 */
        border-radius: 5px;
    }
    
    /* 3. 헤더 전체를 숨기지 않아 화살표가 죽지 않게 함 */
    header {visibility: visible !important; background: rgba(255,255,255,0);}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 시간 및 주차 관리 로직
# ==========================================
now = datetime.now()
weekday = now.weekday()  # 월(0) ~ 일(6)
is_open = 2 <= weekday <= 6 # 수~일 오픈

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    @st.cache_resource
    def get_active_model():
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for p in ['models/gemini-3-flash', 'models/gemini-1.5-flash-latest']:
            if p in available: return p
        return available[0]
    
    active_model = get_active_model()
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"⚠️ 시스템 초기화 오류: {e}")
    st.stop()

# ==========================================
# 3. 사이드바 (주차 선택 및 관리자)
# ==========================================
with st.sidebar:
    st.title("📅 주차 선택")
    selected_week = st.selectbox(
        "제출할 주차를 선택하세요", 
        [f"Week{i:02d}" for i in range(1, 13)]
    )
    st.divider()
    admin_pw = st.text_input("관리자 인증", type="password", placeholder="Password")
    is_admin = (admin_pw == "1234")

# ==========================================
# 4. 현황판 및 데이터 로드
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
# 5. 제출 폼 및 기간 제어
# ==========================================
if not is_open:
    st.warning("⚠️ 지금은 제출 기간이 아닙니다. (매주 수요일 ~ 일요일 제출 가능)")
    st.info(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")
else:
    st.success(f"✅ {selected_week} 과제 제출 가능 (마감: 이번 주 일요일 23:59)")
    
    with st.form("essay_form", clear_on_submit=True):
        st.info(f"📍 [{selected_week}] 에세이를 작성 중입니다.")
        cid, cname = st.columns(2)
        with cid: sid = st.text_input("학번 (숫자만)")
        with cname: sname = st.text_input("이름")
        content = st.text_area("에세이 내용 (1500자 이상)", height=500)
        submitted = st.form_submit_button(f"{selected_week} 과제 제출하기")

        if submitted:
            if not sid or not sname:
                st.warning("학번과 이름을 입력해 주세요.")
            elif len(content) < 1500:
                st.error(f"❌ 제출 실패: 글자수 부족 (현재 {len(content)}자 / 최소 1500자 필요)")
            elif sid in df['학번'].astype(str).values:
                st.error(f"❌ 이미 제출된 학번입니다.")
            else:
                with st.spinner("AI가 참신성을 분석하고 저장하는 중..."):
                    try:
                        model = genai.GenerativeModel(active_model)
                        prompt = f"미술 에세이 참신성 평가(Pass/Fail 및 1문장 요약):\n\n{content}"
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
                        st.error(f"❌ 오류: {e}")

# ==========================================
# 6. 명단 확인 및 관리 도구
# ==========================================
if not df.empty:
    with st.expander("📋 제출 확인 명단"):
        st.dataframe(df[['학번', '이름', '제출시간']].iloc[::-1], use_container_width=True)

if is_admin:
    st.sidebar.divider()
    if st.sidebar.button(f"🔥 {selected_week} 데이터 전체 삭제"):
        empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])
        conn.update(worksheet=selected_week, data=empty_df)
        st.sidebar.success("초기화 완료")
        st.rerun()
