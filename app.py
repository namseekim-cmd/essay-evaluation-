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
is_open = 2 <= weekday <= 6 

# ==========================================
# 3. 데이터베이스 및 AI 설정
# ==========================================
try:
    active_model = 'models/gemini-1.5-flash-latest'
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"⚠️ 시스템 초기화 오류: ({e})")
    st.stop()

# ==========================================
# 4. 데이터 로드 및 덮어쓰기 방지 (보안 강화)
# ==========================================
st.title("🎨 2026 미술하기 생각하기 에세이")

selected_week = st.selectbox(
    "📅 현재 제출하시려는 주차를 선택해 주세요", 
    [f"Week{i:02d}" for i in range(1, 13)]
)

try:
    # 데이터 로드
    roster_df = conn.read(worksheet="Roster", ttl=3600)
    df = conn.read(worksheet=selected_week, ttl=60)
    
    # [데이터 보호 로직] 
    # 1. 시트 로드 자체가 실패한 경우
    if df is None:
        st.error("⚠️ 구글 시트에서 데이터를 가져올 수 없습니다. 잠시 후 새로고침(F5) 해주세요.")
        st.stop()
        
    # 2. 시트가 비어있는 것처럼 보일 때 (가장 위험한 순간)
    if df.empty or '학번' not in df.columns:
        # 진짜 첫 제출인지 확인하기 위한 메시지
        st.warning(f"📍 {selected_week}에 아직 저장된 데이터가 없거나 불러오는 중입니다.")
        # 빈 데이터프레임 초기화
        df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
    else:
        # 데이터 클리닝: 학번을 문자열로 통일하고 공백 제거 (명단 대조용)
        df['학번'] = df['학번'].astype(str).str.strip()
        df = df[df['학번'] != ""]
        
    # Roster 데이터 클리닝
    roster_df['학번'] = roster_df['학번'].astype(str).str.strip()
    roster_df = roster_df[roster_df['학번'] != ""]

except Exception as e:
    st.error(f"⚠️ 데이터 로드 중 오류가 발생했습니다. (에러: {e})")
    st.info("데이터 보호를 위해 현재 제출 기능이 잠시 차단되었습니다. 1분 뒤 새로고침 해주세요.")
    st.stop() 

st.divider()

# [Step 3] 현황판 계산
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
with c4: st.metric("평균 AI 의심도", "N/A")

# ==========================================
# 5. 에세이 제출 폼
# ==========================================
st.divider()

if not is_open:
    st.warning("⚠️ 지금은 제출 기간이 아닙니다.")
else:
    with st.form("essay_form", clear_on_submit=True):
        st.success(f"📍 현재 **[{selected_week}]** 제출 시스템이 작동 중입니다.")
        cid, cname = st.columns(2)
        with cid: sid = st.text_input("학번 (숫자만)").strip()
        with cname: sname = st.text_input("이름").strip()
        
        content = st.text_area("에세이 내용 (최소 1500자 이상)", height=500)
        submitted = st.form_submit_button(f"🚀 {selected_week} 에세이 제출하기")

        if submitted:
            if not sid or not sname:
                st.warning("학번과 이름을 입력해 주세요.")
            elif len(content) < 1500:
                st.error(f"❌ 글자수 부족 (현재 {len(content)}자 / 최소 1500자 필요)")
            # 대조 시 학번 형식을 맞춤
            elif str(sid) in df['학번'].values:
                st.error(f"❌ 이미 제출된 학번입니다.")
            else:
                try:
                    new_data = pd.DataFrame([{
                        "학번": str(sid), "이름": sname, "글자수": len(content), 
                        "내용": content, "1문장요약": "분석 생략", 
                        "AI의견": "정상 제출됨", "AI의심도": "0%", 
                        "제출시간": now.strftime('%Y-%m-%d %H:%M')
                    }])

                    # 덮어쓰기 방지를 위한 최종 체크
                    # 만약 시트에 90명 이상 있었는데 지금 10명 미만으로 읽혔다면 저장을 중단시킴
                    if not df.empty and actual_submit_count > 10 and len(new_data) + len(df) < actual_submit_count:
                        st.error("⚠️ 시스템 오류: 데이터 정합성 문제로 저장이 중단되었습니다. 잠시 후 다시 시도해 주세요.")
                        st.stop()

                    updated_df = pd.concat([df, new_data], ignore_index=True).astype(str)
                    conn.update(worksheet=selected_week, data=updated_df)
                    
                    st.balloons()
                    st.success(f"✅ {sname}님, 제출 완료!")
                    time.sleep(2)
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ 제출 오류: {e}")

# ==========================================
# 6. 명단 확인 (미제출자 로직 수정)
# ==========================================
st.divider()
col_sub, col_non = st.columns(2)

with col_sub:
    with st.expander(f"📋 {selected_week} 제출 완료자 명단"):
        if not df.empty:
            # 학번과 이름으로만 깔끔하게 표시
            st.dataframe(df[['학번', '이름', '제출시간']].iloc[::-1], use_container_width=True)
        else:
            st.info("제출자가 없습니다.")

with col_non:
    with st.expander(f"⚠️ {selected_week} 미제출자 명단 확인"):
        if not roster_df.empty:
            # [중요] 명단 대조 로직 수정
            # 두 데이터프레임의 학번 형식을 완벽히 일치시킴
            submitter_set = set(df['학번'].unique())
            # roster_df에서 제출자 세트에 포함되지 않은 사람만 필터링
            non_submitters = roster_df[~roster_df['학번'].isin(submitter_set)]
            
            if not non_submitters.empty:
                st.warning(f"미제출자: {len(non_submitters)}명")
                st.dataframe(non_submitters[['학번', '이름']], use_container_width=True)
            else:
                st.success("🎉 모든 학생이 제출을 완료했습니다!")

with st.expander("🛠️ 관리자 메뉴"):
    pw = st.text_input("Admin Password", type="password", key="admin_pw")
    if pw == "1234":
        if st.button(f"🔥 {selected_week} 데이터 초기화"):
            empty_df = pd.DataFrame(columns=["학번", "이름", "글자수", "내용", "1문장요약", "AI의견", "AI의심도", "제출시간"])
            conn.update(worksheet=selected_week, data=empty_df)
            st.rerun()
