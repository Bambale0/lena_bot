import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { GenerationTask, ModelInfo } from "@/lib/types";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function asArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    const items = (value as { items?: unknown }).items;
    return Array.isArray(items) ? (items as T[]) : [];
  }
  return [];
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function formatCredits(value: unknown): string {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return "0";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(number);
}

export function kissUnit(value: unknown): string {
  const number = Math.abs(Number(value ?? 0));
  const rounded = Math.floor(number);
  const mod10 = rounded % 10;
  const mod100 = rounded % 100;
  if (mod10 === 1 && mod100 !== 11) return "поцелуй";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "поцелуя";
  return "поцелуев";
}

export function formatKisses(value: unknown, options: { compact?: boolean; emoji?: boolean } = {}): string {
  const amount = formatCredits(value);
  const prefix = options.emoji === false ? "" : "💋 ";
  if (options.compact) return `${prefix}${amount}`.trim();
  return `${prefix}${amount} ${kissUnit(value)}`.trim();
}

export function formatRelativeDate(value?: string | null): string {
  if (!value) return "только что";
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "недавно";
  const diffSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (diffSeconds < 60) return "только что";
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} мин назад`;
  if (diffSeconds < 86_400) return `${Math.floor(diffSeconds / 3600)} ч назад`;
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short" }).format(timestamp);
}

export function generationStatusLabel(status: string): string {
  if (status === "done" || status === "completed") return "Готово";
  if (status === "failed") return "Ошибка";
  if (status === "processing" || status === "running") return "Создаётся";
  if (status === "pending" || status === "queued" || status === "created") return "В очереди";
  return status || "В работе";
}

export function isPendingTask(task?: GenerationTask | null): boolean {
  return Boolean(task && ["created", "queued", "pending", "processing", "running"].includes(task.status));
}

export function safeExternalUrl(value?: string | null): string {
  if (!value) return "";
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.toString() : "";
  } catch {
    return "";
  }
}

export function firstMedia(item: {
  preview_url?: string | null;
  result_url?: string | null;
  preview_urls?: string[];
  result_urls?: string[];
}): string {
  const candidates = [
    item.preview_url,
    item.preview_urls?.find(Boolean),
    item.result_url,
    item.result_urls?.find(Boolean),
  ];
  for (const candidate of candidates) {
    const url = safeExternalUrl(candidate);
    if (url) return url;
  }
  return "";
}

export function modelSupports(model: ModelInfo | undefined, mode: string): boolean {
  return Boolean(model?.modes?.includes(mode));
}

export function estimateImageCost(model: ModelInfo | undefined, quality: string, count: number): number {
  if (!model) return 0;
  const qualityCost = model.quality_options?.find((item) => item.value === quality)?.credits;
  return Number(qualityCost ?? model.credits ?? 0) * Math.max(1, count);
}

export function estimateVideoCost(model: ModelInfo | undefined): number {
  return Number(model?.credits ?? 0);
}

export function splitUrls(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\n,]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}
