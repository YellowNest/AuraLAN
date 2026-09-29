/* AuraLAN local icon system: 24px, rounded, calm, consistent. */
const paths = {
  overview: '<path d="M4.5 11.2 12 4.8l7.5 6.4v7.6a1.7 1.7 0 0 1-1.7 1.7H6.2a1.7 1.7 0 0 1-1.7-1.7Z"/><path d="M9.2 20.5v-5.8h5.6v5.8"/>',
  network: '<circle cx="12" cy="6" r="2.2"/><circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="18" r="2.2"/><path d="M10.9 7.9 7.1 16M13.1 7.9l3.8 8.1M8.2 18h7.6"/>',
  wifi: '<path d="M4.2 10.2a11.6 11.6 0 0 1 15.6 0M7.3 13.6a7 7 0 0 1 9.4 0M10.5 17a2.3 2.3 0 0 1 3 0"/><circle cx="12" cy="19.2" r=".7" fill="currentColor" stroke="none"/>',
  ethernet: '<rect x="5" y="3.5" width="14" height="10" rx="2"/><path d="M8.5 7.2h.01M12 7.2h.01M15.5 7.2h.01M12 13.5v7M8.5 20.5h7"/>',
  devices: '<rect x="3.5" y="4" width="17" height="12" rx="2.4"/><path d="M8.2 20h7.6M12 16v4"/>',
  laptop: '<rect x="4.5" y="4.5" width="15" height="11" rx="2"/><path d="M2.8 19.2h18.4"/>',
  desktop: '<rect x="4" y="3.8" width="16" height="12" rx="2"/><path d="M12 15.8v4M8 19.8h8"/>',
  phone: '<rect x="7.2" y="2.7" width="9.6" height="18.6" rx="2.5"/><path d="M10.3 5h3.4M11 18.7h2"/>',
  tablet: '<rect x="5.2" y="2.8" width="13.6" height="18.4" rx="2.4"/><circle cx="12" cy="18.2" r=".65" fill="currentColor" stroke="none"/>',
  tv: '<rect x="3.2" y="4.6" width="17.6" height="12.8" rx="2.8"/><path d="M8.2 20h7.6M12 17.4V20"/>',
  media_player: '<rect x="4" y="6.2" width="16" height="11.6" rx="3"/><path d="m10.2 9.4 5 2.8-5 2.8Z"/><circle cx="18" cy="15.6" r=".7" fill="currentColor" stroke="none"/>',
  speaker: '<rect x="6" y="3.2" width="12" height="17.6" rx="3"/><circle cx="12" cy="14.2" r="3.4"/><circle cx="12" cy="7.8" r="1.1"/>',
  server: '<rect x="4" y="3.5" width="16" height="7" rx="2"/><rect x="4" y="13.5" width="16" height="7" rx="2"/><path d="M7.7 7h.01M11 7h5M7.7 17h.01M11 17h5"/>',
  host: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 8h8M8 12h5M8 16h3"/>',
  iot: '<path d="M9.2 7.2a4.1 4.1 0 0 1 5.6 0 4 4 0 0 1 .6 5.1c-.5.7-1.2 1.3-1.7 1.8-.4.4-.7 1-.7 1.6h-2c0-.6-.3-1.2-.7-1.6-.5-.5-1.2-1.1-1.7-1.8a4 4 0 0 1 .6-5.1Z"/><path d="M10.3 18h3.4M10.8 21h2.4M12 3V1.8M5.6 5.2l-.9-.9M18.4 5.2l.9-.9M4 11H2.7M21.3 11H20"/>',
  camera: '<path d="M4 8.3h3.4l1.8-2.5h5.6l1.8 2.5H20a1.5 1.5 0 0 1 1.5 1.5v8.4a1.5 1.5 0 0 1-1.5 1.5H4a1.5 1.5 0 0 1-1.5-1.5V9.8A1.5 1.5 0 0 1 4 8.3Z"/><circle cx="12" cy="14" r="3.2"/>',
  printer: '<path d="M7 8V3.5h10V8M6.5 18H4a1.5 1.5 0 0 1-1.5-1.5v-5A3.5 3.5 0 0 1 6 8h12a3.5 3.5 0 0 1 3.5 3.5v5A1.5 1.5 0 0 1 20 18h-2.5"/><path d="M6.5 14h11v7h-11zM17.5 11.2h.01"/>',
  console: '<path d="M7 9.5h10a5 5 0 0 1 4.7 6.8l-.8 2a2.8 2.8 0 0 1-4.5 1l-2.1-1.8H9.7l-2.1 1.8a2.8 2.8 0 0 1-4.5-1l-.8-2A5 5 0 0 1 7 9.5Z"/><path d="M7 13v4M5 15h4M16.5 13.5h.01M19 16h.01"/>',
  watch: '<rect x="7.2" y="6.2" width="9.6" height="11.6" rx="3"/><path d="m9.2 6.2.8-3h4l.8 3M9.2 17.8l.8 3h4l.8-3"/>',
  raspberry_pi: '<path d="M12 5.2c-4 0-7.2 3-7.2 6.8S8 19 12 19s7.2-3.1 7.2-7S16 5.2 12 5.2Z"/><path d="M9.4 5.7 8 3.6M14.6 5.7 16 3.6M8.7 10.3h.01M15.3 10.3h.01M9 14.5c1.8 1.3 4.2 1.3 6 0"/>',
  microcontroller: '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M9 2.5v2.7M15 2.5v2.7M9 18.8v2.7M15 18.8v2.7M2.5 9h2.7M2.5 15h2.7M18.8 9h2.7M18.8 15h2.7"/><path d="M10 10h4v4h-4z"/>',
  device_generic: '<rect x="4" y="5" width="16" height="14" rx="3"/><path d="M8 9h8M8 13h5M10 19v2M14 19v2"/>',
  unknown_device: '<rect x="4" y="5" width="16" height="14" rx="3"/><path d="M8 9h8M8 13h5"/>',
  apple_tv: '<path fill="currentColor" stroke="none" d="M20.57 17.735h-1.815l-3.34-9.203h1.633l2.02 5.987c.075.231.273.9.586 2.012l.297-.997.33-1.006 2.094-6.004H24zm-5.344-.066a5.76 5.76 0 0 1-1.55.207c-1.23 0-1.84-.693-1.84-2.087V9.646h-1.063V8.532h1.121V7.081l1.476-.602v2.062h1.707v1.113H13.38v5.805c0 .446.074.75.214.932.14.182.396.264.75.264.207 0 .495-.041.883-.115zm-7.29-5.343c.017 1.764 1.55 2.358 1.567 2.366-.017.042-.248.842-.808 1.658-.487.71-.99 1.418-1.79 1.435-.783.016-1.03-.462-1.93-.462-.89 0-1.17.445-1.913.478-.758.025-1.344-.775-1.838-1.484-.998-1.451-1.765-4.098-.734-5.88.51-.89 1.426-1.451 2.416-1.46.75-.016 1.468.512 1.93.512.461 0 1.327-.627 2.234-.536.38.016 1.452.157 2.136 1.154-.058.033-1.278.743-1.27 2.219M6.468 7.988c.404-.495.685-1.18.61-1.864-.585.025-1.294.388-1.723.883-.38.437-.71 1.138-.619 1.806.652.05 1.328-.338 1.732-.825Z"/>',
  vacuum: '<circle cx="12" cy="12" r="8.2"/><circle cx="13.2" cy="8.3" r="1.8"/><path d="M5.4 13.8c1.4 3.2 3.7 4.8 6.8 4.8 2.9 0 5.2-1.4 6.5-4.2M12 3.8v2.7M18.4 17.1l2.4 1.4M18.9 15.7l2.1-.8"/>',
  vr_headset: '<path d="M5.2 7.8h13.6a2.7 2.7 0 0 1 2.6 3.4l-1.2 5.2a2.4 2.4 0 0 1-2.3 1.8h-2.2l-2.1-2.7h-3.2l-2.1 2.7H6.1a2.4 2.4 0 0 1-2.3-1.8l-1.2-5.2a2.7 2.7 0 0 1 2.6-3.4Z"/><path d="M7.2 7.8 8 5.8h8l.8 2M8 12h.01M16 12h.01"/>',
  garage: '<path d="m3.5 11 8.5-7 8.5 7"/><path d="M5.5 10.5V21h13V10.5M8.5 14h7M8.5 17h7"/>',
  heat_pump: '<rect x="5" y="4" width="14" height="16" rx="2.5"/><circle cx="12" cy="11" r="3.3"/><path d="M12 5.5v2M12 14.5v2M6.5 11h2M15.5 11h2M8.1 7.1l1.4 1.4M14.5 13.5l1.4 1.4M15.9 7.1l-1.4 1.4M9.5 13.5l-1.4 1.4"/>',
  router: '<rect x="3" y="10" width="18" height="8" rx="2.5"/><path d="M7 14h.01M10.5 14h.01M15.5 10V5.5M18.5 10V4"/><path d="M14.2 6.4a3 3 0 0 1 2.6-.2M17 4.7a4.8 4.8 0 0 1 2.7-.2"/>',
  access_point: '<rect x="4" y="12" width="16" height="7" rx="2.5"/><path d="M8 15.5h.01M12 12V9.5M8.5 7a5 5 0 0 1 7 0M6 4.5a8.5 8.5 0 0 1 12 0"/>',
  dhcp: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 8h8M8 12h5M8 16h3"/><circle cx="17" cy="16" r="1" fill="currentColor" stroke="none"/>',
  dns: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
  pihole: '<path d="M7.2 6.2c1.2-1.9 3-2.9 4.8-2.9s3.6 1 4.8 2.9"/><path d="M9.4 5.1C7.6 4.8 6.2 3.7 5.8 2.1c2.2-.1 3.8.8 4.7 2.6M14.2 5c.7-1.5 1.9-2.3 3.8-2.4-.4 1.5-1.5 2.4-3.3 2.7"/><circle cx="9" cy="11.2" r="3.7"/><circle cx="15" cy="11.2" r="3.7"/><circle cx="9.5" cy="16.2" r="3.7"/><circle cx="14.5" cy="16.2" r="3.7"/><circle cx="12" cy="13.6" r="2.35"/>',
  vpn: '<path d="M12 2.8 5 6v5.2c0 4.4 2.7 7.6 7 10 4.3-2.4 7-5.6 7-10V6Z"/><path d="m8.8 12 2.1 2.1 4.5-4.5"/>',
  wireguard: '<path d="M12 2.8 5 6v5.15c0 4.35 2.7 7.55 7 9.95 4.3-2.4 7-5.6 7-9.95V6Z"/><path d="M8.8 12h6.4M12 8.8v6.4"/><path d="M8.7 16.4h6.6"/>',
  docker: '<path d="M3.5 12.2h15.2c-.35 4.35-3.45 7.3-8.15 7.3-4.15 0-6.95-2.25-6.95-5.75 0-.5 0-.95-.1-1.55Z"/><path d="M6 9h2.6v2.6H6zM8.9 9h2.6v2.6H8.9zM11.8 9h2.6v2.6h-2.6zM8.9 6.1h2.6v2.6H8.9zM18.7 12.2c1.2-.05 1.95-.6 2.8-1.8"/>',
  proxy: '<circle cx="6.3" cy="7" r="1.5"/><circle cx="17.7" cy="7" r="1.5"/><circle cx="12" cy="17" r="1.5"/><path d="M7.8 7h8.4M7.4 8.2 10.9 15.6M16.6 8.2 13.1 15.6"/>',
  services: '<rect x="4" y="4" width="6.4" height="6.4" rx="1.8"/><rect x="13.6" y="4" width="6.4" height="6.4" rx="1.8"/><rect x="4" y="13.6" width="6.4" height="6.4" rx="1.8"/><rect x="13.6" y="13.6" width="6.4" height="6.4" rx="1.8"/>',
  security: '<path d="M12 2.8 5 6v5.2c0 4.4 2.7 7.6 7 10 4.3-2.4 7-5.6 7-10V6Z"/><path d="M9.5 11.5h5v4h-5zM10.5 11.5V10a1.5 1.5 0 0 1 3 0v1.5"/>',
  firewall: '<path d="M4 20V4M10 20V4M16 20V4M22 20V4M4 8h18M4 14h18"/>',
  settings: '<path d="M5 7h8M17 7h2M5 17h2M11 17h8M5 12h3M12 12h7"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/><circle cx="10" cy="12" r="2"/>',
  diagnostics: '<path d="M4 19.5V4.5M4 19.5h16M7 15.5l3.2-4 3.1 2.1 4.7-7"/><circle cx="18" cy="6.5" r="1.2"/>',
  search: '<circle cx="10.8" cy="10.8" r="6.4"/><path d="m15.6 15.6 4.4 4.4"/>',
  refresh: '<path d="M19.5 6.5v5h-5M4.5 17.5v-5h5"/><path d="M18 9A7 7 0 0 0 6.5 6.8L4.5 11M6 15a7 7 0 0 0 11.5 2.2l2-4.2"/>',
  chevron: '<path d="m9.5 5.5 6.5 6.5-6.5 6.5"/>',
  warning: '<path d="m10.3 4.4-6.8 12.5A2 2 0 0 0 5.3 20h13.4a2 2 0 0 0 1.8-3.1L13.7 4.4a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 16.7h.01"/>',
  error: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6m0-6-6 6"/>',
  success: '<circle cx="12" cy="12" r="9"/><path d="m8.2 12.1 2.4 2.5 5.4-5.4"/>',
  offline: '<path d="M4 4l16 16M5 10.2a11.5 11.5 0 0 1 10.8-2M8 13.7a6.6 6.6 0 0 1 4.2-1.4M10.7 17a2.3 2.3 0 0 1 2.6 0"/>',
  uptime: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.2V12l3.3 2"/>',
  cpu: '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M9 2.5v2.7M15 2.5v2.7M9 18.8v2.7M15 18.8v2.7M2.5 9h2.7M2.5 15h2.7M18.8 9h2.7M18.8 15h2.7"/>',
  memory: '<rect x="5" y="4" width="14" height="16" rx="2.5"/><path d="M9 8h6M9 12h6M9 16h3"/>',
  storage: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
  upload: '<path d="M12 20V5M7.5 9.5 12 5l4.5 4.5"/>',
  download: '<path d="M12 4v15M7.5 14.5 12 19l4.5-4.5"/>',
  channel: '<path d="M4 18h16M7 14h10M10 10h4M12 6h.01"/>',
  signal: '<path d="M5 20v-3M9.5 20v-6M14 20v-9M18.5 20V8"/>',
  mac: '<rect x="3" y="7" width="18" height="10" rx="2.5"/><path d="M7 11h.01M10 11h.01M7 14h.01M10 14h.01M14 12h3"/>',
  ip: '<rect x="3.5" y="6" width="17" height="12" rx="2.5"/><path d="M8 10h8M8 14h5"/>',
  logs: '<path d="M6 3h9l3 3v15H6z"/><path d="M15 3v4h4M9 11h6M9 15h6"/>',
  advanced: '<path d="M7 12h10M12 7v10"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  close: '<path d="m7 7 10 10M17 7 7 17"/>',
  copy: '<rect x="8" y="8" width="11" height="12" rx="2.2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2"/>',
  power: '<path d="M12 2.8v8.4"/><path d="M7.2 5.9a8 8 0 1 0 9.6 0"/>'
};

export function icon(name, label = '') {
  const body = paths[name] || paths.info;
  const title = label ? `<title>${label}</title>` : '';
  return `<svg class="icon icon-${name}" viewBox="0 0 24 24" ${label ? 'role="img"' : 'aria-hidden="true"'} focusable="false">${title}${body}</svg>`;
}

export const serviceIcons = { docker: 'docker', pihole: 'pihole', wireguard: 'wireguard', caddy: 'proxy' };

/* Brand marks are presentation-only. Pi-hole uses its bundled upstream mark;
   other services keep AuraLAN's coherent local pictograms. */
export function serviceMark(id) {
  const asset = {
    docker: '/assets/assets/services/docker.svg',
    pihole: '/assets/assets/services/pihole.svg',
    wireguard: '/assets/assets/services/wireguard.svg',
    caddy: '/assets/assets/services/caddy.svg'
  }[id];
  if (asset) {
    return `<img class="service-mark service-mark-${id}" src="${asset}" alt="" aria-hidden="true">`;
  }
  return icon(serviceIcons[id] || 'services');
}
