# FilingFirehose Watch — GitHub Action

Watch SEC EDGAR for new 8-K / S-3 / 13D filings matching your criteria.
Trigger CI failures, open issues, or fire webhooks on a hit.

```yaml
- uses: jaablon/filingfirehose-action@v1
  with:
    query: 'buried_8k'           # or '8k_items:1.05', 'activist:Saba', 'atm:50'
    fail_on_hit: 'true'
    open_issue: 'false'
    webhook_url: ''
    api_key: ${{ secrets.FF_API_KEY }}    # optional — without it, free public tier (last 72h)
```

## Query shapes

| Query | What it matches |
|---|---|
| `buried_8k` | 8-K filings where the body language flags items the filer didn't report (cyber under 8.01, etc.) |
| `8k_items:1.05,5.02` | 8-Ks reporting any of the listed item codes |
| `activist:Saba` | Recent Schedule 13D / 13G filings where this activist is tagged (substring match) |
| `atm:50` | Recent at-the-market offerings (S-3 / 424B5) with shelf size ≥ $50M |

## Use cases

**Compliance team** — get notified when a competitor files a 13D on a strategic asset:
```yaml
on: { schedule: [{ cron: '0 */4 * * *' }] }
jobs:
  watch:
    runs-on: ubuntu-latest
    steps:
      - uses: jaablon/filingfirehose-action@v1
        with:
          query: 'activist:Elliott'
          open_issue: 'true'
        env: { GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }} }
```

**Quant team** — fail nightly CI if a buried Item 1.05 (cyber) appears in our portfolio names:
```yaml
- uses: jaablon/filingfirehose-action@v1
  with:
    query: 'buried_8k'
    fail_on_hit: 'true'
```

**Webhook to Slack / Discord** — post matches to your channel:
```yaml
- uses: jaablon/filingfirehose-action@v1
  with:
    query: 'atm:100'
    fail_on_hit: 'false'
    webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

## Outputs

The action sets `hit_count` and `filings_json` outputs:

```yaml
- id: ff
  uses: jaablon/filingfirehose-action@v1
  with: { query: 'buried_8k', fail_on_hit: 'false' }
- run: |
    echo "${{ steps.ff.outputs.hit_count }} buried events today"
    echo "${{ steps.ff.outputs.filings_json }}" | jq '.[].company'
```

## License

MIT.
