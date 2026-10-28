/** Decorative frame studies for the creation picker; the button supplies its label. */
export function CreationArt({ kind }: { kind: "photo" | "video" }) {
  return <svg className="creation-art" viewBox="0 0 320 184" fill="none" aria-hidden="true" focusable="false">
    {kind === "photo" ? <>
      <g transform="rotate(-9 118 94)">
        <rect x="62" y="37" width="112" height="126" rx="8" fill="currentColor" fillOpacity=".06" stroke="currentColor" strokeOpacity=".35" />
        <path d="M73 130l30-37 24 24 15-16 20 29" stroke="currentColor" strokeOpacity=".4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="142" cy="67" r="10" fill="currentColor" fillOpacity=".2" />
        <path d="M76 147h34" stroke="currentColor" strokeOpacity=".35" strokeWidth="2" strokeLinecap="round" />
      </g>
      <g transform="rotate(6 198 87)">
        <rect x="142" y="17" width="116" height="144" rx="8" className="creation-art-paper" />
        <rect x="151" y="26" width="98" height="116" rx="3" fill="currentColor" fillOpacity=".14" />
        <path d="M169 132c0-20 13-35 31-35s31 15 31 35" fill="currentColor" fillOpacity=".32" />
        <path d="M182 89c-9-7-12-20-7-31 4-11 14-18 26-18 17 0 28 12 28 29 0 9-4 17-11 23" fill="currentColor" fillOpacity=".58" />
        <path d="M184 67c13 1 23-3 29-11 7 10 8 21 3 31-4 8-9 12-16 12-10 0-17-10-17-23z" className="creation-art-paper" />
        <path d="M194 103v8l-8 6m21-14v8l8 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M153 151h31m47 0h15" stroke="currentColor" strokeOpacity=".4" strokeWidth="2" strokeLinecap="round" />
      </g>
      <path d="M47 50V33h17m204 94v17h-17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </> : <>
      <rect x="57" y="31" width="204" height="119" rx="10" fill="currentColor" fillOpacity=".06" stroke="currentColor" strokeOpacity=".3" />
      <rect x="45" y="40" width="204" height="119" rx="10" className="creation-art-paper" />
      <path d="M46 61h202M46 138h202" stroke="currentColor" strokeOpacity=".26" />
      {[60, 89, 118, 147, 176, 205, 234].map(x => <g key={x} fill="currentColor" fillOpacity=".38">
        <rect x={x - 4} y="48" width="8" height="5" rx="1" />
        <rect x={x - 4} y="146" width="8" height="5" rx="1" />
      </g>)}
      <path d="M61 127l32-39 32 33 23-20 30 26" stroke="currentColor" strokeOpacity=".22" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="191" cy="83" r="11" fill="currentColor" fillOpacity=".15" />
      <circle cx="147" cy="100" r="26" className="creation-art-paper" stroke="currentColor" strokeWidth="1.5" />
      <path d="M142 89l16 11-16 11z" fill="currentColor" />
      <path d="M268 73h18m-18 12h27m-27 12h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M65 170h99" stroke="currentColor" strokeOpacity=".35" strokeWidth="2" strokeLinecap="round" />
      <circle cx="108" cy="170" r="4" fill="currentColor" />
    </>}
  </svg>;
}
