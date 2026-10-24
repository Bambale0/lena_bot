export function attachmentName(disposition: string | null, id: number): string {
  const encoded = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(disposition || "");
  const ordinary = /filename\s*=\s*(?:"([^"]*)"|([^;]+))/i.exec(disposition || "");
  let name = ordinary?.[1] || ordinary?.[2] || `apix-result-${id}`;
  if (encoded) { try { name = decodeURIComponent(encoded[1]); } catch { /* Keep the safe ordinary filename. */ } }
  return name.replace(/[/\\\u0000-\u001f\u007f]/g, "_").trim().slice(0, 180) || `apix-result-${id}`;
}

export function saveDownload(file: { blob: Blob; filename: string }): void {
  const url = URL.createObjectURL(file.blob), link = document.createElement("a");
  link.href = url; link.download = file.filename; document.body.appendChild(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
