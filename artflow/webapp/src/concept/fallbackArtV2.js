const SCENES = [
  ["#11091d", "#7b2cff", "#00d9d0", "#ff4d90"],
  ["#07131d", "#00547a", "#00e7df", "#6634ff"],
  ["#190a16", "#a11f72", "#ff7b46", "#5d32ff"],
  ["#0a0f1c", "#23377c", "#8b3cff", "#00dfc6"],
  ["#171008", "#7a3a13", "#ffd45a", "#da44ff"],
  ["#0c0914", "#34205e", "#00c8ff", "#ff4d90"],
];

function svgDataUrl(svg) {
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

export function fallbackArtFor(seed = 0) {
  const [background, glowA, glowB, glowC] = SCENES[Math.abs(Number(seed || 0)) % SCENES.length];
  return svgDataUrl(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 1200">
      <defs>
        <radialGradient id="a" cx="24%" cy="18%" r="78%"><stop stop-color="${glowA}" stop-opacity=".95"/><stop offset="1" stop-color="${background}" stop-opacity="0"/></radialGradient>
        <radialGradient id="b" cx="84%" cy="74%" r="74%"><stop stop-color="${glowB}" stop-opacity=".82"/><stop offset="1" stop-color="${background}" stop-opacity="0"/></radialGradient>
        <linearGradient id="c" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${glowC}" stop-opacity=".65"/><stop offset=".52" stop-color="${background}" stop-opacity="0"/><stop offset="1" stop-color="${glowB}" stop-opacity=".48"/></linearGradient>
        <filter id="blur"><feGaussianBlur stdDeviation="38"/></filter>
        <filter id="soft"><feGaussianBlur stdDeviation="10"/></filter>
      </defs>
      <rect width="900" height="1200" fill="${background}"/>
      <rect width="900" height="1200" fill="url(#a)"/>
      <rect width="900" height="1200" fill="url(#b)"/>
      <circle cx="245" cy="250" r="175" fill="${glowA}" opacity=".48" filter="url(#blur)"/>
      <circle cx="695" cy="825" r="220" fill="${glowB}" opacity=".38" filter="url(#blur)"/>
      <path d="M90 970C250 730 360 655 520 560S760 345 850 135" fill="none" stroke="url(#c)" stroke-width="54" stroke-linecap="round" opacity=".68" filter="url(#soft)"/>
      <ellipse cx="460" cy="490" rx="180" ry="242" fill="#07070c" opacity=".52"/>
      <ellipse cx="460" cy="405" rx="94" ry="118" fill="#101017" opacity=".88"/>
      <path d="M292 860c42-190 130-282 168-282 42 0 132 92 170 282" fill="#0a0a11" opacity=".9"/>
      <path d="M0 1035c150-88 270-116 430-76s285 18 470-96v337H0Z" fill="#050508" opacity=".9"/>
      <g fill="#fff" opacity=".72"><circle cx="120" cy="110" r="2"/><circle cx="760" cy="180" r="2"/><circle cx="710" cy="1030" r="2"/><circle cx="210" cy="930" r="2"/></g>
    </svg>
  `);
}
