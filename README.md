# Pehredaar

This submission targets the WeMakeDevs x AWS First Commit hackathon's Build It track. Everything under Run locally below is open source, runs entirely on your own machine, and needs no AWS account, no API keys and no payment.

Pehredaar is a read only watchdog that finds Indian government and education websites that have been silently hacked to serve illegal gambling and pharma spam. Attackers compromise `.gov.in`, `.nic.in`, `.ac.in` and `.edu.in` sites and inject betting content that is shown only to specific visitors, usually mobile users arriving from a Google search, while the site's own administrator still sees a normal page. Pehredaar fetches each site as four different visitors, compares what each one is served, and scores the difference, so a hack like this gets found instead of surviving for months unnoticed.

The detector itself is finished and tested locally, an offline scanner against saved fixtures, a live single domain fetcher, and a batch scanner that has already run against real government and education domains. AWS infrastructure code exists for the Ship It track but has not been deployed, see AWS deployment status below. See `CLAUDE.md` for the full build plan.

## Run locally

Requires Python 3.12.

```
make install   # pip install -r requirements.txt -r requirements-dev.txt
make test      # pytest, offline, no network or AWS calls
```

Scan a saved fixture, fully offline:

```
PYTHONPATH=src python -m pehredaar.cli scan --fixture cloaked_gambling
```

Scan one live domain, only GET and HEAD requests, no AWS account needed:

```
PYTHONPATH=src python -m pehredaar.cli scan tiet.ac.in
```

Scan every domain in a seed list and write results to `out/scan-<timestamp>.jsonl`:

```
PYTHONPATH=src python -m pehredaar.cli batch seeds/domains.csv --limit 50
```

`make scan DOMAIN=example.ac.in` runs the same single domain scan through the Makefile.

`.env.example` lists the environment variables the AWS handlers read, region, table name, bucket name, queue URL, thresholds. None of them are needed for the commands above, they only matter once the Lambda handlers in `src/pehredaar/handlers/` are actually deployed.

### Frontend, optional

A static React demo lives in `frontend/`, plain Vite and React, no TypeScript. It reads from a JSON sample built from a real batch scan, not a live API.

```
cd frontend
npm install
npm run dev
```

## AWS deployment status

`template.yaml` defines the infrastructure this project was designed for, a DynamoDB table, an S3 snapshot bucket, an SQS queue with a dead letter queue, and an EventBridge Scheduler rule. The dispatcher and worker Lambda handlers in `src/pehredaar/handlers/` are fully implemented and wired to that infrastructure through `src/pehredaar/storage/`.

The API Lambda, FastAPI plus Mangum, and the SES notifier Lambda are stubs only, a docstring and nothing else, left for a later phase. Neither is included in `template.yaml` yet.

None of this has been deployed to a live AWS account. That was the plan for the hackathon's Ship It track, but it did not happen in the time available. What is here is infrastructure as code and two working Lambda handlers, not a running deployment, and this README will not claim otherwise.

## Seed list sources

`seeds/domains.csv` is built by `scripts/build_seed_list.py` from these pages, fetched live, never invented. Every row is a domain that resolved over DNS at build time, restricted to `.gov.in`, `.nic.in`, `.ac.in`, `.edu.in` and `.res.in`.

- Wikipedia, [Indian Institutes of Technology](https://en.wikipedia.org/wiki/Indian_Institutes_of_Technology)
- Wikipedia, [National Institutes of Technology](https://en.wikipedia.org/wiki/National_Institutes_of_Technology)
- Wikipedia, [List of central universities in India](https://en.wikipedia.org/wiki/List_of_central_universities_in_India)
- Wikipedia, [Indian Institutes of Information Technology](https://en.wikipedia.org/wiki/Indian_Institutes_of_Information_Technology)
- Wikipedia, [All India Institutes of Medical Sciences](https://en.wikipedia.org/wiki/All_India_Institutes_of_Medical_Sciences)
- Wikipedia, [States and union territories of India](https://en.wikipedia.org/wiki/States_and_union_territories_of_India), used only for the canonical list of state and union territory names, each one's own Wikipedia article infobox gives that state's official government portal

For the four sources that list institutions without a website column, the script follows each institution's own Wikipedia article and reads the official website out of its infobox, so the domain still traces back to a citable page, not a guess.

### Reported incident domains

One row in `seeds/domains.csv` has `sector` set to `reported_2026` instead of `gov` or `edu`, kept separate from the general population on purpose:

- `maharashtra.gov.in`, named in [Illegal betting syndicates continue to hijack government websites, sparking regulatory crisis](https://www.storyboard18.com/how-it-works/illegal-betting-syndicates-continue-to-hijack-government-websites-sparking-regulatory-crisis-64906.htm) (Storyboard18) as "the state's main portal" among the Maharashtra government sites compromised.

This is the only specific, named, in-scope domain found across the MediaNama, TechCrunch, LatestLY and GBHackers coverage of this story checked while building the seed list (see the assistant's research notes in this conversation for the full list of articles checked). Most reporting on this story describes affected ministries, states and departments without publishing the exact hacked URL, and the one other domain named in that reporting, `vijaygoel.in`, is a politician's personal site on a bare `.in` domain, outside this project's allowed suffixes. `maharashtra.gov.in` may well have been cleaned up since the report; that is expected and does not make it a bad test case, the same way a malware scanner is tested against a known sample regardless of whether that exact file is still circulating.

## Known limitations

Spoofing the Googlebot user agent without matching Google's real crawl IP ranges may cause some sites' bot defenses to serve a minimal or challenge response that looks like cloaking evidence but is not. This has not been confirmed as the cause for the two cases seen so far, `iitm.ac.in` and `mizoram.gov.in`, where the googlebot profile came back with an empty title and near zero text similarity to the desktop profile. It needs real diagnosis, not a guess, before it should be trusted either way.
