import type { GameEnd } from './api';

/**
 * Court calibration points, named from the camera's own point of view ("near" = the
 * baseline in front of the camera, "left" = the camera's left).
 *
 * The backend names points in absolute court coordinates (src/calibration/court_geometry.py):
 * x 0–10.97 across, y 0–23.77 along, "near" = y 23.77. The End B camera stands behind
 * y = 23.77, so its view matches the absolute names. The End A camera stands behind y = 0
 * facing the other way, so near/far and left/right both swap.
 */
export interface ViewAnchor {
  key: string; // name in the camera's view (= absolute name for End B)
  label: string;
  hint: string;
  required: boolean;
  x: number; // position in the camera-view diagram (camera at the bottom)
  y: number;
}

const W = 10.97;
const L = 23.77;
const A = 1.37;
const NET = 11.885;
const SF = 5.485;
const SN = 18.285;

export const VIEW_ANCHORS: ViewAnchor[] = [
  { key: 'near_left_doubles', label: 'Near left corner', hint: 'Baseline meets the left doubles sideline, closest to the camera.', required: true, x: 0, y: L },
  { key: 'near_right_doubles', label: 'Near right corner', hint: 'Baseline meets the right doubles sideline, closest to the camera.', required: true, x: W, y: L },
  { key: 'far_right_doubles', label: 'Far right corner', hint: 'Far baseline meets the right doubles sideline.', required: true, x: W, y: 0 },
  { key: 'far_left_doubles', label: 'Far left corner', hint: 'Far baseline meets the left doubles sideline.', required: true, x: 0, y: 0 },
  { key: 'net_left_sideline', label: 'Net, left post', hint: 'Where the net crosses the left doubles sideline.', required: false, x: 0, y: NET },
  { key: 'net_right_sideline', label: 'Net, right post', hint: 'Where the net crosses the right doubles sideline.', required: false, x: W, y: NET },
  { key: 'near_service_left', label: 'Near service line, left', hint: 'Near service line meets the left singles sideline.', required: false, x: A, y: SN },
  { key: 'near_service_center', label: 'Near service T', hint: 'Near service line meets the centre service line.', required: false, x: W / 2, y: SN },
  { key: 'near_service_right', label: 'Near service line, right', hint: 'Near service line meets the right singles sideline.', required: false, x: W - A, y: SN },
  { key: 'far_service_left', label: 'Far service line, left', hint: 'Far service line meets the left singles sideline.', required: false, x: A, y: SF },
  { key: 'far_service_center', label: 'Far service T', hint: 'Far service line meets the centre service line.', required: false, x: W / 2, y: SF },
  { key: 'far_service_right', label: 'Far service line, right', hint: 'Far service line meets the right singles sideline.', required: false, x: W - A, y: SF },
  { key: 'near_left_singles', label: 'Near left singles corner', hint: 'Baseline meets the left singles sideline, near side.', required: false, x: A, y: L },
  { key: 'near_right_singles', label: 'Near right singles corner', hint: 'Baseline meets the right singles sideline, near side.', required: false, x: W - A, y: L },
];

function swapView(name: string) {
  return name
    .replace(/near|far/g, (m) => (m === 'near' ? '\u0000' : 'near'))
    .replace(/\u0000/g, 'far')
    .replace(/left|right/g, (m) => (m === 'left' ? '\u0001' : 'left'))
    .replace(/\u0001/g, 'right');
}

/** Camera-view name -> backend (absolute) name. The mapping is its own inverse. */
export function toAbsolute(viewKey: string, end: GameEnd) {
  return end === 'end_b' ? viewKey : swapView(viewKey);
}

export const fromAbsolute = toAbsolute;
