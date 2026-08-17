import { marked } from "marked";
import DOMPurify from "dompurify";

marked.use({
  gfm: true,
  breaks: true,
  renderer: {
    link(token, title, text) {
      const href = typeof token === "string" ? token : token?.href || "";
      const linkTitle = typeof token === "string" ? title : token?.title;
      const label = typeof token === "string" ? text : token?.text;
      const t = linkTitle ? ` title="${String(linkTitle).replace(/"/g, "&quot;")}"` : "";
      return `<a href="${href}"${t} target="_blank" rel="noopener noreferrer">${label}</a>`;
    },
  },
});

/** slug/name → public asset (Vite serves frontend/public at /) */
export const SERVICE_IMAGES = [
  {
    slug: "intro-consult",
    names: ["introductory consultation", "intro consult"],
    file: "/assets/intro-consult.jpg",
    alt: "Introductory Consultation",
  },
  {
    slug: "strategy-session",
    names: ["strategy session"],
    file: "/assets/strategy-session.jpg",
    alt: "Strategy Session",
  },
  {
    slug: "document-review",
    names: ["document review"],
    file: "/assets/document-review.jpg",
    alt: "Document Review",
  },
];

function assetUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  const origin =
    typeof window !== "undefined" && window.location?.origin
      ? window.location.origin
      : "";
  return `${origin}${path.startsWith("/") ? path : `/${path}`}`;
}

/** If the reply names a service but omitted its photo, insert markdown images. */
export function ensureServiceImages(text) {
  let out = String(text || "");
  for (const svc of SERVICE_IMAGES) {
    if (out.includes(svc.file) || out.includes(svc.file.split("/").pop())) {
      continue;
    }
    const patterns = [svc.slug, ...svc.names];
    let inserted = false;
    for (const p of patterns) {
      const re = new RegExp(`(${p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "i");
      if (!re.test(out)) continue;
      out = out.replace(re, `$1\n\n![${svc.alt}](${svc.file})\n`);
      inserted = true;
      break;
    }
    if (!inserted) continue;
  }
  return out;
}

function absolutizeLocalAssets(text) {
  return String(text).replace(
    /\]\((\/assets\/[^)\s]+)\)/gi,
    (_, path) => `](${assetUrl(path)})`,
  );
}

const SUPPORTS_REGEX_LOOKBEHIND = (() => {
  try {
    new RegExp("(?<!a)b");
    return true;
  } catch {
    return false;
  }
})();

/** Turn bare http(s) image URLs into markdown ![](url) so marked renders <img>. */
export function promoteBareImageUrls(text) {
  const imageUrl =
    "https?:\\/\\/[^\\s<>\"')]+\\.(?:png|jpe?g|gif|webp|svg)(?:\\?[^\\s<>\"')]*)?";
  if (SUPPORTS_REGEX_LOOKBEHIND) {
    const re = new RegExp(`(?<!\\]\\()(${imageUrl})`, "gi");
    return text.replace(re, "![]($1)");
  }
  return text
    .split("\n")
    .map((line) => {
      const t = line.trim();
      if (
        t &&
        new RegExp(`^${imageUrl}$`, "i").test(t) &&
        !/^\s*!\[/.test(line)
      ) {
        return line.replace(t, `![](${t})`);
      }
      return line;
    })
    .join("\n");
}

export function renderBotMarkdown(text) {
  const md = absolutizeLocalAssets(
    promoteBareImageUrls(ensureServiceImages(String(text))),
  );
  const dirty = marked.parse(md);
  return DOMPurify.sanitize(dirty, {
    USE_PROFILES: { html: true },
    ADD_TAGS: ["img"],
    ADD_ATTR: [
      "src",
      "alt",
      "title",
      "loading",
      "decoding",
      "width",
      "height",
      "target",
      "rel",
    ],
    ALLOWED_URI_REGEXP:
      /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp):|\/|#|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,
  });
}
