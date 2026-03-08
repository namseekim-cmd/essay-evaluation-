import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# 1. 초기 설정
st.set_page_config(page_title="2026 에세이 마스터 시스템", page_icon="📝", layout="wide")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    @st.cache_resource
    def get_model():
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for p in ['models/gemini-1.5-flash-latest', 'models/gemini-1.5-flash']:
            if p in available: return p
        return available[0]
    
    active_model = get_model()
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"설정 에러: {e}")
    st.stop()

# 2. 데이터 불러오기 (중복 체크 및 현황판용)
try:
    df = conn.read(ttl=0) # 실시간 데이터를 위해 캐시 0
except:
    df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])

# 3. 메인 화면 및 현황판 (기능 3)
st.title("🎓 2026 에세이 통합 제출 및 관리 시스템")

col_a, col_b, col_c = st.columns(3)
col_a.metric("총 제출 인원", f"{len(df)}명 / 125명")
if not df.empty:
    pass_count = df['AI의견'].str.contains("Pass").sum()
    col_b.metric("통과(Pass) 인원", f"{pass_count}명")
    col_c.metric("미제출 인원", f"{125 - len(df)}명")

st.divider()

# 4. 제출 폼
with st.form("essay_form", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1: sid = st.text_input("학번 (숫자만)")
    with c2: sname = st.text_input("이름")
    content = st.text_area("에세이 내용 (1500자 이상)", height=450)
    submitted = st.form_submit_button("제출 및 AI 참신성 평가 시작")

# 5. 제출 로직
if submitted:
    # 기능 1: 글자수 제한 (1500자)
    if len(content) < 1500:
        st.error(f"❌ 글자수가 부족합니다. (현재 {len(content)}자 / 최소 1500자 필요)")
    
    # 기능 2: 중복 제출 차단
    elif sid in df['학번'].astype(str).values:
        st.error(f"❌ 이미 제출된 학번입니다. (학번: {sid})")
        
    elif not sid or not sname:
        st.warning("학번과 이름을 입력해 주세요.")
        
    else:
        with st.spinner("AI가 에세이의 참신성을 정밀 분석 중입니다..."):
            try:
                # 기능 4: 참신하고 새로운 내용 평가 전용 프롬프트
                model = genai.GenerativeModel(active_model)
                prompt = f"""
                다음 에세이의 '참신함'과 '기존에 없던 새로운 시각'을 중점적으로 평가해줘.
                형식은 반드시 아래를 지켜줘.
                결과: Pass 또는 Fail
                이유: 왜 참신한지(혹은 상투적인지) 1문장으로 요약.
                
                에세이 내용:
                {content}
                """
                response = model.generate_content(prompt)
                ai_comment = response.text

                # 데이터 저장
                new_row = pd.DataFrame([{
                    "학번": str(sid), "이름": str(sname), 
                    "글자수": len(content), "AI의견": str(ai_comment),
                    "제출시간": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
                }])
                
                updated_df = pd.concat([df, new_row], ignore_index=True).astype(str)
                conn.update(data=updated_df)
                
                st.balloons()
                st.success("✅ 제출이 완료되었습니다!")
                st.info(f"🤖 AI 평가 결과:\n{ai_comment}")
                st.rerun() # 현황판 즉시 갱신

            except Exception as e:
                st.error(f"오류 발생: {e}")

# 6. 하단 실시간 명단 (선택 사항)
if not df.empty:
    with st.expander("📊 실시간 제출자 명단 확인 (최근순)"):
        st.table(df[['학번', '이름', '제출시간']].iloc[::-1])
