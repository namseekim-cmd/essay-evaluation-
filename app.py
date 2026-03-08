import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# 1. 고정 설정 (주소 중복 방지 완료)
SHEET_URL = "https://docs.google.com/spreadsheets/d/19j2Ikt7WIaDe4WOHciK1uBJY0z1n1tyE2Q7BpfPnAPA"

st.set_page_config(page_title="2026 에세이 평가 시스템", page_icon="📝")

# 2. 시스템 초기화 및 모델 자동 탐색
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    @st.cache_resource
    def get_latest_model():
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # 2026년 가동 모델 순위
        for p in ['models/gemini-3-flash', 'models/gemini-2.0-flash', 'models/gemini-1.5-flash-latest']:
            if p in models: return p
        return models[0] if models else None

    active_model = get_latest_model()
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"시스템 초기화 실패 (Secrets 확인 필요): {e}")
    st.stop()

# 3. 메인 화면 UI
st.title("🎓 2026 에세이 통합 제출처")
st.caption(f"연결된 AI: {active_model.split('/')[-1]} | 저장소: Sheet1")

with st.form("essay_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1: sid = st.text_input("학번 (숫자만)")
    with col2: sname = st.text_input("이름")
    content = st.text_area("에세이 내용 (300자 이상)", height=400)
    submitted = st.form_submit_button("제출 및 AI 평가")

# 4. 제출 로직 (NameError 및 400 에러 방지)
if submitted:
    if not sid or not sname or len(content) < 300:
        st.warning("모든 정보를 입력해 주세요 (에세이 300자 이상).")
    else:
        with st.spinner("AI 분석 및 시트 저장 중..."):
            try:
                # [변수 초기화] NameError 방지
                ai_comment = "분석 중 오류 발생"
                
                # AI 평가 실행
                model = genai.GenerativeModel(active_model)
                response = model.generate_content(f"에세이 평가(결과:Pass/Fail, 이유:1문장): {content}")
                ai_comment = response.text

                # 시트 데이터 읽기 (404 방지: worksheet 명시)
                try:
                    df = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                except:
                    # 시트가 비어있을 경우 헤더 생성
                    df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])
                
                # 새 데이터 추가 (ASCII/400 방지: 모든 데이터 강제 문자열 변환)
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
                st.info(f"🤖 AI 의견: {ai_comment}")

            except Exception as e:
                st.error(f"❌ 제출 실패: {e}")
                st.write("도움말: 구글 시트 탭 이름이 'Sheet1'인지, 공유 설정이 '편집자'인지 확인하세요.")




