export function wordCount(s) {
  const t = String(s).trim();
  if (!t) return 0;
  return t.split(/\s+/).filter(Boolean).length;
}
