// Live data layer for the Pehredaar frontend, talking to the local FastAPI backend at
// http://localhost:8000. This module used to return a static sample built from a real Phase 3
// scan run, this is the small change that swap was designed for, only this file changed, the
// pages that call it did not.

export const ALLOWED_SUFFIXES = ['.gov.in', '.nic.in', '.ac.in', '.edu.in', '.res.in']

const API_BASE = 'http://localhost:8000'

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

// A live single domain lookup has no seed list row to read a sector from, so this labels it from
// the suffix alone, the same suffix families CLAUDE.md already defines, not a new classification.
function sectorLabelForDomain(domain) {
  if (domain.endsWith('.gov.in') || domain.endsWith('.nic.in')) return 'Government'
  if (domain.endsWith('.ac.in') || domain.endsWith('.edu.in') || domain.endsWith('.res.in')) return 'Education'
  return 'Other'
}

async function readErrorDetail(response) {
  try {
    const body = await response.json()
    return body.detail
  } catch {
    return undefined
  }
}

// Calls the real GET /domains/{domain}, which runs a live scan through the existing fetcher and
// detector, no queue, no polling, this request itself waits for the scan to finish, several
// seconds is normal. Domain names are only ever returned here because the caller supplied the
// domain directly, per CLAUDE.md section 2 rule 6.
export async function lookupDomain(rawDomain) {
  const domain = normalizeDomainInput(rawDomain)

  if (!domain) {
    return { status: 'rejected', domain, reason: 'Enter a domain to check.' }
  }

  if (!isAllowedDomain(domain)) {
    return {
      status: 'rejected',
      domain,
      reason: `${domain} is outside the scope of this scanner. Only ${ALLOWED_SUFFIXES.join(', ')} hosts are accepted.`,
    }
  }

  let response
  try {
    response = await fetch(`${API_BASE}/domains/${encodeURIComponent(domain)}`)
  } catch {
    return {
      status: 'not_scanned',
      domain,
      reason: `Could not reach the Pehredaar API at ${API_BASE}. Make sure it is running, "make api" in the project root.`,
    }
  }

  if (response.status === 400 || response.status === 403) {
    const detail = await readErrorDetail(response)
    return { status: 'rejected', domain, reason: detail || `${domain} was rejected by the scanner.` }
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response)
    return {
      status: 'not_scanned',
      domain,
      reason:
        detail ||
        'The live scan could not complete just now. This does not mean the site is clean or compromised, we simply could not reach it.',
    }
  }

  const scanResult = await response.json()

  return {
    status: 'found',
    domain,
    record: {
      domain: scanResult.domain,
      band: scanResult.band,
      score: Math.round(scanResult.score * 10) / 10,
      institutionName: 'Not tracked for a single domain lookup',
      sectorLabel: sectorLabelForDomain(domain),
      state: 'Not tracked for a single domain lookup',
      injectionClass: scanResult.injection_class,
      scannedAt: scanResult.finished_at,
    },
  }
}

// Calls the real GET /findings/recent, already redacted server side, no domain names, matching
// CLAUDE.md section 2 rule 6 and section 7.
export async function getRecentFindings() {
  try {
    const response = await fetch(`${API_BASE}/findings/recent`)
    if (!response.ok) return []
    return await response.json()
  } catch {
    return []
  }
}
