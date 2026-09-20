import LetterGlitch from './LetterGlitch'
import './GlitchBackground.css'

// Same Letter Glitch configuration on every page. Pages that need the
// content readable over it pass `dimmed`, which layers a blurred, darkened
// overlay in front of the canvas rather than changing the component itself.
function GlitchBackground({ dimmed = false }) {
  return (
    <div className="glitch-stage" aria-hidden="true">
      <LetterGlitch
        glitchColors={['#2b4539', '#61dca3', '#61b3dc']}
        glitchSpeed={10}
        centerVignette={true}
        outerVignette={false}
        smooth={true}
      />
      {dimmed && <div className="glitch-overlay" />}
    </div>
  )
}

export default GlitchBackground
