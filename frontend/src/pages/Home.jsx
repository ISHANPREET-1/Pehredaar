import { Link } from 'react-router-dom'
import GlitchBackground from '../components/GlitchBackground'
import './Home.css'

const GITHUB_URL = 'https://github.com/ISHANPREET-1/pehredaar'

function Home() {
  return (
    <div className="home-page">
      <GlitchBackground />
      <div className="home-content">
        <h1 className="home-title">Pehredaar</h1>
        <div className="home-actions">
          <Link to="/findings" className="btn btn-primary">
            Check a domain
          </Link>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="btn btn-secondary">
            GitHub
          </a>
        </div>
      </div>
    </div>
  )
}

export default Home
