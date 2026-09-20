# CLAUDE.md

Project guide for Claude Code. Read this fully before writing any code. Follow it over your own defaults.

---

## 1. What we are building

**Pehredaar** is a read only watchdog that finds Indian government and education websites that have been silently hacked to serve illegal gambling and pharma spam.

Attackers compromise `.gov.in`, `.nic.in`, `.ac.in` and `.edu.in` sites and inject betting content (satta, rummy, teen patti, slot). They serve that content only to specific visitors, usually mobile users arriving from a Google search, and show a normal page or a 404 to everyone else. The site's own administrator visits the homepage, sees nothing wrong, and the hack survives for months.

Pehredaar fetches each site as four different visitors, compares what each one is served, and scores the difference. When a site flips from clean to compromised it records the evidence and drafts a disclosure notice to the site owner and CERT-In.

**Why this has not been built:** single URL cloaking checkers exist as paid SEO products, where the site owner adds their own site. A district office or a small college will never buy one, because they do not know they are hacked. Nobody runs this continuously across the whole Indian public sector. That gap is the project.

**Context:** this is a submission to the WeMakeDevs x AWS "First Commit" hackathon (Ship It track, deployed on AWS, judged on real world impact, working execution and AWS architecture). Time is very short. Working beats complete.

---

## 2. Non negotiable rules of conduct

These are hard limits. If a task in this file seems to require breaking one, stop and ask.

1. **Read only. Always.** `GET` and `HEAD` only. Never `POST`, `PUT` or `DELETE` to any scanned host.
2. **No probing of any kind.** No login attempts, no credential guessing, no admin panel discovery, no path fuzzing or wordlists, no SQLi, XSS or any payload injection, no port scanning, no vulnerability scanning, no exploit code anywhere in this repo.
3. **Public pages only.** Homepage, `robots.txt`, `sitemap.xml`, and pages linked from those. Nothing behind a login. Nothing at a guessed URL.
4. **Be polite.** One request at a time per host, minimum 2 seconds between requests to the same host, global concurrency cap, honour `Retry-After`, back off on 429 and 5xx, hard cap of 8 requests per host per scan.
5. **Honour opt out.** `seeds/optout.txt` is checked before every fetch. A domain listed there is never contacted again.
6. **Responsible disclosure.** The public dashboard shows counts and breakdowns by state and sector. It never lists compromised domain names. A per domain result is shown only when the user types that domain themselves.
7. **Defang attacker infrastructure.** Any attacker URL or domain stored or displayed is written as `hxxp://evil[.]example`. Never render it as a clickable link, in the API, the UI, logs or the report.
8. **No PII.** We store page HTML, headers and our own verdicts. If a fetched page contains personal data, we do not index it, display it or ship it to the frontend.
9. **Honesty in output.** A "clean" verdict means we found no evidence, not that the site is safe. Every API response and UI surface must carry that wording.

---

## 3. Tech stack

Fixed. Do not substitute.

| Layer | Choice | Note |
|---|---|---|
| Language | Python 3.12 | Match the Lambda runtime exactly |
| HTTP client | `httpx` | Sync client, explicit timeouts, `follow_redirects=False` so we walk the chain ourselves |
| HTML parsing | `beautifulsoup4` with the stdlib `html.parser` | No `lxml`, no binary wheels |
| Models | `pydantic` v2 | Every boundary object is a model, no loose dicts |
| API | `FastAPI` + `Mangum` | One Lambda behind API Gateway HTTP API |
| AWS SDK | `boto3` | Provided by the Lambda runtime, still pinned for local dev |
| Infra as code | AWS SAM (`template.yaml`) | `sam build` without containers, `sam deploy --guided` |
| Storage | DynamoDB single table, S3 for snapshots | |
| Queue | SQS standard + DLQ | |
| Schedule | EventBridge Scheduler | |
| Alerts | SES | |
| Tests | `pytest`, `respx` (HTTP mocks), `moto` (AWS mocks) | |
| Region | `ap-south-1` (Mumbai) | Many government hosts throttle or block foreign IPs |

### Environment constraints (important)

- Development machine is a 2016 Intel MacBook on macOS 12.7. **CPU only. No Docker. No CUDA or Metal. No ML models, no embeddings, no GPU anything.**
- Every dependency must be pure Python or ship a universal wheel. If a package needs a compiler, pick a different package.
- If `sam build` asks for a container, use plain `sam build` with the local Python 3.12 runtime. If that fails, fall back to zipping `src/` and the `site-packages` directory by hand in `scripts/deploy.sh`.
- Everything the detector does must run locally with no AWS account: `python -m pehredaar.cli scan <domain>` has to work offline against fixtures and online against a live domain.

---

## 4. Architecture

```
EventBridge Scheduler (every 6h)
        |
        v
  dispatcher Lambda  ---- reads domains due for scan from DynamoDB
        |
        v
      SQS queue  (1 message = 1 domain)            --> DLQ after 2 retries
        |
        v
   worker Lambda  (reserved concurrency 20, timeout 60s)
        |
        |-- 4 sequential fetches of the domain (the four profiles)
        |-- run signal modules
        |-- score, decide band
        |-- gzip + write snapshots to S3
        |-- write scan + update domain state in DynamoDB
        |
        v
  DynamoDB Stream (band changed only)
        |
        v
   notifier Lambda ---- SES: internal alert + drafted disclosure notice

  API Gateway HTTP API --> api Lambda (FastAPI + Mangum) --> DynamoDB
  CloudFront + S3 (static site) --> calls the API
```

### The four fetch profiles

Every domain is fetched four times, sequentially, with a delay in between.

| Profile key | User Agent | Extra headers |
|---|---|---|
| `desktop` | Chrome on Windows desktop | none |
| `mobile` | Chrome on Android | none |
| `mobile_serp` | Chrome on Android | `Referer: https://www.google.com/` |
| `googlebot` | Googlebot smartphone | none |

We spoof user agents because that is the only way to observe cloaking. We do not hide who we are in any other sense: the public site carries an about page naming the project, its purpose, its source IPs and a contact address, and `seeds/optout.txt` is honoured. Document this tradeoff in the README.

For each profile capture: final URL after the redirect chain, every hop in the chain, status code, response headers, raw HTML, elapsed time.

---

## 5. Detection logic

This is the core of the project. Get it right before anything else.

### Two classes of finding

- **Class A, cloaked injection.** The spam appears in some profiles and not others. This is the interesting case and the strongest evidence.
- **Class B, persistent injection.** The spam appears in all four profiles. A `.gov.in` page about teen patti is still a hacked page, so this is a finding too, just a different class.

Report both. Label them distinctly.

### Signals

Each signal module lives in `src/pehredaar/signals/` and returns a `Signal(name, fired: bool, weight: float, evidence: dict)`. No module is allowed to make a final verdict.

| Id | Module | What it looks for |
|---|---|---|
| S1 | `redirect.py` | Final host differs between profiles, or a redirect chain leaves the original registrable domain in one profile only |
| S2 | `keywords.py` | Gambling and pharma keyword hits, per profile, with position and surrounding text |
| S3 | `outbound.py` | External link hosts present in one profile and absent in the others |
| S4 | `title.py` | `<title>` or meta description differs materially between profiles |
| S5 | `hidden.py` | Keyword bearing text inside `display:none`, `visibility:hidden`, `font-size:0`, `text-indent:-9999px`, or absolute positioning far off screen |
| S6 | `similarity.py` | Normalised text similarity between `googlebot` and `desktop` below threshold, using Jaccard over token 5-grams |
| S7 | `injected_script.py` | `<script src>` to a host that is neither the site's own nor on a known CDN allowlist, low weight on its own |

### Normalisation before any diff

`normalize.py` strips the things that legitimately differ between two fetches of the same page, otherwise every site looks cloaked:

- timestamps, dates, "last updated" strings
- CSRF tokens, nonces, session ids, cache busting query strings
- visitor counters and hit counts
- CSS and JS file hashes
- whitespace, comments, and attribute order
- mobile versus desktop layout differences (compare extracted visible text, not raw HTML)

### Scoring

Weighted sum of fired signals, normalised to 0 to 100. Bands:

| Score | Band |
|---|---|
| 0 to 19 | `clean` |
| 20 to 49 | `suspicious` |
| 50 to 74 | `likely_compromised` |
| 75 to 100 | `compromised` |

**Hard rule: `compromised` requires at least two independent signals firing.** A keyword hit alone is never enough.

### False positive guards

These matter more than raw detection. A wrong accusation against a government site is the one failure mode we cannot afford.

- **Legal context downweight.** If gambling keywords sit near enforcement or legal words (Act, Section, prohibition, seized, arrested, FIR, advisory, banned, notification), downweight heavily. Police and court sites legitimately discuss satta.
- **Legitimate lottery allowlist.** State lottery departments and official lottery pages belong in `data/allowlist.yaml`.
- **Anti spam advisory pages.** Cyber cell awareness pages list the same keywords on purpose.
- **Layout noise.** Never fire S6 on raw HTML differences alone.
- Everything above lives in `data/allowlist.yaml` and `data/keywords.yaml` as data, not as code. Claude must not hardcode keyword lists inside Python files.

---

## 6. Data model

### DynamoDB, single table `pehredaar`

| Entity | PK | SK | Key attributes |
|---|---|---|---|
| Domain | `DOMAIN#<domain>` | `META` | sector, state, institution_name, band, score, first_seen, last_scanned, last_band_change, scan_interval_hours, opt_out |
| Scan | `DOMAIN#<domain>` | `SCAN#<iso8601>` | scan_id, band, score, signals[], profiles{status,final_host}, snapshot_prefix, ttl (30 days) |
| Finding | `FINDING#<yyyy-mm>` | `<iso8601>#<domain>` | domain, from_band, to_band, evidence_prefix, notified_at, notice_s3_key |
| Stats | `STATS` | `GLOBAL` or `STATE#<code>` or `SECTOR#<gov\|edu>` | counts per band, last_updated |
| Rate limit | `RATE#<ip_hash>` | `<window>` | count, ttl |

GSI1: `gsi1pk = BAND#<band>`, `gsi1sk = <score padded>` for listing by band.

On demand billing. TTL attribute enabled on `ttl`.

### S3, bucket `pehredaar-snapshots-<account>`

```
<domain>/<scan_id>/<profile>.html.gz
<domain>/<scan_id>/meta.json
notices/<domain>/<scan_id>.md
```

Block all public access. Lifecycle rule expires objects after 90 days. Server side encryption with the S3 managed key.

---

## 7. API surface

FastAPI, one Lambda, all responses are pydantic models.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness, build sha |
| GET | `/stats` | Totals by band, by state, by sector, last scan time |
| GET | `/domains/{domain}` | Latest verdict for one domain. 404 if never scanned |
| POST | `/scan` | Queue an on demand scan. This is the "check your college" feature |
| GET | `/scan/{job_id}` | Poll an on demand scan |
| GET | `/findings/recent` | Recent band changes, domain names redacted unless the caller supplies the domain |

Rules for `/scan`:
- Accept only hosts ending in `.gov.in`, `.nic.in`, `.ac.in`, `.edu.in`, `.res.in`. Reject everything else with a clear message.
- Reject anything in `optout.txt`.
- Per IP token bucket in DynamoDB, 5 scans per hour.
- Return a job id immediately, never block the request on the scan.

---

## 8. Repository layout

```
pehredaar/
  CLAUDE.md
  README.md
  .env.example
  .gitignore
  Makefile
  requirements.txt
  requirements-dev.txt
  template.yaml
  seeds/
    domains.csv           # domain,sector,state,institution_name
    optout.txt
  src/pehredaar/
    __init__.py
    config.py             # env driven settings, pydantic-settings
    models.py             # FetchResult, Signal, ScanResult, DomainState
    fetcher.py            # profiles, redirect chain, politeness, retries
    normalize.py          # html to comparable text
    signals/
      __init__.py         # registry
      redirect.py keywords.py outbound.py title.py hidden.py similarity.py injected_script.py
    scoring.py
    detector.py           # fetch -> signals -> score -> ScanResult
    storage/
      ddb.py s3.py
    handlers/
      dispatcher.py worker.py api.py notifier.py
    notices.py            # disclosure notice drafting
    cli.py
    data/
      keywords.yaml allowlist.yaml profiles.yaml
  tests/
    fixtures/             # saved html pages, one directory per scenario
    test_fetcher.py test_normalize.py test_signals.py test_scoring.py test_detector.py test_api.py
  scripts/
    build_seed_list.py
    deploy.sh
```

---

## 9. Build order

Do not skip ahead. Each phase ends with something runnable.

**Phase 0. Skeleton.** Repo layout, `requirements.txt`, `config.py`, `models.py`, `Makefile`, passing empty test suite. No AWS.

**Phase 1. Detector core, offline.** `fetcher.py`, `normalize.py`, all seven signal modules, `scoring.py`, `detector.py`. Full unit tests against fixtures in `tests/fixtures/`. Deliverable: `python -m pehredaar.cli scan --fixture cloaked_gambling` prints a verdict with per signal evidence.

**Phase 2. Live single domain.** The same CLI against a real domain, with politeness and retries. Deliverable: `python -m pehredaar.cli scan tiet.ac.in` works and writes a JSON report locally.

**Phase 3. Batch, local.** Read `seeds/domains.csv`, scan N domains with a concurrency cap, write results to a local SQLite or JSONL file. Deliverable: a first real scan of 200 domains and a count of what it found. **This is the moment the project becomes real. Prioritise reaching it.**

**Phase 4. AWS.** `template.yaml` with DynamoDB, S3, SQS, DLQ, dispatcher, worker, EventBridge Scheduler. Storage adapters. Deployed and scanning on a schedule.

**Phase 5. API.** FastAPI handler, Mangum, API Gateway. All endpoints above.

**Phase 6. Notifier.** DynamoDB stream to SES. Disclosure notice drafting in `notices.py`.

**Phase 7. Frontend and submission.** Static site to S3 and CloudFront. Demo video. AWS Builder Center blog post.

Cut list if time runs out, in this order: S7, the notifier, the on demand scan endpoint. Never cut the false positive guards.

---

## 10. Working rules for Claude Code

### Process

- **One step at a time.** Do the current task, report what changed and what to verify, then stop. Do not chain three phases together because they look related.
- **Ask before you invent.** If a decision is not covered here, ask rather than picking something and building on it.
- **State the plan first for anything over about 100 lines.** Short plan, then the code.
- **Never say a step is done without running it.** Run the tests, run the CLI, paste the real output.
- The developer has no browser tooling in Claude Code and checks the UI himself. **Never ask for a screenshot and never write a step that depends on you seeing one.**

### Code

- Type hints on every function. `pydantic` models at every boundary.
- No bare `except`. Catch specific exceptions, log with context, re raise or return a typed failure.
- Every network call has an explicit timeout. No unbounded retries. Exponential backoff with jitter.
- Structured logging as JSON to stdout. No `print` outside `cli.py`.
- Configuration comes from `config.py` reading environment variables. No magic numbers scattered through modules, no hardcoded ARNs, bucket names, table names or keyword lists.
- Keyword lists, allowlists and profile definitions live in `data/*.yaml`.
- Modules stay small. If a file passes roughly 300 lines, split it.
- No dead code, no commented out blocks, no "in a real implementation" stubs left behind.

### Tests

- **Tests never touch the network.** Mock with `respx`. Mock AWS with `moto`.
- Every signal module needs a fixture that fires it and a fixture that must not fire it.
- Required fixture scenarios in `tests/fixtures/`:
  - `clean_college` a normal site
  - `cloaked_gambling` spam for `mobile_serp` only
  - `cloaked_googlebot` spam for `googlebot` only
  - `doorway_persistent` spam in all four profiles
  - `police_advisory` gambling keywords in a legitimate enforcement context, must stay `clean`
  - `state_lottery` an official lottery page, must stay `clean`
  - `dynamic_noise` identical page with changing timestamps and tokens, must stay `clean`
- Run `pytest` before declaring any phase complete.

### Security of our own code

- No secrets in the repo. `.env` is gitignored, `.env.example` lists the variable names only.
- IAM in `template.yaml` is least privilege per function. The worker does not get `dynamodb:*`. The API Lambda has no write access to the snapshot bucket.
- Never log full response bodies. Log sizes, hashes and the extracted signals.
- Validate and normalise every domain from user input before it reaches a fetch: lowercase, strip scheme and path, reject IPs, reject ports, reject anything outside the allowed suffixes.
- The fetcher must refuse private and loopback address ranges after DNS resolution, to prevent SSRF through the on demand scan endpoint. This is required, not optional.

### Git

- Small commits, present tense, one concern each: `add keyword signal module`, `wire worker lambda to sqs`.
- Commit at the end of every phase.
- Never commit `seeds/domains.csv` rows that came from a source we cannot cite in the README.

### Writing style for anything human readable

README, notices, API messages, commit bodies, blog post:

- Plain words, short sentences.
- **No dashes as punctuation, and no em dashes.** Use a comma, a full stop or a separate sentence.
- No marketing language, no "leveraging", no "seamless", no "revolutionary".
- Do not overclaim. We detect evidence of injection. We do not certify any site as safe.

---

## 11. Things Claude Code must not do

- Do not add LangChain, an LLM call, an ML model, an embedding, or a vector database. The detector is deterministic string and structure comparison. That is a feature, and it is defensible in an interview.
- Do not add Docker, Kubernetes or a container build.
- Do not add a database server. DynamoDB and local files only.
- Do not add Terraform or CDK. SAM only.
- Do not write any code that attacks, probes, exploits or authenticates against a scanned host.
- Do not publish compromised domain names anywhere in the public frontend.
- Do not scale the seed list beyond a few thousand domains during the hackathon. Politeness over coverage.
- Do not refactor or reorganise files that the current task did not ask about.

---

## 12. Definition of done for the hackathon

- [ ] Deployed on AWS in `ap-south-1` with a public URL
- [ ] A real scan run over at least 500 seed domains, with results in DynamoDB
- [ ] At least one genuine finding, verified by hand, with a saved snapshot as evidence
- [ ] One disclosure notice drafted and actually sent to a site owner or CERT-In
- [ ] `/stats` and the "check your domain" lookup both working from the public site
- [ ] `pytest` green
- [ ] README with the architecture diagram, the cost note, the ethics section and the data sources
- [ ] Three minute demo video: the problem, a live lookup, the architecture, what we learned
- [ ] AWS Builder Center blog post linked in the submission