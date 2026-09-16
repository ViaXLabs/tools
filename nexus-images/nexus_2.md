Really thought this through again — here's the honest breakdown of what's fact vs. what's a hypothesis you still need to test.

**What I'm sure about (this is documented Confluence behavior, not a guess):** The Confluence API stores pages in "storage format," a strict XHTML dialect. A plain `<a href="URL">label</a>` inside a `<td>` is native to that format — it needs zero macros and zero admin permissions. This isn't in dispute; it's how Confluence has worked for years.

**What I'm not 100% sure about:** which exact failure mode is hitting *your* pipeline, since I haven't seen your code or the actual output. That's the part your "we have to test" instinct is right about. So instead of one guess, here's a quick diagnostic — look at the published page and match what you actually see:

| What you see on the page | What's actually happening | The fix |
|---|---|---|
| The literal text `<a href="...">name</a>` shows up, angle brackets and all | Wrong representation was sent (e.g. "view"/wiki markup instead of "storage"), or the HTML got double-escaped before sending | Send with `representation: "storage"`, and only escape the *dynamic* parts (URL, label) — never escape the tags themselves |
| A grey "Unknown macro" box, or nothing where the link should be | You're going through the legacy HTML macro, which is disabled by default (Data Center/Server) or doesn't exist natively at all (Cloud) | Drop the macro entirely — use plain `<a>` tags, no macro needed |
| The cell is just blank / link silently vanished, maybe an API error | Nexus URLs have `&` in the query string, and it wasn't XML-escaped, so the body wasn't valid XML | Build the tag with `xml.sax.saxutils.quoteattr()`/`escape()`, never raw string concatenation |

---

### Summary to send your friend

> Confluence's API stores pages in "storage format" (strict XHTML), not raw HTML and not CSV. A plain `<a href="URL">label</a>` inside a `<td>` works natively — no macro, no admin needed. CSV and the HTML macro were dead ends because CSV has no concept of a link, and the HTML macro is disabled by default.
>
> Check what the published page actually shows:
> - Literal `<a href...>` text visible → wrong representation type or double-escaping. Fix: send `representation: "storage"`, escape only the URL/label, not the tags.
> - "Unknown macro" box → you're using the HTML macro, which is off by default. Fix: don't use it, use plain `<a>` tags instead.
> - Blank cell / silent failure → unescaped `&` in the Nexus URL broke the XML. Fix: build the anchor with `xml.sax.saxutils.quoteattr()`.
>
> ```python
> from xml.sax.saxutils import escape, quoteattr
> row = f"<tr><td>{escape(name)}</td><td><a href={quoteattr(nexus_url)}>{escape(name)}</a></td></tr>"
> ```
> Send that as `body.storage.value` with `representation: "storage"` via the Confluence content API. No admin ticket needed for this part.

Test with one artifact first — ideally one whose Nexus URL has a `&` in it — and check the page source for which symptom shows up. That'll tell you which row of the table you're actually in.