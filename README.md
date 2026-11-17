# US Company Financials Explorer

A Streamlit app from The Mountain Path Academy (https://themountainpathacademy.com).
It pulls statements for any US-listed company from Financial Modeling Prep (FMP), using your own API key.

## What it shows
- Price, market cap, beta, latest revenue and net income
- Trends: revenue, net income, margins, cash flow, ROE, ROA, debt/equity
- Ratios table with the formulas used
- Income statement, balance sheet and cash flow (millions or billions)
- Cost of capital: CAPM cost of equity and WACC, with editable inputs
- Excel download of statements, ratios and every raw field

## Run it on your computer
1. `pip install -r requirements.txt`
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste your FMP key into it
   (or leave it out and type the key in the sidebar each time)
3. `streamlit run app.py`

## Deploy on Streamlit Community Cloud
Push the folder to GitHub (secrets.toml is excluded by .gitignore). In the app settings, open
Secrets and add: `FMP_API_KEY = "your-key"`.

## Free-plan limits
250 calls per day; US stocks; about 5 years of annual statements. Each new ticker uses 5 calls,
and results are cached for 24 hours, so about 50 companies a day.
