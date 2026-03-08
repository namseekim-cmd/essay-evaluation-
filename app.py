import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# 1. 시트 주소 설정 (본인의 주소로 교체)
SHEET_ID = "https://docs.google.com/spreadsheets/19j2Ikt7WIaDe4WOHciK1uBJY0z1n1tyE2Q7BpfPnAPA"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0"

st.set_page_config(page_title="2026 에세이 통합 시스템", page_icon="🎓")

# 2. 시스템 진단 및 설정
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    # [진단] 사용 가능한 최신 모델 찾기
    @st.cache_resource
    def get_working_model():
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # 2026년 기준 가동 모델 순위
        for m in ['models/gemini-3-flash', 'models/gemini-1.5-flash-latest']:
            if m in models: return m
        return models[0] if models else None

    active_model = get_working_model()
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"시스템 초기화 실패: {e}")
    st.stop()

# 3. 사용자 화면 구성
st.title("📝 2026 에세이 제출처")
st.caption(f"AI 모델 {active_model} 연결됨 | 데이터 저장소: Sheet1")

with st.form("essay_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1: sid = st.text_input("학번")
    with col2: sname = st.text_input("이름")
    content = st.text_area("에세이 내용 (300자 이상)", height=350)
    submitted = st.form_submit_button("제출 및 AI 평가 받기")

# 4. 제출 로직
if submitted:
    if not sid or not sname or len(content) < 300:
        st.warning("정보를 모두 입력해 주세요 (에세이는 300자 이상).")
    else:
        with st.spinner("AI 분석 및 데이터 전송 중..."):
            try:
                # AI 평가 실행
                model = genai.GenerativeModel(active_model)
                response = model.generate_content(f"에세이 독창성 평가. 결과:Pass/Fail, 이유:1문장.\n\n{content}")
                ai_result = response.text

                # 구글 시트 읽기 (한글 에러 방지를 위해 worksheet 명시)
                # 만약 여기서 에러가 나면 시트 탭 이름이 'Sheet1'이 아닌 것입니다.
                df = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1")
                
                # 새 데이터 생성 (모든 텍스트를 문자열로 강제 변환하여 ASCII 에러 방지)
                new_entry = pd.DataFrame([{
                    "학번": str(sid),
                    "이름": str(sname),
                    "글자수": len(content),
                    "AI평가": str(ai_result),
                    "제출일시": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
                }])

                # 데이터 병합 및 업데이트
                updated_df = pd.concat([df, new_entry], ignore_index=True).astype(str)
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated_df)

                st.balloons()
                st.success(f"✅ {sname}님, 제출이 완료되었습니다!")
                st.info(f"🤖 AI 코멘트: {ai_result}")

            except Exception as e:
                if "ascii" in str(e):
                    st.error("❌ 한글 처리 오류: 구글 시트 하단 탭 이름을 'Sheet1'으로 변경했는지 확인하세요.")
                else:
                    st.error(f"❌ 제출 중 오류 발생: {e}")



