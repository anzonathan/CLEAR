'use client';

import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { homeFor } from '@/lib/roles';

const STEPS = [
  {
    n: '01',
    title: 'Pair up',
    body: 'Share a six-character code with your playing partner. You are connected in one tap.',
  },
  {
    n: '02',
    title: 'Pick your end',
    body: 'Start a session or schedule one. Each of you claims an end and mounts a phone behind that baseline.',
  },
  {
    n: '03',
    title: 'Play',
    body: 'When both cameras hold steady the game starts by itself. Your phone chimes, and both ends record together.',
  },
  {
    n: '04',
    title: 'Review',
    body: 'Line calls, ball speed and faults come back from the recording, end by end.',
  },
];

const CALLS = [
  { title: 'In or out', body: 'Every bounce is placed on the court and called. Close calls inside the doubt zone are flagged, not guessed.' },
  { title: 'Ball speed', body: 'Average and top speed, plus the strokes in each rally, from the tracked flight of the ball.' },
  { title: 'Faults', body: 'Foot faults on the serve and service faults are judged against the real court lines.' },
  { title: 'Two views, one court', body: 'Both phones feed one model of the court, so the ball is followed end to end.' },
];

const REFEREE = [
  'Watch both camera feeds live, with the fused court beside them',
  'Calibrate each phone to the real lines by clicking the corners',
  'Set streaming quality for the court’s signal, with floors that keep the ball visible',
  'Run the full analysis on any recorded game',
];

function CourtHero() {
  // Top-down court, End A at the top. Phones sit behind each baseline looking down the court.
  return (
    <svg className="lp-court" viewBox="0 0 420 780" role="img" aria-label="Two phones filming a clay court from opposite ends, tracking a ball that lands in">
      <defs>
        <linearGradient id="lp-cone-a" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#bed95b" stopOpacity=".32" />
          <stop offset="1" stopColor="#bed95b" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="lp-cone-b" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#bed95b" stopOpacity=".32" />
          <stop offset="1" stopColor="#bed95b" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect className="lp-clay" x="40" y="70" width="340" height="640" rx="6" />
      <path className="lp-cone" d="M210 28 L58 400 L362 400 Z" fill="url(#lp-cone-a)" />
      <path className="lp-cone" d="M210 752 L58 380 L362 380 Z" fill="url(#lp-cone-b)" />
      <g className="lp-lines">
        <rect x="70" y="100" width="280" height="580" />
        <line x1="104" y1="100" x2="104" y2="680" />
        <line x1="316" y1="100" x2="316" y2="680" />
        <line x1="104" y1="234" x2="316" y2="234" />
        <line x1="104" y1="546" x2="316" y2="546" />
        <line x1="210" y1="234" x2="210" y2="546" />
        <line x1="210" y1="100" x2="210" y2="112" />
        <line x1="210" y1="668" x2="210" y2="680" />
      </g>
      <line className="lp-net" x1="52" y1="390" x2="368" y2="390" />
      <path className="lp-trail" d="M160 600 Q 196 420 286 262" />
      <circle className="lp-bounce" cx="286" cy="262" r="16" />
      <circle className="lp-ball" cx="286" cy="262" r="7" />
      <g className="lp-call" transform="translate(300 214)">
        <rect width="62" height="30" rx="15" />
        <text x="31" y="20">IN</text>
      </g>
      <g className="lp-phone" transform="translate(194 6)">
        <rect width="32" height="44" rx="7" />
        <circle cx="16" cy="34" r="4" />
      </g>
      <g className="lp-phone" transform="translate(194 730)">
        <rect width="32" height="44" rx="7" />
        <circle cx="16" cy="10" r="4" />
      </g>
      <text className="lp-end" x="250" y="34">END A</text>
      <text className="lp-end" x="250" y="760">END B</text>
    </svg>
  );
}

export default function Landing() {
  const { user, loading } = useAuth();
  const signedIn = !loading && !!user;
  const appHref = homeFor(user?.role);

  return (
    <div className="lp">
      <header className="lp-header">
        <div className="lp-wrap lp-header-row">
          <Link href="/" className="brand lp-brand" aria-label="CLEAR home">
            <div className="brand-mark">
              <span></span>
            </div>
            CLEAR
          </Link>
          <nav className="lp-nav" aria-label="Page">
            <a href="#how">How it works</a>
            <a href="#calls">What it calls</a>
            <a href="#referee">For referees</a>
          </nav>
          <div className="lp-header-cta">
            {signedIn ? (
              <Link href={appHref} className="btn lp-btn-accent">Open CLEAR</Link>
            ) : (
              <>
                <Link href="/login" className="lp-signin">Sign in</Link>
                <Link href="/register" className="btn lp-btn-accent">Create account</Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        <section className="lp-hero">
          <div className="lp-wrap lp-hero-grid">
            <div className="lp-hero-copy">
              <span className="lp-eyebrow">CLAY-COURT AI REFEREE</span>
              <h1>Every line call, from both ends of the court.</h1>
              <p className="lp-lede">
                CLEAR turns two phones into a referee. Pair with your partner, mount a phone behind each baseline and
                play. Every bounce is tracked, called and recorded.
              </p>
              <div className="lp-hero-actions">
                {signedIn ? (
                  <Link href={appHref} className="btn lp-btn-accent lp-btn-lg">Open CLEAR</Link>
                ) : (
                  <>
                    <Link href="/register" className="btn lp-btn-accent lp-btn-lg">Create an account</Link>
                    <Link href="/login" className="btn lp-btn-ghost lp-btn-lg">Sign in</Link>
                  </>
                )}
              </div>
              <p className="lp-fine">Runs in the phone’s browser. Nothing to install.</p>
            </div>
            <div className="lp-hero-art">
              <CourtHero />
            </div>
          </div>
        </section>

        <section id="how" className="lp-section">
          <div className="lp-wrap">
            <div className="lp-section-head">
              <span className="lp-eyebrow dark">HOW IT WORKS</span>
              <h2>Four steps from pairing to the final call.</h2>
            </div>
            <ol className="lp-steps">
              {STEPS.map((s) => (
                <li key={s.n}>
                  <span className="lp-step-n">{s.n}</span>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="calls" className="lp-section lp-clay-band">
          <div className="lp-wrap lp-calls-grid">
            <div className="lp-section-head">
              <span className="lp-eyebrow">WHAT IT CALLS</span>
              <h2>The calls that start arguments.</h2>
              <p>
                CLEAR watches the ball, the players and the lines together, and gives you the evidence behind each
                call.
              </p>
            </div>
            <div className="lp-calls">
              {CALLS.map((c) => (
                <article key={c.title}>
                  <h3>{c.title}</h3>
                  <p>{c.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="referee" className="lp-section">
          <div className="lp-wrap lp-referee">
            <div className="lp-section-head">
              <span className="lp-eyebrow dark">FOR REFEREES AND DEVELOPERS</span>
              <h2>A control room for every court.</h2>
              <p>
                Developer accounts get the tools behind the calls. They can also play, like anyone else.
              </p>
            </div>
            <ul className="lp-checks">
              {REFEREE.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        </section>

        <section className="lp-section lp-need">
          <div className="lp-wrap lp-need-grid">
            <h2>What you need</h2>
            <dl>
              <div>
                <dt>Two phones</dt>
                <dd>Any phone with a rear camera and a modern browser, one per player.</dd>
              </div>
              <div>
                <dt>Two mounts</dt>
                <dd>Something steady behind each baseline, high enough to see the whole court.</dd>
              </div>
              <div>
                <dt>A connection</dt>
                <dd>Court wifi or mobile data. Streaming adapts when the signal drops.</dd>
              </div>
            </dl>
          </div>
        </section>

        <section className="lp-final">
          <div className="lp-wrap lp-final-row">
            <h2>Bring a partner. Leave the arguing out.</h2>
            {signedIn ? (
              <Link href={appHref} className="btn lp-btn-accent lp-btn-lg">Open CLEAR</Link>
            ) : (
              <Link href="/register" className="btn lp-btn-accent lp-btn-lg">Create an account</Link>
            )}
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-wrap lp-footer-row">
          <span className="brand lp-brand-small">
            <div className="brand-mark">
              <span></span>
            </div>
            CLEAR
          </span>
          <span>Clay-court AI referee studio</span>
          <Link href="/login">Sign in</Link>
        </div>
      </footer>
    </div>
  );
}
