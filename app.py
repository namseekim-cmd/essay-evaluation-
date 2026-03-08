import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# 1. 초기 설정
st.set_page_config(page_title="2026 미술하기 생각하기", page_icon="🎨", layout="wide")

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

# 2. 주차 선택 (1주 ~ 12주)
st.title("🎨 2026 미술하기 생각하기 에세이")
selected_week = st.sidebar.selectbox(
    "📅 제출 주차를 선택하세요", 
    [f"Week{i:02d}" for i in range(1, 13)],
    index=0
)

# 3. 해당 주차 데이터 불러오기 (기능 2: 중복 체크용)
try:
    # 선택된 주차의 시트(예: Week01)를 읽어옵니다.
    df = conn.read(worksheet=selected_week, ttl=0)
except Exception:
    # 시트가 없거나 비어있을 경우 빈 표 생성
    df = pd.DataFrame(columns=["학번", "이름", "글자수", "AI의견", "제출시간"])

# 4. 실시간 현황판 (기능 3)
st.subheader(f"📊 {selected_week} 제출 현황")
col_a, col_b, col_c = st.columns(3)
col_a.metric("현재 제출 인원", f"{len(df)}명")
if not df.empty:
    pass_count = df['AI의견'].str.contains("Pass").sum()
    col_b.metric("참신성 통과(Pass)", f"{pass_count}명")
    col_c.metric("평균 글자수", f"{int(df['글자수'].astype(int).mean())}자")

st.divider()

# 5. 에세이 제출 폼
with st.form("essay_form", clear_on_submit=True):
    st.info(f"📍 현재 **[{selected_week}]** 과제를 작성 중입니다.")
    c1, c2 = st.columns(2)
    with c1: sid = st.text_input("학번 (숫자만)")
    with c2: sname = st.text_input("이름")
    content = st.text_area("에세이 내용 (1500자 이상)", height=450, placeholder="미술과 생각에 대한 당신의 독창적인 견해를 1500자 이상 작성해 주세요.")
    submitted = st.form_submit_button(f"{selected_week} 에세이 제출 및 AI 분석")

# 6. 제출 검증 및 저장 (기능 1, 2, 4)
if submitted:
    # 기능 1: 글자수 제한 (1500자)
    if len(content) < 1500:
        st.error(f"❌ 글자수가 부족합니다. (현재 {len(content)}자 / 최소 1500자 필요)")
    
    # 기능 2: 해당 주차 내 중복 제출 차단
    elif sid in df['학번'].astype(str).values:
        st.error(f"❌ {selected_week}에 이미 제출된 학번입니다.")
        
    elif not sid or not sname:
        st.warning("학번과 이름을 입력해 주세요.")
        
    else:
        with st.spinner(f"AI가 {selected_week} 에세이의 참신성을 분석 중입니다..."):
            try:
                # 기능 4: 참신성 평가 프롬프트
                model = genai.GenerativeModel(active_model)
                prompt = f"""
                당신은 '미술하기와 생각하기' 수업의 전문 평가관입니다.
                다음 에세이가 기존의 관념을 벗어나 얼마나 '참신하고 새로운 시각'을 제시하는지 평가하세요.
                
                [평가 기준]
                1. 상투적인 표현보다는 개인의 깊은 사유가 담겼는가?
                2. 미술적 실천과 사고의 연결이 독창적인가?
                
                [응답 형식]
                결과: Pass 또는 Fail
                이유: 참신함에 대한 평가를 1문장으로 요약.
                
                에세이 내용:
                {content}
                """
                response = model.generate_content(prompt)
                ai_comment = response.text

                # 해당 주차 시트에 저장
                new_row = pd.DataFrame([{
                    "학번": str(sid), "이름": str(sname), 
                    "글자수": len(content), "AI의견": str(ai_comment),
                    "제출시간": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
                }])
                
                updated_df = pd.concat([df, new_row], ignore_index=True).astype(str)
                conn.update(worksheet=selected_week, data=updated_df)
                
                st.balloons()
                st.success(f"✅ {selected_week} 제출 완료!")
                st.info(f"🤖 AI 분석 결과:\n{ai_comment}")
                st.rerun()

            except Exception as e:
                st.error(f"❌ 오류 발생: {e}")

# 7. 명단 확인
if not df.empty:
    with st.expander(f"📋 {selected_week} 제출자 명단 (최근순)"):
        st.dataframe(df[['학번', '이름', '글자수', '제출시간']].iloc[::-1], use_container_width=True)
