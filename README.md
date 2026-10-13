# indmoney-exporter

A robust, privacy-first Python CLI tool to exhaustively extract your complete portfolio, assets, and liabilities from [INDmoney](https://www.indmoney.com) and export them into timestamped, human- and machine-readable Markdown reports.

---

## ✨ Features

- **100% Unabridged & Zero-Truncation:** Unlike standard UI exports or basic scripts, every single holding across every asset class is captured without omission or row limits.
- **Dynamic Asset Discovery:** Automatically discovers all existing and future asset classes linked in INDmoney, including:
  - 🏦 **Bank Accounts:** Real-time balances and linked accounts via Account Aggregator.
  - 🛡️ **EPFO / Retirement:** Total PF corpus, employee share, employer share, pension share, and individual employer member passbooks.
  - 🏢 **ESOPs & RSUs:** Corporate stock grants with vested vs. unvested valuations.
  - 📈 **Mutual Funds:** Complete list of all active mutual fund schemes with category, sub-category, invested value, current valuation, absolute gains, return %, XIRR, and Morningstar/IND ratings.
  - 🇮🇳 **Indian Direct Stocks & ETFs:** Complete stock portfolio across all tracked brokers (Zerodha, ICICI Direct, Groww, Upstox, etc.) with values and direct stock URLs.
  - 🇺🇸 **US Stocks & ETFs:** Holdings via DriveWealth / INDmoney Global with shares count, buy average price, live market price, invested USD, current USD, day return, overall PnL, and withdrawable cash balance.
  - 🥇 **Gold & Fixed Income:** Sovereign Gold Bonds (SGB), Bharat Bond ETFs, and debt instruments.
  - 💳 **Liabilities & Credit Cards:** Outstanding credit card balances, due dates, and tracked cards.
  - 🛡️ **Insurance:** Tracked life and motor policies along with pre-approved coverage offers.
  - ⚡ **Credit Lines:** Pre-approved credit limits (Insta Cash).
- **Dual Human & Machine Format:**
  - **YAML Frontmatter** at the top for quick programmatic parsing of net worth, liabilities, and category summaries.
  - **Clean Markdown Tables** for readable, presentation-grade documentation.
  - **Raw Normalized JSON Block** at the bottom of the Markdown file for downstream data pipelines or automated financial analysis.
- **Privacy & Security First:**
  - Zero telemetry or external tracking. Runs 100% locally on your machine.
  - No hardcoded personal identifiable information (PII) or secrets.
  - Pre-configured `.gitignore` ensures your token and personal portfolio dumps are never committed to version control.

---

## 🚀 Quick Start

### Prerequisites

- [uv](https://astral.sh/uv) (recommended for instant execution with no virtualenv setup) or Python 3.10+

To install `uv` on macOS/Linux:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
*(Or via Homebrew: `brew install uv`)*

---

### 🔑 Getting Your INDmoney Bearer Token

1. Open Chrome and go to [https://www.indmoney.com/dashboard](https://www.indmoney.com/dashboard).
2. Log in with your mobile number / OTP.
3. Open Developer Tools (`F12` or `Cmd + Option + I` on macOS) and navigate to the **Network** tab.
4. Filter by `dashboard` or `octopus`.
5. Click on any request (e.g. `dashboard` or `assets`) and go to the **Headers** tab.
6. Look under **Request Headers** for `Authorization: Bearer <TOKEN>` (a string starting with `eyJ...`).
7. Copy the token.

---

### 📦 Running the Exporter

#### Option 1: Passing the token via CLI flag (Easiest)
```bash
uv run export_portfolio.py --token "eyJhbGciOi..."
```

#### Option 2: Using an Environment Variable
```bash
export INDMONEY_TOKEN="eyJhbGciOi..."
uv run export_portfolio.py
```

#### Option 3: Interactive Prompt (Secure)
If you run without arguments, the script will prompt you securely (hidden input):
```bash
chmod +x export_portfolio.py
./export_portfolio.py
```

#### Option 4: Pointing to a Token File
```bash
uv run export_portfolio.py --token-file /path/to/token.txt
```

---

## 🛠️ Command-Line Options

| Flag | Description | Default |
| :--- | :--- | :--- |
| `--token` | INDmoney Bearer JWT token string | None |
| `--token-file` | Path to a text file containing the token or curl command | None |
| `--output-dir` | Directory where the Markdown file will be saved | `.` (Current directory) |
| `--output-file` | Custom output filename | `indmoney_portfolio_YYYY-MM-DD_HHMMSS.md` |
| `-q`, `--quiet` | Suppress non-error console output | `False` |

---

## 📄 Output File Structure

Each generated Markdown report has three structured layers:

1. **YAML Frontmatter:**
   ```yaml
   ---
   title: INDmoney Comprehensive Assets & Liabilities Report
   exported_at: '2026-10-13 21:30:00'
   iso_timestamp: '2026-10-13T21:30:00.123456'
   total_networth_inr: 118996496.0
   total_liabilities_inr: 463.0
   net_asset_value_inr: 118996033.0
   category_totals_inr:
     ESOPs & RSUs: 31000000.0
     Bank Accounts / Liquid: 30592772.0
     Indian Direct Stocks & ETFs: 16179757.0
     Mutual Funds: 22753673.0
     EPF / Retirement: 14343512.0
     US Stocks & ETFs: 2690000.0
   ---
   ```
2. **Formatted Markdown Tables:** Clean breakdown of all holdings, banks, EPFO accounts, ESOPs, US stocks, mutual funds, gold, and liabilities.
3. **Raw Normalized JSON Codeblock:** Embedded at the end of the file containing the complete dataset with full precision.

---

## 🔒 Security & Privacy

- This tool does not store or transmit your token anywhere other than directly to the official `*.indmoney.com` endpoints.
- Ensure you never share or commit your generated Markdown report or Bearer token to public repositories.

---

## 📜 License

MIT License. Open-source and free to use.
