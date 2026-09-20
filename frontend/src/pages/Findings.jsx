import { useEffect, useState } from 'react'
import GlitchBackground from '../components/GlitchBackground'
import Modal from '../components/Modal'
import { ALLOWED_SUFFIXES, getRecentFindings, lookupDomain } from '../api/pehredaarApi'
import './Findings.css'

const BAND_LABELS = {
  clean: 'Clean',
  suspicious: 'Suspicious',
  likely_compromised: 'Likely compromised',
  compromised: 'Compromised',
}

function formatScanTime(iso) {
  const date = new Date(iso)
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  }) + ' UTC'
}

function bandNote(band) {
  if (band === 'clean') {
    return 'Clean means no evidence of injection was found in this scan. It does not certify the site as safe.'
  }
  return 'This reflects automated evidence from one scan, not a certified verdict. It is a reason to look closer, not a final judgment.'
}

function BandPill({ band }) {
  return <span className={`band-pill band-${band}`}>{BAND_LABELS[band] || band}</span>
}

function Findings() {
  const [domainInput, setDomainInput] = useState('')
  const [result, setResult] = useState(null)
  const [checking, setChecking] = useState(false)
  const [recent, setRecent] = useState([])
  const [recentLoading, setRecentLoading] = useState(true)
  const [showRecent, setShowRecent] = useState(false)

  useEffect(() => {
    let cancelled = false
    getRecentFindings().then((entries) => {
      if (!cancelled) {
        setRecent(entries)
        setRecentLoading(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()
    setChecking(true)
    setResult(null)
    const outcome = await lookupDomain(domainInput)
    setResult(outcome)
    setChecking(false)
  }

  return (
    <div className="findings-page">
      <GlitchBackground dimmed />
      <div className="findings-content">
        <div className="panel lookup-panel">
          <h1 className="lookup-heading">Check a domain</h1>
          <p className="lookup-subheading">
            Enter a government or education domain to see its latest scan result. Only domains ending in{' '}
            {ALLOWED_SUFFIXES.join(', ')} are accepted.
          </p>
          <form className="lookup-form" onSubmit={handleSubmit}>
            <input
              type="text"
              inputMode="url"
              autoComplete="off"
              spellCheck="false"
              placeholder="yourcollege.ac.in"
              value={domainInput}
              onChange={(event) => setDomainInput(event.target.value)}
              className="lookup-input"
            />
            <button type="submit" className="btn btn-primary" disabled={checking}>
              {checking ? 'Checking...' : 'Check domain'}
            </button>
          </form>

          {result && result.status === 'rejected' && (
            <div className="result-card result-card-rejected">
              <p>{result.reason}</p>
            </div>
          )}

          {result && result.status === 'not_scanned' && (
            <div className="result-card result-card-neutral">
              <p className="result-domain">{result.domain}</p>
              <p>{result.reason}</p>
            </div>
          )}

          {result && result.status === 'found' && (
            <div className="result-card">
              <div className="result-header">
                <p className="result-domain">{result.record.domain}</p>
                <BandPill band={result.record.band} />
              </div>
              <dl className="result-meta">
                <div>
                  <dt>Institution</dt>
                  <dd>{result.record.institutionName}</dd>
                </div>
                <div>
                  <dt>Sector</dt>
                  <dd>{result.record.sectorLabel}</dd>
                </div>
                <div>
                  <dt>State</dt>
                  <dd>{result.record.state}</dd>
                </div>
                <div>
                  <dt>Score</dt>
                  <dd>{result.record.score} / 100</dd>
                </div>
                <div>
                  <dt>Last scanned</dt>
                  <dd>{formatScanTime(result.record.scannedAt)}</dd>
                </div>
              </dl>
              <p className="result-note">{bandNote(result.record.band)}</p>
            </div>
          )}
        </div>

        <button type="button" className="btn btn-secondary recent-trigger" onClick={() => setShowRecent(true)}>
          View recent scan activity
        </button>
      </div>

      {showRecent && (
        <Modal title="Recent scan activity" onClose={() => setShowRecent(false)}>
          <p className="recent-intro">
            Drawn from a real Phase 3 batch scan. Domain names are withheld here and shown only when you look up
            that domain yourself, per our disclosure policy.
          </p>
          {recentLoading && <p className="recent-loading">Loading recent activity...</p>}
          {!recentLoading && (
            <ul className="recent-list">
              {recent.map((entry, index) => (
                <li key={index} className="recent-item">
                  <BandPill band={entry.band} />
                  <span className="recent-sector">{entry.sectorLabel}</span>
                  <span className="recent-state">{entry.state}</span>
                  <span className="recent-score">{entry.score} / 100</span>
                  <span className="recent-time">{formatScanTime(entry.scannedAt)}</span>
                </li>
              ))}
            </ul>
          )}
        </Modal>
      )}
    </div>
  )
}

export default Findings
