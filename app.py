import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import re
import time

# ==========================================
# 1. 시스템 보안 및 UI 설정
# ==========================================
st.set_page_config(page_title="2026 미술하기 생각하기", page_icon="🎨", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    .stAppDeployButton {display: none;}
    [data-testid="stToolbar"] {display: none;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .main .block-container {padding-top: 1.5rem;}
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        background-color: #2E7D32;
        color: white;
        font-weight: bold;
    }
    [data-testid="stMetricValue"] { font-size: 1.8rem; color: #1565C0; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 시간 설정 및 제출 기한 체크
# ==========================================
# datetime.utcnow() 대신 timezone을 고려한 설정을 권장하지만, 기존 로직을 유지합니다.
now = datetime.utcnow() + timedelta(hours=9) 
weekday = now.weekday() 
is_open = 2 <= weekday <= 6 # 수(2) ~ 일(6)

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
# 4. 본문 상단: 주차 선택 및 데이터 로드 (안정화 버전)
# ==========================================
st.title("🎨 2026 미술하기 생각하기 에세이")

selected_week = st.selectbox(
    "📅 현재 제출하시려는 주차를 선택해 주세요", 
    [f"Week{i:02d}" for i in range(1, 13)]
)

# [Step 1] 전체 학생 명단(Roster) 로드
try:
    roster_df = conn.read(worksheet="Roster", ttl=0)
    roster_df = roster_df.dropna(subset=['학번'])
    roster_df['학번'] = roster_df['학번'].astype(str).str.strip()
    roster_df = roster_df[roster_df['학번'] != ""]
except Exception as e:
    st.error(f"⚠️ 'Roster' 시트를 불러올 수 없습니다. ({e})")
    st.stop()

# [Step 2] 선택한 주차 데이터 로드
try:
    df = conn.read(worksheet=selected_week, ttl=0)
    if df is None or df.empty or '학번' not in df.columns:
        df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
    else:
        df = df.dropna(subset=['학번'])
        df['학번'] = df['학번'].astype(str).str.strip()
        df = df[df['학번'] != ""]
except Exception:
    df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
    st.info(f"📍 {selected_week}의 첫 번째 제출을 받을 준비가 되었습니다.")

st.divider()

# [Step 3] 현황판 계산
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
# 5. 에세이 제출 폼
# ==========================================
st.divider()

if not is_open:
    st.warning("⚠️ 지금은 제출 기간이 아닙니다. (제출 가능: 매주 수요일 00:00 ~ 일요일 23:59)")
else:
    with st.form("essay_form", clear_on_submit=True):
        st.success(f"📍 현재 **[{selected_week}]** 에세이 정밀 분석 중입니다.")
        cid, cname = st.columns(2)
        with cid: sid = st.text_input("학번 (숫자만)").strip()
        with cname: sname = st.text_input("이름").strip()
        
        content = st.text_area(
            "에세이 내용 (최소 1500자 이상)", 
            height=500,
            placeholder="당신만의 경험과 사유를 적어주세요."
        )
        
        submitted = st.form_submit_button(f"🚀 {selected_week} 에세이 제출 및 AI 분석")

        if submitted:
            if not sid or not sname:
                st.warning("학번과 이름을 입력해 주세요.")
            elif len(content) < 1500:
                st.error(f"❌ 글자수 부족 (현재 {len(content)}자 / 최소 1500자 필요)")
            elif sid in df['학번'].values:
                st.error(f"❌ 이미 제출된 학번입니다.")
            else:
                with st.spinner("AI 분석 중..."):
                    try:
                        model = genai.GenerativeModel(active_model)
                        prompt = f"미술 에세이 분석: 1. 1문장 요약, 2. AI 의심도(%), 3. 의견(Pass/Fail 포함)\n\n내용:\n{content}"
                        response = model.generate_content(prompt)
                        
                        full_text = response.text if response else ""
                        s_match = re.search(r'1문장 요약:\s*(.*)', full_text)
                        d_match = re.search(r'AI 의심도:\s*(\d+%)', full_text)
                        
                        summary = s_match.group(1).split('\n')[0] if s_match else "요약 실패"
                        suspicion = d_match.group(1) if d_match else "0%"

                        new_data = pd.DataFrame([{
                            "학번": sid, "이름": sname, "글자수": len(content), 
                            "내용": content, "1문장요약": summary, 
                            "AI의견": full_text, "AI의심도": suspicion, 
                            "제출시간": now.strftime('%Y-%m-%d %H:%M')
                        }])

                        updated_df = pd.concat([df, new_data], ignore_index=True).astype(str)
                        conn.update(worksheet=selected_week, data=updated_df)
                        
                        st.balloons()
                        st.success(f"✅ 제출 완료! 화면을 갱신합니다...")
                        time.sleep(2) # 성공 메시지를 볼 시간 확보
                        st.rerun() # 현황판 즉시 업데이트

                    except Exception as e:
                        st.error(f"❌ 오류 발생: {e}")

# ==========================================
# 6. 하단 데이터 확인 및 관리 도구
# ==========================================
st.divider()

col_sub, col_non = st.columns(2)

with col_sub:
    with st.expander(f"📋 {selected_week} 제출 완료자 명단"):
        if not df.empty:
            st.dataframe(df[['학번', '이름', 'AI의심도', '제출시간']].iloc[::-1], use_container_width=True)
        else:
            st.info("제출자가 없습니다.")

with col_non:
    with st.expander(f"⚠️ {selected_week} 미제출자 명단"):
        if not roster_df.empty:
            submitted_sids = set(df['학번'].unique())
            non_submitters = roster_df[~roster_df['학번'].isin(submitted_sids)]
            if not non_submitters.empty:
                st.dataframe(non_submitters[['학번', '이름']], use_container_width=True)
            else:
                st.success("전원 제출 완료!")

with st.expander("🛠️ 시스템 관리자 메뉴"):
    pw = st.text_input("Admin Password", type="password", key="admin_pw")
    if pw == "1234":
        if st.button(f"🔥 {selected_week} 데이터 초기화"):
            empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
            conn.update(worksheet=selected_week, data=empty_df)
            st.success("초기화 완료")
            st.rerun()
