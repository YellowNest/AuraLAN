const PRODUCT_WORDS = new Map([
  ['iphone', 'iPhone'],
  ['ipad', 'iPad'],
  ['imac', 'iMac'],
  ['macbook', 'MacBook'],
  ['homepod', 'HomePod'],
  ['airplay', 'AirPlay'],
  ['apple', 'Apple'],
  ['android', 'Android'],
  ['pixel', 'Pixel'],
  ['galaxy', 'Galaxy'],
  ['chromecast', 'Chromecast'],
  ['espressif', 'Espressif'],
  ['esp32', 'ESP32'],
  ['esp8266', 'ESP8266'],
  ['raspberry', 'Raspberry'],
  ['roborock', 'Roborock'],
  ['meross', 'Meross'],
  ['sonos', 'Sonos'],
  ['docker', 'Docker'],
  ['tv', 'TV'],
  ['nas', 'NAS'],
  ['lg', 'LG'],
]);

const GENERIC_NAMES = new Set([
  'unknown',
  'unknown device',
  'device',
  'unnamed',
  'unnamed device',
  'network device',
  'wi-fi device',
  'ethernet device',
  'vpn device',
]);

export function isTechnicalDeviceName(value) {
  const text = String(value || '').trim();
  if (!text) return true;
  const lower = text.toLowerCase();
  if (GENERIC_NAMES.has(lower)) return true;
  if (/^(?:\d{1,3}\.){3}\d{1,3}$/.test(text)) return true;
  if (/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/i.test(text)) return true;
  if (/^[0-9a-f:]{12,}$/i.test(text) && text.includes(':')) return true;
  if (/^[0-9a-f]{12,}$/i.test(text)) return true;
  if (/^device[-_ ]?\d+$/i.test(text)) return true;
  return false;
}

function prettifyWord(word, index) {
  const known = PRODUCT_WORDS.get(word.toLowerCase());
  if (known) return known;
  if (/^[A-Z0-9]{2,6}$/.test(word)) return word;
  if (/^[a-z0-9]+$/.test(word)) {
    return index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word;
  }
  return word;
}

export function prettifyDeviceName(value) {
  const raw = String(value || '')
    .trim()
    .replace(/\.local\.?$/i, '')
    .replace(/\bApple\s+de\s+TV\b/gi, 'Apple TV');
  if (!raw) return '';
  if (isTechnicalDeviceName(raw)) return '';
  const withoutNoiseSuffix = raw.replace(/[-_ ](?:[0-9a-f]{6,}|[0-9]{7,})$/i, '');
  return withoutNoiseSuffix
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .split(' ')
    .map(prettifyWord)
    .join(' ');
}

function candidateValues(device) {
  const identityDisplay = device?.identity?.display_name;
  const trustedIdentityName = identityDisplay?.source && identityDisplay.source !== 'heuristic'
    ? identityDisplay.value
    : '';
  const displayName = !identityDisplay || identityDisplay.source !== 'heuristic'
    ? device?.display_name
    : '';
  return [
    device?.metadata?.alias,
    trustedIdentityName,
    displayName,
    device?.hostname,
  ];
}

function appleFamilyName(vendor, category) {
  if (!/apple/i.test(vendor || '')) return '';
  return {
    phone: 'iPhone',
    tablet: 'iPad',
    watch: 'Apple Watch',
    tv: 'Apple TV',
    media_player: 'Apple TV',
    speaker: 'HomePod',
    computer: 'Mac',
  }[category] || '';
}

export function friendlyDeviceName(device, options = {}) {
  const alias = String(device?.metadata?.alias || '').trim();
  if (alias) return alias;

  for (const candidate of candidateValues(device).slice(1)) {
    const cleaned = prettifyDeviceName(candidate);
    if (cleaned) return cleaned;
  }

  const vendor = String(device?.vendor || '').trim();
  const category = String(device?.category || device?.device_type || 'unknown');
  const categoryName = String(options.categoryName || '').trim();
  const appleName = appleFamilyName(vendor, category);
  if (appleName) return appleName;
  if (/raspberry pi/i.test(vendor)) return 'Raspberry Pi';
  if (/espressif/i.test(vendor) && category === 'microcontroller') return options.espDevice || 'ESP device';

  if (vendor && categoryName && category !== 'unknown') return `${vendor} · ${categoryName}`;
  if (vendor) return vendor;
  if (categoryName && category !== 'unknown') {
    return typeof options.unnamedType === 'function' ? options.unnamedType(categoryName) : categoryName;
  }

  if (device?.mac_type === 'private') return options.privateDevice || 'Private-address device';

  const connectionType = String(device?.connection_type || '');
  if (connectionType === 'wifi') return options.wifiDevice || 'Wi-Fi device';
  if (connectionType === 'ethernet') return options.ethernetDevice || 'Ethernet device';
  if (connectionType === 'vpn') return options.vpnDevice || 'VPN device';
  return options.networkDevice || options.unnamedDevice || 'Network device';
}


export function friendlyDeviceListIdentity(device, options = {}) {
  const vendor = String(device?.vendor || device?.identity?.vendor?.value || '').trim();
  const mac = String(device?.mac || '').trim();
  const macVisible = /^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(mac) ? mac.toUpperCase() : '';

  // The full MAC comes first so the stable technical identifier remains
  // visible on narrow rows even when a manufacturer label is unusually long.
  if (macVisible && vendor) return `${macVisible} · ${vendor}`;
  if (macVisible && device?.mac_type === 'private') return `${macVisible} · ${options.privateMac || 'Private MAC'}`;
  if (macVisible) return macVisible;
  if (vendor) return vendor;
  return '';
}

export function friendlyDeviceContext(device, name, categoryName) {
  const parts = [];
  const vendor = String(device?.vendor || '').trim();
  const model = String(device?.model || device?.identity?.model?.value || '').trim();
  const type = String(categoryName || '').trim();

  // Keep the list deliberately strict: manufacturer + identified type.
  // Model, MAC, interface and discovery evidence belong in the inspector.
  if (vendor) parts.push(vendor);
  if (type && !parts.some((part) => part.toLowerCase() === type.toLowerCase())) {
    parts.push(type);
  }

  // If there is no detected category, a useful model is preferable to
  // showing an artificial "unknown" label. Never invent an exact model.
  if (!type && model && !parts.some((part) => part.toLowerCase() === model.toLowerCase())) {
    parts.push(model);
  }

  return parts.join(' · ');
}
