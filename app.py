import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 시스템 보안 설정 (외부 링크 완전 차단)
# ==========================================
st.set_page_config(page_title="2026 미술하기 생각하기", page_icon="🎨", layout="wide")

st.markdown("""
    <style>
    /* 1. 불필요한 모든 메뉴와 툴바 제거 */
    #MainMenu {visibility: hidden;}
    .stAppDeployButton {display: none;}
    [data-testid="stToolbar"] {display: none;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 2. 본문 디자인 최적화 */
    .main .block-container {padding-top: 1.5rem;}
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        background-color: #2E7D32;
        color: white;
        font-weight: bold;
    }
    /* 3. 메트릭 가독성 강화 */
    [data-testid="stMetricValue"] { font-size: 1.8rem; color: #1565C0; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 시간 설정 및 제출 기한 체크
# ==========================================
now = datetime.now()
weekday = now.weekday()  # 월(0) ~ 일(6)
# 수요일(2) 00:00부터 일요일(6) 23:59까지 열림
is_open = 2 <= weekday <= 6

# ==========================================
# 3. AI 모델 및 데이터베이스 연결
# ==========================================
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    @st.cache_resource
    def get_latest_model():
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for p in ['models/gemini-3-flash', 'models/gemini-1.5-flash-latest']:
            if p in available: return p
        return available[0]
    
    active_model = get_latest_model()
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"⚠️ 시스템 오류: Secrets 설정을 확인하세요. ({e})")
    st.stop()

# ==========================================
# 4. 본문 상단: 주차 선택 및 현황판
# ==========================================
st.title("🎨 2026 미술하기 생각하기 에세이")

selected_week = st.selectbox(
    "📅 현재 제출하시려는 주차를 선택해 주세요", 
    [f"Week{i:02d}" for i in range(1, 13)]
)

try:
    df = conn.read(worksheet=selected_week, ttl=0)
except:
    # 시트가 없으면 생성될 수 있도록 초기 틀 마련
    df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의심도", "AI의견", "제출시간"])

st.divider()

# 실시간 현황 요약
c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("총 제출", f"{len(df)}명")
with c2: 
    pass_cnt = df['AI의견'].str.contains("Pass").sum() if not df.empty else 0
    st.metric("Pass 건수", f"{pass_cnt}건")
with c3:
    avg_len = int(df['글자수'].astype(int).mean()) if not df.empty else 0
    st.metric("평균 글자수", f"{avg_len}자")
with c4:
    # AI 의심도 평균값 계산
    try:
        avg_ai = f"{df['AI의심도'].str.replace('%','').astype(float).mean():.1f}%" if not df.empty else "0%"
    except: avg_ai = "N/A"
    st.metric("평균 AI 의심도", avg_ai)

# ==========================================
# 5. 에세이 제출 폼 (AI 탐지 로직 포함)
# ==========================================
st.divider()

if not is_open:
    st.warning("⚠️ 지금은 제출 기간이 아닙니다. (제출 가능: 매주 수요일 00:00 ~ 일요일 23:59)")
    st.info(f"현재 서버 시간: {now.strftime('%Y-%m-%d %H:%M')}")
else:
    with st.form("essay_form", clear_on_submit=True):
        st.success(f"📍 현재 **[{selected_week}]** 에세이 진정성 분석 시스템이 작동 중입니다.")
        cid, cname = st.columns(2)
        with cid: sid = st.text_input("학번 (숫자만)")
        with cname: sname = st.text_input("이름")
        
        content = st.text_area(
            "에세이 내용 (최소 1500자 이상)", 
            height=500,
            placeholder="AI의 일반적인 문체가 아닌, 당신만의 경험과 고유한 사유를 1500자 이상 적어주세요."
        )
        
        submitted = st.form_submit_button(f"🚀 {selected_week} 에세이 제출 및 AI 정밀 분석")

        if submitted:
            if not sid or not sname:
                st.warning("학번과 이름을 입력해 주세요.")
            elif len(content) < 1500:
                st.error(f"❌ 제출 실패: 현재 {len(content)}자입니다. (최소 1500자 이상 작성 필수)")
            elif sid in df['학번'].astype(str).values:
                st.error(f"❌ 이미 해당 주차에 제출된 학번입니다.")
            else:
                with st.spinner("AI가 글의 참신성과 AI 작성 가능성을 정밀하게 대조 분석 중입니다..."):
                    try:
                        model = genai.GenerativeModel(active_model)
                        # [핵심] AI 탐지 및 참신성 평가 프롬프트
                        prompt = f"""
                        당신은 '미술하기와 생각하기' 수업의 평가관입니다. 다음 에세이를 읽고 분석하세요.
                        
                        [평가 항목]
                        1. 결과: Pass 또는 Fail (참신함과 논리적 전개가 우수하면 Pass)
                        2. AI 의심도: 0%~100% (기계적인 문체, 상투적 구조, 구체적인 개인 경험 부재 시 수치가 높음)
                        3. 종합 의견: 참신한 관점과 AI 작성 의심 근거를 포함한 1문장 요약.

                        반드시 아래 형식을 엄수하세요:
                        결과: [내용]
                        AI 의심도: [숫자]%
                        종합 의견: [내용]

                        에세이 내용:
                        {content}
                        """
                        response = model.generate_content(prompt)
                        result_text = response.text
                        
                        # 결과에서 AI 의심도만 추출 (시트 저장용)
                        ai_risk = "0%"
                        for line in result_text.split('\n'):
                            if "AI 의심도:" in line:
                                ai_risk = line.split(':')[-1].strip()

                        # 데이터 저장
                       new_data = pd.DataFrame([{
    "학번": str(sid),
    "이름": str(sname),
    "글자수": len(content),
    "내용": content,  # 원문 저장을 위해 이 줄이 꼭 필요합니다
    "AI의견": str(ai_comment),
    "제출시간": datetime.now().strftime('%Y-%m-%d %H:%M')
}])

# 데이터 저장 시 모든 컬럼이 문자열로 인식되도록 설정
updated_df = pd.concat([df, new_data], ignore_index=True).astype(str)
conn.update(worksheet=selected_week, data=updated_df)

                        
                        st.balloons()
                        st.success("✅ 제출 성공! 당신의 사유가 안전하게 기록되었습니다.")
                        st.warning(f"🔍 **분석 리포트**\n\n{result_text}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 분석 중 오류 발생: {e}")

# ==========================================
# 6. 하단 데이터 확인 및 관리 도구
# ==========================================
st.divider()

# 관리자 모드
with st.expander("🛠️ 시스템 관리자 메뉴"):
    pw = st.text_input("Admin Password", type="password")
    if pw == "1234":
        if st.button(f"🔥 {selected_week} 데이터 초기화 (주의)"):
            empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의심도", "AI의견", "제출시간"])
            conn.update(worksheet=selected_week, data=empty_df)
            st.success("초기화되었습니다.")
            st.rerun()

# 제출 명단 확인
if not df.empty:
    with st.expander("📋 최근 제출자 명단 (AI 의심도 포함)"):
        # 의심도가 높은 순서대로 정렬해서 볼 수 있게 기능 제공
        show_df = df[['학번', '이름', 'AI의심도', '제출시간']].iloc[::-1]
        st.dataframe(show_df, use_container_width=True)

