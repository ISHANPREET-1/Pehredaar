import GlitchBackground from '../components/GlitchBackground'
import './About.css'

function About() {
  return (
    <div className="about-page">
      <GlitchBackground dimmed />
      <div className="about-shell">
        <div className="panel about-content">
          <h1>About Pehredaar</h1>

          <section>
            <h2>What this checks</h2>
            <p>
              Pehredaar looks for Indian government and education sites that have been silently hacked to serve
              illegal gambling and pharma spam. Attackers who compromise a .gov.in, .nic.in, .ac.in or .edu.in site
              often show the injected content only to certain visitors, usually mobile users arriving from a Google
              search, and show the site's own administrator a normal page. That is why the hack can survive for
              months without anyone noticing.
            </p>
            <p>
              Pehredaar fetches each site as four different visitors, compares what each one is served, and scores
              the difference. It only ever reads public pages with GET and HEAD requests. It does not log in, guess
              passwords, fuzz paths or run any exploit code against a scanned site.
            </p>
          </section>

          <section>
            <h2>What clean actually means</h2>
            <p>
              A clean result means our scan found no evidence of injected content. It does not mean the site has
              been certified safe. Our signals catch known patterns of cloaked and persistent injection, not every
              possible compromise, and a site can change between scans.
            </p>
          </section>

          <section>
            <h2>The four fetch profiles</h2>
            <p>Every domain is fetched as four separate visitors, one after another, with a polite delay between each.</p>
            <ul className="profile-list">
              <li>
                <strong>Desktop.</strong> A normal Chrome browser on a Windows desktop, the view most site owners
                see themselves.
              </li>
              <li>
                <strong>Mobile.</strong> Chrome on an Android phone, with no referring page.
              </li>
              <li>
                <strong>Mobile from search.</strong> The same Android phone, but arriving with a Google search page
                as the referrer. Cloaked spam usually targets this exact combination.
              </li>
              <li>
                <strong>Googlebot.</strong> The Googlebot smartphone user agent, to see what gets indexed and shown
                in search results.
              </li>
            </ul>
            <p>
              We spoof these user agents because that is the only way to observe cloaking from the outside. We do
              not hide who we are in any other sense, our source IPs and contact address are public, and any domain
              owner can opt out of future scans.
            </p>
          </section>

          <section>
            <h2>Where the seed list comes from</h2>
            <p>
              The scanned domains are drawn from public Wikipedia pages listing IITs, NITs, central universities,
              IIITs and AIIMS campuses, plus each state and union territory's official government portal, every
              entry fetched live and checked against DNS before it is scanned.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}

export default About
