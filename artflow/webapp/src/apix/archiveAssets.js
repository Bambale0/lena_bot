// Lightweight premium APIX demo assets.
// These are text-safe SVG art placeholders for GitHub Connector commits.
// Production feed still uses media URLs returned by /api/v1/feed.
const svg = (body) => `data:image/svg+xml;utf8,${encodeURIComponent(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 900" preserveAspectRatio="xMidYMid slice">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ff4d90"/><stop offset=".48" stop-color="#8a2cff"/><stop offset="1" stop-color="#00f0ff"/></linearGradient>
    <radialGradient id="r" cx="50%" cy="35%" r="70%"><stop stop-color="#ff4d90" stop-opacity=".32"/><stop offset=".55" stop-color="#7b4dff" stop-opacity=".16"/><stop offset="1" stop-color="#08070c" stop-opacity="0"/></radialGradient>
    <filter id="b"><feGaussianBlur stdDeviation="22"/></filter>
    <filter id="s"><feDropShadow dx="0" dy="16" stdDeviation="18" flood-color="#000" flood-opacity=".45"/></filter>
  </defs>
  <rect width="720" height="900" fill="#08070c"/>
  <rect width="720" height="900" fill="url(#r)"/>
  ${body}
  <rect width="720" height="900" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="2"/>
</svg>` )}`;

export const archiveAssets = {
  portraitNeon: svg(`<circle cx="365" cy="292" r="150" fill="#ff4d90" opacity=".28" filter="url(#b)"/><path d="M225 760c24-190 76-290 140-290s118 100 142 290" fill="#11101a" filter="url(#s)"/><circle cx="365" cy="345" r="104" fill="#17101d"/><path d="M250 355c72-72 158-78 232-6" fill="none" stroke="#ff4d90" stroke-width="18" opacity=".75"/><rect x="260" y="338" width="210" height="48" rx="24" fill="#050408" stroke="#00f0ff" stroke-opacity=".55"/>`),
  architecture: svg(`<path d="M70 710 360 120 650 710Z" fill="#111827" stroke="#00f0ff" stroke-opacity=".38" stroke-width="4"/><path d="M128 740h464V430H128z" fill="#15111c" filter="url(#s)"/><path d="M190 670h42V500h-42zm92 0h42V452h-42zm92 0h42V386h-42zm92 0h42V526h-42z" fill="url(#g)" opacity=".74"/><path d="M130 716h460" stroke="#fff" stroke-opacity=".24"/>`),
  fashion: svg(`<path d="M360 110c86 112 132 234 132 374 0 142-50 248-132 316-82-68-132-174-132-316 0-140 46-262 132-374Z" fill="#0d0a12" stroke="#ff4d90" stroke-opacity=".56" stroke-width="6" filter="url(#s)"/><circle cx="360" cy="250" r="82" fill="#1d1320"/><path d="M170 690c92-56 287-74 392 8" stroke="url(#g)" stroke-width="26" opacity=".72"/><circle cx="505" cy="250" r="95" fill="#bb2cff" opacity=".18" filter="url(#b)"/>`),
  car: svg(`<ellipse cx="360" cy="642" rx="260" ry="55" fill="#00f0ff" opacity=".16" filter="url(#b)"/><path d="M108 590c42-98 108-164 204-184h126c86 18 140 86 176 184Z" fill="#090910" stroke="url(#g)" stroke-width="7" filter="url(#s)"/><circle cx="235" cy="600" r="54" fill="#050408" stroke="#ff4d90" stroke-width="9"/><circle cx="515" cy="600" r="54" fill="#050408" stroke="#00f0ff" stroke-width="9"/><path d="M205 486h300" stroke="#ff4d90" stroke-width="12" opacity=".58"/>`),
  abstractGlass: svg(`<g filter="url(#s)"><path d="M360 120 520 330 430 720 235 650 190 355Z" fill="url(#g)" opacity=".32" stroke="#fff" stroke-opacity=".36" stroke-width="4"/><path d="M170 570c120-250 300-290 390-120" fill="none" stroke="#00f0ff" stroke-width="12" opacity=".68"/><path d="M225 260c170 40 260 160 260 360" fill="none" stroke="#ff4d90" stroke-width="14" opacity=".72"/></g><circle cx="430" cy="215" r="34" fill="#fff" opacity=".44"/>`),
  product: svg(`<rect x="284" y="190" width="152" height="420" rx="54" fill="#160d20" stroke="url(#g)" stroke-width="8" filter="url(#s)"/><rect x="308" y="250" width="104" height="250" rx="42" fill="#050408" stroke="#ffd700" stroke-opacity=".45"/><text x="360" y="385" text-anchor="middle" fill="#d4af37" font-size="34" font-family="serif">APIX</text><ellipse cx="360" cy="650" rx="190" ry="42" fill="#ff4d90" opacity=".25" filter="url(#b)"/><path d="M130 720h460" stroke="#fff" stroke-opacity=".22"/>`),
  watch: svg(`<ellipse cx="360" cy="590" rx="230" ry="74" fill="#7b4dff" opacity=".18" filter="url(#b)"/><circle cx="360" cy="420" r="128" fill="#090910" stroke="url(#g)" stroke-width="9" filter="url(#s)"/><circle cx="360" cy="420" r="92" fill="#11101a" stroke="#fff" stroke-opacity=".28"/><path d="M360 420 420 365M360 420 330 500" stroke="#fff" stroke-width="8" stroke-linecap="round"/><rect x="280" y="545" width="160" height="120" rx="32" fill="#0d0a12" stroke="#ff4d90" stroke-opacity=".5"/>`),
  lounge: svg(`<rect x="80" y="100" width="560" height="700" rx="34" fill="#0c0b12" stroke="#fff" stroke-opacity=".10"/><path d="M105 585h510" stroke="#00f0ff" stroke-opacity=".34"/><path d="M105 250h510" stroke="#ff4d90" stroke-width="16" opacity=".52" filter="url(#b)"/><rect x="130" y="510" width="460" height="120" rx="58" fill="#12111a" stroke="#ff4d90" stroke-opacity=".36"/><circle cx="535" cy="295" r="88" fill="#00f0ff" opacity=".12" filter="url(#b)"/><path d="M160 690h400" stroke="#fff" stroke-opacity=".22"/>`),
  editorialSculpture: svg(`<circle cx="360" cy="305" r="190" fill="none" stroke="#ff4d90" stroke-width="10" opacity=".78"/><path d="M245 720c18-150 58-250 115-250s98 100 115 250Z" fill="#11101a" stroke="url(#g)" stroke-width="5" filter="url(#s)"/><circle cx="360" cy="330" r="106" fill="#17141d"/><path d="M305 345c50-78 110-96 150-30" fill="none" stroke="#ff4d90" stroke-width="12" opacity=".7"/><ellipse cx="360" cy="750" rx="170" ry="36" fill="#ff4d90" opacity=".22" filter="url(#b)"/>`),
};
