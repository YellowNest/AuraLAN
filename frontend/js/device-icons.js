/* Stable frontend mapping for normalized backend icon keys.
   The backend owns product-family recognition; the browser only applies safe fallbacks. */

const ICON_KEYS = new Set([
  'phone', 'tablet', 'laptop', 'apple_tv', 'tv', 'media_player', 'speaker', 'iot', 'camera', 'printer',
  'router', 'access_point', 'server', 'raspberry_pi', 'microcontroller', 'console', 'watch', 'vacuum',
  'garage', 'heat_pump', 'vr_headset', 'device_generic',
]);

const CATEGORY_ICONS = {
  phone: 'phone',
  tablet: 'tablet',
  computer: 'laptop',
  tv: 'tv',
  media_player: 'media_player',
  speaker: 'speaker',
  smart_home: 'iot',
  iot: 'iot',
  camera: 'camera',
  printer: 'printer',
  router: 'router',
  access_point: 'access_point',
  server: 'server',
  raspberry_pi: 'raspberry_pi',
  microcontroller: 'microcontroller',
  console: 'console',
  watch: 'watch',
  unknown: 'device_generic',
};

export function deviceIconKey(device) {
  const explicit = String(device?.icon_key || '').trim();
  if (ICON_KEYS.has(explicit)) return explicit;

  const category = String(device?.category || device?.device_type || 'unknown');
  const vendor = String(device?.vendor || device?.identity?.vendor?.value || '');
  const model = String(device?.model || device?.identity?.model?.value || '');
  const alias = String(device?.metadata?.alias || '');
  const familyCorpus = `${vendor} ${model} ${alias}`.toLowerCase();

  // Compatibility fallback for older API payloads. Modern payloads should
  // always carry icon_key from the backend; these rules use only resolved
  // identity fields and a user-owned alias.
  if (/apple/i.test(vendor) && (category === 'tv' || category === 'media_player')) return 'apple_tv';
  if (/\broborock\b|\birobot\b|\broomba\b|\becovacs\b|\bdeebot\b|\brobot[\s_-]*vac(?:uum)?\b|\bvacuum\b/.test(familyCorpus)) return 'vacuum';
  if (/\bgarageport\b|\bgarage[\s_-]*(?:door|opener)\b|\bmsg(?:100|200)\b/.test(familyCorpus)) return 'garage';
  if (/\bluftv[aä]rmepump\b|\bheat[\s_-]*pump\b|\bheatpump\b|\bair[\s_-]*conditioner\b|\baircon\b/.test(familyCorpus)) return 'heat_pump';
  if (/\bmeta[\s_-]*quest\b|\boculus\b|\bquest[\s_-]*(?:2|3|pro)\b|\bvr[\s_-]*headset\b|\bvirtual[\s_-]*reality\b|(?:^|\s)vr(?:\s|$)/.test(familyCorpus)) return 'vr_headset';

  return CATEGORY_ICONS[category] || 'device_generic';
}

export function isKnownDeviceIconKey(value) {
  return ICON_KEYS.has(String(value || ''));
}
