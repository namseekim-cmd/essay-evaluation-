import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# 1. 온라인 저장소(구글 시트) 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. AI 설정 (Streamlit Cloud 설정창에 입력할 키 사용)
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-3-flash')
else:
    st.error("설정에서 API 키를 등록해주세요!")

st.title("🎓 2026 에세이 제출 및 1차 평가")
st.write("300자 이상의 에세이를 작성하여 제출하세요. 제출 즉시 AI가 1차 통과 여부를 알려줍니다.")

# 3. 학생용 제출 양식
with st.form("essay_form"):
    st.subheader("과제 제출란")
    student_id = st.text_input("학번 (예: 20260001)")
    name = st.text_input("이름")
    essay_content = st.text_area("에세이 내용", height=400)
    
    submitted = st.form_submit_button("제출하기")

if submitted:
    if not student_id or not name or not essay_content:
        st.warning("모든 정보를 입력해주세요.")
    elif len(essay_content) < 300:
        st.error(f"❌ 분량 미달 (현재 {len(essay_content)}자 / 300자 이상 필요)")
    else:
        with st.spinner("AI가 과제를 검토하고 기록하는 중입니다..."):
            # AI 평가
            prompt = f"에세이 독창성 평가. 결과: Pass/Fail, 이유: 1문장.\n\n{essay_content}"
            response = model.generate_content(prompt)
            ai_comment = response.text
            status = "합격" if "Pass" in ai_comment else "재검토"
            
            # 구글 시트에 실시간 기록
            new_data = pd.DataFrame([{
                "학번": student_id,
                "이름": name,
                "글자수": len(essay_content),
                "AI평가": ai_comment,
                "상태": status
            }])
            
            # 시트 업데이트 (Sheet1에 누적)
            existing_data = conn.read(worksheet="Sheet1")
            updated_df = pd.concat([existing_data, new_data], ignore_index=True)
            conn.update(worksheet="Sheet1", data=updated_df)
            
            st.success(f"✅ 제출 성공! {name} 학생은 [1차 {status}]입니다.")
            st.info(f"AI 코멘트: {ai_comment}")