import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 강력 보안 설정 (외부 링크 완전 차단)
# ==========================================
st.set_page_config(page_title="2026 미술하기 생각하기", page_icon="🎨", layout="wide")

# [핵심] 화살표가 없어도 되게끔 헤더와 툴바를 아예 무시하고 본문 위주로 구성
st.markdown("""
    <style>
    /* 1. 우측 메뉴, 깃허브 아이콘, 배포 버튼, 푸터 완전히 제거 */
    #MainMenu {visibility: hidden;}
    .stAppDeployButton {display: none;}
    [data-testid="stToolbar"] {display: none;}
    footer {visibility: hidden;}
    header {visibility: hidden;} /* 헤더를 아예 날려서 화살표에 의존하지 않음 */
    
    /* 2. 본문 상단 여백 조절 */
    .main .block-container {padding-top: 2rem;}
    
    /* 3. 버튼 디자인 강화 */
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #4CAF50;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 시간 및 모델 설정
# ==========================================
now = datetime.now()
is_open = 2 <= now.weekday() <= 6 # 수~일 오픈

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
# 3. 본문 상단 주차 선택 (화살표 대신!)
# ==========================================
st.title("🎨 2026 미술하기 생각하기 에세이")

# 학생들이 바로 주차를 바꿀 수 있게 본문에 배치
selected_week = st.selectbox(
    "📅 제출하시려는 주차를 선택해 주세요", 
    [f"Week{i:02d}" for i in range(1, 13)],
    help="해당 주차를 선택하면 실시간 현황이 업데이트됩니다."
)

# ==========================================
# 4. 실시간 현황판 (Dashboard)
# ==========================================
try:
    df = conn.read(worksheet=selected_week, ttl=0)
except:
    df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])

st.markdown("---")
c1, c2, c3 = st.columns(3)
with c1: st.metric("현재 제출 인원", f"{len(df)}명 / 125명")
with c2: 
    pass_cnt = df['AI의견'].str.contains("Pass").sum() if not df.empty else 0
    st.metric("참신성 통과(Pass)", f"{pass_cnt}명")
with c3:
    avg_len = int(df['글자수'].astype(int).mean()) if not df.empty else 0
    st.metric("평균 글자수", f"{avg_len}자")

# ==========================================
# 5. 에세이 제출 폼
# ==========================================
st.divider()

if not is_open:
    st.warning("⚠️ 지금은 제출 기간이 아닙니다. (매주 수요일 00:00 ~ 일요일 23:59 제출 가능)")
    st.info(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")
else:
    with st.form("essay_form", clear_on_submit=True):
        st.success(f"📍 현재 **[{selected_week}]** 에세이를 작성 중입니다.")
        cid, cname = st.columns(2)
        with cid: sid = st.text_input("학번 (숫자만)")
        with cname: sname = st.text_input("이름")
        content = st.text_area("에세이 내용 (1500자 이상)", height=500)
        submitted = st.form_submit_button(f"🚀 {selected_week} 에세이 제출 및 AI 분석 시작")

        if submitted:
            if not sid or not sname:
                st.warning("학번과 이름을 입력해 주세요.")
            elif len(content) < 1500:
                st.error(f"❌ 제출 실패: 현재 {len(content)}자입니다. (최소 1500자 필요)")
            elif sid in df['학번'].astype(str).values:
                st.error(f"❌ 이미 제출된 학번입니다.")
            else:
              
with st.spinner("AI가 참신성과 진정성을 정밀 분석 중입니다..."):
                try:
                    model = genai.GenerativeModel(active_model)
                    # [핵심] AI 판별 로직을 포함한 프롬프트 강화
                    prompt = f"""
                    당신은 대학 에세이의 '진정성'과 'AI 작성 여부'를 판별하는 전문가입니다.
                    다음 에세이를 분석하여 아래 3가지 항목을 반드시 포함해 응답하세요.

                    1. 결과: Pass 또는 Fail (참신성과 논리성 기준)
                    2. AI 의심도: 0~100% (문장의 상투성, 기계적인 구조, 구체적 사례 부재 등을 기준으로 판단)
                    3. 한줄평: 참신성에 대한 평가와 AI 의심 근거를 포함한 짧은 요약.

                    에세이 내용:
                    {content}
                    """
                    response = model.generate_content(prompt)
                    ai_comment = response.text

                    # (시트 저장 로직 - 기존과 동일)
                    # ...
                    
                    st.balloons()
                    st.success("✅ 제출 성공!")
                    
                    # 화면에 AI 의심도와 평가 결과를 눈에 띄게 표시
                    st.warning(f"🔍 **AI 분석 결과 보고서**\n\n{ai_comment}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 오류 발생: {e}")
# ==========================================
# 6. 관리자 기능 (화면 하단으로 이동)
# ==========================================
st.divider()
with st.expander("🛠️ 시스템 관리자 전용"):
    admin_pw = st.text_input("관리자 인증", type="password")
    if admin_pw == "1234":
        if st.button(f"🔥 {selected_week} 데이터 전체 초기화"):
            empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])
            conn.update(worksheet=selected_week, data=empty_df)
            st.success("초기화 완료")
            st.rerun()

if not df.empty:
    with st.expander("📋 제출 확인 명단"):
        st.dataframe(df[['학번', '이름', '제출시간']].iloc[::-1], use_container_width=True)

