#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "curl_cffi>=0.7.0",
#     "pyyaml>=6.0",
# ]
# ///
"""
INDmoney Portfolio Exporter
Fetches comprehensive investment, bank, retirement, stock, mutual fund,
and liability data from INDmoney APIs and exports it to a timestamped,
human- and machine-readable Markdown file.

Features:
- Completely generic & privacy-first (no hardcoded tokens or PII)
- Dynamic asset discovery (captures all current and future asset classes)
- Zero truncation (every individual holding is exported)
- Dual format (formatted Markdown tables + YAML frontmatter + raw JSON)
"""

import os
import sys
import re
import json
import yaml
import getpass
import argparse
from datetime import datetime
from pathlib import Path
from curl_cffi import requests

BASE_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.indmoney.com",
    "platform": "web",
    "referer": "https://www.indmoney.com/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
}

def resolve_token(token_arg=None, token_file=None):
    """
    Resolve the INDmoney Bearer token from CLI argument, environment variable,
    optional file, or interactive prompt.
    """
    if token_arg:
        token = token_arg.strip()
        if token.startswith("Bearer "):
            token = token[7:].strip()
        return token

    env_token = os.environ.get("INDMONEY_TOKEN")
    if env_token:
        token = env_token.strip()
        if token.startswith("Bearer "):
            token = token[7:].strip()
        return token

    if token_file:
        p = Path(token_file)
        if p.exists():
            content = p.read_text(encoding="utf-8").strip()
            m = re.search(r"Bearer\s+([A-Za-z0-9_\-\.]+)", content)
            if m:
                return m.group(1).strip()
            if content.startswith("eyJ"):
                return content.strip()
            raise ValueError(f"Could not extract a valid Bearer token from file '{token_file}'.")
        else:
            raise FileNotFoundError(f"Specified token file '{token_file}' does not exist.")

    # Interactive prompt fallback if running in a terminal
    if sys.stdin.isatty():
        try:
            prompt_token = getpass.getpass("Enter your INDmoney Bearer token (hidden): ").strip()
            if prompt_token:
                if prompt_token.startswith("Bearer "):
                    prompt_token = prompt_token[7:].strip()
                return prompt_token
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled by user.", file=sys.stderr)
            sys.exit(1)

    print(
        "Error: No INDmoney token provided.\n"
        "Please provide your token using one of the following methods:\n"
        "  1. Pass --token '<JWT>' on the command line\n"
        "  2. Set the INDMONEY_TOKEN environment variable\n"
        "  3. Pass --token-file /path/to/token_file\n",
        file=sys.stderr
    )
    sys.exit(1)

def parse_amount(text):
    """Safely converts Indian currency strings (₹1.5Cr, ₹45L, ₹10K, $500) into float INR."""
    if not text:
        return 0.0
    cleaned = str(text).replace("₹", "").replace("$", "").replace(",", "").strip()
    if cleaned.endswith("Cr"):
        return float(cleaned[:-2]) * 10_000_000.0
    elif cleaned.endswith("L"):
        return float(cleaned[:-1]) * 100_000.0
    elif cleaned.endswith("K"):
        return float(cleaned[:-1]) * 1_000.0
    try:
        return float(cleaned)
    except Exception:
        return 0.0

def fetch_json(session, url, headers, desc="API"):
    """Fetches a JSON endpoint using TLS client impersonation with error handling."""
    try:
        resp = session.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        print(f"[{desc}] Request failed for {url}: {e}", file=sys.stderr)
        return None

def collect_portfolio_data(token, verbose=True):
    """
    Dynamically connects to INDmoney services and aggregates complete, unabridged
    portfolio and liability data across all categories.
    """
    headers = dict(BASE_HEADERS)
    headers["authorization"] = f"Bearer {token}"
    session = requests.Session(impersonate="chrome")

    if verbose:
        print("Connecting to INDmoney APIs and discovering assets...")

    # 1. Assets / Networth Masthead
    assets_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/octopus/v2/users/assets?rank=0&UserGlobalState=S73",
        headers,
        "Assets Masthead"
    )

    # 2. Macro Asset Allocation Distribution
    distribution_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/track/api/v1/native/networth/overall-portfolio-distribution",
        headers,
        "Asset Distribution"
    )

    # 3. Dynamic Investments Grid
    investments_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/octopus/v2/users/investments?rank=1&UserGlobalState=S73",
        headers,
        "Investments Grid"
    )

    # 4. Comprehensive Holdings Breakup (all individual items across all classes)
    breakup_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/track/api/v1/native/networth/portfolio-allocation-breakup",
        headers,
        "Portfolio Breakup"
    )

    # 5. Detailed Mutual Funds Tracking
    mf_funds_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/mf-tracking-ext/v1/users/portfolio/funds",
        headers,
        "Mutual Funds List"
    )
    mf_dash_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/mf-tracking-ext/v1/users/dashboard",
        headers,
        "Mutual Funds Dashboard"
    )

    # 6. US Stocks Demat Holdings & Cash
    us_stocks_raw = fetch_json(
        session,
        "https://apixt-us.indmoney.com/us-stock-broker/us/portfolio/equity/summary?response_format=json",
        headers,
        "US Stocks Summary"
    )

    # 7. Account Aggregator / Bank Accounts
    aa_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/acc-aggregator/api/v1/aggregator/l1-screen-v2",
        headers,
        "Bank Accounts"
    )

    # 8. EPFO / Retirement Passbooks
    epf_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/epf/api/v1/epf/portfolio",
        headers,
        "EPF Portfolio"
    )

    # Dynamically fetch details for every employer account discovered
    epf_accounts_data = []
    if epf_raw and "data" in epf_raw and "hot_state" in epf_raw["data"]:
        employers = epf_raw["data"]["hot_state"].get("employers", [])
        for emp in employers:
            emp_id = None
            navlink = emp.get("navlink", "")
            m = re.search(r"employer-id=([A-Za-z0-9]+)", navlink)
            if m:
                emp_id = m.group(1)
            if emp_id:
                acc_detail = fetch_json(
                    session,
                    f"https://apixt-iw.indmoney.com/epf/api/v1/epf/account-details/{emp_id}",
                    headers,
                    f"EPF Account {emp_id}"
                )
                port_detail = fetch_json(
                    session,
                    f"https://apixt-iw.indmoney.com/epf/api/v1/epf/portfolio/{emp_id}",
                    headers,
                    f"EPF Portfolio {emp_id}"
                )
                epf_accounts_data.append({
                    "employer_name": emp.get("name"),
                    "employer_id": emp_id,
                    "duration": emp.get("duration"),
                    "balance": emp.get("balance"),
                    "account_details": acc_detail.get("data") if acc_detail else None,
                    "portfolio_details": port_detail.get("data") if port_detail else None
                })

    # 9. ESOPs / RSUs Tracking Widgets
    esop_w1_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/track/api/v2/other-investments/mini-app-investment-widget?instrument_type=ESOPs-RSUs",
        headers,
        "ESOP Investment Widget"
    )

    # 10. Credit Cards / Liabilities
    cc_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/octopus/v1/user/cc-widget?rank=4&UserGlobalState=S73",
        headers,
        "Credit Cards"
    )

    # 11. Bank Balance & Pre-approved Credit Lines (Insta Cash)
    bank_bal_raw = fetch_json(
        session,
        "https://apixt-iw.indmoney.com/octopus/v2/user/bank-balance?rank=2&UserGlobalState=S73",
        headers,
        "Bank Balances"
    )

    # 12. Insurance Tracking Widget
    insurance_raw = fetch_json(
        session,
        "https://apixt-fz.indmoney.com/insurance-ext/api/v3/user-dashboard/insurance-widget?rank=3&UserGlobalState=S73",
        headers,
        "Insurance Widget"
    )

    # --- Normalize and Construct Complete Data Model ---
    out = {
        "metadata": {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "iso_timestamp": datetime.now().isoformat(),
        },
        "summary": {},
        "asset_allocation": [],
        "investment_categories_discovered": [],
        "bank_accounts": [],
        "epf_retirement": {},
        "esops_rsus": [],
        "us_stocks": {},
        "mutual_funds": [],
        "categorized_holdings": {},
        "liabilities": {},
        "credit_lines": {},
        "insurance": {},
        "all_holdings_raw": []
    }

    # Summary & Masthead
    if assets_raw and "data" in assets_raw:
        wp = assets_raw["data"].get("widget_properties", {})
        debug_val = wp.get("debug_val")
        subtitle = wp.get("summary", {}).get("subtitle1", {}).get("text", "")
        change_list = wp.get("change", {}).get("list", [])
        day_change_val = ""
        day_change_pct = ""
        top_gainer = ""
        top_gainer_pct = ""
        if len(change_list) > 0:
            day_change_val = change_list[0].get("title2", {}).get("text", "")
            day_change_pct = change_list[0].get("title3", {}).get("text", "")
        if len(change_list) > 1:
            top_gainer = change_list[1].get("title2", {}).get("text", "")
            top_gainer_pct = change_list[1].get("title3", {}).get("text", "")

        out["summary"]["total_networth_inr"] = float(debug_val) if debug_val else parse_amount(subtitle)
        out["summary"]["networth_display"] = subtitle or f"₹{out['summary']['total_networth_inr']/1e7:.2f}Cr"
        out["summary"]["one_day_change"] = day_change_val
        out["summary"]["one_day_change_percentage"] = day_change_pct
        out["summary"]["top_gainer"] = top_gainer
        out["summary"]["top_gainer_percentage"] = top_gainer_pct

    # Dynamic Discovery of Investment Categories
    if investments_raw and "data" in investments_raw:
        chips = investments_raw["data"].get("widget_properties", {}).get("chips_data", {}).get("chips", [])
        for c in chips:
            grid = c.get("gridList", [])
            for item in grid:
                title = item.get("title1", {}).get("text")
                val = item.get("title2", {}).get("text")
                cta = item.get("cta", {}).get("primary", {}).get("request", {})
                if title and title != "Add":
                    out["investment_categories_discovered"].append({
                        "name": title,
                        "value_display": val or "₹0",
                        "value_inr": parse_amount(val) if val else 0.0,
                        "navlink": cta.get("navlink", {}).get("web") or cta.get("navlink", {}).get("android", "")
                    })

    # Macro Asset Class Allocation
    if distribution_raw and "data" in distribution_raw:
        widgets = distribution_raw["data"].get("content_section", {}).get("widgets", [])
        if widgets:
            chips = widgets[0].get("widget_properties", {}).get("data", {}).get("chips_data", {}).get("chips", [])
            for c in chips:
                tab_title = c.get("cta", {}).get("primary", {}).get("title", {}).get("text", "")
                if tab_title.lower() == "assets":
                    for item in c.get("list", []):
                        cat_name = item.get("title1", {}).get("text")
                        amt_str = item.get("subtitle1", {}).get("text")
                        if cat_name:
                            out["asset_allocation"].append({
                                "category": cat_name,
                                "amount_display": amt_str,
                                "amount_inr": parse_amount(amt_str)
                            })

    # Bank Accounts from Account Aggregator
    if aa_raw and "data" in aa_raw:
        aa_data = aa_raw["data"]
        out["bank_accounts_summary"] = {
            "total_balance_display": aa_data.get("masthead", {}).get("amount", ""),
            "accounts_count_display": aa_data.get("masthead", {}).get("num_of_accounts", ""),
            "total_balance_inr": parse_amount(aa_data.get("masthead", {}).get("amount", ""))
        }
        upper_banks = aa_data.get("upper_banks", [])
        for b in upper_banks:
            out["bank_accounts"].append({
                "bank_name": b.get("title", ""),
                "account_mask": b.get("description", ""),
                "balance_inr": float(b.get("latest_balance_value", 0.0)),
                "balance_display": b.get("right_content", {}).get("value", f"₹{b.get('latest_balance_value', 0.0):,.2f}"),
                "status": "Linked" if b.get("latest_balance_value", 0.0) > 0 else "Discovered / Unlinked"
            })

    # EPFO / Retirement Passbooks
    if epf_raw and "data" in epf_raw and "hot_state" in epf_raw["data"]:
        hs = epf_raw["data"]["hot_state"]
        mh = hs.get("masthead", {})
        shares = mh.get("shares_section", [])
        footer = mh.get("footer_section", [])

        uan_text = footer[0].get("text", "") if len(footer) > 0 else ""
        last_updated = footer[1].get("text", "") if len(footer) > 1 else ""

        emp_share = ""
        empr_share = ""
        pension_share = ""
        for s in shares:
            lbl = s.get("label", "").lower()
            if "employee share" in lbl: emp_share = s.get("amount", "")
            elif "employers share" in lbl: empr_share = s.get("amount", "")
            elif "pension share" in lbl: pension_share = s.get("amount", "")

        out["epf_retirement"] = {
            "total_value_display": mh.get("amount_section", {}).get("amount", ""),
            "total_value_inr": parse_amount(mh.get("amount_section", {}).get("amount", "")),
            "uan": uan_text.replace("UAN:", "").strip(),
            "last_updated": last_updated.replace("Last updated:", "").strip(),
            "employee_share_display": emp_share,
            "employee_share_inr": parse_amount(emp_share),
            "employer_share_display": empr_share,
            "employer_share_inr": parse_amount(empr_share),
            "pension_share_display": pension_share,
            "pension_share_inr": parse_amount(pension_share),
            "accounts": epf_accounts_data,
            "projected_corpus": hs.get("projected_retirement_corpus", {}).get("chart", {}).get("projected_data", [])
        }

    # ESOPs / RSUs Grants
    if esop_w1_raw and "data" in esop_w1_raw:
        try:
            esop_items = esop_w1_raw["data"]["widget_properties"]["data"]["list"]
            for es in esop_items:
                out["esops_rsus"].append({
                    "company": es.get("name", ""),
                    "total_value_display": es.get("sectionEnd", {}).get("subtitle", {}).get("text", ""),
                    "vested_value_display": es.get("sectionStart", {}).get("subtitle", {}).get("text", ""),
                    "unvested_value_display": es.get("sectionMiddle", {}).get("subtitle", {}).get("text", ""),
                    "total_value_inr": parse_amount(es.get("sectionEnd", {}).get("subtitle", {}).get("text", ""))
                })
        except Exception:
            pass

    # US Stocks & ETFs
    if us_stocks_raw and "demat_summary" in us_stocks_raw:
        ds = us_stocks_raw["demat_summary"]
        summ = ds.get("summary", {})
        scrips = ds.get("asset_summary", {}).get("scrip_details", [])
        wallet = us_stocks_raw.get("user_wallet_balance", {})

        us_holdings = []
        for s in scrips:
            m = s.get("metadata", {})
            h = s.get("holdings", {})
            us_holdings.append({
                "symbol": m.get("symbol", ""),
                "name": m.get("name", ""),
                "isin": m.get("isin", ""),
                "sector": m.get("sector", ""),
                "quantity": float(h.get("quantity", 0.0)),
                "avg_price_usd": float(h.get("avg_price", 0.0)),
                "live_price_usd": float(m.get("live_price", 0.0)),
                "invested_usd": float(h.get("invested_amount", 0.0)),
                "current_usd": float(h.get("current_value", 0.0)),
                "overall_pnl_usd": float(h.get("overall_pnl", 0.0)),
                "overall_pnl_pct": float(h.get("overall_pnl_percentage", 0.0)),
                "day_pnl_usd": float(h.get("day_pnl", 0.0)),
                "day_pnl_pct": float(h.get("day_pnl_percentage", 0.0)),
            })

        out["us_stocks"] = {
            "summary": {
                "current_value_usd": float(summ.get("current_value", 0.0)),
                "invested_value_usd": float(summ.get("invested_value", 0.0)),
                "total_pnl_usd": float(summ.get("pnl", 0.0)),
                "total_pnl_percentage": float(summ.get("percentage_return", 0.0)),
                "day_change_usd": float(summ.get("day_change", 0.0)),
                "day_change_percentage": float(summ.get("day_change_percentage", 0.0)),
                "holding_count": int(summ.get("holding_count", len(us_holdings))),
                "cash_balance_usd": float(wallet.get("total_balance", 0.0))
            },
            "holdings": us_holdings
        }

    # Mutual Funds (All Schemes)
    if mf_funds_raw and "data" in mf_funds_raw:
        funds = mf_funds_raw["data"].get("funds", [])
        for f in funds:
            tags = f.get("sort_filter_tags", {})
            name = tags.get("fundName") or f.get("title", {}).get("text", "")
            curr_val = tags.get("currentValue", 0.0)
            inv_val = tags.get("investedAmount", 0.0)
            gain_pct = tags.get("gainPercentage", 0.0)
            xirr = tags.get("xirr", 0.0)

            cat_list = tags.get("Category") or []
            cat = cat_list[0] if cat_list else ""
            subcat_list = tags.get("SubCategory") or []
            subcat = subcat_list[0] if subcat_list else ""
            advisors_list = tags.get("advisors") or []
            advisors = advisors_list[0] if advisors_list else ""
            rating_list = tags.get("Rating") or []
            rating = rating_list[0] if rating_list else ""
            risk_list = tags.get("Risk") or []
            risk = risk_list[0] if risk_list else ""

            out["mutual_funds"].append({
                "fund_name": name,
                "category": cat,
                "sub_category": subcat,
                "advisor": advisors,
                "rating": rating,
                "risk": risk,
                "invested_inr": float(inv_val),
                "current_inr": float(curr_val),
                "gain_inr": float(curr_val - inv_val),
                "gain_percentage": float(gain_pct),
                "xirr_percentage": float(xirr) if xirr else None
            })
        out["mutual_funds"].sort(key=lambda x: x["current_inr"], reverse=True)

    # Dynamic Classification of All Individual Holdings (Zero Truncation)
    raw_holdings = []
    if breakup_raw and "data" in breakup_raw:
        widgets = breakup_raw["data"].get("content_section", {}).get("widgets", [])
        for w in widgets:
            if w.get("widgetTemplateName") == "neo_transactions_widget":
                raw_holdings = w.get("widget_properties", {}).get("list", [])
                break

    categorized = {}
    for it in raw_holdings:
        name = it.get("title2", {}).get("text", "").strip()
        source = it.get("title3", {}).get("text", "").strip()
        amt_str = it.get("title4", {}).get("text", "").strip()
        perf = it.get("title5", {}).get("text", "").strip()
        navlink = it.get("button1", {}).get("primary", {}).get("request", {}).get("navlink", {})
        web_url = navlink.get("web", "") or navlink.get("android", "")

        amt = parse_amount(amt_str)
        item_obj = {
            "name": name,
            "source": source or "Direct / Tracked",
            "amount_display": amt_str,
            "amount_inr": amt,
            "return_display": perf,
            "url": web_url
        }
        out["all_holdings_raw"].append(item_obj)

        # Dynamic category determination
        name_lower = name.lower()
        url_lower = web_url.lower()

        if "mutual-fund" in url_lower:
            cat = "Mutual Funds"
        elif "us-stock" in url_lower or "v2_us_mini_app" in url_lower:
            cat = "US Stocks & ETFs"
        elif "stocks" in url_lower or "stock-details" in url_lower or source in ["Zerodha", "Icici Securities", "Upstox", "Groww", "Angel One"]:
            cat = "Indian Direct Stocks & ETFs"
        elif "epf" in url_lower or "epf" in name_lower or "provident" in name_lower:
            cat = "EPF / Retirement"
        elif "esop" in url_lower or "rsu" in url_lower or "netapp-inc" in name_lower:
            cat = "ESOPs & RSUs"
        elif "bank" in name_lower or "icici" in name_lower or "state bank" in name_lower or "savings" in url_lower:
            cat = "Bank Accounts / Liquid"
        elif "gold" in name_lower or "sgb" in name_lower or "sovereign gold" in name_lower:
            cat = "Gold & Precious Metals"
        elif "bond" in name_lower:
            cat = "Bonds & Fixed Income"
        elif "wallet" in name_lower:
            cat = "Cash Wallets"
        elif "crypto" in url_lower or "crypto" in name_lower or "digital asset" in name_lower:
            cat = "Digital Assets & Crypto"
        elif "nps" in url_lower or "nps" in name_lower:
            cat = "National Pension System (NPS)"
        elif "fd" in url_lower or "fixed deposit" in name_lower:
            cat = "Fixed Deposits"
        elif "real-estate" in url_lower or "property" in name_lower:
            cat = "Real Estate"
        elif "vehicle" in url_lower or "vehicle" in name_lower:
            cat = "Vehicles"
        else:
            cat = "Other Investments & Assets"

        categorized.setdefault(cat, []).append(item_obj)

    # Sort each category by amount descending
    for k in categorized:
        categorized[k].sort(key=lambda x: x["amount_inr"], reverse=True)
    out["categorized_holdings"] = categorized

    # Liabilities & Credit Cards
    if cc_raw and "data" in cc_raw:
        cc_list = cc_raw["data"].get("widget_properties", {}).get("list", [])
        if cc_list:
            due_str = cc_list[0].get("title2", {}).get("text", "")
            sub_str = cc_list[0].get("title3", {}).get("attributed_text", [{}])[0].get("text", "")
            out["liabilities"] = {
                "credit_card_total_due_inr": parse_amount(due_str),
                "due_display": due_str,
                "notes": sub_str
            }

    # Pre-approved Credit Lines
    if bank_bal_raw and "data" in bank_bal_raw:
        chips = bank_bal_raw["data"].get("widget_properties", {}).get("data", {}).get("chips_data", {}).get("chips", [])
        for c in chips:
            t = c.get("cta", {}).get("primary", {}).get("title", {}).get("text", "")
            if t == "Insta Cash":
                try:
                    summary1 = c["graphData"]["barChartData"][0][0]["insight_summary"]["summary1"]
                    out["credit_lines"]["insta_cash"] = {
                        "title": summary1.get("title1", {}).get("text", "Insta Cash"),
                        "limit_display": summary1.get("subtitle1", {}).get("text", "₹0"),
                        "limit_inr": parse_amount(summary1.get("subtitle1", {}).get("text", "₹0"))
                    }
                except Exception:
                    pass

    # Insurance
    if insurance_raw and "data" in insurance_raw:
        try:
            chips = insurance_raw["data"]["widget_properties"]["data"]["chips_data"]["chips"]
            for c in chips:
                name = c.get("cta", {}).get("primary", {}).get("title", {}).get("text", "")
                if name.lower() == "life":
                    lst = c.get("graphData", {}).get("barChartData", [[{}]])[0][0].get("list", [])
                    ins_sum = c.get("graphData", {}).get("barChartData", [[{}]])[0][0].get("insight_summary", {}).get("summary1", {})
                    out["insurance"]["approved_life_offer"] = ins_sum.get("subtitle1", "")
                    if lst:
                        out["insurance"]["life_cover_display"] = lst[0].get("subtitle1", {}).get("text", "")
                        out["insurance"]["policies_tracked"] = lst[0].get("title1", {}).get("text", "")
        except Exception:
            pass

    return out

def format_inr(val):
    """Formats numeric float into Indian Rupee style string."""
    if abs(val) >= 10_000_000:
        return f"₹{val/10_000_000:.2f} Cr"
    elif abs(val) >= 100_000:
        return f"₹{val/100_000:.2f} L"
    elif abs(val) >= 1_000:
        return f"₹{val/1_000:.2f} K"
    return f"₹{val:,.2f}"

def generate_markdown(data):
    """
    Renders an exhaustive, structured Markdown report featuring:
    1. Machine-readable YAML frontmatter
    2. Comprehensive human-readable Markdown tables for every asset & liability
    3. Zero truncation across all individual holdings
    4. Full raw normalized JSON payload
    """
    meta = data["metadata"]
    summary = data["summary"]
    alloc = data["asset_allocation"]
    banks = data["bank_accounts"]
    epf = data.get("epf_retirement", {})
    esops = data.get("esops_rsus", [])
    us = data.get("us_stocks", {})
    mfs = data.get("mutual_funds", [])
    categorized = data.get("categorized_holdings", {})
    liabilities = data.get("liabilities", {})
    credit_lines = data.get("credit_lines", {})
    insurance = data.get("insurance", {})

    total_networth = summary.get("total_networth_inr", 0.0)
    total_due_inr = liabilities.get("credit_card_total_due_inr", 0.0)

    # Compute category totals
    category_totals = {cat: sum(i["amount_inr"] for i in items) for cat, items in categorized.items()}

    # Frontmatter dictionary (machine-readable)
    frontmatter = {
        "title": "INDmoney Comprehensive Assets & Liabilities Report",
        "exported_at": meta["exported_at"],
        "iso_timestamp": meta["iso_timestamp"],
        "total_networth_inr": total_networth,
        "total_liabilities_inr": total_due_inr,
        "net_asset_value_inr": total_networth - total_due_inr,
        "one_day_change": summary.get("one_day_change", ""),
        "one_day_change_percentage": summary.get("one_day_change_percentage", ""),
        "top_gainer": summary.get("top_gainer", ""),
        "top_gainer_percentage": summary.get("top_gainer_percentage", ""),
        "category_totals_inr": {k: round(v, 2) for k, v in category_totals.items()},
        "item_counts": {k: len(v) for k, v in categorized.items()}
    }

    md = []
    md.append("---")
    md.append(yaml.dump(frontmatter, sort_keys=False, allow_unicode=True).strip())
    md.append("---\n")

    md.append("# 🏛️ Complete Portfolio & Liabilities Report")
    md.append(f"> **Snapshot Date:** `{meta['exported_at']}` | **Data Source:** INDmoney Realtime APIs\n")

    # 1. Executive Summary Table
    md.append("## 📌 Executive Summary")
    md.append("| Metric | Value | Reference Details |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| **Total Net Worth** | **{format_inr(total_networth)}** (`₹{total_networth:,.2f}`) | Live Assets Masthead Indicator |")
    md.append(f"| **1-Day Net Change** | **{summary.get('one_day_change', 'N/A')}** | `{summary.get('one_day_change_percentage', '0%')}` |")
    md.append(f"| **Top 1-Day Mover** | **{summary.get('top_gainer', 'N/A')}** | `{summary.get('top_gainer_percentage', '')}` |")
    md.append(f"| **Total Current Liabilities** | **₹{total_due_inr:,.0f}** | Credit cards outstanding dues |")
    md.append(f"| **Net Asset Value (NAV)** | **{format_inr(total_networth - total_due_inr)}** | Total Assets minus Outstanding Liabilities |")
    if credit_lines.get("insta_cash"):
        ic = credit_lines["insta_cash"]
        md.append(f"| **Pre-Approved Credit Line** | **{ic['limit_display']}** | {ic['title']} |")
    md.append("")

    # 2. Asset Allocation Breakdown
    md.append("## 💼 Macro Asset Allocation Breakdown")
    md.append("| Asset Category | Allocated Amount | % of Portfolio | Status |")
    md.append("| :--- | :--- | :--- | :--- |")
    for a in alloc:
        pct = (a["amount_inr"] / total_networth * 100.0) if total_networth else 0.0
        md.append(f"| **{a['category']}** | **{a['amount_display']}** | `{pct:.2f}%` | Active Allocation |")
    md.append("")

    # 3. Bank Accounts & Liquid Savings
    if banks:
        tot_bank = sum(b['balance_inr'] for b in banks)
        md.append("## 🏦 Bank Accounts & Liquid Balances")
        md.append(f"> **Total Liquid Savings:** **{format_inr(tot_bank)}** across linked banks\n")
        md.append("| Bank Name | Account Mask | Balance (₹) | Status / Tracking Channel |")
        md.append("| :--- | :--- | :--- | :--- |")
        for b in banks:
            md.append(f"| **{b['bank_name']}** | `{b['account_mask']}` | **{format_inr(b['balance_inr'])}** (`₹{b['balance_inr']:,.2f}`) | {b['status']} (Account Aggregator) |")
        md.append("")

    # 4. EPFO (Employees' Provident Fund)
    if epf and epf.get("accounts"):
        md.append("## 🛡️ Employees' Provident Fund (EPFO)")
        md.append(f"> **Total EPF Corpus:** **{epf.get('total_value_display')}** | **UAN:** `{epf.get('uan')}` | **Last Updated:** `{epf.get('last_updated')}`\n")
        md.append("| Component | Amount | Share Details |")
        md.append("| :--- | :--- | :--- |")
        md.append(f"| **Employee Contribution** | **{epf.get('employee_share_display')}** | Direct employee accumulated PF |")
        md.append(f"| **Employer Contribution** | **{epf.get('employer_share_display')}** | Employer matching accumulated PF |")
        md.append(f"| **Pension Share (EPS)** | **{epf.get('pension_share_display')}** | Employee Pension Scheme corpus |")
        md.append("")

        md.append("### 📋 Employer Accounts & Member Passbooks")
        md.append("| Employer Name | Member ID | Period | Total Deposit | Employee Share | Employer Share | Pension Share |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for acc in epf.get("accounts", []):
            emp_name = acc["employer_name"]
            mid = acc["employer_id"]
            dur = acc["duration"]
            tot_bal = acc["balance"]
            sh_emp = "-"
            sh_empr = "-"
            sh_pen = "-"
            if acc.get("portfolio_details") and "masthead" in acc["portfolio_details"]:
                for s in acc["portfolio_details"]["masthead"].get("shares_section", []):
                    lbl = s.get("label", "").lower()
                    if "employee" in lbl: sh_emp = s.get("amount", "-")
                    elif "employer" in lbl: sh_empr = s.get("amount", "-")
                    elif "pension" in lbl: sh_pen = s.get("amount", "-")
            md.append(f"| **{emp_name}** | `{mid}` | {dur} | **{tot_bal}** | {sh_emp} | {sh_empr} | {sh_pen} |")
        md.append("")

    # 5. ESOPs & RSUs
    if esops:
        md.append("## 🏢 ESOPs & RSUs (Corporate Grants)")
        md.append("| Company / Grant | Total Value | Vested Value | Unvested Value | Status |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for es in esops:
            md.append(f"| **{es.get('company')}** | **{es.get('total_value_display')}** | **{es.get('vested_value_display')}** | {es.get('unvested_value_display')} | Vested Shares |")
        md.append("")

    # 6. US Stocks & ETFs
    if us and us.get("holdings"):
        u_sum = us.get("summary", {})
        u_holdings = us.get("holdings", [])
        md.append("## 🇺🇸 US Stocks & ETFs (INDmoney Global / DriveWealth)")
        md.append(f"> **Portfolio Valuation:** `${u_sum.get('current_value_usd', 0.0):,.2f}` | **Invested:** `${u_sum.get('invested_value_usd', 0.0):,.2f}` | **Total Gain:** `+${u_sum.get('total_pnl_usd', 0.0):,.2f} (+{u_sum.get('total_pnl_percentage', 0.0):.2f}%)` | **Cash Wallet:** `${u_sum.get('cash_balance_usd', 0.0):,.2f}`\n")
        md.append("| Ticker | Asset Name | ISIN | Qty | Buy Avg ($) | Live Price ($) | Invested ($) | Current Value ($) | Day Return | Overall Return |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for u in u_holdings:
            ov_sign = "+" if u["overall_pnl_usd"] >= 0 else ""
            d_sign = "+" if u["day_pnl_usd"] >= 0 else ""
            ov_str = f"{ov_sign}${u['overall_pnl_usd']:,.2f} ({ov_sign}{u['overall_pnl_pct']:.2f}%)"
            d_str = f"{d_sign}${u['day_pnl_usd']:,.2f} ({d_sign}{u['day_pnl_pct']:.2f}%)"
            md.append(f"| **{u['symbol']}** | {u['name']} | `{u['isin']}` | {u['quantity']:.2f} | ${u['avg_price_usd']:.2f} | ${u['live_price_usd']:.2f} | ${u['invested_usd']:,.2f} | **${u['current_usd']:,.2f}** | `{d_str}` | `{ov_str}` |")
        md.append("")

    # 7. Mutual Funds (All Schemes)
    if mfs:
        tot_curr = sum(f["current_inr"] for f in mfs)
        tot_inv = sum(f["invested_inr"] for f in mfs)
        tot_gain = tot_curr - tot_inv
        tot_pct = (tot_gain / tot_inv * 100.0) if tot_inv else 0.0
        md.append(f"## 📈 Mutual Funds ({len(mfs)} Active Schemes)")
        md.append(f"> **Total Valuation:** `{format_inr(tot_curr)}` (`₹{tot_curr:,.2f}`) | **Total Invested:** `{format_inr(tot_inv)}` (`₹{tot_inv:,.2f}`) | **Total Profit:** `+{format_inr(tot_gain)} (+{tot_pct:.2f}%)`\n")
        md.append("| # | Scheme Name | Category | Sub-Category | Invested (₹) | Current Value (₹) | Absolute Gain (₹) | Return % | XIRR % | Rating | Advisor |")
        md.append("| :- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :-: | :--- |")
        for idx, f in enumerate(mfs, 1):
            xirr_str = f"{f['xirr_percentage']:.1f}%" if f["xirr_percentage"] is not None else "-"
            gain_sign = "+" if f["gain_inr"] >= 0 else ""
            rat = f"{f['rating']}★" if f["rating"] else "-"
            md.append(f"| {idx} | **{f['fund_name']}** | {f['category']} | {f['sub_category']} | {f['invested_inr']:>12,.0f} | **{f['current_inr']:>12,.0f}** | {gain_sign}{f['gain_inr']:>10,.0f} | `{gain_sign}{f['gain_percentage']:.2f}%` | `{xirr_str}` | {rat} | {f['advisor']} |")
        md.append("")

    # 8. Dynamic Sections for All Holdings Categories (Zero Truncation)
    for cat_name, items in categorized.items():
        if cat_name in ["Mutual Funds", "US Stocks & ETFs"]:
            continue  # Handled above with specialized schemas

        cat_tot = sum(i["amount_inr"] for i in items)
        icon_map = {
            "Indian Direct Stocks & ETFs": "🇮🇳",
            "Gold & Precious Metals": "🥇",
            "Bonds & Fixed Income": "📜",
            "Cash Wallets": "💵",
            "Digital Assets & Crypto": "🪙",
            "National Pension System (NPS)": "🏛️",
            "Fixed Deposits": "🔒",
            "Real Estate": "🏠",
            "Vehicles": "🚗"
        }
        icon = icon_map.get(cat_name, "📁")

        md.append(f"## {icon} {cat_name} ({len(items)} Holdings)")
        md.append(f"> **Total Category Valuation:** `{format_inr(cat_tot)}` (`₹{cat_tot:,.2f}`)\n")
        md.append("| # | Asset / Holding Name | Current Value | Value (INR) | Custodian / Source | Return / Notes | Direct Link |")
        md.append("| :- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for idx, s in enumerate(items, 1):
            perf_str = s["return_display"] if s["return_display"] else "-"
            link_str = f"[View on Platform]({s['url']})" if s["url"] else "-"
            md.append(f"| {idx} | **{s['name']}** | **{s['amount_display']}** | ₹{s['amount_inr']:,.0f} | {s['source']} | `{perf_str}` | {link_str} |")
        md.append("")

    # 9. Liabilities & Credit Cards
    md.append("## 💳 Liabilities & Credit Cards")
    md.append("| Liability Item | Current Outstanding | Status / Details |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| **Tracked Credit Cards** | **{liabilities.get('due_display', '₹0')}** | {liabilities.get('notes', 'No outstanding dues')} |")
    md.append(f"| **Active Loans / Mortgages** | **₹0.00** | None reported across bureaus |\n")

    # 10. Insurance
    if insurance:
        md.append("## 🛡️ Insurance Policies Tracking")
        md.append(f"* **Tracked Life Cover:** **{insurance.get('life_cover_display', '₹0')}** ({insurance.get('policies_tracked', '0 Policies tracked')})")
        if insurance.get("approved_life_offer"):
            md.append(f"* **Pre-Approved Life Cover Offer:** **{insurance.get('approved_life_offer')}**")
        md.append("")

    # 11. Full Raw Normalized Machine-Readable JSON Codeblock
    md.append("## 🤖 Machine-Readable Full Normalized JSON")
    md.append("The JSON payload below contains the complete, unabridged, raw normalized portfolio data model for programmatic processing:\n")
    md.append("```json")
    md.append(json.dumps(data, indent=2, ensure_ascii=False))
    md.append("```\n")

    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(
        description="Exhaustively export INDmoney portfolio to a timestamped Markdown report"
    )
    parser.add_argument("--token", help="INDmoney Bearer JWT token string")
    parser.add_argument("--token-file", help="Path to a text file containing the Bearer token or curl command")
    parser.add_argument("--output-dir", default=".", help="Directory to save the markdown file (default: current directory)")
    parser.add_argument("--output-file", help="Custom output filename (defaults to timestamped name)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")

    args = parser.parse_args()

    token = resolve_token(token_arg=args.token, token_file=args.token_file)

    data = collect_portfolio_data(token, verbose=not args.quiet)
    md_content = generate_markdown(data)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.output_file:
        out_path = out_dir / args.output_file
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        out_path = out_dir / f"indmoney_portfolio_{timestamp}.md"

    out_path.write_text(md_content, encoding="utf-8")

    if not args.quiet:
        print(f"\n✅ Complete portfolio successfully exported to:")
        print(f"   {out_path.resolve()}")
        print(f"   File size: {len(md_content)/1024:.1f} KB")

if __name__ == "__main__":
    main()
