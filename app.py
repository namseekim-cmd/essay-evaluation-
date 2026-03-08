import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd

st.set_page_config(page_title="2026 에세이 진단 시스템", page_icon="🔍")

# --- [1단계: 진단 구간] 실행되자마자 문제를 찾아냅니다 ---
st.title("🔍 시스템 진단 모드")

if not st.secrets:
    st.error("❌ [진단 결과] Secrets 설정(또는 secrets.toml 파일)을 아예 찾을 수 없습니다.")
    st.info("해결법: .streamlit 폴더 안에 secrets.toml 파일이 있는지, 혹은 Streamlit Cloud 설정에 내용을 넣었는지 확인하세요.")
    st.stop()
elif "GEMINI_API_KEY" not in st.secrets:
    st.error("❌ [진단 결과] 장부(Secrets)는 찾았는데, 'GEMINI_API_KEY'라는 이름의 열쇠가 없습니다.")
    st.info("해결법: 파일 안의 글자가 GEMINI_API_KEY = \"...\" 형식인지 확인하세요. (대문자 필수)")
    st.stop()
else:
    st.success("✅ [진단 완료] API 열쇠를 정상적으로 찾았습니다. 과제 제출 창을 띄웁니다.")

# --- [2단계: 정상 작동 구간] 진단이 통과되면 아래가 실행됩니다 ---
api_key = st.secrets["GEMINI_API_KEY"]

@st.cache_resource
def get_working_model(key):
    try:
        genai.configure(api_key=key)
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # 2026년 최신 모델 우선 순위
        for p in ['models/gemini-3-flash', 'models/gemini-2.5-flash', 'models/gemini-1.5-flash']:
            if p in available: return p
        return available[0]
    except: return None

active_model = get_working_model(api_key)

st.divider()
st.subheader("🎓 에세이 과제 제출처")

with st.form("essay_form"):
    sid = st.text_input("학번")
    sname = st.text_input("이름")
    content = st.text_area("에세이 내용 (300자 이상)", height=300)
    btn = st.form_submit_button("평가 및 제출")

if btn:
    if len(content) < 300:
        st.error(f"❌ 분량 미달 (현재 {len(content)}자)")
    else:
        with st.spinner("AI 분석 중..."):
            try:
                model = genai.GenerativeModel(active_model)
                response = model.generate_content(f"에세이 독창성 평가. 결과: Pass/Fail, 이유: 1문장.\n\n{content}")
                ai_eval = response.text
                res = "합격" if "Pass" in ai_eval else "재검토"
                
                # 구글 시트 저장
                conn = st.connection("gsheets", type=GSheetsConnection)
                new_row = pd.DataFrame([{"학번": sid, "이름": sname, "글자수": len(content), "AI의견": ai_eval, "결과": res}])
                df = conn.read()
                conn.update(data=pd.concat([df, new_row], ignore_index=True))
                
                st.balloons()
                st.success(f"✅ {sname}님, 제출 완료! (AI 판정: {res})")
            except Exception as e:
                st.error(f"제출 오류: {e}")
