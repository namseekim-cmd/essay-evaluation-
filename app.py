import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import re

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

from datetime import datetime, timedelta # timedelta 추가

# ==========================================
# 2. 시간 설정 및 제출 기한 체크 (한국 시간 기준)
# ==========================================
# 서버 시간(UTC)에 9시간을 더해 한국 시간(KST)으로 변환
now = datetime.utcnow() + timedelta(hours=9) 
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
# 4. 본문 상단: 주차 선택 및 데이터 로드 (최종 유연성 확보 버전)
# ==========================================
st.title("🎨 2026 미술하기 생각하기 에세이")

selected_week = st.selectbox(
    "📅 현재 제출하시려는 주차를 선택해 주세요", 
    [f"Week{i:02d}" for i in range(1, 13)]
)

# [Step 1] 전체 학생 명단(Roster) 로드 - 시스템의 기준점
try:
    roster_df = conn.read(worksheet="Roster", ttl=0)
    # 데이터 클리닝
    roster_df = roster_df.dropna(subset=['학번'])
    roster_df['학번'] = roster_df['학번'].astype(str).str.strip()
    roster_df = roster_df[roster_df['학번'] != ""]
except Exception as e:
    st.error(f"⚠️ 'Roster' 시트를 불러올 수 없습니다. 시트 이름을 확인해 주세요. ({e})")
    st.stop()

# [Step 2] 선택한 주차 데이터 로드 - 에러가 나도 무조건 '새 시작' 허용
try:
    df = conn.read(worksheet=selected_week, ttl=0)
    
    # 읽어온 데이터가 비어있거나 제목줄만 있는 경우 처리
    if df is None or df.empty or '학번' not in df.columns:
        df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
    else:
        # 정상 데이터 클리닝
        df = df.dropna(subset=['학번'])
        df['학번'] = df['학번'].astype(str).str.strip()
        df = df[df['학번'] != ""]

except Exception:
    # [핵심] Week08 등 시트가 존재하더라도 읽기 오류가 나면 
    # 기존 데이터를 보호하면서 새 데이터를 받을 수 있게 빈 틀을 제공합니다.
    df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
    st.info(f"📍 {selected_week}의 첫 번째 제출을 받을 준비가 되었습니다.")

st.divider()

# [Step 3] 현황판 계산 (에러 방지용 안전 장치 포함)
actual_submit_count = df['학번'].nunique() if not df.empty else 0
total_roster_count = roster_df['학번'].nunique() if not roster_df.empty else 0
non_submit_count = total_roster_count - actual_submit_count

c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("총 제출", f"{actual_submit_count}명")
with c2: st.metric("미제출", f"{max(0, non_submit_count)}명")
with c3:
    if not df.empty and '글자수' in df.columns:
        df['글자수_n'] = pd.to_numeric(df['글자수'], errors='coerce')
        avg_len = int(df['글자수_n'].mean()) if not df['글자수_n'].isna().all() else 0
    else: avg_len = 0
    st.metric("평균 글자수", f"{avg_len}자")
with c4:
    try:
        avg_ai = f"{df['AI의심도'].str.replace('%','').astype(float).mean():.1f}%" if not df.empty and 'AI의심도' in df.columns else "0%"
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
                st.error(f"❌ 글자수 부족 (현재 {len(content)}자 / 최소 1500자 필요)")
            elif sid in df['학번'].astype(str).values:
                st.error(f"❌ 이미 제출된 학번입니다.")
            else:
                with st.spinner("AI가 에세이를 정밀 분석 중입니다..."):
                    # 변수 초기화
                    summary_text = "요약 실패"
                    final_ai_opinion = "분석 실패"
                    ai_suspicion = "0%"
                    
                    try:
                        model = genai.GenerativeModel(active_model)
                        # AI에게 명확한 형식을 요구하는 프롬프트
                        prompt = f"""
                        미술 에세이 전문가로서 다음 글을 분석하고 반드시 아래 형식을 지켜 응답하세요.
                        
                        1. 1문장 요약: 전체 내용을 관통하는 핵심 사유를 한 문장으로 요약
                        2. AI 의심도: 0%~100% 사이의 수치
                        3. 주장의 명확성 평가: Pass/Fail 여부와 구체적인 분석 의견
                                            
                        내용:
                        {content}
                        """
                        response = model.generate_content(prompt)
                        
                        if response and response.text:
                            full_text = response.text
                            final_ai_opinion = full_text # 전체 의견 저장
                            
                            # 정규표현식으로 각 항목 추출
                            import re
                            s_match = re.search(r'1문장 요약:\s*(.*)', full_text)
                            d_match = re.search(r'AI 의심도:\s*(\d+%)', full_text)
                            
                            if s_match: summary_text = s_match.group(1).split('\n')[0]
                            if d_match: ai_suspicion = d_match.group(1)

                        # 데이터 생성 (시트 컬럼 순서와 일치)
                        new_data = pd.DataFrame([{
                            "학번": str(sid), 
                            "이름": str(sname), 
                            "글자수": len(content), 
                            "내용": content, 
                            "1문장요약": summary_text, # [추가] 핵심 요약
                            "AI의견": final_ai_opinion,
                            "AI의심도": ai_suspicion,
                            "제출시간": datetime.now().strftime('%Y-%m-%d %H:%M')
                        }])

                        updated_df = pd.concat([df, new_data], ignore_index=True).astype(str)
                        conn.update(worksheet=selected_week, data=updated_df)
                        
                        st.balloons()
                        st.success(f"✅ 제출 완료! 요약: {summary_text}")
                        # st.rerun() 은 시각 효과를 위해 제거하거나 sleep 후 사용하세요.

                    except Exception as e:
                        st.error(f"❌ 오류 발생: {e}")
          
# ==========================================
# 6. 하단 데이터 확인 및 관리 도구
# ==========================================
# [위치 6번 섹션] 이 코드로 교체하세요
st.divider()

# 1. 제출 완료자 확인
with st.expander(f"📋 {selected_week} 제출 완료자 명단"):
    if not df.empty:
        # 최신순으로 정렬하여 필요한 정보만 표시
        show_df = df[['학번', '이름', 'AI의심도', '제출시간']].iloc[::-1]
        st.dataframe(show_df, use_container_width=True)
    else:
        st.info("아직 제출자가 없습니다.")

# 2. 미제출자 명단 확인 (Roster와 대조)
with st.expander(f"⚠️ {selected_week} 미제출자 명단 확인"):
    if not roster_df.empty:
        # 양쪽 데이터의 학번 형식을 맞춤 (공백 제거 및 문자열화)
        submitted_sids = set(df['학번'].astype(str).str.strip().unique())
        roster_df['학번_clean'] = roster_df['학번'].astype(str).str.strip()
        
        # 전체 명단 중 제출자 세트에 없는 학생만 추출
        non_submitters = roster_df[~roster_df['학번_clean'].isin(submitted_sids)]
        
        if not non_submitters.empty:
            st.warning(f"현재 총 {len(non_submitters)}명이 미제출 상태입니다.")
            st.dataframe(non_submitters[['학번', '이름']], use_container_width=True)
        else:
            st.success("🎉 모든 학생이 에세이 제출을 완료했습니다!")
    else:
        st.error("구글 시트에 'Roster' 탭(전체 명단)이 있는지 확인해 주세요.")

# 관리자 모드
with st.expander("🛠️ 시스템 관리자 메뉴"):
    pw = st.text_input("Admin Password", type="password")
    if pw == "1234":
        if st.button(f"🔥 {selected_week} 데이터 초기화 (주의)"):
            empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
            conn.update(worksheet=selected_week, data=empty_df)
            st.success("초기화되었습니다.")
            st.rerun()

# 제출 명단 확인
if not df.empty:
    with st.expander("📋 최근 제출자 명단 (AI 의심도 포함)"):
        # 의심도가 높은 순서대로 정렬해서 볼 수 있게 기능 제공
        show_df = df[['학번', '이름', 'AI의심도', '제출시간']].iloc[::-1]
        st.dataframe(show_df, use_container_width=True)








