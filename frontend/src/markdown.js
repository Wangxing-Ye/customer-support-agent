import { marked } from "marked";
import DOMPurify from "dompurify";

marked.use({ gfm: true, breaks: true });

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
  const md = promoteBareImageUrls(String(text));
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
  });
}
