import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# ==========================================
# 1. 보안 및 기본 설정 (메뉴/푸터 숨기기)
# ==========================================
st.set_page_config(page_title="2026 미술하기 생각하기", page_icon="🎨", layout="wide")

# CSS 주입: 우측 상단 메뉴, Deploy 버튼, 하단 푸터 숨기기
hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display: none;}
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# ==========================================
# 2. AI 및 데이터베이스 연결
# ==========================================
try:
    # Secrets에서 정보 로드
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    @st.cache_resource
    def get_active_model():
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # 2026년 기준 최신 Flash 모델 탐색
        for p in ['models/gemini-3-flash', 'models/gemini-1.5-flash-latest', 'models/gemini-1.5-flash']:
            if p in available: return p
        return available[0]
    
    active_model = get_active_model()
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"⚠️ 시스템 초기화 중 오류가 발생했습니다. (Secrets 확인 필요): {e}")
    st.stop()

# ==========================================
# 3. 사이드바: 주차 선택 및 관리자 기능
# ==========================================
with st.sidebar:
    st.title("📅 주차 관리")
    selected_week = st.selectbox(
        "제출할 주차를 선택하세요", 
        [f"Week{i:02d}" for i in range(1, 13)]
    )
    
    st.divider()
    # 관리자 기능 (비밀번호 입력 시에만 노출)
    admin_pw = st.text_input("시스템 관리자 인증", type="password", placeholder="Password Required")
    is_admin = (admin_pw == "1234") # 본인만의 비밀번호로 변경 권장

# ==========================================
# 4. 데이터 로드 및 현황판 (Dashboard)
# ==========================================
try:
    # 선택된 주차의 시트 읽기 (ttl=0으로 실시간 반영)
    df = conn.read(worksheet=selected_week, ttl=0)
except Exception:
    # 시트가 없거나 비어있는 경우 초기화
    df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])

st.title("📝 2026 미술하기 생각하기 에세이")
st.subheader(f"📊 {selected_week} 실시간 현황")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("총 제출 인원", f"{len(df)}명 / 125명")
with col2:
    pass_count = df['AI의견'].str.contains("Pass").sum() if not df.empty else 0
    st.metric("참신성 통과(Pass)", f"{pass_count}명")
with col3:
    avg_len = int(df['글자수'].astype(int).mean()) if not df.empty else 0
    st.metric("평균 글자수", f"{avg_len}자")

st.divider()

# ==========================================
# 5. 에세이 제출 폼 (Validation 포함)
# ==========================================
with st.form("essay_form", clear_on_submit=True):
    st.info(f"📍 현재 **[{selected_week}]** 과제 제출란입니다.")
    c1, c2 = st.columns(2)
    with c1: sid = st.text_input("학번 (숫자만 입력)")
    with c2: sname = st.text_input("이름")
    
    content = st.text_area(
        "에세이 내용 (최소 1500자 이상)", 
        height=500, 
        placeholder="미술적 실천과 사유에 대한 당신만의 참신한 견해를 자유롭게 서술해 주세요."
    )
    
    submitted = st.form_submit_button(f"{selected_week} 과제 제출하기")

# ==========================================
# 6. 제출 처리 로직
# ==========================================
if submitted:
    # 검증 1: 학번/이름 입력 여부
    if not sid or not sname:
        st.warning("학번과 이름을 모두 입력해 주세요.")
    # 검증 2: 글자수 제한 (1500자)
    elif len(content) < 1500:
        st.error(f"❌ 제출 실패: 글자수가 부족합니다. (현재 {len(content)}자 / 최소 1500자 필요)")
    # 검증 3: 해당 주차 중복 제출 확인
    elif sid in df['학번'].astype(str).values:
        st.error(f"❌ 제출 실패: {selected_week}에 이미 제출된 학번입니다.")
    else:
        with st.spinner("AI가 에세이의 독창성을 평가하고 저장하는 중입니다..."):
            try:
                # AI 참신성 평가 프롬프트
                model = genai.GenerativeModel(active_model)
                prompt = f"""
                당신은 '미술하기와 생각하기' 수업의 에세이 평가관입니다.
                다음 에세이가 상투적인 내용을 넘어 얼마나 '참신하고 새로운 시각'을 제시하는지 평가하세요.
                
                [평가 지침]
                1. 단순 지식 전달이 아닌 개인의 깊은 사유가 느껴지는가?
                2. 미술과 삶을 연결하는 방식이 독창적인가?
                
                [응답 규격]
                결과: Pass 또는 Fail
                이유: 참신성에 대한 평가를 1문장으로 요약.
                
                에세이 내용:
                {content}
                """
                response = model.generate_content(prompt)
                ai_comment = response.text

                # 구글 시트에 데이터 추가
                new_data = pd.DataFrame([{
                    "학번": str(sid),
                    "이름": str(sname),
                    "글자수": len(content),
                    "AI의견": str(ai_comment),
                    "제출시간": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
                }])

                # 데이터 병합 및 업데이트
                updated_df = pd.concat([df, new_data], ignore_index=True).astype(str)
                conn.update(worksheet=selected_week, data=updated_df)

                st.balloons()
                st.success(f"✅ {sname}님, 제출이 성공적으로 완료되었습니다!")
                st.info(f"🤖 AI 평가 코멘트:\n{ai_comment}")
                st.rerun()

            except Exception as e:
                st.error(f"❌ 시스템 오류로 제출되지 않았습니다: {e}")

# ==========================================
# 7. 하단 현황 및 관리자 도구
# ==========================================
if not df.empty:
    with st.expander("📋 제출 확인 명단"):
        st.dataframe(df[['학번', '이름', '제출시간']].iloc[::-1], use_container_width=True)

# 관리자 전용 초기화 버튼
if is_admin:
    st.sidebar.divider()
    if st.sidebar.button(f"🔥 {selected_week} 전체 데이터 삭제"):
        empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])
        conn.update(worksheet=selected_week, data=empty_df)
        st.sidebar.success("데이터가 초기화되었습니다.")
        st.rerun()
