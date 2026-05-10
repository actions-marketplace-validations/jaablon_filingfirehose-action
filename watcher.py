"""SEC filing watcher — runs inside the GitHub Action.

Parses the FF_QUERY input, hits FilingFirehose for matches, then optionally:
  - fails the job (`FF_FAIL_ON_HIT=true`)
  - opens a GitHub issue per filing (`FF_OPEN_ISSUE=true`)
  - POSTs matches to a webhook URL
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error

from filing_firehose import FilingFirehose


def _gh_open_issue(title: str, body: str) -> None:
    token = os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        print("(skip issue: GH_TOKEN or GITHUB_REPOSITORY missing)", flush=True)
        return
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps({"title": title, "body": body, "labels": ["filingfirehose"]}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"opened issue: {json.loads(r.read())['html_url']}", flush=True)
    except urllib.error.HTTPError as exc:
        print(f"(issue open failed: {exc.code} {exc.read()[:200]!r})", flush=True)


def _post_webhook(url: str, payload: dict) -> None:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"webhook posted: HTTP {r.status}", flush=True)
    except Exception as exc:
        print(f"(webhook failed: {exc})", flush=True)


def _set_action_output(name: str, value: str) -> None:
    """Write to $GITHUB_OUTPUT so subsequent steps can use the value."""
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a") as f:
        # Multi-line outputs use heredoc syntax in the new $GITHUB_OUTPUT format
        if "\n" in value:
            f.write(f"{name}<<__EOF__\n{value}\n__EOF__\n")
        else:
            f.write(f"{name}={value}\n")


def main() -> int:
    query = os.environ.get("FF_QUERY", "").strip()
    if not query:
        print("ERROR: query input required", flush=True)
        return 2

    api_key = os.environ.get("FF_API_KEY") or None
    fail_on_hit = os.environ.get("FF_FAIL_ON_HIT", "true").lower() == "true"
    open_issue = os.environ.get("FF_OPEN_ISSUE", "false").lower() == "true"
    webhook_url = os.environ.get("FF_WEBHOOK_URL") or None

    ff = FilingFirehose(api_key=api_key)

    # Dispatch on query shape
    matches: list[dict] = []
    if query == "buried_8k":
        for f in ff.recent_8k(suspected_buried_only=True, limit=50):
            matches.append({
                "accession": f.accession_number,
                "company": f.company_name,
                "filed_at": f.filed_at,
                "filer_reported": f.filer_reported_items,
                "suspected_buried": f.suspected_buried_events,
                "url": f"https://filingfirehose.com/sec/8-k/item/8.01",
            })
    elif query.startswith("8k_items:"):
        items = query.split(":", 1)[1]
        for f in ff.recent_8k(items=items, limit=50):
            matches.append({
                "accession": f.accession_number, "company": f.company_name,
                "filed_at": f.filed_at, "items": f.detected_items,
            })
    elif query.startswith("activist:"):
        name = query.split(":", 1)[1]
        for f in ff.recent_13d(activist=name, limit=50):
            matches.append({
                "accession": f.accession_number, "company": f.company_name,
                "filed_at": f.filed_at, "activist": f.activist_filers,
                "percent": f.percent_of_class, "cusip": f.cusip,
            })
    elif query.startswith("atm:"):
        try:
            min_m = float(query.split(":", 1)[1])
        except ValueError:
            min_m = 0.0
        for f in ff.recent_atm(min_shelf_million_usd=min_m, limit=50):
            matches.append({
                "accession": f.accession_number, "company": f.company_name,
                "filed_at": f.filed_at, "shelf_million": f.shelf_size_million_usd,
                "agents": f.sales_agents,
            })
    else:
        print(f"ERROR: unknown query shape: {query!r}", flush=True)
        print("Supported: 'buried_8k', '8k_items:CODE,CODE', 'activist:NAME', 'atm:MIN_MILLION'",
              flush=True)
        return 2

    print(f"hits: {len(matches)}", flush=True)
    for m in matches[:5]:
        print(f"  {m.get('filed_at','')[:10]} {m.get('company','')[:40]} — {m.get('accession','')}", flush=True)
    if len(matches) > 5:
        print(f"  … and {len(matches) - 5} more", flush=True)

    # Outputs for subsequent workflow steps
    _set_action_output("hit_count", str(len(matches)))
    _set_action_output("filings_json", json.dumps(matches))

    # Side effects
    if open_issue:
        for m in matches:
            title = f"FilingFirehose: {m.get('company', '?')} — {query}"
            body = f"```json\n{json.dumps(m, indent=2)}\n```\n\nVia FilingFirehose (`{query}`)."
            _gh_open_issue(title, body)
    if webhook_url:
        _post_webhook(webhook_url, {"query": query, "hit_count": len(matches), "filings": matches})

    if fail_on_hit and matches:
        print(f"::error::FilingFirehose watcher matched {len(matches)} filings; failing the job.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
