import streamlit as st
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
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
now = datetime.utcnow() + timedelta(hours=9) 
weekday = now.weekday() 
is_open = 2 <= weekday <= 6 # 수(2) ~ 일(6)

# ==========================================
# 3. 데이터베이스 및 AI 설정 (API 부하 최적화)
# ==========================================
try:
    # [부하 감소 1] AI 모델 목록을 조회하지 않고 고정된 최신 모델명을 직접 사용합니다.
    active_model = 'models/gemini-1.5-flash-latest'
    
    # 구글 시트 연결
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"⚠️ 시스템 초기화 오류: ({e})")
    st.stop()

# ==========================================
# 4. 본문 상단: 주차 선택 및 데이터 로드 (데이터 보호 완전판)
# ==========================================
st.title("🎨 2026 미술하기 생각하기 에세이")

# [1] 변수 정의 (NameError 방지)
selected_week = st.selectbox(
    "📅 현재 제출하시려는 주차를 선택해 주세요", 
    [f"Week{i:02d}" for i in range(1, 13)]
)

# [2] 데이터 안전 로드 (TTL 설정으로 429 에러 방지)
try:
    # Roster는 1시간(3600초), 주차별 데이터는 1분(60초) 캐시 사용
    roster_df = conn.read(worksheet="Roster", ttl=3600)
    df = conn.read(worksheet=selected_week, ttl=60)
    
    if df is None:
        raise ValueError("시트를 읽어올 수 없습니다.")
        
    if df.empty or '학번' not in df.columns:
        df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
    else:
        # 데이터 클리닝 (학번 기준)
        df = df.dropna(subset=['학번'])
        df['학번'] = df['학번'].astype(str).str.strip()
        df = df[df['학번'] != ""]

except Exception as e:
    st.error(f"⚠️ 구글 서버 연결 지연 (에러: {e})")
    st.warning("데이터 보호를 위해 제출 기능이 잠시 차단되었습니다. 1분 뒤 '새로고침(F5)' 해주세요.")
    st.stop() 

st.divider()

# [Step 3] 현황판 계산
# nunique()를 사용하여 중복 제출자를 1명으로 정확히 계산합니다.
actual_submit_count = df['학번'].nunique() if not df.empty else 0
total_roster_count = roster_df['학번'].nunique() if not roster_df.empty else 0
non_submit_count = total_roster_count - actual_submit_count

c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("총 제출 (실인원)", f"{actual_submit_count}명")
with c2: st.metric("미제출", f"{max(0, non_submit_count)}명")
with c3:
    if not df.empty and '글자수' in df.columns:
        df['글자수_n'] = pd.to_numeric(df['글자수'], errors='coerce')
        avg_len = int(df['글자수_n'].mean()) if not df['글자수_n'].isna().all() else 0
    else: avg_len = 0
    st.metric("평균 글자수", f"{avg_len}자")
with c4:
    # 분석 생략 시 N/A로 표시
    st.metric("평균 AI 의심도", "N/A")

# ==========================================
# 5. 에세이 제출 폼 (AI 분석 최소화 버전)
# ==========================================
st.divider()

if not is_open:
    st.warning("⚠️ 지금은 제출 기간이 아닙니다. (제출 가능: 매주 수요일 00:00 ~ 일요일 23:59)")
else:
    with st.form("essay_form", clear_on_submit=True):
        st.success(f"📍 현재 **[{selected_week}]** 에세이 제출이 가능합니다.")
        cid, cname = st.columns(2)
        with cid: sid = st.text_input("학번 (숫자만)").strip()
        with cname: sname = st.text_input("이름").strip()
        
        content = st.text_area(
            "에세이 내용 (최소 1500자 이상)", 
            height=500,
            placeholder="당신만의 경험과 사유를 적어주세요."
        )
        
        submitted = st.form_submit_button(f"🚀 {selected_week} 에세이 제출하기")

        if submitted:
            if not sid or not sname:
                st.warning("학번과 이름을 입력해 주세요.")
            elif len(content) < 1500:
                st.error(f"❌ 글자수 부족 (현재 {len(content)}자 / 최소 1500자 필요)")
            elif sid in df['학번'].values:
                st.error(f"❌ 이미 제출된 학번입니다.")
            else:
                try:
                    # [부하 감소 2] AI 분석(Gemini 호출) 과정을 생략하고 즉시 저장 데이터 생성
                    new_data = pd.DataFrame([{
                        "학번": sid, 
                        "이름": sname, 
                        "글자수": len(content), 
                        "내용": content, 
                        "1문장요약": "분석 생략", 
                        "AI의견": "정상 제출됨", 
                        "AI의심도": "0%", 
                        "제출시간": now.strftime('%Y-%m-%d %H:%M')
                    }])

                    # 시트 업데이트
                    updated_df = pd.concat([df, new_data], ignore_index=True).astype(str)
                    conn.update(worksheet=selected_week, data=updated_df)
                    
                    st.balloons()
                    st.success(f"✅ 제출 완료! 현황 업데이트를 위해 잠시만 기다려주세요...")
                    time.sleep(2)
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ 제출 중 오류 발생: {e}")

# ==========================================
# 6. 하단 데이터 확인 및 관리 도구
# ==========================================
st.divider()
col_sub, col_non = st.columns(2)

with col_sub:
    with st.expander(f"📋 {selected_week} 제출 완료자 확인"):
        if not df.empty:
            st.dataframe(df[['학번', '이름', '제출시간']].iloc[::-1], use_container_width=True)
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
                st.success("🎉 전원 제출 완료!")

with st.expander("🛠️ 시스템 관리자 메뉴"):
    pw = st.text_input("Admin Password", type="password", key="admin_pw")
    if pw == "1234":
        if st.button(f"🔥 {selected_week} 데이터 초기화"):
            empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
            conn.update(worksheet=selected_week, data=empty_df)
            st.success("초기화 완료")
            st.rerun()
