export type ThemeId = "neonPink" | "cyberLime" | "minimalGlass" | "darkAurora";

export type Theme = {
  name: string;
  background: string;
  card: string;
  cardAlt: string;
  text: string;
  muted: string;
  accent: string;
  accent2: string;
  border: string;
  buttonGradient: string;
  glow: string;
  nav: string;
};

export const themes: Record<ThemeId, Theme> = {
  neonPink: {
    name: "Neon Pink Premium",
    background: "radial-gradient(circle at 80% 0%, #36154f 0, transparent 34%), linear-gradient(160deg, #09070d 0%, #16091b 54%, #050407 100%)",
    card: "rgba(44, 13, 37, 0.82)",
    cardAlt: "rgba(115, 20, 80, 0.34)",
    text: "#fff4fb",
    muted: "#c9a9bd",
    accent: "#ff4db3",
    accent2: "#9a6cff",
    border: "rgba(255, 77, 179, 0.38)",
    buttonGradient: "linear-gradient(135deg, #ff4db3, #8d5cff)",
    glow: "0 20px 60px rgba(255, 77, 179, 0.28)",
    nav: "rgba(22, 8, 26, 0.88)",
  },
  cyberLime: {
    name: "Cyber Lime",
    background: "radial-gradient(circle at 20% 20%, #1f4d15 0, transparent 32%), linear-gradient(150deg, #030803 0%, #071307 55%, #020502 100%)",
    card: "rgba(9, 28, 14, 0.86)",
    cardAlt: "rgba(84, 154, 42, 0.18)",
    text: "#efffe9",
    muted: "#9fc79b",
    accent: "#a8ff45",
    accent2: "#4cf0a6",
    border: "rgba(168, 255, 69, 0.34)",
    buttonGradient: "linear-gradient(135deg, #a8ff45, #4cf0a6)",
    glow: "0 18px 55px rgba(168, 255, 69, 0.22)",
    nav: "rgba(3, 14, 7, 0.9)",
  },
  minimalGlass: {
    name: "Minimal Glass",
    background: "radial-gradient(circle at 15% 0%, #ffffff 0, transparent 32%), linear-gradient(145deg, #eef2f8 0%, #dcd8ee 48%, #f7f6fb 100%)",
    card: "rgba(255, 255, 255, 0.64)",
    cardAlt: "rgba(229, 231, 244, 0.78)",
    text: "#111827",
    muted: "#667085",
    accent: "#7557d6",
    accent2: "#4b91d9",
    border: "rgba(125, 125, 150, 0.24)",
    buttonGradient: "linear-gradient(135deg, #7557d6, #4b91d9)",
    glow: "0 20px 60px rgba(87, 99, 170, 0.18)",
    nav: "rgba(246, 247, 252, 0.9)",
  },
  darkAurora: {
    name: "Dark Aurora",
    background: "radial-gradient(circle at 30% 18%, #0ec8aa 0, transparent 30%), radial-gradient(circle at 82% 42%, #8a45ff 0, transparent 32%), linear-gradient(155deg, #06131f 0%, #0b1025 52%, #050712 100%)",
    card: "rgba(10, 25, 45, 0.82)",
    cardAlt: "rgba(25, 77, 111, 0.34)",
    text: "#edf9ff",
    muted: "#a4bdd1",
    accent: "#35e6d3",
    accent2: "#8a6bff",
    border: "rgba(53, 230, 211, 0.28)",
    buttonGradient: "linear-gradient(135deg, #35e6d3, #8a6bff)",
    glow: "0 22px 65px rgba(53, 230, 211, 0.22)",
    nav: "rgba(5, 14, 29, 0.9)",
  },
};

export const themeIds = Object.keys(themes) as ThemeId[];
