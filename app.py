"""US Company Financials Explorer — The Mountain Path Academy.
Pulls company data from Financial Modeling Prep (FMP) 'stable' API with your own key.
Free FMP plan: 250 calls/day, US stocks, ~5 years of annual statements.
Each company look-up uses 5 calls (profile, quote, 3 statements); results are cached for 24 hours.
"""
import datetime as dt
import hashlib
import io
import os
import numpy as np
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
header[data-testid="stHeader"]{{background:transparent;}}
section[data-testid="stSidebar"]{{background:{CARD};border-right:1px solid {MID};}}
/* inputs: dark field, light text, visible border */
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"]{{
  background:#0b1a33!important;border:1px solid {MID}!important;}}
div[data-baseweb="input"] *, div[data-baseweb="base-input"], div[data-baseweb="select"] > div *,
div[data-testid="stTextInputRootElement"], div[data-testid="stNumberInputContainer"]{{background:#0b1a33!important;}}
input, textarea{{background:#0b1a33!important;color:{TXT}!important;-webkit-text-fill-color:{TXT}!important;caret-color:{GOLD};}}
div[data-baseweb="select"] svg{{fill:{LB}!important;}}
input::placeholder{{color:{MUTED}!important;-webkit-text-fill-color:{MUTED}!important;opacity:1}}
div[data-baseweb="select"] *{{color:{TXT}!important;-webkit-text-fill-color:{TXT}!important;}}
ul[role="listbox"]{{background:{CARD}!important;}}
ul[role="listbox"] li{{color:{TXT}!important;-webkit-text-fill-color:{TXT}!important;}}
ul[role="listbox"] li:hover, ul[role="listbox"] li[aria-selected="true"]{{background:{MID}!important;}}
button[data-testid="stNumberInputStepDown"], button[data-testid="stNumberInputStepUp"]{{background:{MID}!important;color:{TXT}!important;}}
/* labels and captions */
label, label p, div[data-testid="stWidgetLabel"] p{{color:{LB}!important;-webkit-text-fill-color:{LB}!important;font-weight:600}}
div[data-testid="stCaptionContainer"] p{{color:{MUTED}!important;-webkit-text-fill-color:{MUTED}!important}}
h1,h2,h3,h4{{color:{TXT}!important}}
/* tabs */
[role="tab"], [role="tab"] *{{color:{LB}!important;-webkit-text-fill-color:{LB}!important;font-weight:600}}
[role="tab"][aria-selected="true"], [role="tab"][aria-selected="true"] *{{color:{GOLD}!important;-webkit-text-fill-color:{GOLD}!important}}
div[data-baseweb="tab-highlight"]{{background:{GOLD}!important}}
/* buttons: primary = gold with navy text; secondary = navy with gold border and white text */
button[data-testid="stBaseButton-primary"], button[kind="primary"]{{background:{GOLD}!important;border:1px solid {GOLD}!important;}}
button[data-testid="stBaseButton-primary"] *, button[kind="primary"] *{{color:{BLUE}!important;-webkit-text-fill-color:{BLUE}!important;font-weight:800}}
button[data-testid="stBaseButton-secondary"], button[kind="secondary"]{{background:{MID}!important;border:1px solid {GOLD}!important;}}
button[data-testid="stBaseButton-secondary"] *, button[kind="secondary"] *{{color:#ffffff!important;-webkit-text-fill-color:#ffffff!important;font-weight:700}}
button[data-testid="stBaseButton-secondary"]:hover, button[kind="secondary"]:hover{{background:{BLUE}!important;}}
/* alerts readable on dark */
div[data-testid="stAlert"]{{background:{CARD}!important;border:1px solid {GOLD}!important;}}
div[data-testid="stAlert"] p, div[data-testid="stAlert"] div{{color:{TXT}!important;-webkit-text-fill-color:{TXT}!important;}}
/* expander */
details summary p{{color:{GOLD}!important;-webkit-text-fill-color:{GOLD}!important;font-weight:700}}
div[data-testid="stExpander"] details{{background:{CARD};border:1px solid {MID};}}
div[data-testid="stExpander"] li, div[data-testid="stExpander"] p{{color:{TXT}!important}}
/* radio / slider text */
div[role="radiogroup"] p{{color:{TXT}!important;-webkit-text-fill-color:{TXT}!important}}
div[data-testid="stSliderTickBarMin"], div[data-testid="stSliderTickBarMax"], div[data-testid="stThumbValue"]{{color:{GOLD}!important}}
div[data-testid="stSlider"] div[role="slider"]{{background:{GOLD}!important;border-color:{GOLD}!important}}
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


@st.cache_resource
def _call_store():
    return {}  # (key-hash, date) -> live calls made through this app (cache misses only); survives reruns


CALLS = _call_store()


def _count(key):
    k = (hashlib.sha1(key.encode()).hexdigest()[:10], dt.date.today().isoformat())
    CALLS[k] = CALLS.get(k, 0) + 1


def calls_today(key):
    return CALLS.get((hashlib.sha1(key.encode()).hexdigest()[:10], dt.date.today().isoformat()), 0) if key else 0


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fmp(endpoint, symbol, key, period="annual", limit=5, extra=None):
    params = {"apikey": key}
    if symbol:
        params["symbol"] = symbol
    if endpoint.endswith("statement"):
        params.update(period=period, limit=limit)
    if extra:
        params.update(dict(extra))
    _count(key)
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


US_EXCH = {"NASDAQ", "NYSE", "AMEX", "NYSE ARCA", "NYSEARCA", "BATS", "CBOE"}


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def search_company(query, key):
    """Name search (1 API call). Returns US-listed matches only."""
    out = []
    for ep in ("search-name", "search-symbol"):
        try:
            _count(key)
            r = requests.get(f"{BASE}/{ep}", params={"query": query, "limit": 50, "apikey": key}, timeout=20)
            data = r.json()
        except Exception:
            continue
        if isinstance(data, dict):
            if data.get("Error Message"):
                raise FMPError(data["Error Message"])
            continue
        for d in data or []:
            ex = str(d.get("exchange") or d.get("exchangeShortName") or "").upper()
            if ex in US_EXCH and d.get("symbol") and not any(o["symbol"] == d["symbol"] for o in out):
                out.append({"symbol": d["symbol"], "name": d.get("name", ""), "exchange": ex})
        if out:
            break
    return out[:25]


def get_key():
    try:
        k = st.secrets.get("FMP_API_KEY", "")
    except Exception:
        k = ""
    return k or os.environ.get("FMP_API_KEY", "")


def safe(endpoint, symbol, key, **kw):
    """Optional data: return None instead of stopping the app (e.g. endpoint not in the free plan)."""
    try:
        return fmp(endpoint, symbol, key, **kw)
    except FMPError as e:
        return {"_error": str(e)}


def latest_10y(key):
    d = safe("treasury-rates", None, key)
    if isinstance(d, list) and d:
        row = sorted(d, key=lambda r: r.get("date", ""))[-1]
        v = row.get("year10")
        if v is not None:
            return float(v) / 100, row.get("date", "")
    return None, None


def price_history(symbol, key, years=5):
    end = dt.date.today()
    start = end.replace(year=end.year - years)
    d = safe("historical-price-eod/light", symbol, key, extra=(("from", start.isoformat()), ("to", end.isoformat())))
    if not isinstance(d, list) or not d:
        return None
    df = pd.DataFrame(d)
    pcol = "price" if "price" in df else ("adjClose" if "adjClose" in df else "close")
    df = df[["date", pcol]].rename(columns={pcol: "price"})
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").set_index("date")["price"].astype(float)


def pick(d, *names):
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None:
            return d.get(n)
    return None


# ---------------- sidebar ----------------
with st.sidebar:
    st.html(card(t("THE MOUNTAIN PATH ACADEMY", GOLD, 12, 800, "letter-spacing:1.5px") + "<br>" +
                 t("US Company Financials Explorer", TXT, 18, 700)))
    key = get_key()
    if key:
        st.caption("API key loaded from secrets.")
    else:
        key = st.text_input("FMP API key", type="password", help="Free key from financialmodelingprep.com. Not stored.")
    if "ticker" not in st.session_state:
        st.session_state.ticker = "AAPL"
    q = st.text_input("Search company name", placeholder="e.g. Coca Cola, Nvidia, JPMorgan")
    if q.strip() and key:
        try:
            hits = search_company(q.strip(), key)
        except FMPError as e:
            hits = []
            st.error(str(e))
        if hits:
            labels = [f"{h['symbol']} — {h['name']} ({h['exchange']})" for h in hits]
            choice = st.selectbox(f"{len(hits)} US matches", labels, index=None, placeholder="Choose a company")
            if choice:
                st.session_state.ticker = choice.split(" — ")[0]
        else:
            st.caption("No US-listed match. Try a shorter name.")
    elif q.strip():
        st.caption("Enter your API key first to search.")
    symbol = st.text_input("US ticker", key="ticker").strip().upper()
    period = st.radio("Statements", ["annual", "quarter"], horizontal=True)
    limit = st.slider("Periods", 2, 5, 5)
    st.divider()
    st.subheader("Cost of capital inputs")
    y10, y10_date = latest_10y(key) if key else (None, None)
    rf = st.number_input("Risk-free rate (10-yr US Treasury)", 0.0, 0.15, round(y10, 4) if y10 else 0.043, 0.001,
                         format="%.4f", help="Filled from FMP's latest Treasury yield when available.")
    if y10:
        st.caption(f"10-yr Treasury {y10:.2%} on {y10_date} (FMP).")
    mrp = st.number_input("Market risk premium", 0.0, 0.15, 0.055, 0.001, format="%.3f")
    tax = st.number_input("Tax rate", 0.0, 0.5, 0.21, 0.01, format="%.2f")
    go_btn = st.button("Fetch data", type="primary", width="stretch")
    usage_box = st.empty()
    st.caption("Free plan: 250 calls/day. A new company uses about 8 calls (statements, prices, DCF); "
               "peers about 2 each; a search uses 1. Repeats are cached for 24 hours.")

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

    def frame_annual(rows):
        df = pd.DataFrame(rows)
        if not df.empty:
            df.index = df["date"].astype(str).str[:4]
            df = df.iloc[::-1]
        return df

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
          ("Market cap", money(mcap, cur), ""), ("Beta (FMP)", f"{beta:.2f}" if beta else "–", t("monthly vs S&P 500", MUTED, 12)),
          ("Latest revenue", money(rev.iloc[-1], cur), t(I.index[-1], MUTED, 12)),
          ("Latest net income", money(ni.iloc[-1], cur), t(pct(R['Net margin'].iloc[-1]) + " margin", MUTED, 12))]
    cols = st.columns(len(kp))
    for c_, (h, v, s) in zip(cols, kp):
        c_.html(card(t(h.upper(), GOLD, 11, 800, "letter-spacing:1px") + "<br>" + t(v, TXT, 22, 800) + "<br>" + s))

    tabs = st.tabs(["📈 Trends", "🧮 Ratios", "📑 Statements", "📉 Beta & returns", "👥 Peers", "🏦 Cost of capital",
                    "💵 DCF", "ℹ️ Company", "⬇️ Download"])

    def fig_base(title):
        f = go.Figure()
        f.update_layout(title=dict(text=title, font=dict(color=TXT)), paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(17,34,64,.6)", font=dict(color=TXT), height=380,
                        legend=dict(orientation="h", y=-0.2, font=dict(color=TXT)), margin=dict(l=20, r=20, t=50, b=20))
        f.update_xaxes(gridcolor="rgba(255,255,255,.08)", type="category")
        f.update_yaxes(gridcolor="rgba(255,255,255,.08)")
        return f

    with tabs[0]:
        a, b = st.columns(2)
        f = fig_base(f"Revenue and net income ({cur.strip()})")
        f.add_bar(x=I.index, y=rev, name="Revenue", marker_color=MID)
        f.add_bar(x=I.index, y=ni, name="Net income", marker_color=GOLD)
        a.plotly_chart(f, width="stretch")
        f = fig_base("Margins")
        for nm, s, c_ in [("Gross", R["Gross margin"], LB), ("Operating", R["Operating margin"], GOLD), ("Net", R["Net margin"], GRN)]:
            f.add_scatter(x=I.index, y=s * 100, name=nm, mode="lines+markers", line=dict(color=c_, width=3))
        f.update_yaxes(ticksuffix="%")
        b.plotly_chart(f, width="stretch")
        a, b = st.columns(2)
        f = fig_base(f"Cash flow ({cur.strip()})")
        f.add_bar(x=I.index, y=ocf, name="Operating cash flow", marker_color=MID)
        f.add_bar(x=I.index, y=fcf, name="Free cash flow", marker_color=GRN)
        a.plotly_chart(f, width="stretch")
        f = fig_base("Returns and leverage")
        f.add_scatter(x=I.index, y=R["ROE (NI ÷ equity)"] * 100, name="ROE %", mode="lines+markers", line=dict(color=GOLD, width=3))
        f.add_scatter(x=I.index, y=R["ROA (NI ÷ assets)"] * 100, name="ROA %", mode="lines+markers", line=dict(color=LB, width=3))
        f.add_bar(x=I.index, y=R["Debt ÷ equity (×)"], name="Debt ÷ equity (×)", marker_color=RED, opacity=.5, yaxis="y2")
        f.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False))
        b.plotly_chart(f, width="stretch")

    with tabs[1]:
        st.caption("All ratios use one-line formulas on the reported figures (equity and assets at period end).")
        show = R.T.astype(object)
        for r_ in show.index:
            fmt = (lambda v: "–" if pd.isna(v) else f"{v:.2f}×") if "(×)" in r_ else pct
            show.loc[r_] = [fmt(v) for v in show.loc[r_]]
        st.dataframe(show, width="stretch")
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
            st.dataframe(view, width="stretch")
        st.caption("Source: Financial Modeling Prep, as reported. Check against the company's 10-K before using in graded work.")

    # ---------------- beta from price history ----------------
    with tabs[3]:
        st.caption("Beta by regression: the slope of the stock's returns on the market's (S&P 500, via SPY). "
                   "Uses 2 API calls (stock and SPY price history, up to 5 years).")
        freq = st.radio("Return frequency", ["Monthly", "Weekly"], horizontal=True)
        yrs = st.slider("Years of history", 1, 5, 5)
        px_s, px_m = price_history(sym, key), price_history("SPY", key)
        reg_beta, RET = None, None
        if px_s is None or px_m is None:
            st.warning("Price history is not available for this ticker on your FMP plan.")
        else:
            cut = pd.Timestamp(dt.date.today().replace(year=dt.date.today().year - yrs))
            rule = "ME" if freq == "Monthly" else "W-FRI"
            ps = px_s[px_s.index >= cut].resample(rule).last()
            pm = px_m[px_m.index >= cut].resample(rule).last()
            RET = pd.DataFrame({"Stock price": ps, "SPY price": pm}).dropna()
            RET["Stock return"] = RET["Stock price"].pct_change()
            RET["Market return"] = RET["SPY price"].pct_change()
            rr = RET.dropna()
            if len(rr) >= 12:
                cov = np.cov(rr["Stock return"], rr["Market return"], ddof=1)
                reg_beta = cov[0, 1] / cov[1, 1]
                alpha = rr["Stock return"].mean() - reg_beta * rr["Market return"].mean()
                r2 = np.corrcoef(rr["Stock return"], rr["Market return"])[0, 1] ** 2
                k_ = 12 if freq == "Monthly" else 52
                vol_s, vol_m = rr["Stock return"].std() * np.sqrt(k_), rr["Market return"].std() * np.sqrt(k_)
                cc = st.columns(5)
                for c_, (h, v_) in zip(cc, [("Regression beta", f"{reg_beta:.2f}"), ("FMP beta (monthly)", f"{beta:.2f}" if beta else "–"),
                                           ("R²", f"{r2:.2f}"), ("Stock volatility (ann.)", pct(vol_s)),
                                           ("Market volatility (ann.)", pct(vol_m))]):
                    c_.html(card(t(h.upper(), GOLD, 11, 800, "letter-spacing:1px") + "<br>" + t(v_, TXT, 22, 800)))
                a, b = st.columns(2)
                f = fig_base(f"{freq} returns: {sym} vs S&P 500 (SPY)")
                f.add_scatter(x=rr["Market return"] * 100, y=rr["Stock return"] * 100, mode="markers", name="Periods",
                              marker=dict(color=LB, size=8, opacity=.75))
                xs = np.linspace(rr["Market return"].min(), rr["Market return"].max(), 20)
                f.add_scatter(x=xs * 100, y=(alpha + reg_beta * xs) * 100, mode="lines", name=f"Fit: β = {reg_beta:.2f}",
                              line=dict(color=GOLD, width=3))
                f.update_xaxes(title="Market return %", type="linear"); f.update_yaxes(title="Stock return %")
                a.plotly_chart(f, width="stretch")
                f = fig_base("Growth of $100")
                f.update_xaxes(type="date")
                f.add_scatter(x=RET.index, y=RET["Stock price"] / RET["Stock price"].iloc[0] * 100, name=sym, line=dict(color=GOLD, width=3))
                f.add_scatter(x=RET.index, y=RET["SPY price"] / RET["SPY price"].iloc[0] * 100, name="S&P 500 (SPY)", line=dict(color=LB, width=3))
                b.plotly_chart(f, width="stretch")
                st.caption(f"β = Cov(Rs, Rm) ÷ Var(Rm) on {len(rr)} {freq.lower()} returns. In Excel: =SLOPE(stock returns, market returns).")
                # FMP-style betas from the same prices (no extra API calls): monthly returns vs S&P 500, 5 and 3 years
                def mbeta(years):
                    cut_ = pd.Timestamp(dt.date.today().replace(year=dt.date.today().year - years))
                    d_ = pd.DataFrame({"s": px_s[px_s.index >= cut_].resample("ME").last(),
                                       "m": px_m[px_m.index >= cut_].resample("ME").last()}).dropna().pct_change().dropna()
                    if len(d_) < 12:
                        return None, 0, None
                    c_m = np.cov(d_["s"], d_["m"], ddof=1)
                    return c_m[0, 1] / c_m[1, 1], len(d_), (c_m[0, 1], c_m[1, 1])
                b5, n5, cv5 = mbeta(5)
                b3, n3, _ = mbeta(3)
                fmp_txt = f"{beta:.2f}" if beta else "–"
                close = ""
                if beta and b5 is not None and b3 is not None:
                    near = "5-year" if abs(beta - b5) <= abs(beta - b3) else "3-year"
                    close = (f"Here FMP's {fmp_txt} is closer to the {near} figure. Small differences also come from the exact "
                             "month-end dates, the latest partial month, and whether prices are adjusted for dividends.")
                with st.expander("📘 How FMP calculates beta (and why it can differ from the regression above)"):
                    st.html(card(
                        t("FMP's method", GOLD, 16, 800) + "<br>" +
                        t("FMP defines beta as the stock's monthly price change relative to the S&P 500's monthly price change, "
                          "over 5 years (60 months) when available:", TXT, 15) + "<br>" +
                        t("β = Cov(R<sub>stock</sub>, R<sub>S&P 500</sub>) ÷ Var(R<sub>S&P 500</sub>)", TXT, 17, 700,
                          "font-family:Georgia,serif") + "<br><br>" +
                        t("Step by step", GOLD, 15, 800) + "<br>" +
                        t("1. Take month-end prices of the stock and the S&P 500 for the last 60 months.<br>"
                          "2. Monthly return = (this month's price ÷ last month's price) − 1, for both.<br>"
                          "3. Covariance of the two return series, divided by the variance of the market's returns.<br>"
                          "4. This is the slope of the regression line of stock returns on market returns — "
                          "in Excel, =SLOPE(stock returns, market returns), as on the Beta sheet of the download.", TXT, 14) + "<br><br>" +
                        t(f"{sym} worked through with the prices loaded here", GOLD, 15, 800) + "<br>" +
                        (t(f"5 years, {n5} monthly returns: Cov = {cv5[0]:.5f}, Var(S&P 500) = {cv5[1]:.5f} → "
                           f"β = {cv5[0]:.5f} ÷ {cv5[1]:.5f} = <b>{b5:.2f}</b>", TXT, 14) + "<br>" if b5 is not None else "") +
                        (t(f"3 years, {n3} monthly returns: β = <b>{b3:.2f}</b>", TXT, 14) + "<br>" if b3 is not None else "") +
                        t(f"FMP's published beta: <b>{fmp_txt}</b>", TXT, 14) + "<br><br>" +
                        t("Why the numbers can differ", GOLD, 15, 800) + "<br>" +
                        t("• <b>Window</b>: FMP's formula page says 5 years, but its DCF page describes a 3-year monthly beta. "
                          "For some stocks (e.g. Apple) the 3-year and 5-year betas differ a lot. " + close + "<br>"
                          "• <b>Frequency</b>: the regression above can use weekly returns; FMP uses monthly.<br>"
                          "• <b>Market proxy</b>: this app uses SPY (an S&P 500 ETF, with dividends); FMP uses the S&P 500 index. "
                          "The effect is very small.", TXT, 14) + "<br><br>" +
                        t("Which to use? Both are valid market betas against the S&P 500. For teaching and WACC, the regression "
                          "beta is fully transparent and reproducible in Excel. Optional refinement: Blume-adjusted beta "
                          "= 0.67 × raw beta + 0.33 × 1, which pulls betas towards 1.", MUTED, 13)))
            else:
                st.warning("Not enough price history to estimate beta.")

    # ---------------- peers ----------------
    with tabs[4]:
        st.caption("Compare the company with up to 4 US peers on TTM (trailing twelve months) ratios. About 2 API calls per company.")
        PEERS = st.session_state.get("peers") if st.session_state.get("peers_for") == sym else None
        if st.session_state.get("peer_sug_for") != sym:
            st.session_state.peer_sug_for, st.session_state.peer_text = sym, ""
        a, b = st.columns([3, 1])
        if b.button("Suggest US peers (1 call)", key="peer_sug", width="stretch"):
            pl = safe("stock-peers", sym, key)
            if isinstance(pl, dict):
                st.error(pl.get("_error", "Peer list not available."))
            else:
                us = [d["symbol"] for d in (pl or []) if d.get("symbol") and "." not in d["symbol"] and d["symbol"] != sym]
                st.session_state.peer_text = ", ".join(us[:4])
                if not us:
                    st.warning("FMP's peer list for this company has no US-listed names. Type your own peers.")
        peer_text = a.text_input("Peer tickers (US, comma-separated)", key="peer_text",
                                 placeholder="e.g. MSFT, GOOGL, AMZN, META")
        if st.button("Load peer comparison", key="peer_btn"):
            tick = [sym] + [x.strip().upper() for x in peer_text.split(",") if x.strip() and x.strip().upper() != sym][:4]
            if len(tick) == 1:
                st.warning("Add at least one peer ticker, or click Suggest US peers.")
            else:
                rows = []
                for tk in tick:
                    r_ = safe("ratios-ttm", tk, key)
                    r_ = r_[0] if isinstance(r_, list) and r_ else (r_ if isinstance(r_, dict) and "_error" not in r_ else {})
                    nm = p.get("companyName") if tk == sym else ""
                    if tk != sym:
                        pr_ = safe("profile", tk, key)
                        nm = pr_[0].get("companyName", "") if isinstance(pr_, list) and pr_ else ""
                    npm = pick(r_, "netProfitMarginTTM")
                    at_ = pick(r_, "assetTurnoverTTM")
                    lev = pick(r_, "financialLeverageRatioTTM", "equityMultiplierTTM")
                    rows.append({"Ticker": tk, "Company": nm,
                                 "Gross margin": pick(r_, "grossProfitMarginTTM"),
                                 "Operating margin": pick(r_, "operatingProfitMarginTTM"),
                                 "Net margin": npm, "Asset turnover (×)": at_, "Equity multiplier (×)": lev,
                                 "ROE (DuPont)": (npm * at_ * lev) if None not in (npm, at_, lev) else None,
                                 "Current ratio (×)": pick(r_, "currentRatioTTM"),
                                 "Debt ÷ equity (×)": pick(r_, "debtToEquityRatioTTM"),
                                 "P/E (×)": pick(r_, "priceToEarningsRatioTTM", "peRatioTTM"),
                                 "P/B (×)": pick(r_, "priceToBookRatioTTM"),
                                 "EV/EBITDA (×)": pick(r_, "enterpriseValueMultipleTTM"),
                                 "Dividend yield": pick(r_, "dividendYieldTTM")})
                PEERS = pd.DataFrame(rows).set_index("Ticker")
                st.session_state.peers, st.session_state.peers_for = PEERS, sym
        if PEERS is not None:
            view = PEERS.astype(object)
            for c_ in view.columns:
                if c_ == "Company":
                    continue
                view[c_] = [("–" if v_ is None or pd.isna(v_) else (f"{v_:.2f}×" if "(×)" in c_ else f"{v_*100:.1f}%"))
                            for v_ in PEERS[c_]]
            st.dataframe(view, width="stretch")
            st.caption("ROE (DuPont) = net margin × asset turnover × equity multiplier. US-listed tickers only on the free plan. "
                       "Each peer uses 2 calls (ratios + name); results are kept for this session.")
        else:
            st.html(card(t("Type up to 4 US peer tickers or click <b>Suggest US peers</b>, then <b>Load peer comparison</b>.", TXT, 14)))

    # ---------------- cost of capital ----------------
    with tabs[5]:
        st.caption("WACC with CAPM. Risk-free rate, market risk premium and tax rate are in the sidebar.")
        e_val = mcap or 0
        d_val = float(debt.iloc[-1]) if pd.notna(debt.iloc[-1]) else 0.0
        kd_pre = float(intexp.iloc[-1] / d_val) if d_val and pd.notna(intexp.iloc[-1]) and intexp.iloc[-1] > 0 else 0.0
        opts = ["FMP beta"] + (["Regression beta"] if reg_beta is not None else []) + ["Manual"]
        src = st.radio("Beta to use", opts, horizontal=True, index=1 if reg_beta is not None else 0)
        dflt = float(reg_beta) if src == "Regression beta" else float(beta or 1.0)
        b_ = st.number_input("Beta", 0.0, 4.0, round(dflt, 2), 0.01, key=f"beta_{src}", disabled=(src != "Manual"))
        # ---------------- cost of debt: four methods ----------------
        ann_ = 4 if per == "quarter" else 1  # quarterly statements: annualise the latest quarter
        int_last = float(intexp.iloc[-1]) * ann_ if pd.notna(intexp.iloc[-1]) and intexp.iloc[-1] > 0 else None
        d_prev = float(debt.iloc[-2]) if len(debt) > 1 and pd.notna(debt.iloc[-2]) else None
        ebit_last = float(op.iloc[-1]) * ann_ if pd.notna(op.iloc[-1]) else None
        kd_end = int_last / d_val if int_last and d_val else None
        kd_avg = int_last / ((d_val + d_prev) / 2) if int_last and d_val and d_prev else None
        icr = ebit_last / int_last if ebit_last is not None and int_last else None
        # Damodaran, January 2026: interest coverage → synthetic rating → default spread (large non-financial firms)
        RATING_TABLE = [(-1e9, 0.2, "D", 0.19), (0.2, 0.65, "C", 0.16), (0.65, 0.8, "CC", 0.1261), (0.8, 1.25, "CCC", 0.0885),
                        (1.25, 1.5, "B-", 0.0509), (1.5, 1.75, "B", 0.0321), (1.75, 2.0, "B+", 0.0275), (2.0, 2.25, "BB", 0.0184),
                        (2.25, 2.5, "BB+", 0.0138), (2.5, 3.0, "BBB", 0.0111), (3.0, 4.25, "A-", 0.0089), (4.25, 5.5, "A", 0.0078),
                        (5.5, 6.5, "A+", 0.0070), (6.5, 8.5, "AA", 0.0055), (8.5, 1e12, "AAA", 0.0045)]
        syn_rating, syn_spread = None, None
        if icr is not None:
            for lo_, hi_, rt_, sp_ in RATING_TABLE:
                if lo_ < icr <= hi_:
                    syn_rating, syn_spread = rt_, sp_
                    break
        elif ebit_last is not None and ebit_last > 0 and not int_last:
            syn_rating, syn_spread = "AAA", 0.0045  # no interest expense: treat as top-rated
        kd_syn = rf + syn_spread if syn_spread is not None else None
        kd_methods = {"Interest ÷ year-end debt": kd_end, "Interest ÷ average debt": kd_avg,
                      "Synthetic rating (Rf + spread)": kd_syn, "Manual": None}
        kd_avail = [k for k, v in kd_methods.items() if v is not None] + ["Manual"]
        kd_src = st.radio("Cost of debt method", kd_avail, horizontal=True, index=0,
                          help="See 'How Kd is calculated' below for each method worked through.")
        kd_dflt = kd_methods.get(kd_src) or (kd_pre or 0.0)
        kd_in = st.number_input("Pre-tax cost of debt (Kd)", 0.0, 0.3, round(float(kd_dflt), 4), 0.001, format="%.4f",
                                key=f"kd_{kd_src}", disabled=(kd_src != "Manual"))
        with st.expander("📘 How Kd (cost of debt) is calculated"):
            def _m(v):
                return money(v, cur) if v is not None else "–"
            def _p(v):
                return f"{v:.2%}" if v is not None else "–"
            rows_ = [
                ("1. Interest ÷ year-end debt (book method)", "Kd = Interest expense ÷ Total debt",
                 f"{_m(int_last)} ÷ {_m(d_val)} = <b>{_p(kd_end)}</b>" if kd_end is not None else "Not available (no interest or no debt reported).",
                 "The average rate the company actually paid last year. Simple, but historical: it reflects old loans, "
                 "not today's borrowing cost."),
                ("2. Interest ÷ average debt", "Kd = Interest expense ÷ [(Opening debt + Closing debt) ÷ 2]",
                 f"{_m(int_last)} ÷ (({_m(d_prev)} + {_m(d_val)}) ÷ 2) = <b>{_p(kd_avg)}</b>" if kd_avg is not None else "Not available (needs two balance sheets).",
                 "Better matching: interest accrues through the year, so divide by the average debt outstanding, not one day's balance."),
                ("3. Synthetic rating: Kd = Rf + default spread", "Interest coverage = EBIT ÷ Interest expense → rating → spread",
                 (f"Coverage = {_m(ebit_last)} ÷ {_m(int_last)} = {icr:.2f}× → rating <b>{syn_rating}</b> → spread {syn_spread:.2%}; "
                  f"Kd = {rf:.2%} (10-yr Treasury) + {syn_spread:.2%} = <b>{kd_syn:.2%}</b>") if icr is not None and kd_syn is not None else
                 (f"No interest expense: treated as AAA, Kd = {rf:.2%} + 0.45% = <b>{kd_syn:.2%}</b>" if kd_syn is not None else "Not available (EBIT or interest missing)."),
                 "A forward-looking, market-based rate: what a company with this coverage would pay to borrow today. "
                 "This is the method Damodaran uses for unrated companies."),
                ("4. Manual", "Enter your own Kd",
                 "e.g. the yield to maturity on the company's traded bonds, or Rf + the spread for its actual credit rating.",
                 "Best when the company has listed bonds or a published rating."),
            ]
            body_ = ""
            for lab_, frm_, ex_, rd_ in rows_:
                body_ += (f'<div style="border-left:4px solid {GOLD};padding:10px 14px;margin:0 0 12px;background:rgba(0,51,102,.35);border-radius:6px">'
                          + t(lab_, GOLD, 15, 800) + "<br>" + t(frm_, TXT, 16, 700, "font-family:Georgia,serif") + "<br>"
                          + t(ex_, LB, 14) + "<br>" + t(rd_, TXT, 14) + "</div>")
            body_ += (t("After-tax cost of debt", GOLD, 15, 800) + "<br>" +
                      t(f"Kd × (1 − t) = {kd_in:.2%} × (1 − {tax:.2%}) = <b>{kd_in * (1 - tax):.2%}</b>. "
                        "Interest is tax-deductible, so each rupee/dollar of interest costs the company only (1 − t).", TXT, 14) + "<br><br>")
            tbl_ = "".join(
                f'<tr style="background:{"#004d80" if rt_ == syn_rating else "transparent"}">'
                f'<td style="padding:3px 10px">{t(("> " + format(lo_, ".2f")) if lo_ > -1e8 else "≤ 0.20", TXT, 13)}</td>'
                f'<td style="padding:3px 10px">{t(format(hi_, ".2f") if hi_ < 1e11 else "and above", TXT, 13)}</td>'
                f'<td style="padding:3px 10px">{t(rt_, GOLD if rt_ == syn_rating else TXT, 13, 700)}</td>'
                f'<td style="padding:3px 10px">{t(format(sp_, ".2%"), TXT, 13)}</td></tr>'
                for lo_, hi_, rt_, sp_ in reversed(RATING_TABLE))
            body_ += (t("Coverage → rating → spread table", GOLD, 15, 800) + "<br>" +
                      f'<table style="border-collapse:collapse;margin:6px 0 10px"><tr>'
                      f'<th style="padding:3px 10px;text-align:left">{t("Coverage >", LB, 13, 700)}</th>'
                      f'<th style="padding:3px 10px;text-align:left">{t("up to", LB, 13, 700)}</th>'
                      f'<th style="padding:3px 10px;text-align:left">{t("Rating", LB, 13, 700)}</th>'
                      f'<th style="padding:3px 10px;text-align:left">{t("Spread", LB, 13, 700)}</th></tr>{tbl_}</table>' +
                      t("Spreads are Damodaran's January 2026 table for large US non-financial firms (from traded US corporate bonds).", MUTED, 12) + "<br>" +
                      t("Cautions: banks and NBFCs (interest is an operating cost) and near debt-free companies give meaningless "
                        "book-method Kd; quarterly figures are annualised (× 4). Source: Damodaran, 'Ratings, Interest Coverage "
                        "Ratios and Default Spread', January 2026.", MUTED, 12))
            st.html(card(body_))
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
        st.caption("Teaching estimate: book debt from the latest balance sheet; cost of debt from reported interest.")

    # ---------------- DCF ----------------
    with tabs[6]:
        st.caption("A simple 5-year free cash flow DCF, discounted at the WACC from the previous tab, next to FMP's own DCF value.")
        Ia, fcf_d = I, fcf
        if per == "quarter":  # DCF always runs on annual figures (2 extra cached calls)
            try:
                Ia = frame_annual(fmp("income-statement", sym, key, "annual", 5))
                Ca = frame_annual(fmp("cash-flow-statement", sym, key, "annual", 5))
                o_, c_x = col(Ca, "operatingCashFlow"), col(Ca, "capitalExpenditure")
                fcf_d = col(Ca, "freeCashFlow"); fcf_d = fcf_d.where(fcf_d.notna(), o_ + c_x)
                st.caption("Quarterly view selected: the DCF uses the last 5 annual cash flow statements.")
            except FMPError as e:
                st.warning(f"Annual statements needed for the DCF could not be loaded: {e}")
        shares = col(Ia, "weightedAverageShsOutDil").iloc[-1] if "weightedAverageShsOutDil" in Ia else None
        if (shares is None or pd.isna(shares)) and mcap and price:
            shares = mcap / price
        f0 = float(fcf_d.iloc[-1]) if pd.notna(fcf_d.iloc[-1]) else 0.0
        fv = fcf_d.dropna()
        cagr = (fv.iloc[-1] / fv.iloc[0]) ** (1 / (len(fv) - 1)) - 1 if len(fv) > 1 and fv.iloc[0] > 0 and fv.iloc[-1] > 0 else 0.05
        a, b, c3 = st.columns(3)
        g = a.number_input("FCF growth, years 1–5", -0.2, 0.4, float(round(min(max(cagr, 0.0), 0.15), 3)), 0.005, format="%.3f",
                           help="Default: historical FCF growth, capped between 0% and 15%.")
        gt = b.number_input("Terminal growth", 0.0, 0.05, 0.025, 0.0025, format="%.4f")
        r_d = c3.number_input("Discount rate (WACC)", 0.03, 0.25, float(round(wacc, 4)), 0.0025, format="%.4f")
        yrs_ = list(range(1, 6))
        proj = [f0 * (1 + g) ** n for n in yrs_]
        pv = [cf / (1 + r_d) ** n for cf, n in zip(proj, yrs_)]
        tv = proj[-1] * (1 + gt) / (r_d - gt) if r_d > gt else float("nan")
        pv_tv = tv / (1 + r_d) ** 5
        ev = sum(pv) + pv_tv
        cash0 = float(cash.iloc[-1]) if pd.notna(cash.iloc[-1]) else 0.0
        eq = ev - d_val + cash0
        ps_ = eq / shares if shares else float("nan")
        dcf_f = safe("discounted-cash-flow", sym, key)
        dcf_fmp = pick(dcf_f[0] if isinstance(dcf_f, list) and dcf_f else {}, "dcf")
        tbl = pd.DataFrame({"Year": [f"Year {n}" for n in yrs_], "FCF": proj, "Discount factor": [1 / (1 + r_d) ** n for n in yrs_], "PV of FCF": pv})
        show = tbl.copy()
        show["FCF"] = show["FCF"].map(lambda x: money(x, cur)); show["PV of FCF"] = show["PV of FCF"].map(lambda x: money(x, cur))
        show["Discount factor"] = show["Discount factor"].map(lambda x: f"{x:.4f}")
        st.dataframe(show.set_index("Year"), width="stretch")
        up = ps_ / price - 1 if price and pd.notna(ps_) else None
        lines = [("Latest FCF (base)", money(f0, cur)), ("PV of 5 years' FCF", money(sum(pv), cur)),
                 ("Terminal value = FCF₅ × (1 + g) ÷ (WACC − g)", money(tv, cur)), ("PV of terminal value", money(pv_tv, cur)),
                 ("Enterprise value", money(ev, cur)), ("− Debt + cash  →  equity value", money(eq, cur)),
                 ("Value per share (÷ diluted shares)", f"{cur}{ps_:,.2f}" if pd.notna(ps_) else "–"),
                 ("Market price", f"{cur}{price:,.2f}" if price else "–"),
                 ("FMP's DCF value per share", f"{cur}{dcf_fmp:,.2f}" if dcf_fmp else "not on your plan")]
        a, b = st.columns([3, 2])
        a.html(card("<br>".join(t(h, LB, 14, 600) + "&nbsp;&nbsp;" + t(v_, GOLD if "per share" in h.lower() else TXT, 15, 800)
                                for h, v_ in lines)))
        if up is not None:
            b.html(card(t("MODEL VALUE vs PRICE", GOLD, 12, 800, "letter-spacing:1px") + "<br>" +
                        t(f"{up:+.1%}", GRN if up >= 0 else RED, 40, 800) + "<br>" +
                        t("Positive = model value above market price. A teaching model, not a recommendation.", MUTED, 13),
                        border=GOLD))

    with tabs[7]:
        a, b = st.columns([2, 1])
        a.html(card(t("About the company", GOLD, 15, 700) + "<br>" + t(p.get("description", "–"), TXT, 14, extra="line-height:1.55")))
        facts = [("CEO", p.get("ceo")), ("Employees", p.get("fullTimeEmployees")), ("Country", p.get("country")),
                 ("IPO date", p.get("ipoDate")), ("Website", p.get("website")), ("52-week range", p.get("range"))]
        b.html(card("<br>".join(t(k + ": ", GOLD, 13, 700) + t(str(v_ or "–"), TXT, 13) for k, v_ in facts)))

    # ---------------- formatted Excel ----------------
    with tabs[8]:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter as CL

        NAVY_, GOLD_, LBF, YEL = "003366", "C9A227", "EAF3F8", "FFF2CC"
        thin = Side(style="thin", color="B7C4D6"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
        F = lambda **k: Font(name="Arial", size=k.pop("size", 11), **k)
        NUM, PCT, X2, PS = '#,##0.0;(#,##0.0);"–"', '0.0%;-0.0%;"–"', '0.00"×"', '#,##0.00'
        wb = Workbook(); wb.remove(wb.active)

        def sheet(name, title, widths):
            ws = wb.create_sheet(name); ws.sheet_view.showGridLines = False
            ws.column_dimensions["A"].width = widths[0]
            for i_, w_ in enumerate(widths[1:], start=2):
                ws.column_dimensions[CL(i_)].width = w_
            ws["A1"] = title; ws["A1"].font = F(size=15, bold=True, color="FFFFFF")
            ws["A2"] = f"{p.get('companyName', sym)} ({sym}) · Source: Financial Modeling Prep · {SITE}"
            ws["A2"].font = F(size=9, italic=True, color="5A6B85")
            for c_ in range(1, len(widths) + 1):
                ws.cell(1, c_).fill = PatternFill("solid", fgColor=NAVY_)
                ws.cell(3, c_).fill = PatternFill("solid", fgColor=GOLD_)
            ws.row_dimensions[3].height = 4
            return ws

        def header(ws, r, labels):
            for j, lab in enumerate(labels, start=1):
                c_ = ws.cell(r, j, lab); c_.font = F(bold=True, color="FFFFFF"); c_.fill = PatternFill("solid", fgColor=NAVY_)
                c_.alignment = Alignment(horizontal="left" if j == 1 else "center", vertical="center", wrap_text=True); c_.border = BOX

        def put(ws, r, c_, v_, fmt=None, bold=False, inp=False, fill=None):
            cell = ws.cell(r, c_, v_)
            cell.font = F(bold=bold, color="0000FF" if inp else "000000"); cell.border = BOX
            if fmt: cell.number_format = fmt
            if inp: cell.fill = PatternFill("solid", fgColor=LBF)
            if fill: cell.fill = PatternFill("solid", fgColor=fill)
            return cell

        years = list(I.index); ny = len(years)
        ROWPOS = {}
        for name, df in ST.items():
            ws = sheet(name, f"{name} ({cur.strip()} millions; EPS in {cur.strip()})", [34] + [14] * ny)
            header(ws, 5, ["Line item"] + years)
            for i_, (lab, vals) in enumerate(df.iterrows()):
                r = 6 + i_; ROWPOS[(name, lab)] = r
                put(ws, r, 1, lab, bold=lab in ("Revenue", "Net income", "Total assets", "Free cash flow", "Operating cash flow"))
                for j, yv in enumerate(years):
                    v_ = vals.get(yv)
                    v_ = None if v_ is None or pd.isna(v_) else (float(v_) if "EPS" in lab else float(v_) / 1e6)
                    put(ws, r, 2 + j, v_, PS if "EPS" in lab else NUM)
            ws.freeze_panes = "B6"

        # ratios with live formulas
        ws = sheet("Ratios", "Ratios (live formulas on the statement sheets)", [34] + [14] * ny + [52])
        header(ws, 5, ["Ratio"] + years + ["Formula"])
        IS_, BS_, CF_ = "'Income statement'!", "'Balance sheet'!", "'Cash flow'!"
        def ref(sh, lab, col_):
            return f"{sh}{col_}{ROWPOS[(dict(zip([IS_, BS_, CF_], ST))[sh], lab)]}"
        ratio_defs = [("Revenue growth", PCT, lambda c_, p_: f"={ref(IS_, 'Revenue', c_)}/{ref(IS_, 'Revenue', p_)}-1" if p_ else None, "Revenue ÷ previous revenue − 1"),
                      ("Gross margin", PCT, lambda c_, p_: f"={ref(IS_, 'Gross profit', c_)}/{ref(IS_, 'Revenue', c_)}", "Gross profit ÷ revenue"),
                      ("Operating margin", PCT, lambda c_, p_: f"={ref(IS_, 'Operating income', c_)}/{ref(IS_, 'Revenue', c_)}", "Operating income ÷ revenue"),
                      ("Net margin", PCT, lambda c_, p_: f"={ref(IS_, 'Net income', c_)}/{ref(IS_, 'Revenue', c_)}", "Net income ÷ revenue"),
                      ("ROE", PCT, lambda c_, p_: f"={ref(IS_, 'Net income', c_)}/{ref(BS_, chr(39).join(['Shareholders', ' equity']), c_)}", "Net income ÷ shareholders' equity"),
                      ("ROA", PCT, lambda c_, p_: f"={ref(IS_, 'Net income', c_)}/{ref(BS_, 'Total assets', c_)}", "Net income ÷ total assets"),
                      ("Asset turnover", X2, lambda c_, p_: f"={ref(IS_, 'Revenue', c_)}/{ref(BS_, 'Total assets', c_)}", "Revenue ÷ total assets"),
                      ("Current ratio", X2, lambda c_, p_: f"={ref(BS_, 'Total current assets', c_)}/{ref(BS_, 'Total current liabilities', c_)}", "Current assets ÷ current liabilities"),
                      ("Debt ÷ equity", X2, lambda c_, p_: f"={ref(BS_, 'Total debt', c_)}/{ref(BS_, chr(39).join(['Shareholders', ' equity']), c_)}", "Total debt ÷ equity"),
                      ("Interest cover", X2, lambda c_, p_: f"=IFERROR({ref(IS_, 'Operating income', c_)}/{ref(IS_, 'Interest expense', c_)},\"–\")", "Operating income ÷ interest expense"),
                      ("FCF margin", PCT, lambda c_, p_: f"={ref(CF_, 'Free cash flow', c_)}/{ref(IS_, 'Revenue', c_)}", "Free cash flow ÷ revenue"),
                      ("Cash conversion", X2, lambda c_, p_: f"={ref(CF_, 'Operating cash flow', c_)}/{ref(IS_, 'Net income', c_)}", "Operating cash flow ÷ net income")]
        for i_, (lab, fmt, fn, txt) in enumerate(ratio_defs):
            r = 6 + i_; put(ws, r, 1, lab, bold=True)
            for j in range(ny):
                c_, p_ = CL(2 + j), (CL(1 + j) if j else None)
                fx = fn(c_, p_)
                put(ws, r, 2 + j, ("=IFERROR(" + fx[1:] + ",\"–\")") if fx and not fx.startswith("=IFERROR") else fx, fmt)
            put(ws, r, 2 + ny, txt).font = F(italic=True, color="5A6B85")
        ws.freeze_panes = "B6"

        # WACC with formulas
        ws = sheet("WACC", "Cost of capital (CAPM and WACC): change the blue inputs", [44, 18, 50])
        header(ws, 5, ["Item", "Value", "Formula / source"])
        rows_w = [("Risk-free rate (10-yr Treasury)", rf, PCT, True, "Input (sidebar / FMP Treasury)"),
                  ("Beta", b_, PS, True, f"Input ({src})"), ("Market risk premium", mrp, PCT, True, "Input"),
                  ("Cost of equity Ke", "=B6+B7*B8", '0.00%', False, "Rf + β × MRP"),
                  ("Pre-tax cost of debt Kd", kd_in, '0.00%', True, f"Input ({kd_src})"),
                  ("Tax rate", tax, PCT, True, "Input"), ("After-tax cost of debt", "=B10*(1-B11)", '0.00%', False, "Kd × (1 − t)"),
                  (f"Equity value E ({cur.strip()} m, market cap)", (e_val or 0) / 1e6, NUM, True, "Market capitalisation"),
                  (f"Debt D ({cur.strip()} m, book)", d_val / 1e6, NUM, True, "Total debt, latest balance sheet"),
                  ("E / V", "=B13/(B13+B14)", PCT, False, "E ÷ (E + D)"), ("D / V", "=B14/(B13+B14)", PCT, False, "D ÷ (E + D)"),
                  ("WACC", "=B15*B9+B16*B12", '0.00%', False, "E/V × Ke + D/V × Kd(1 − t)")]
        for i_, (lab, v_, fmt, inp, txt) in enumerate(rows_w):
            r = 6 + i_; put(ws, r, 1, lab, bold=(lab == "WACC"))
            put(ws, r, 2, v_, fmt, bold=(lab == "WACC"), inp=inp, fill=YEL if lab == "WACC" else None)
            put(ws, r, 3, txt).font = F(italic=True, color="5A6B85")

        # DCF with formulas
        ws = sheet("DCF", "Simple 5-year FCF DCF: change the blue inputs", [40, 16, 16, 16, 16, 16])
        header(ws, 5, ["Input", "Value", "", "", "", ""])
        ins = [(f"Base FCF ({cur.strip()} m, latest year)", f0 / 1e6, NUM), ("FCF growth, years 1–5", g, PCT),
               ("Terminal growth", gt, PCT), ("Discount rate (WACC)", "=WACC!B17", '0.00%'),
               (f"Debt ({cur.strip()} m)", d_val / 1e6, NUM), (f"Cash ({cur.strip()} m)", cash0 / 1e6, NUM),
               ("Diluted shares (m)", (shares or 0) / 1e6, NUM), (f"Market price ({cur.strip()})", price or 0, PS)]
        for i_, (lab, v_, fmt) in enumerate(ins):
            put(ws, 6 + i_, 1, lab); put(ws, 6 + i_, 2, v_, fmt, inp=not str(v_).startswith("="))
        header(ws, 15, ["Projection", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5"])
        put(ws, 16, 1, "Year number"); put(ws, 17, 1, "FCF"); put(ws, 18, 1, "Discount factor"); put(ws, 19, 1, "PV of FCF")
        for j in range(5):
            c_ = CL(2 + j)
            put(ws, 16, 2 + j, j + 1)
            put(ws, 17, 2 + j, f"=$B$6*(1+$B$7)^{c_}16", NUM)
            put(ws, 18, 2 + j, f"=1/(1+$B$9)^{c_}16", '0.0000')
            put(ws, 19, 2 + j, f"={c_}17*{c_}18", NUM)
        outs = [("PV of 5 years' FCF", "=SUM(B19:F19)", NUM), ("Terminal value", "=F17*(1+B8)/(B9-B8)", NUM),
                ("PV of terminal value", "=B22*F18", NUM), ("Enterprise value", "=B21+B23", NUM),
                ("Equity value = EV − debt + cash", "=B24-B10+B11", NUM), (f"Value per share ({cur.strip()})", "=B25/B12", PS),
                ("Upside vs market price", "=B26/B13-1", PCT)]
        for i_, (lab, fx, fmt) in enumerate(outs):
            r = 21 + i_; put(ws, r, 1, lab, bold=r in (26, 27)); put(ws, r, 2, fx, fmt, bold=r in (26, 27), fill=YEL if r == 26 else None)
        if dcf_fmp:
            put(ws, 29, 1, f"FMP's DCF value per share ({cur.strip()})"); put(ws, 29, 2, float(dcf_fmp), PS)

        # beta sheet
        if RET is not None and len(RET.dropna()) >= 12:
            ws = sheet("Beta", f"Beta by regression ({freq.lower()} returns vs SPY)", [14, 14, 14, 15, 15, 4, 30, 14])
            header(ws, 5, ["Date", f"{sym} price", "SPY price", f"{sym} return", "SPY return"])
            for i_, (d_, row) in enumerate(RET.iterrows()):
                r = 6 + i_
                put(ws, r, 1, d_.date(), "yyyy-mm-dd"); put(ws, r, 2, float(row["Stock price"]), PS); put(ws, r, 3, float(row["SPY price"]), PS)
                if i_:
                    put(ws, r, 4, f"=B{r}/B{r-1}-1", '0.00%'); put(ws, r, 5, f"=C{r}/C{r-1}-1", '0.00%')
            last = 5 + len(RET)
            for k_, (lab, fx, fmt) in enumerate([("Beta = SLOPE", f"=SLOPE(D7:D{last},E7:E{last})", '0.00'),
                                                ("R² = RSQ", f"=RSQ(D7:D{last},E7:E{last})", '0.00'),
                                                ("Correlation", f"=CORREL(D7:D{last},E7:E{last})", '0.00')]):
                put(ws, 6 + k_, 7, lab, bold=True); put(ws, 6 + k_, 8, fx, fmt, bold=True, fill=YEL if k_ == 0 else None)
            ws.freeze_panes = "A6"

        if PEERS is not None:
            ws = sheet("Peers", "Peer comparison (TTM ratios)", [10, 30] + [13] * (len(PEERS.columns) - 1))
            header(ws, 5, ["Ticker"] + list(PEERS.columns))
            for i_, (tk, row) in enumerate(PEERS.iterrows()):
                r = 6 + i_; put(ws, r, 1, tk, bold=True, fill=YEL if tk == sym else None)
                for j, c_ in enumerate(PEERS.columns):
                    v_ = row[c_]
                    put(ws, r, 2 + j, None if v_ is None or (not isinstance(v_, str) and pd.isna(v_)) else v_,
                        None if c_ == "Company" else (X2 if "(×)" in c_ else PCT))

        # summary first
        ws = sheet("Summary", f"{p.get('companyName', sym)}: summary", [36, 22, 40])
        header(ws, 5, ["Item", "Value", "Note"])
        summ = [("Ticker / exchange", f"{sym} · {p.get('exchange', '')}", None, ""), ("Sector / industry", f"{p.get('sector', '')} / {p.get('industry', '')}", None, ""),
                (f"Price ({cur.strip()})", price, PS, "FMP quote"), (f"Market cap ({cur.strip()} m)", (mcap or 0) / 1e6, NUM, ""),
                ("Beta (FMP)", beta, '0.00', ""), ("Beta (regression)", reg_beta, '0.00', "See Beta sheet" if reg_beta is not None else "n/a"),
                ("WACC", "=WACC!B17", '0.00%', "See WACC sheet"), (f"DCF value per share ({cur.strip()})", "=DCF!B26", PS, "See DCF sheet"),
                ("Statements", f"{per}, {ny} periods", None, f"{years[0]} to {years[-1]}"),
                ("Downloaded", dt.date.today().isoformat(), None, "Blue = input, black = formula"),
                ("Built with", SITE, None, "Education only, not investment advice")]
        for i_, (lab, v_, fmt, note) in enumerate(summ):
            r = 6 + i_; put(ws, r, 1, lab, bold=True); put(ws, r, 2, v_, fmt); put(ws, r, 3, note).font = F(italic=True, color="5A6B85")
        wb.move_sheet("Summary", offset=-(len(wb.sheetnames) - 1))

        raw = wb.create_sheet("Raw data")
        r0 = 1
        for name_, df_ in (("Income statement (raw)", I), ("Balance sheet (raw)", B), ("Cash flow (raw)", C)):
            raw.cell(r0, 1, name_).font = F(bold=True, color="003366", size=12)
            tdf = df_.T
            raw.cell(r0 + 1, 1, "Field").font = F(bold=True)
            for j, cn in enumerate(tdf.columns, start=2):
                raw.cell(r0 + 1, j, str(cn)).font = F(bold=True)
            for i_, (idx, row) in enumerate(tdf.iterrows(), start=r0 + 2):
                raw.cell(i_, 1, str(idx))
                for j, v_ in enumerate(row, start=2):
                    raw.cell(i_, j, v_ if isinstance(v_, (int, float, str)) and not (isinstance(v_, float) and pd.isna(v_)) else None)
            r0 = i_ + 3
        raw.column_dimensions["A"].width = 38
        buf = io.BytesIO(); wb.save(buf)
        if os.environ.get("MPA_SAVE_XLSX"):
            open(os.environ["MPA_SAVE_XLSX"], "wb").write(buf.getvalue())
        st.download_button(f"Download {sym} financials (formatted Excel)", buf.getvalue(), f"{sym}_financials_{per}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        st.html(card(t("What's in the workbook", GOLD, 15, 700) + "<br>" + t(
            "Summary · Income statement · Balance sheet · Cash flow ($ millions) · Ratios (live formulas linked to the statements) · "
            "WACC (live CAPM and WACC formulas) · DCF (live 5-year model) · Beta (returns with SLOPE and RSQ) · Peers (if loaded) · Raw data. "
            "Blue cells are inputs; change them and the model updates.", TXT, 14)))

if key:
    n_ = calls_today(key)
    usage_box.html(card(t("API CALLS TODAY", GOLD, 11, 800, "letter-spacing:1px") + "<br>" + t(f"{n_} of 250", TXT, 20, 800) +
                        "<br>" + t("Counted by this app for your key (free plan limit 250/day).", MUTED, 12)))

# ---------------- footer ----------------
st.html(f"""<div style="margin-top:28px;padding:16px 10px;border-top:2px solid {GOLD};text-align:center;user-select:none;-webkit-user-select:none">
{t("The Mountain Path Academy · Prof. V. Ravichandran", TXT, 14, 700)}<br>
<a href="{SITE}" target="_blank" style="color:{GOLD};-webkit-text-fill-color:{GOLD};text-decoration:none;font-weight:700">{SITE}</a>
{t(" · ", MUTED)}<a href="https://www.linkedin.com/in/trichyravis" target="_blank" style="color:{GOLD};-webkit-text-fill-color:{GOLD};text-decoration:none;font-weight:700">LinkedIn</a>
{t(" · ", MUTED)}<a href="https://github.com/trichyravis" target="_blank" style="color:{GOLD};-webkit-text-fill-color:{GOLD};text-decoration:none;font-weight:700">GitHub</a><br>
{t("Data: Financial Modeling Prep. Education only — not investment advice.", MUTED, 12)}</div>""")
