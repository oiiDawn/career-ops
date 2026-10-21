// @ts-check
// Shared HTML → plain-text pipeline for providers whose payloads embed
// description markup. Greenhouse's contentToText was the first instance;
// this is the extracted form so later providers cannot grow a divergent
// copy — same rationale that produced _html-entities when entity decoders
// drifted across four files (#1555/#1639/#2623).
import { decodeEntities } from './_html-entities.mjs';

// Capped like greenhouse/alibaba full-text JDs: a 10 KB/posting body is
// normal on these boards, and scan payloads must stay sane.
export const DESCRIPTION_CAP = 4000;

// A tag ends at an unquoted `>`. Attribute values may contain angle brackets,
// so the common `<[^>]+>` shortcut can stop midway through a tag and expose
// the remaining attributes as description text. Requiring content between the
// brackets preserves a literal `<>`, as the old matcher did.
const HTML_TAG_RE = /<(?:[^>"']|"[^"]*"|'[^']*')+>/g;
const HTML_MEDIA_RE = /<(script|style)\b(?:[^>"']|"[^"]*"|'[^']*')*>[\s\S]*?<\/\1\s*>/gi;

/** @param {string} content */
function stripMarkup(content) {
  return content.replace(HTML_MEDIA_RE, ' ').replace(HTML_TAG_RE, ' ');
}

/**
 * Entity-decoded markup → stripped plain text.
 *
 * Double-decode: the payload often carries entity-escaped tags (`&lt;p&gt;`),
 * so the first pass reveals real tags, and text-level entities (`&amp;`,
 * `&#39;`) only become decodable once those tags are gone. Plain text is what
 * the description-consuming filters match against — substring matching over
 * raw HTML misses keywords split by a tag and pads matches into attribute
 * soup.
 * Strip literal markup before decoding so quote entities inside attributes
 * cannot become false delimiters. Strip after each decode so encoded active
 * markup cannot survive. Neutralize incomplete tag openers without losing text.
 *
 * Exported for tests.
 *
 * @param {unknown} content
 * @param {number} [maxChars] Search summaries are capped; full detail readers can pass Infinity.
 * @returns {string}
 */
export function htmlToText(content, maxChars = DESCRIPTION_CAP) {
  if (typeof content !== 'string' || !content) return '';
  const decoded = decodeEntities(stripMarkup(content));
  const decodedTwice = decodeEntities(stripMarkup(decoded));
  return stripMarkup(decodedTwice)
    .replace(/<(?=\/?[a-z!?])/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, maxChars);
}
