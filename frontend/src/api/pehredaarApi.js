// Mock data layer for the Pehredaar frontend.
//
// This module is the only place that knows the current data source is a
// static sample built from a real Phase 3 scan run, not a live API. Every
// exported function returns a Promise shaped like the real endpoints
// described in CLAUDE.md section 7, so pointing this file at
// `fetch(import.meta.env.VITE_API_BASE + ...)` later is a small change,
// not a rewrite of the pages that call it.

import scanSample from '../data/scanSample.json'

export const ALLOWED_SUFFIXES = ['.gov.in', '.nic.in', '.ac.in', '.edu.in', '.res.in']

const MOCK_LATENCY_MS = 350

function delay(value) {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS))
}

// Lowercases, strips a scheme, path, query and port, the same shape of
// cleanup the real API applies server side before it ever reaches a fetch.
export function normalizeDomainInput(raw) {
  let value = (raw || '').trim().toLowerCase()
  value = value.replace(/^[a-z]+:\/\//, '')
  value = value.split('/')[0]
  value = value.split('?')[0]
  value = value.split(':')[0]
  return value
}

export function isAllowedDomain(domain) {
  return ALLOWED_SUFFIXES.some((suffix) => domain.endsWith(suffix))
}

// Mirrors POST /scan followed by GET /domains/{domain}, collapsed into one
// call because the mock has no queue to poll. Domain names are only ever
// returned here because the caller supplied the domain directly, per
// CLAUDE.md section 2 rule 6.
export function lookupDomain(rawDomain) {
  const domain = normalizeDomainInput(rawDomain)

  if (!domain) {
    return delay({ status: 'rejected', domain, reason: 'Enter a domain to check.' })
  }

  if (!isAllowedDomain(domain)) {
    return delay({
      status: 'rejected',
      domain,
      reason: `${domain} is outside the scope of this scanner. Only ${ALLOWED_SUFFIXES.join(', ')} hosts are accepted.`,
    })
  }

  const record = scanSample.lookup.find((entry) => entry.domain === domain)

  if (!record) {
    return delay({
      status: 'not_scanned',
      domain,
      reason: 'This domain has not been scanned yet. No evidence found means we have not looked, not that the site is clean.',
    })
  }

  return delay({ status: 'found', domain, record })
}

// Mirrors GET /findings/recent with domain names redacted by default, per
// CLAUDE.md section 2 rule 6 and section 7.
export function getRecentFindings() {
  return delay(scanSample.recentFindings)
}

export function getScanMeta() {
  return delay({ sourceScan: scanSample.sourceScan, totalScanned: scanSample.totalScanned })
}
