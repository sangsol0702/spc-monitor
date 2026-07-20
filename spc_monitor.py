"""
반도체 공정 SPC(Statistical Process Control) 이상탐지 대시보드
--------------------------------------------------------------
- 사용자가 파라미터별 Target / USL(관리상한) / LSL(관리하한)을 설정
- 공정 데이터를 랜덤 시뮬레이션(또는 수동 입력)으로 생성
- 레퍼런스 대비 편차(deviation) 및 오차율(%)을 계산해 이상 여부 판단
- 최근 N개 데이터의 추세(drift) 여부도 함께 표시
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="반도체 공정 SPC 모니터링", layout="wide")

st.title("🔬 반도체 공정 SPC 이상탐지 대시보드")
st.caption("Target / USL / LSL 기준으로 공정 데이터를 모니터링하고, 기준을 벗어난 지점과 오차율을 자동으로 표시합니다.")

# -----------------------------
# 1. 파라미터 & 레퍼런스 설정
# -----------------------------
st.sidebar.header("⚙️ 공정 & 레퍼런스 설정")

process_name = st.sidebar.text_input("공정명", value="식각(Etch) 공정")
param_name = st.sidebar.text_input("모니터링 파라미터명", value="Chamber 온도 (℃)")

col1, col2, col3 = st.sidebar.columns(3)
target = col1.number_input("Target", value=250.0)
lsl = col2.number_input("LSL(하한)", value=245.0)
usl = col3.number_input("USL(상한)", value=255.0)

n_points = st.sidebar.slider("시뮬레이션 데이터 개수", min_value=10, max_value=200, value=50)
noise_level = st.sidebar.slider("공정 변동성(노이즈)", min_value=0.5, max_value=10.0, value=3.0)
anomaly_rate = st.sidebar.slider("의도적 이상치 발생 확률(%)", min_value=0, max_value=30, value=10)
seed = st.sidebar.number_input("랜덤 시드", value=42, step=1)

run_btn = st.sidebar.button("▶ 공정 시뮬레이션 시작", type="primary")

# -----------------------------
# 2. 공정 데이터 시뮬레이션
# -----------------------------
def simulate_process(n, target, noise, anomaly_pct, seed):
    rng = np.random.default_rng(seed)
    values = rng.normal(loc=target, scale=noise, size=n)

    # 일부 지점에 의도적으로 큰 이상치 삽입 (실제 공정 오류 상황 재현)
    n_anomaly = int(n * anomaly_pct / 100)
    anomaly_idx = rng.choice(n, size=n_anomaly, replace=False)
    for idx in anomaly_idx:
        direction = rng.choice([-1, 1])
        values[idx] += direction * rng.uniform(noise * 2.5, noise * 5)

    # 후반부에 서서히 값이 한쪽으로 쏠리는 드리프트(drift) 패턴 추가
    drift = np.linspace(0, noise * 1.5, n)
    values = values + drift

    timestamps = pd.date_range("2026-07-20 09:00", periods=n, freq="2min")
    return pd.DataFrame({"time": timestamps, "value": values})


if run_btn or "df" not in st.session_state:
    st.session_state.df = simulate_process(n_points, target, noise_level, anomaly_rate, seed)

df = st.session_state.df.copy()

# -----------------------------
# 3. 이상탐지 로직
# -----------------------------
df["deviation"] = df["value"] - target
spec_range = usl - lsl
df["error_pct"] = (df["deviation"] / spec_range) * 100
df["status"] = np.where((df["value"] > usl) | (df["value"] < lsl), "이상(Out of Spec)", "정상")

# 추세(drift) 탐지: 최근 10개 이동평균이 target 대비 spec_range의 20% 이상 벗어나면 경고
window = min(10, len(df))
df["moving_avg"] = df["value"].rolling(window=window, min_periods=1).mean()
drift_flag = abs(df["moving_avg"].iloc[-1] - target) > (spec_range * 0.2)

n_anomalies = (df["status"] == "이상(Out of Spec)").sum()
anomaly_ratio = n_anomalies / len(df) * 100

# -----------------------------
# 4. 요약 지표
# -----------------------------
st.subheader(f"📌 {process_name} — {param_name}")

m1, m2, m3, m4 = st.columns(4)
m1.metric("총 측정 데이터", f"{len(df)}건")
m2.metric("이상 감지 건수", f"{n_anomalies}건", f"{anomaly_ratio:.1f}%")
m3.metric("최근 이동평균", f"{df['moving_avg'].iloc[-1]:.2f}", f"{df['moving_avg'].iloc[-1]-target:+.2f}")
m4.metric("추세(Drift) 경고", "⚠ 발생" if drift_flag else "✅ 없음")

# -----------------------------
# 5. 관리도(Control Chart)
# -----------------------------
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["time"], y=df["value"], mode="lines+markers",
                          name="측정값", line=dict(color="royalblue")))
fig.add_trace(go.Scatter(x=df["time"], y=df["moving_avg"], mode="lines",
                          name=f"이동평균({window}개)", line=dict(color="orange", dash="dot")))

anomalies = df[df["status"] == "이상(Out of Spec)"]
fig.add_trace(go.Scatter(x=anomalies["time"], y=anomalies["value"], mode="markers",
                          name="이상치", marker=dict(color="red", size=10, symbol="x")))

fig.add_hline(y=target, line_color="green", line_dash="dash", annotation_text="Target")
fig.add_hline(y=usl, line_color="red", annotation_text="USL")
fig.add_hline(y=lsl, line_color="red", annotation_text="LSL")

fig.update_layout(height=450, xaxis_title="시간", yaxis_title=param_name,
                   legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

# -----------------------------
# 6. 이상 발생 상세 리스트
# -----------------------------
st.subheader("🚨 기준 초과 상세 내역")

if n_anomalies == 0:
    st.success("설정한 레퍼런스 범위를 벗어난 데이터가 없습니다.")
else:
    detail = anomalies[["time", "value", "deviation", "error_pct"]].copy()
    detail.columns = ["발생 시각", "측정값", "Target 대비 편차", "오차율(%)"]
    detail["측정값"] = detail["측정값"].round(2)
    detail["Target 대비 편차"] = detail["Target 대비 편차"].round(2)
    detail["오차율(%)"] = detail["오차율(%)"].round(1)

    def highlight_row(row):
        return ['background-color: #ffe5e5'] * len(row)

    st.dataframe(detail.style.apply(highlight_row, axis=1), use_container_width=True)

    worst = detail.loc[detail["오차율(%)"].abs().idxmax()]
    st.warning(
        f"가장 큰 이상치: **{worst['발생 시각']}**에 **{param_name}** 값이 "
        f"**{worst['측정값']}** 로 측정되어 Target 대비 **{worst['오차율(%)']:+.1f}%** 벗어났습니다."
    )

if drift_flag:
    st.error(
        f"⚠ 최근 {window}개 데이터의 이동평균이 Target에서 관리범위의 20% 이상 벗어났습니다. "
        f"공정이 한쪽으로 서서히 쏠리는 **드리프트(drift)** 가능성이 있어 점검이 필요합니다."
    )

st.divider()
st.caption("※ 본 대시보드는 SPC(통계적 공정관리) 개념 — Target/USL/LSL 기반 이상탐지 + 이동평균 기반 드리프트 탐지 — 를 적용한 시뮬레이션 예시입니다.")
