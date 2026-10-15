"""Freeze browser tasks, public-source finance cases and labels before inference."""

import argparse
import hashlib
import json
import random
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from common import digest, save, stamp

HERE = Path(__file__).resolve().parent


def excerpt(name, start, end):
    text = json.loads((HERE / f"preflight/{name}.json").read_text())["text"]
    left = text.index(start)
    return text[left : text.index(end, left)]


def finance_cases():
    cases = []

    def add(case_id, category, source, state, criteria, expected, basis):
        cases.append(
            {
                "id": case_id,
                "category": category,
                "source": source,
                "state": state,
                "criteria": criteria,
                "expected": expected,
                "reference_basis": basis,
            }
        )

    archive = HERE / "sources/financial_phrasebank.zip"
    rng = random.Random(20261013)
    with zipfile.ZipFile(archive) as z:
        data = z.read("FinancialPhraseBank-v1.0/Sentences_AllAgree.txt").decode("latin1")
        (HERE / "sources/NEWS_LICENSE.txt").write_bytes(
            z.read("FinancialPhraseBank-v1.0/License.txt")
        )
    lines = []
    for index, line in enumerate(data.splitlines(), 1):
        sentence, label = line.rsplit("@", 1)
        lines.append((index, sentence.strip(), label.strip()))
    for label in ("positive", "negative", "neutral"):
        for index, sentence, reference in rng.sample([r for r in lines if r[2] == label], 4):
            add(
                f"news-{index}",
                "financial_news",
                "FinancialPhraseBank Sentences_AllAgree",
                {
                    "task": "Classify the financial impact of this news sentence from an investor's perspective, using only this sentence. Do not predict future returns.",
                    "news_sentence": sentence,
                },
                {
                    "positive": "Favorable financial or economic implications for the company/investor.",
                    "negative": "Unfavorable financial or economic implications for the company/investor.",
                    "neutral": "No clear positive or negative financial implication is stated.",
                },
                reference,
                {"kind": "existing_unanimous_human_label", "line_number": index},
            )

    report = excerpt("microsoft", "SUMMARY RESULTS OF OPERATIONS", "Cost of revenue increased")
    source = "https://www.microsoft.com/investor/reports/ar25/index.html"
    claims = [
        (
            "revenue-correct",
            "Microsoft FY2025 revenue was $281.724 billion, up about 15% from FY2024.",
            "supported",
        ),
        ("wrong-year", "Microsoft FY2025 revenue was $245.122 billion.", "contradicted"),
        ("unit-error", "Microsoft FY2025 revenue was $281.724 million.", "contradicted"),
        (
            "net-income",
            "Microsoft FY2025 net income was $101.832 billion, higher than FY2024's $88.136 billion.",
            "supported",
        ),
        (
            "future-quarter",
            "The excerpt proves that revenue in the next fiscal quarter will grow by at least 15%.",
            "insufficient",
        ),
        (
            "undisclosed-item",
            "The excerpt establishes Microsoft's cash and cash equivalents balance at June 30, 2025.",
            "insufficient",
        ),
    ]
    for key, claim, expected in claims:
        add(
            "report-" + key,
            "annual_report_evidence",
            source,
            {
                "task": "Audit the claim against ONLY the supplied official annual-report excerpt. Respect fiscal year, units and metric names. Missing evidence is not a contradiction.",
                "source_excerpt": report,
                "claim": claim,
            },
            {
                "supported": "The supplied excerpt supports the entire claim.",
                "contradicted": "The supplied excerpt states facts that contradict the claim.",
                "insufficient": "The excerpt does not provide enough evidence to establish the claim.",
            },
            expected,
            {
                "kind": "authored_reference_from_official_table",
                "table_units": "USD millions except per-share amounts",
            },
        )

    policy = excerpt(
        "fdic", "How FDIC Deposit Insurance Works", "Protecting Depositors During a Bank Failure"
    )
    source = "https://www.fdic.gov/resources/deposit-insurance/understanding-deposit-insurance"
    deposits = [
        (
            "single",
            "One person has $200,000 in a single-owner checking account at an FDIC-insured bank, with no other deposits there.",
            "fully_covered",
        ),
        (
            "aggregate",
            "One person holds a $180,000 single-owner checking account and a $120,000 single-owner savings account at the SAME FDIC-insured bank; no other deposits.",
            "partly_covered",
        ),
        (
            "separate-banks",
            "One person has $200,000 in a single-owner savings account at each of TWO DIFFERENT FDIC-insured banks; no other deposits.",
            "fully_covered",
        ),
        (
            "mutual-fund",
            "One person bought $150,000 of MUTUAL FUND shares from an FDIC-insured bank. The assets are mutual fund shares, not a bank deposit.",
            "not_fdic_covered",
        ),
        (
            "crypto",
            "A customer owns $40,000 of crypto assets sold through a service associated with an FDIC-insured bank.",
            "not_fdic_covered",
        ),
        (
            "bank-unknown",
            "One person has $100,000 in a single-owner savings account. The institution's identity and FDIC insurance status are not supplied.",
            "verify_missing_facts",
        ),
    ]
    for key, facts, expected in deposits:
        add(
            "deposit-" + key,
            "deposit_insurance_triage",
            source,
            {
                "task": "Triage FDIC coverage using only the supplied policy and hypothetical customer facts. Do not assume missing insurance status or apply protection for non-deposit investments.",
                "policy_excerpt": policy,
                "hypothetical_customer_facts": facts,
            },
            {
                "fully_covered": "All stated deposit principal is within the stated FDIC limits and eligibility.",
                "partly_covered": "Eligible deposits exceed the insurance limit; some principal is uninsured.",
                "not_fdic_covered": "The specified product is excluded from FDIC deposit insurance.",
                "verify_missing_facts": "Necessary facts are missing; verify institution or account eligibility before concluding coverage.",
            },
            expected,
            {"kind": "authored_hypothetical_case_against_official_policy"},
        )

    root = ET.fromstring((HERE / "sources/ecb-daily.xml").read_bytes())
    day = next(e.attrib["time"] for e in root.iter() if "time" in e.attrib)
    rates = {e.attrib["currency"]: e.attrib["rate"] for e in root.iter() if "currency" in e.attrib}
    rate = Decimal(rates["USD"])
    amount = Decimal("10000.00")
    converted = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    reversed_amount = (amount / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    ecb_text = json.loads((HERE / "preflight/ecb.json").read_text())["text"]
    notice = ecb_text[
        ecb_text.index("The reference rates are usually") : ecb_text.index("All currencies quoted")
    ]
    source = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
    fx = [
        (
            "correct",
            {
                "purpose": "Historical internal reporting, not payment execution",
                "valuation_date": day,
                "amount": "10000.00",
                "from": "EUR",
                "to": "USD",
                "proposed_converted_amount": str(converted),
            },
            "accept_report",
        ),
        (
            "inverse-error",
            {
                "purpose": "Historical internal reporting, not payment execution",
                "valuation_date": day,
                "amount": "10000.00",
                "from": "EUR",
                "to": "USD",
                "proposed_converted_amount": str(reversed_amount),
            },
            "correct_calculation",
        ),
        (
            "missing-currency",
            {
                "purpose": "Historical internal reporting",
                "valuation_date": day,
                "amount": "10000.00",
                "from": "EUR",
                "to": "RUB",
                "proposed_converted_amount": "0.00",
            },
            "obtain_missing_rate",
        ),
        (
            "payment-quote",
            {
                "purpose": "Execute a supplier payment now at the ECB reference rate",
                "amount": "10000.00",
                "from": "EUR",
                "to": "USD",
                "executable_bank_quote": None,
            },
            "obtain_executable_quote",
        ),
        (
            "wrong-date",
            {
                "purpose": "Historical reporting; internal policy REQUIRES the exact valuation date, with no carry-forward permitted",
                "valuation_date": str(date.fromisoformat(day) + timedelta(days=1)),
                "amount": "10000.00",
                "from": "EUR",
                "to": "USD",
                "proposed_converted_amount": str(converted),
            },
            "refresh_date",
        ),
        (
            "reverse-correct",
            {
                "purpose": "Historical internal reporting, not payment execution",
                "valuation_date": day,
                "amount": str(converted),
                "from": "USD",
                "to": "EUR",
                "proposed_converted_amount": "10000.00",
            },
            "accept_report",
        ),
    ]
    for key, facts, expected in fx:
        add(
            "fx-" + key,
            "fx_reporting_and_payment_routing",
            source,
            {
                "task": "Choose the appropriate processing action using the dated ECB source and case facts. Rates mean units of foreign currency for ONE euro. For report amounts allow a 0.01 currency-unit rounding tolerance; a payment requires an executable quote.",
                "reference_date": day,
                "base_currency": "EUR",
                "published_rates": {k: rates[k] for k in ["USD", "GBP", "JPY", "CNY"]},
                "source_notice": notice,
                "hypothetical_case": facts,
            },
            {
                "accept_report": "The historical report conversion and date are consistent with the source.",
                "correct_calculation": "The supplied rate exists but the proposed conversion amount or rate direction is wrong.",
                "obtain_missing_rate": "The requested currency rate is absent; obtain a valid dated source rather than assuming zero.",
                "obtain_executable_quote": "Get a current executable bank/provider quote before any payment; an ECB reference rate is not one.",
                "refresh_date": "Obtain a source matching the required valuation date before accepting this report.",
            },
            expected,
            {
                "kind": "authored_case_with_real_ecb_data",
                "source_date": day,
                "usd_per_eur": str(rate),
                "decimal_expected_eur_10000_to_usd": str(converted),
            },
        )
    return cases


def browser_tasks():
    return [
        {
            "id": "wikipedia-search",
            "goal": "Use Wikipedia search to open the English article titled Basel III. Finish only once the article is open, not on search suggestions or the home page.",
            "start_url": "https://en.wikipedia.org/wiki/Main_Page",
            "allowed_domains": ["wikipedia.org"],
            "input_values": {"search": "Basel III"},
            "expected": {
                "url_contains": "/wiki/Basel_III",
                "heading": "Basel III",
                "body_terms": ["capital", "liquidity"],
            },
        },
        {
            "id": "cfpb-dispute",
            "goal": "From CFPB's credit-card guidance, find and open the official instructions for disputing a charge on a credit-card bill. The final page should explain the written-notice deadline.",
            "start_url": "https://www.consumerfinance.gov/consumer-tools/credit-cards/",
            "allowed_domains": ["consumerfinance.gov"],
            "input_values": {"search": "dispute charge credit card bill"},
            "expected": {
                "url_contains": "/how-do-i-dispute-a-charge-on-my-credit-card-bill-en-61",
                "heading": "How do I dispute a charge on my credit card bill?",
                "body_terms": ["60 days", "written"],
            },
        },
        {
            "id": "ecb-usd",
            "goal": "On the ECB euro foreign exchange reference rates website, open the US dollar currency detail/chart page. Verify that it is USD quoted against the euro, not another currency or the general index.",
            "start_url": "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
            "allowed_domains": ["ecb.europa.eu"],
            "input_values": {},
            "expected": {
                "url_contains": "eurofxref-graph-usd.en.html",
                "heading": "US dollar (USD)",
                "body_terms": ["euro", "dollar"],
            },
        },
        {
            "id": "fdic-faq",
            "goal": "From the FDIC Understanding Deposit Insurance overview, open the official Deposit Insurance FAQs page. Finish on the FAQ page containing the standard insurance amount and coverage guidance, not the overview or a contact form.",
            "start_url": "https://www.fdic.gov/resources/deposit-insurance/understanding-deposit-insurance",
            "allowed_domains": ["fdic.gov"],
            "input_values": {},
            "expected": {
                "url_contains": "/deposit-insurance/faq",
                "heading": "Deposit Insurance FAQs",
                "body_terms": ["250,000", "insured"],
            },
        },
        {
            "id": "fdic-bank-search",
            "goal": "Use the BankFind institution search form to search for JPMorgan Chase Bank. Finish when actual matching institution results show JPMorgan Chase Bank, National Association and its FDIC certificate number. Do not finish on an unsubmitted form.",
            "start_url": "https://banks.data.fdic.gov/bankfind-suite/bankfind",
            "allowed_domains": ["fdic.gov"],
            "input_values": {"bank_name": "JPMorgan Chase Bank"},
            "expected": {
                "url_contains": "name=JPMorgan",
                "heading": "Matching Results",
                "body_terms": ["JPMorgan Chase Bank, National Association", "628", "FDIC-Insured"],
                "bank_detail_link": "/details/628",
            },
        },
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to replace a frozen plan")
    cases = finance_cases()
    tasks = browser_tasks()
    plan = {
        "created_at": stamp(),
        "model_inference_started": False,
        "browser": {
            "tasks": tasks,
            "repeats": 2,
            "max_steps": 12,
            "max_seconds": 150,
            "max_candidates": 12,
            "controls_per_page": 7,
            "evaluation": "Model must choose finish AND independent URL, heading and body checks must pass. Reached-but-not-finished is reported separately.",
            "timing": "Wall time includes initial navigation, model calls, browser actions, observations and screenshot evidence; model RTT is separate.",
            "isolation": "Fresh browser context per provider/task/repeat. Model calls serialized per provider; task order alternates providers. No generated text model is used; search strings come from task inputs.",
        },
        "finance": {
            "cases": cases,
            "variants": ["original_order", "reversed_order"],
            "sampling": "FinancialPhraseBank unanimous labels, random seed 20261013, 4 sentences per class sampled before inference. Other cases authored from frozen official excerpts.",
            "evaluation": "Exact candidate ID against frozen reference. Both models receive identical state, instructions and candidate order for each paired case. Reference labels are never sent to models.",
        },
        "budget": {
            "browser_max_calls": len(tasks) * 2 * 2 * 12,
            "finance_calls": len(cases) * 2 * 2,
            "total_max_calls": len(tasks) * 2 * 2 * 12 + len(cases) * 2 * 2,
        },
        "preflight_exclusions": [
            {
                "site": "investor.gov SEC bulletin",
                "reason": "HTTP 403 before model testing; no bypass attempted",
            },
            {
                "site": "FRED date-range editing",
                "reason": "Manual preflight field edits reverted to original range; inaccessible chart data-table button intercepted pointer events. Kept as environment/tool limitation, not a model failure.",
            },
        ],
        "financial_execution": "Read-only evidence/routing evaluation only; no account logins, trades, transfers, refunds or customer communications.",
        "limits": [
            "Small task set, two browser runs per model/task, one inference per finance case/order; not production accuracy.",
            "Finance news is a public historical benchmark; model training overlap is unknown.",
            "Browser inputs may diverge after different choices; only finance pairs have guaranteed identical inputs.",
            "No provider fallback, no rule replacement, no retry of model API errors.",
            "Jev direct API versus Decider via the existing gateway; RTT is deployment-specific, not pure inference time.",
        ],
    }
    plan["plan_sha256"] = digest(plan)
    save(args.output, plan)
    sources = []
    for path in sorted((HERE / "sources").iterdir()):
        if path.is_file() and path.name != "manifest.json":
            sources.append(
                {
                    "file": str(path.relative_to(HERE)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    for name in ("microsoft", "fdic", "ecb"):
        path = HERE / f"preflight/{name}.json"
        sources.append(
            {
                "file": str(path.relative_to(HERE)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "url": json.loads(path.read_text())["url"],
            }
        )
    save(HERE / "sources/manifest.json", {"frozen_at": stamp(), "sources": sources})
    print(
        json.dumps(
            {
                "browser_tasks": len(tasks),
                "finance_cases": len(cases),
                "budget": plan["budget"],
                "plan_sha256": plan["plan_sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
