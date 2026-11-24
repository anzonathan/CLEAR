/** Top-down court in metres (ITF): x across 0–10.97, y along 0–23.77, origin at a far corner.
 *  Matches src/calibration/court_geometry.py so fused positions plot without conversion. */

const W = 10.97;
const L = 23.77;
const ALLEY = 1.37;
const NET = 11.885;
const SVC_FAR = 5.485;
const SVC_NEAR = 18.285;
const PAD = 2;

export interface CourtPoint {
  x: number;
  y: number;
}

export default function CourtDiagram({
  ball,
  trail = [],
  players = [],
  label,
}: {
  ball?: (CourtPoint & { predicted?: boolean }) | null;
  trail?: CourtPoint[];
  players?: (CourtPoint & { id: string })[];
  label?: string;
}) {
  const inBounds = (p: CourtPoint) => p.x > -PAD && p.x < W + PAD && p.y > -PAD && p.y < L + PAD;
  const pts = trail.filter(inBounds);
  return (
    <svg className="court-diagram" viewBox={`${-PAD} ${-PAD} ${W + PAD * 2} ${L + PAD * 2}`} role="img" aria-label={label ?? 'Court'}>
      <rect x={-PAD} y={-PAD} width={W + PAD * 2} height={L + PAD * 2} className="court-surround" />
      <g className="court-lines">
        <rect x={0} y={0} width={W} height={L} />
        <line x1={ALLEY} y1={0} x2={ALLEY} y2={L} />
        <line x1={W - ALLEY} y1={0} x2={W - ALLEY} y2={L} />
        <line x1={ALLEY} y1={SVC_FAR} x2={W - ALLEY} y2={SVC_FAR} />
        <line x1={ALLEY} y1={SVC_NEAR} x2={W - ALLEY} y2={SVC_NEAR} />
        <line x1={W / 2} y1={SVC_FAR} x2={W / 2} y2={SVC_NEAR} />
      </g>
      <line className="court-net" x1={-0.9} y1={NET} x2={W + 0.9} y2={NET} />
      <text className="court-end-label" x={W / 2} y={-0.6}>END A</text>
      <text className="court-end-label" x={W / 2} y={L + 1.3}>END B</text>
      {pts.length > 1 && <polyline className="court-trail" points={pts.map((p) => `${p.x},${p.y}`).join(' ')} />}
      {players.filter(inBounds).map((p) => (
        <g key={p.id} className="court-player" transform={`translate(${p.x} ${p.y})`}>
          <circle r={0.55} />
          <text y={0.22}>{p.id}</text>
        </g>
      ))}
      {ball && inBounds(ball) && <circle className={`court-ball ${ball.predicted ? 'is-predicted' : ''}`} cx={ball.x} cy={ball.y} r={0.32} />}
    </svg>
  );
}
