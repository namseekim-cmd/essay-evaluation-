import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# [설정] 주소 중복 방지 완료
SHEET_URL = "https://docs.google.com/spreadsheets/d/19j2Ikt7WIaDe4WOHciK1uBJY0z1n1tyE2Q7BpfPnAPA"

st.set_page_config(page_title="2026 에세이 평가 시스템", page_icon="📝")

# 1. AI 및 데이터베이스 설정
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    # [수정] 현재 사용 가능한 모델을 실시간으로 확인하여 선택
    @st.cache_resource
    def get_working_model():
        # 내 API 키로 쓸 수 있는 모델 목록 가져오기
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # 2026년 기준 우선순위 (최신 순)
        priorities = [
            'models/gemini-3-flash',          # 최신 모델
            'models/gemini-1.5-flash-latest', # 가장 안정적인 최신 포인터
            'models/gemini-1.5-flash',        # 표준 모델
        ]
        
        for p in priorities:
            if p in available_models:
                return p
        return available_models[0] if available_models else None

    active_model = get_working_model()
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"⚠️ 시스템 초기화 실패: {e}")
    st.stop()

# 2. 메인 화면 UI
st.title("🎓 2026 에세이 통합 제출처")
if active_model:
    st.caption(f"🤖 현재 가동 중인 AI: {active_model.split('/')[-1]}")
else:
    st.error("사용 가능한 AI 모델이 없습니다. Google AI Studio에서 API 키 상태를 확인하세요.")

with st.form("essay_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1: sid = st.text_input("학번 (숫자만)")
    with col2: sname = st.text_input("이름")
    content = st.text_area("에세이 내용 (300자 이상)", height=400)
    submitted = st.form_submit_button("제출 및 AI 평가")

# 3. 제출 로직
if submitted:
    if not sid or not sname or len(content) < 300:
        st.warning("정보를 모두 입력해 주세요 (300자 이상).")
    elif not active_model:
        st.error("AI 모델 연결이 필요합니다.")
    else:
        with st.spinner("AI 분석 및 데이터 저장 중..."):
            try:
                # AI 평가 실행
                model = genai.GenerativeModel(active_model)
                response = model.generate_content(f"에세이 평가(결과:Pass/Fail, 이유:1문장): {content}")
                ai_comment = response.text

                # 구글 시트 데이터 읽기
                try:
                    df = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                except:
                    df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])
                
                # 새 데이터 생성
                new_row = pd.DataFrame([{
                    "학번": str(sid),
                    "이름": str(sname),
                    "글자수": len(content),
                    "AI의견": str(ai_comment),
                    "제출시간": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
                }])

                # 데이터 병합 및 업데이트
                updated_df = pd.concat([df, new_row], ignore_index=True).astype(str)
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated_df)
                
                st.balloons()
                st.success(f"✅ {sname}님, 제출 완료!")
                st.info(f"🔍 AI 분석: {ai_comment}")

            except Exception as e:
                st.error(f"❌ 제출 실패: {e}")
