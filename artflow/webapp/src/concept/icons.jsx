import React from "react";

export default function Icon({ name, size = 22, strokeWidth = 1.8, className = "" }) {
  const props = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className,
    "aria-hidden": true,
  };

  const paths = {
    home: <><path d="m3 10 9-7 9 7"/><path d="M5 9v11h14V9"/><path d="M9 20v-6h6v6"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    sparkle: <><path d="M12 3c.6 4.4 2.6 6.4 7 7-4.4.6-6.4 2.6-7 7-.6-4.4-2.6-6.4-7-7 4.4-.6 6.4-2.6 7-7Z"/><path d="M19 3v4M17 5h4"/></>,
    search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
    sliders: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></>,
    prompt: <><path d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M8 9h8M8 13h5"/></>,
    user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
    heart: <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8Z"/>,
    eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.6"/></>,
    share: <><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4"/></>,
    bookmark: <path d="M6 3h12v18l-6-4-6 4V3Z"/>,
    play: <path d="m8 5 11 7-11 7V5Z"/>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    chevron: <path d="m9 18 6-6-6-6"/>,
    back: <path d="m15 18-6-6 6-6"/>,
    image: <><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="m21 15-5-5L5 20"/></>,
    video: <><rect x="3" y="5" width="14" height="14" rx="2"/><path d="m17 10 4-3v10l-4-3"/></>,
    camera: <><path d="M14.5 5 13 3h-2L9.5 5H5a2 2 0 0 0-2 2v11h18V7a2 2 0 0 0-2-2h-4.5Z"/><circle cx="12" cy="12" r="4"/></>,
    wallet: <><path d="M4 5h15a2 2 0 0 1 2 2v12H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/><path d="M16 10h5v5h-5a2.5 2.5 0 0 1 0-5Z"/></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></>,
    trash: <><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14"/></>,
    reload: <><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 9A7 7 0 0 1 18 6l2 6M17.9 15A7 7 0 0 1 6 18l-2-6"/></>,
    external: <><path d="M14 3h7v7M10 14 21 3"/><path d="M21 14v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h6"/></>,
    crown: <><path d="m3 7 4 4 5-7 5 7 4-4-2 11H5L3 7Z"/><path d="M5 21h14"/></>,
    more: <><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/></>,
    download: <><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></>,
    copy: <><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.37a1.7 1.7 0 0 0-1 .63 1.7 1.7 0 0 0-.4 1.08V21h-4v-.08A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.23 15a1.7 1.7 0 0 0-.63-1 1.7 1.7 0 0 0-1.08-.4H2.5v-4h.08A1.7 1.7 0 0 0 4.1 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 8.47 4.2a1.7 1.7 0 0 0 1-.63 1.7 1.7 0 0 0 .4-1.08V2.5h4v.08A1.7 1.7 0 0 0 15 4.1a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 8.47a1.7 1.7 0 0 0 .63 1 1.7 1.7 0 0 0 1.08.4h.08v4h-.08A1.7 1.7 0 0 0 19.4 15Z"/></>,
  };

  return <svg {...props}>{paths[name] || paths.sparkle}</svg>;
}
