import { useEffect, useMemo, useState } from "react";

export const colorSchemes = [
  { id: "violet", label: "Неон", emoji: "🟣", description: "Фирменный фиолетовый APIX" },
  { id: "kiss", label: "Поцелуй", emoji: "💋", description: "Тёплый розово-красный акцент" },
  { id: "ocean", label: "Океан", emoji: "🌊", description: "Холодный сине-бирюзовый акцент" },
  { id: "banana", label: "Банан", emoji: "🍌", description: "Жёлтый акцент для banana-моделей" },
] as const;

export type ColorScheme = (typeof colorSchemes)[number]["id"];

const COLOR_SCHEME_STORAGE_KEY = "apix-color-scheme";
export const DEFAULT_COLOR_SCHEME: ColorScheme = "violet";

export function isColorScheme(value: string | null): value is ColorScheme {
  return Boolean(value && colorSchemes.some((scheme) => scheme.id === value));
}

export function readColorScheme(): ColorScheme {
  if (typeof window === "undefined") return DEFAULT_COLOR_SCHEME;
  const stored = window.localStorage.getItem(COLOR_SCHEME_STORAGE_KEY);
  return isColorScheme(stored) ? stored : DEFAULT_COLOR_SCHEME;
}

export function applyColorScheme(scheme: ColorScheme) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.apixScheme = scheme;
}

export function saveColorScheme(scheme: ColorScheme) {
  applyColorScheme(scheme);
  if (typeof window !== "undefined") window.localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, scheme);
}

export function useColorScheme() {
  const [scheme, setSchemeState] = useState<ColorScheme>(() => {
    const initial = readColorScheme();
    applyColorScheme(initial);
    return initial;
  });

  useEffect(() => {
    saveColorScheme(scheme);
  }, [scheme]);

  const current = useMemo(
    () => colorSchemes.find((item) => item.id === scheme) || colorSchemes[0],
    [scheme],
  );

  const setScheme = (next: ColorScheme) => setSchemeState(next);

  const cycle = () => {
    const index = colorSchemes.findIndex((item) => item.id === scheme);
    setSchemeState((colorSchemes[(index + 1) % colorSchemes.length] || colorSchemes[0]).id);
  };

  return { scheme, current, setScheme, cycle };
}
