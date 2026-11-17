"""US Company Financials Explorer — The Mountain Path Academy.
Pulls company data from Financial Modeling Prep (FMP) 'stable' API with your own key.
Free FMP plan: 250 calls/day, US stocks, ~5 years of annual statements.
Each company look-up uses 5 calls (profile, quote, 3 statements); results are cached for 24 hours.
"""
import io
import os
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------- palette (Mountain Path) ----------------
GOLD, BLUE, MID, CARD = "#FFD700", "#003366", "#004d80", "#112240"
TXT, MUTED, GRN, RED, LB = "#e6f1ff", "#8892b0", "#28a745", "#dc3545", "#ADD8E6"
BG = "linear-gradient(135deg,#1a2332,#243447,#2a3f5f)"
BASE = "https://financialmodelingprep.com/stable"
SITE = "https://themountainpathacademy.com"

st.set_page_config(page_title="US Company Financials Explorer | Mountain Path", page_icon="📊", layout="wide")
st.html(f"""<style>
.stApp{{background:{BG};}}
section[data-testid="stSidebar"]{{background:{CARD};}}
section[data-testid="stSidebar"] *{{color:{TXT};}}
section[data-testid="stSidebar"] input{{color:#0b1a33!important;-webkit-text-fill-color:#0b1a33!important;}}
header[data-testid="stHeader"]{{background:transparent;}}
h1,h2,h3,h4,p,label,.stMarkdown,.stCaption{{color:{TXT}!important;}}
div[data-baseweb="tab-list"] button p{{color:{LB}!important;font-weight:600}}
div[data-baseweb="tab-list"] button[aria-selected="true"] p{{color:{GOLD}!important}}
</style>""")


def t(text, color=TXT, size=15, weight=400, extra=""):
    """Inline-styled text node (colour + -webkit-text-fill-color) per house style."""
    return (f'<span style="color:{color};-webkit-text-fill-color:{color};font-size:{size}px;'
            f'font-weight:{weight};{extra}">{text}</span>')


def card(inner, border=MID, pad="14px 18px"):
    return (f'<div style="background:{CARD};border:1px solid {border};border-radius:12px;padding:{pad};'
            f'user-select:none;-webkit-user-select:none;height:100%">{inner}</div>')


def money(v, cur="$"):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    a = abs(v)
    s = f"{a/1e12:.2f}T" if a >= 1e12 else f"{a/1e9:.2f}B" if a >= 1e9 else f"{a/1e6:.1f}M" if a >= 1e6 else f"{a:,.0f}"
    return ("-" if v < 0 else "") + cur + s


def pct(v):
    return "–" if v is None or pd.isna(v) else f"{v*100:.1f}%"


# ---------------- API layer ----------------
class FMPError(Exception):
    pass


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fmp(endpoint, symbol, key, period="annual", limit=5):
    params = {"symbol": symbol, "apikey": key}
    if endpoint.endswith("statement"):
        params.update(period=period, limit=limit)
    try:
        r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=25)
    except requests.RequestException as e:
        raise FMPError(f"Network error: {e}")
    text = r.text.strip()
    if r.status_code == 401 or "Invalid API KEY" in text:
        raise FMPError("Your API key was rejected. Check it on your FMP dashboard.")
    if r.status_code == 429 or "Limit Reach" in text:
        raise FMPError("Daily call limit reached (free plan: 250 calls/day). Try again tomorrow.")
    if r.status_code == 402 or "Premium" in text or "Restricted" in text or "not available under your current subscription" in text:
        raise FMPError(f"'{endpoint}' for {symbol} is not included in your FMP plan.")
    try:
        data = r.json()
    except ValueError:
        raise FMPError(f"Unexpected reply from FMP for {endpoint}: {text[:150]}")
    if isinstance(data, dict) and data.get("Error Message"):
        raise FMPError(data["Error Message"])
    return data


def get_key():
    try:
        k = st.secrets.get("FMP_API_KEY", "")
    except Exception:
        k = ""
    return k or os.environ.get("FMP_API_KEY", "")


# ---------------- sidebar ----------------
with st.sidebar:
    st.html(card(t("THE MOUNTAIN PATH ACADEMY", GOLD, 12, 800, "letter-spacing:1.5px") + "<br>" +
                 t("US Company Financials Explorer", TXT, 18, 700)))
    key = get_key()
    if key:
        st.caption("API key loaded from secrets.")
    else:
        key = st.text_input("FMP API key", type="password", help="Free key from financialmodelingprep.com. Not stored.")
    symbol = st.text_input("US ticker", "AAPL").strip().upper()
    period = st.radio("Statements", ["annual", "quarter"], horizontal=True)
    limit = st.slider("Periods", 2, 5, 5)
    st.divider()
    st.subheader("Cost of capital inputs")
    rf = st.number_input("Risk-free rate (10-yr US Treasury)", 0.0, 0.15, 0.043, 0.001, format="%.3f")
    mrp = st.number_input("Market risk premium", 0.0, 0.15, 0.055, 0.001, format="%.3f")
    tax = st.number_input("Tax rate", 0.0, 0.5, 0.21, 0.01, format="%.2f")
    go_btn = st.button("Fetch data", type="primary", use_container_width=True)
    st.caption("Each new ticker uses 5 API calls. Repeat look-ups are cached for 24 hours.")

st.html(card(t("FREE LEARNING TOOL · MBA · CFA · FRM", BLUE, 12, 800,
               f"background:{GOLD};-webkit-text-fill-color:{BLUE};padding:4px 10px;border-radius:5px;letter-spacing:1px") +
             "<br><br>" + t("US Company Financials Explorer", TXT, 34, 800) + "<br>" +
             t("Statements, ratios, trends and cost of capital for any US-listed company, from your own Financial "
               "Modeling Prep API key.", LB, 16), pad="22px 26px"))

if "loaded" not in st.session_state:
    st.session_state.loaded = None
if go_btn:
    st.session_state.loaded = (symbol, period, limit)

if not st.session_state.loaded:
    st.html(card(t("How to start", GOLD, 16, 700) + "<br>" +
                 t("1. Get a free API key at financialmodelingprep.com (free plan: 250 calls/day, US stocks).<br>"
                   "2. Paste it in the sidebar, or save it as FMP_API_KEY in .streamlit/secrets.toml.<br>"
                   "3. Enter a US ticker such as AAPL, MSFT or JPM and click <b>Fetch data</b>.", TXT, 15)))
elif not key:
    st.error("Enter your FMP API key in the sidebar first.")
else:
    sym, per, lim = st.session_state.loaded
    try:
        with st.spinner(f"Fetching {sym} from FMP…"):
            prof = fmp("profile", sym, key)
            quote = fmp("quote", sym, key)
            inc = fmp("income-statement", sym, key, per, lim)
            bal = fmp("balance-sheet-statement", sym, key, per, lim)
            cfs = fmp("cash-flow-statement", sym, key, per, lim)
    except FMPError as e:
        st.error(str(e))
        st.stop()
    if not prof or not inc:
        st.warning(f"No data returned for '{sym}'. Check the ticker (US-listed symbols only on the free plan).")
        st.stop()

    p = prof[0] if isinstance(prof, list) else prof
    q = (quote[0] if isinstance(quote, list) and quote else {}) or {}
    cur = "$" if p.get("currency", "USD") == "USD" else p.get("currency", "") + " "

    def frame(rows):
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        lab = df["period"].astype(str) + " " + df["fiscalYear"].astype(str) if per == "quarter" and "fiscalYear" in df else df["date"].astype(str).str[:4]
        if per == "quarter" and "fiscalYear" not in df:
            lab = df["date"].astype(str)
        df.index = lab
        return df.iloc[::-1]  # oldest → newest

    I, B, C = frame(inc), frame(bal), frame(cfs)

    def col(df, name):
        return pd.to_numeric(df[name], errors="coerce") if name in df else pd.Series(index=df.index, dtype=float)

    # ---------------- ratios (simple whiteboard formulas) ----------------
    R = pd.DataFrame(index=I.index)
    rev, gp, op, ni = col(I, "revenue"), col(I, "grossProfit"), col(I, "operatingIncome"), col(I, "netIncome")
    ebitda, intexp = col(I, "ebitda"), col(I, "interestExpense")
    ta, te = col(B, "totalAssets").reindex(I.index), col(B, "totalStockholdersEquity").reindex(I.index)
    ca, cl = col(B, "totalCurrentAssets").reindex(I.index), col(B, "totalCurrentLiabilities").reindex(I.index)
    debt, cash = col(B, "totalDebt").reindex(I.index), col(B, "cashAndCashEquivalents").reindex(I.index)
    ocf, capex = col(C, "operatingCashFlow").reindex(I.index), col(C, "capitalExpenditure").reindex(I.index)
    fcf = col(C, "freeCashFlow").reindex(I.index)
    fcf = fcf.where(fcf.notna(), ocf + capex)
    R["Revenue growth"] = rev.pct_change()
    R["Gross margin"] = gp / rev
    R["Operating margin"] = op / rev
    R["Net margin"] = ni / rev
    R["ROE (NI ÷ equity)"] = ni / te
    R["ROA (NI ÷ assets)"] = ni / ta
    R["Asset turnover (×)"] = rev / ta
    R["Current ratio (×)"] = ca / cl
    R["Debt ÷ equity (×)"] = debt / te
    R["Interest cover (×)"] = op / intexp.replace(0, pd.NA)
    R["FCF margin"] = fcf / rev
    R["Cash conversion (OCF ÷ NI) (×)"] = ocf / ni

    # ---------------- header cards ----------------
    price = q.get("price", p.get("price"))
    chg = q.get("changePercentage", p.get("changePercentage"))
    mcap = q.get("marketCap", p.get("marketCap"))
    beta = p.get("beta")
    st.html(card(t(p.get("companyName", sym), TXT, 26, 800) + "&nbsp;&nbsp;" +
                 t(f"{sym} · {p.get('exchange', p.get('exchangeFullName', ''))} · {p.get('sector', '')} · {p.get('industry', '')}", LB, 14),
                 pad="16px 22px"))
    kp = [("Price", f"{cur}{price:,.2f}" if price else "–",
           (t(f"{chg:+.2f}% today", GRN if (chg or 0) >= 0 else RED, 13, 700) if chg is not None else "")),
          ("Market cap", money(mcap, cur), ""), ("Beta", f"{beta:.2f}" if beta else "–", t("vs market", MUTED, 12)),
          ("Latest revenue", money(rev.iloc[-1], cur), t(I.index[-1], MUTED, 12)),
          ("Latest net income", money(ni.iloc[-1], cur), t(pct(R['Net margin'].iloc[-1]) + " margin", MUTED, 12))]
    cols = st.columns(len(kp))
    for c_, (h, v, s) in zip(cols, kp):
        c_.html(card(t(h.upper(), GOLD, 11, 800, "letter-spacing:1px") + "<br>" + t(v, TXT, 22, 800) + "<br>" + s))

    tabs = st.tabs(["📈 Trends", "🧮 Ratios", "📑 Statements", "🏦 Cost of capital", "ℹ️ Company", "⬇️ Download"])

    def fig_base(title):
        f = go.Figure()
        f.update_layout(title=dict(text=title, font=dict(color=TXT)), paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(17,34,64,.6)", font=dict(color=TXT), height=380,
                        legend=dict(orientation="h", y=-0.2, font=dict(color=TXT)), margin=dict(l=20, r=20, t=50, b=20))
        f.update_xaxes(gridcolor="rgba(255,255,255,.08)")
        f.update_yaxes(gridcolor="rgba(255,255,255,.08)")
        return f

    with tabs[0]:
        a, b = st.columns(2)
        f = fig_base(f"Revenue and net income ({cur.strip()})")
        f.add_bar(x=I.index, y=rev, name="Revenue", marker_color=MID)
        f.add_bar(x=I.index, y=ni, name="Net income", marker_color=GOLD)
        a.plotly_chart(f, use_container_width=True)
        f = fig_base("Margins")
        for nm, s, c_ in [("Gross", R["Gross margin"], LB), ("Operating", R["Operating margin"], GOLD), ("Net", R["Net margin"], GRN)]:
            f.add_scatter(x=I.index, y=s * 100, name=nm, mode="lines+markers", line=dict(color=c_, width=3))
        f.update_yaxes(ticksuffix="%")
        b.plotly_chart(f, use_container_width=True)
        a, b = st.columns(2)
        f = fig_base(f"Cash flow ({cur.strip()})")
        f.add_bar(x=I.index, y=ocf, name="Operating cash flow", marker_color=MID)
        f.add_bar(x=I.index, y=fcf, name="Free cash flow", marker_color=GRN)
        a.plotly_chart(f, use_container_width=True)
        f = fig_base("Returns and leverage")
        f.add_scatter(x=I.index, y=R["ROE (NI ÷ equity)"] * 100, name="ROE %", mode="lines+markers", line=dict(color=GOLD, width=3))
        f.add_scatter(x=I.index, y=R["ROA (NI ÷ assets)"] * 100, name="ROA %", mode="lines+markers", line=dict(color=LB, width=3))
        f.add_bar(x=I.index, y=R["Debt ÷ equity (×)"], name="Debt ÷ equity (×)", marker_color=RED, opacity=.5, yaxis="y2")
        f.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False))
        b.plotly_chart(f, use_container_width=True)

    with tabs[1]:
        st.caption("All ratios use one-line formulas on the reported figures (equity and assets at period end).")
        show = R.T.astype(object)
        for r_ in show.index:
            fmt = (lambda v: "–" if pd.isna(v) else f"{v:.2f}×") if "(×)" in r_ else pct
            show.loc[r_] = [fmt(v) for v in show.loc[r_]]
        st.dataframe(show, use_container_width=True)
        with st.expander("Formulas used"):
            st.markdown("""
- Gross / operating / net margin = gross profit / operating income / net income ÷ revenue
- ROE = net income ÷ shareholders' equity · ROA = net income ÷ total assets
- Asset turnover = revenue ÷ total assets · Current ratio = current assets ÷ current liabilities
- Debt ÷ equity = total debt ÷ equity · Interest cover = operating income ÷ interest expense
- FCF = operating cash flow − capital expenditure · FCF margin = FCF ÷ revenue · Cash conversion = OCF ÷ net income
""")

    with tabs[2]:
        rows_i = [("Revenue", "revenue"), ("Cost of revenue", "costOfRevenue"), ("Gross profit", "grossProfit"),
                  ("Operating expenses", "operatingExpenses"), ("Operating income", "operatingIncome"),
                  ("EBITDA", "ebitda"), ("Interest expense", "interestExpense"), ("Income before tax", "incomeBeforeTax"),
                  ("Income tax", "incomeTaxExpense"), ("Net income", "netIncome"), ("EPS (diluted)", "epsDiluted")]
        rows_b = [("Cash & equivalents", "cashAndCashEquivalents"), ("Total current assets", "totalCurrentAssets"),
                  ("Net PP&E", "propertyPlantEquipmentNet"), ("Total assets", "totalAssets"),
                  ("Total current liabilities", "totalCurrentLiabilities"), ("Total debt", "totalDebt"),
                  ("Total liabilities", "totalLiabilities"), ("Shareholders' equity", "totalStockholdersEquity")]
        rows_c = [("Net income", "netIncome"), ("Depreciation & amortisation", "depreciationAndAmortization"),
                  ("Operating cash flow", "operatingCashFlow"), ("Capital expenditure", "capitalExpenditure"),
                  ("Free cash flow", "freeCashFlow"), ("Dividends paid", "commonDividendsPaid"),
                  ("Share buybacks", "commonStockRepurchased"), ("Net change in cash", "netChangeInCash")]

        def tidy(df, rows):
            out = pd.DataFrame({lab: pd.to_numeric(df[k], errors="coerce") if k in df else pd.NA for lab, k in rows}).T
            out.columns = df.index
            return out

        ST = {"Income statement": tidy(I, rows_i), "Balance sheet": tidy(B, rows_b), "Cash flow": tidy(C, rows_c)}
        unit = st.radio("Show in", ["millions", "billions"], horizontal=True)
        div = 1e6 if unit == "millions" else 1e9
        for name, df in ST.items():
            st.subheader(f"{name} ({cur.strip()} {unit})")
            view = df.astype(object)
            for r_ in view.index:
                view.loc[r_] = [("–" if pd.isna(v) else (f"{v:,.2f}" if "EPS" in r_ else f"{v/div:,.1f}")) for v in df.loc[r_]]
            st.dataframe(view, use_container_width=True)
        st.caption("Source: Financial Modeling Prep, as reported. Check against the company's 10-K before using in graded work.")

    with tabs[3]:
        st.caption("Quick WACC with CAPM — adjust the risk-free rate, market risk premium and tax rate in the sidebar.")
        e_val = mcap or 0
        d_val = float(debt.iloc[-1]) if pd.notna(debt.iloc[-1]) else 0.0
        kd_pre = float(intexp.iloc[-1] / d_val) if d_val and pd.notna(intexp.iloc[-1]) and intexp.iloc[-1] > 0 else 0.0
        b_ = st.number_input("Beta (from FMP, editable)", 0.0, 4.0, float(beta or 1.0), 0.01)
        kd_in = st.number_input("Pre-tax cost of debt (default = interest ÷ debt)", 0.0, 0.3, round(kd_pre, 4), 0.001, format="%.4f")
        ke = rf + b_ * mrp
        v = e_val + d_val
        we, wd = (e_val / v, d_val / v) if v else (1.0, 0.0)
        wacc = we * ke + wd * kd_in * (1 - tax)
        steps = [("Cost of equity  Ke = Rf + β × MRP", f"{rf:.2%} + {b_:.2f} × {mrp:.2%}", f"{ke:.2%}"),
                 ("After-tax cost of debt  Kd(1 − t)", f"{kd_in:.2%} × (1 − {tax:.0%})", f"{kd_in*(1-tax):.2%}"),
                 ("Weights  E/V and D/V (market cap, book debt)", f"{money(e_val, cur)} : {money(d_val, cur)}", f"{we:.1%} / {wd:.1%}"),
                 ("WACC = E/V·Ke + D/V·Kd(1 − t)", f"{we:.1%}×{ke:.2%} + {wd:.1%}×{kd_in*(1-tax):.2%}", f"{wacc:.2%}")]
        for i_, (h, w, v_) in enumerate(steps):
            hl = i_ == 3
            st.html(card(t(h, GOLD if hl else LB, 15, 700) + "<br>" + t(w, TXT, 14) +
                         f'<div style="float:right;margin-top:-30px">{t(v_, GOLD if hl else TXT, 24, 800)}</div>',
                         border=GOLD if hl else MID))
        st.caption("Teaching estimate: book debt from the latest balance sheet; cost of debt from reported interest. "
                   "Use yields on the company's bonds for a market-based Kd.")

    with tabs[4]:
        a, b = st.columns([2, 1])
        a.html(card(t("About the company", GOLD, 15, 700) + "<br>" + t(p.get("description", "–"), TXT, 14, extra="line-height:1.55")))
        facts = [("CEO", p.get("ceo")), ("Employees", p.get("fullTimeEmployees")), ("Country", p.get("country")),
                 ("IPO date", p.get("ipoDate")), ("Website", p.get("website")), ("52-week range", p.get("range"))]
        b.html(card("<br>".join(t(k + ": ", GOLD, 13, 700) + t(str(v_ or "–"), TXT, 13) for k, v_ in facts)))

    with tabs[5]:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            pd.DataFrame({"Item": ["Company", "Ticker", "Period", "Source", "Built with"],
                          "Value": [p.get("companyName", sym), sym, per, "Financial Modeling Prep (stable API)",
                                    SITE]}).to_excel(xw, sheet_name="About", index=False)
            for name, df in ST.items():
                df.to_excel(xw, sheet_name=name[:31])
            R.T.to_excel(xw, sheet_name="Ratios")
            I.T.to_excel(xw, sheet_name="Raw_Income")
            B.T.to_excel(xw, sheet_name="Raw_Balance")
            C.T.to_excel(xw, sheet_name="Raw_CashFlow")
        st.download_button(f"Download {sym} financials (Excel)", buf.getvalue(), f"{sym}_financials_{per}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        st.caption("Includes tidy statements, the ratio table and every raw field FMP returned.")

# ---------------- footer ----------------
st.html(f"""<div style="margin-top:28px;padding:16px 10px;border-top:2px solid {GOLD};text-align:center;user-select:none;-webkit-user-select:none">
{t("The Mountain Path Academy · Prof. V. Ravichandran", TXT, 14, 700)}<br>
<a href="{SITE}" target="_blank" style="color:{GOLD};-webkit-text-fill-color:{GOLD};text-decoration:none;font-weight:700">{SITE}</a>
{t(" · ", MUTED)}<a href="https://www.linkedin.com/in/trichyravis" target="_blank" style="color:{GOLD};-webkit-text-fill-color:{GOLD};text-decoration:none;font-weight:700">LinkedIn</a>
{t(" · ", MUTED)}<a href="https://github.com/trichyravis" target="_blank" style="color:{GOLD};-webkit-text-fill-color:{GOLD};text-decoration:none;font-weight:700">GitHub</a><br>
{t("Data: Financial Modeling Prep. Education only — not investment advice.", MUTED, 12)}</div>""")
