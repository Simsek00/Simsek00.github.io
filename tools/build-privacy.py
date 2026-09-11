#!/usr/bin/env python3
"""Render the games' privacy policies into pages of this site.

The policy text is NOT written here. It is owned by each game's own repository,
because the app ships it too — HexaWord bundles the markdown as an asset and
reads it offline, and Pitch Tactics links it from its About screen. Google Play
rejects a listing whose in-app text, store listing and hosted policy disagree,
so this script copies rather than rewrites: it turns the markdown into HTML and
changes nothing else.

Sources (clone the repos next to this one, or pass --src):

    hexaword       Simsek00/HexaWord    docs/privacy-policy.md
                   One file, Turkish first, English after a `---\\n---` break.

    pitch-tactics  Simsek00/Mobil       futbol_menajer/docs/privacy/
                   Two files: gizlilik-politikasi.md (tr), privacy-policy.md (en).

Usage:

    python3 tools/build-privacy.py \\
        --hexaword /home/user/hexaword \\
        --pitch-tactics /home/user/mobil

Writes hexaword/privacy/index.html and pitch-tactics/privacy/index.html.
Re-run it whenever a policy changes upstream; never hand-edit the output.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------
# markdown -> html
#
# The policies use a deliberately small subset: h1, h2, paragraphs, bullet
# lists, bold, inline code, links and `---` rules. Anything else would be a
# surprise, so unknown constructs are passed through as text rather than
# guessed at.
# --------------------------------------------------------------------------

CODE_TOKEN = "\x00CODE%d\x00"

ITEM_UL = re.compile(r"^-\s+")
ITEM_OL = re.compile(r"^(\d+)\.\s+")
CELL_RULE = re.compile(r"^:?-{2,}:?$")


def inline(text: str) -> str:
    """Bold, emphasis, inline code and links, with code spans held out of the way."""
    codes: list[str] = []

    def stash(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return CODE_TOKEN % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}" rel="noopener">{m.group(1)}</a>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Single asterisks, once the bold markers are gone. Kept tight — no spaces
    # against the delimiters — so a stray asterisk in prose is left alone.
    text = re.sub(r"\*(\S[^*]*?\S|\S)\*", r"<em>\1</em>", text)

    for i, code in enumerate(codes):
        text = text.replace(CODE_TOKEN % i, f"<code>{html.escape(code, quote=False)}</code>")
    return text


def slug(heading: str, lang: str) -> str:
    """A stable anchor. Numbered sections keep their number, which is what the
    two language versions have in common."""
    # `## 4. Title` and `### 4.1 Title` must not collapse onto the same anchor.
    m = re.match(r"^(\d+)\.(\d+)\s", heading.strip())
    if m:
        return f"s{m.group(1)}-{m.group(2)}-{lang}"
    m = re.match(r"^(\d+)\.\s", heading.strip())
    if m:
        return f"s{m.group(1)}-{lang}"
    base = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
    return f"{base[:40]}-{lang}"


def group_items(lines: list[str], pattern: re.Pattern[str]) -> list[str]:
    """Split list lines into items, folding wrapped continuation lines back in.

    A list item in these policies routinely runs onto a second, indented line;
    treating every line as its own item would silently double the list.
    """
    items: list[str] = []
    for line in lines:
        m = pattern.match(line.strip())
        if m:
            items.append(line.strip()[m.end():].strip())
        elif items:
            items[-1] += " " + line.strip()
        else:
            items.append(line.strip())
    return items


def render_table(lines: list[str]) -> str:
    """A pipe table. The first row is a header unless every cell in it is empty,
    which is how the two-column fact tables in these policies are written."""
    rows: list[list[str]] = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and all(CELL_RULE.fullmatch(c) for c in cells):
            continue  # the |---|---| alignment row
        rows.append(cells)
    if not rows:
        return ""

    head, body = rows[0], rows[1:]
    out = ['<div class="table-wrap"><table>']
    if any(c for c in head):
        out.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead>")
    out.append("<tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def render_block(lines: list[str]) -> str:
    """Turn one run of consecutive non-blank lines into HTML.

    The kind is decided by the first line: anything unrecognised falls through
    to a paragraph rather than being guessed at.
    """
    first = lines[0].strip()

    if first.startswith("|"):
        return render_table(lines)

    if first.startswith(">"):
        text = " ".join(l.strip().lstrip(">").strip() for l in lines)
        return f"<blockquote><p>{inline(text)}</p></blockquote>"

    if ITEM_UL.match(first):
        items = group_items(lines, ITEM_UL)
        return "<ul>" + "".join(f"<li>{inline(t)}</li>" for t in items) + "</ul>"

    if ITEM_OL.match(first):
        start = int(ITEM_OL.match(first).group(1))
        attr = f' start="{start}"' if start != 1 else ""
        items = group_items(lines, ITEM_OL)
        return f"<ol{attr}>" + "".join(f"<li>{inline(t)}</li>" for t in items) + "</ol>"

    if len(lines) > 1 and all(l.strip().startswith("**") for l in lines):
        # A run of `**Label:** value` lines is a metadata stack, not one
        # paragraph — markdown would join them, which is not the intent.
        return '<p class="rows">' + "<br>".join(inline(l.strip()) for l in lines) + "</p>"

    return f"<p>{inline(' '.join(l.strip() for l in lines))}</p>"


@dataclass
class Policy:
    title: str
    meta: list[str]      # the dated `**Label:** value` header, boxed
    intro: list[str]     # any prose before the first section
    sections: list[tuple[str, str, str]]  # (anchor, heading, body html)


def parse(md: str, lang: str) -> Policy:
    lines = md.replace("\r\n", "\n").split("\n")
    title = ""
    meta: list[str] = []
    intro: list[str] = []
    sections: list[tuple[str, str, str]] = []

    current_heading: str | None = None
    buf: list[str] = []
    block: list[str] = []
    mode = "meta"  # until the first `##`

    def target() -> list[str]:
        return buf if mode == "body" else (intro if intro else meta)

    def flush_block() -> None:
        if not block:
            return
        into = target()
        bold_run = len(block) > 1 and all(l.strip().startswith("**") for l in block)
        if into is meta and not bold_run:
            # Prose in the header region is a lede, not metadata.
            into = intro
        into.append(render_block(block))
        block.clear()

    def flush_section() -> None:
        flush_block()
        if current_heading is not None:
            sections.append((slug(current_heading, lang), current_heading, "".join(buf)))
        buf.clear()

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if line.startswith("# "):
            title = line[2:].strip()
            continue

        if line.startswith("### "):
            flush_block()
            heading = line[4:].strip()
            target().append(f'<h3 id="{slug(heading, lang)}">{inline(heading)}</h3>')
            continue

        if line.startswith("## "):
            if mode == "meta":
                flush_block()
                mode = "body"
            else:
                flush_section()
            current_heading = line[3:].strip()
            continue

        if stripped == "---":
            flush_block()
            target().append('<hr class="legal-rule">')
            continue

        if not stripped:
            flush_block()
            continue

        block.append(line)

    flush_section()
    return Policy(title=title, meta=meta, intro=intro, sections=sections)


# --------------------------------------------------------------------------
# page assembly
# --------------------------------------------------------------------------

STRINGS = {
    "en": {
        "toc": "On this page",
        "back": "Back to {game}",
        "home": "Home",
        "skip": "Skip to content",
        "contact": "Contact",
        "elsewhere": "Elsewhere",
        "allgames": "All games",
        "top": "Back to top",
    },
    "tr": {
        "toc": "Bu sayfada",
        "back": "{game} sayfasına dön",
        "home": "Ana sayfa",
        "skip": "İçeriğe geç",
        "contact": "İletişim",
        "elsewhere": "Diğer",
        "allgames": "Tüm oyunlar",
        "top": "Başa dön",
    },
}


def render_policy(p: Policy, lang: str, game_path: str, game_name: str) -> str:
    s = STRINGS[lang]
    out: list[str] = [f'<div lang="{lang}" class="legal">']
    out.append(
        f'<a class="back-link" href="{game_path}">'
        f'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f'<path d="M19 12H5M12 19l-7-7 7-7"/></svg>'
        f'{html.escape(s["back"].format(game=game_name))}</a>'
    )
    out.append(f"<h1>{inline(p.title)}</h1>")
    if p.meta:
        out.append(f'<div class="legal-meta">{"".join(p.meta)}</div>')
    if p.intro:
        out.append(f'<div class="legal-intro">{"".join(p.intro)}</div>')

    if len(p.sections) >= 6:
        items = "".join(
            f'<li><a href="#{anchor}">{inline(heading)}</a></li>'
            for anchor, heading, _ in p.sections
        )
        out.append(
            f'<nav class="toc" aria-label="{html.escape(s["toc"], quote=True)}">'
            f'<h2>{html.escape(s["toc"])}</h2><ol>{items}</ol></nav>'
        )

    for anchor, heading, body in p.sections:
        out.append(f'<h2 id="{anchor}">{inline(heading)}</h2>{body}')

    out.append(f'<p class="to-top"><a href="#main">{html.escape(s["top"])}</a></p>')
    out.append("</div>")
    return "\n".join(out)


PAGE = """<!DOCTYPE html>
<html lang="en" data-lang="en">

<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title_en}</title>
    <meta name="description" content="{desc_en}">
    <meta name="theme-color" content="{theme_color}">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://simsek00.github.io{path}">

    <meta property="og:type" content="article">
    <meta property="og:site_name" content="Meok Apps">
    <meta property="og:title" content="{title_en}">
    <meta property="og:description" content="{desc_en}">
    <meta property="og:url" content="https://simsek00.github.io{path}">

    <link rel="icon" href="{favicon}">

    <link rel="stylesheet" href="/assets/site.css">

    <script>
        (function () {{
            var r = document.documentElement, lang = null, theme = null;
            try {{ lang = localStorage.getItem('meok-lang'); theme = localStorage.getItem('meok-theme'); }} catch (e) {{ }}
            if (lang !== 'tr' && lang !== 'en') {{
                lang = (navigator.language || 'en').toLowerCase().indexOf('tr') === 0 ? 'tr' : 'en';
            }}
            r.setAttribute('data-lang', lang);
            r.setAttribute('lang', lang);
            if (theme === 'dark' || theme === 'light') r.setAttribute('data-theme', theme);
        }})();
    </script>
{extra_style}</head>

<body class="{body_class}">

    <a class="skip-link" href="#main">
        <span lang="en">Skip to content</span>
        <span lang="tr">İçeriğe geç</span>
    </a>

    <header class="site-header">
        <div class="wrap">
            <a class="brand" href="/" aria-label="Meok Apps">
                <svg width="24" height="26" viewBox="0 0 24 26" aria-hidden="true">
                    <path d="M12 1 L22.4 7 V19 L12 25 L1.6 19 V7 Z" fill="currentColor" opacity=".12" />
                    <path d="M12 1 L22.4 7 V19 L12 25 L1.6 19 V7 Z" fill="none" stroke="currentColor"
                        stroke-width="1.5" />
                    <path d="M12 7.6 L17.2 10.6 V16.6 L12 19.6 L6.8 16.6 V10.6 Z" fill="currentColor" />
                </svg>
                Meok Apps
            </a>

            <nav class="nav" aria-label="Main">
                <a href="/">
                    <span lang="en">Home</span><span lang="tr">Ana sayfa</span>
                </a>
                <a href="/pitch-tactics/"{pt_current}>Pitch Tactics</a>
                <a href="/hexaword/"{hw_current}>HexaWord</a>
                <a href="/about/">
                    <span lang="en">About</span><span lang="tr">Hakkımda</span>
                </a>
            </nav>

            <div class="controls">
                <div class="switch" role="group" aria-label="Language / Dil">
                    <button type="button" data-set-lang="en" aria-pressed="true">EN</button>
                    <button type="button" data-set-lang="tr" aria-pressed="false">TR</button>
                </div>
                <button type="button" class="icon-btn" data-toggle-theme aria-label="Switch theme">
                    <svg class="icon-sun" width="16" height="16" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                        <circle cx="12" cy="12" r="4.5" />
                        <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
                    </svg>
                    <svg class="icon-moon" width="16" height="16" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                        aria-hidden="true">
                        <path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z" />
                    </svg>
                </button>
            </div>
        </div>
    </header>

    <main id="main">
        <section class="legal-page">
            <div class="wrap">
{body}
            </div>
        </section>
    </main>

    <footer class="site-footer">
        <div class="wrap">
            <div class="footer-grid">
                <div>
                    <h3>{game_name}</h3>
                    <ul>
                        <li><a href="{game_path}">
                            <span lang="en">Game page</span><span lang="tr">Oyun sayfası</span>
                        </a></li>
{store_link}
                    </ul>
                </div>
                <div>
                    <h3>
                        <span lang="en">Elsewhere</span><span lang="tr">Diğer</span>
                    </h3>
                    <ul>
                        <li><a href="/">
                            <span lang="en">All games</span><span lang="tr">Tüm oyunlar</span>
                        </a></li>
                        <li><a href="{other_path}">{other_name}</a></li>
                        <li><a href="{other_privacy}">
                            <span lang="en">{other_name} privacy policy</span>
                            <span lang="tr">{other_name} gizlilik politikası</span>
                        </a></li>
                    </ul>
                </div>
                <div>
                    <h3>
                        <span lang="en">Contact</span><span lang="tr">İletişim</span>
                    </h3>
                    <ul>
                        <li><a href="mailto:55mehmetokur@gmail.com">55mehmetokur@gmail.com</a></li>
                    </ul>
                </div>
            </div>

            <div class="footer-bottom">
                <span>© <span data-year>2026</span> Meok Apps</span>
                <span lang="en">This page is the published privacy policy for {game_name}.</span>
                <span lang="tr">Bu sayfa {game_name} için yayımlanmış gizlilik politikasıdır.</span>
            </div>
        </div>
    </footer>

    <script>
        window.PAGE_META = {{
            en: {{ title: {title_en_js}, desc: {desc_en_js} }},
            tr: {{ title: {title_tr_js}, desc: {desc_tr_js} }}
        }};
    </script>
    <script src="/assets/site.js" defer></script>

</body>

</html>
"""


def js(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


HEX_STYLE = """
    <style>
        /* HexaWord's warm ground, the same one its game page uses. */
        body.t-hex {
            --bg: #FAF6EC;
            --bg-2: #F3ECDB;
            --surface: #FFFDF8;
            --surface-2: #F4EEE0;
            --ink: #3F382E;
            --ink-2: #6B6252;
            --ink-3: #92897A;
            --line: #E8DFC9;
            --line-strong: #D9CDB0;
        }

        @media (prefers-color-scheme: dark) {
            :root:not([data-theme="light"]) body.t-hex {
                --bg: #17130D;
                --bg-2: #1D1811;
                --surface: #221C14;
                --surface-2: #2B241A;
                --ink: #F2EBDA;
                --ink-2: #BEB29A;
                --ink-3: #948977;
                --line: #322A1E;
                --line-strong: #443A2A;
            }
        }

        :root[data-theme="dark"] body.t-hex {
            --bg: #17130D;
            --bg-2: #1D1811;
            --surface: #221C14;
            --surface-2: #2B241A;
            --ink: #F2EBDA;
            --ink-2: #BEB29A;
            --ink-3: #948977;
            --line: #322A1E;
            --line-strong: #443A2A;
        }
    </style>
"""

GAMES = {
    "hexaword": dict(
        game_name="HexaWord",
        game_path="/hexaword/",
        path="/hexaword/privacy/",
        body_class="t-hex",
        theme_color="#F6E3BE",
        extra_style=HEX_STYLE,
        hw_current=' aria-current="page"',
        pt_current="",
        other_name="Pitch Tactics",
        other_path="/pitch-tactics/",
        other_privacy="/pitch-tactics/privacy/",
        favicon=(
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
            "%3Cpath d='M16 1.5 L28.5 8.75 V23.25 L16 30.5 L3.5 23.25 V8.75 Z' fill='%23E2B15B' "
            "stroke='%23B98F3E' stroke-width='1.5'/%3E%3Ctext x='16' y='22.5' text-anchor='middle' "
            "font-family='system-ui,sans-serif' font-size='16' font-weight='700' fill='%234A4238'%3E"
            "H%3C/text%3E%3C/svg%3E"
        ),
        store_link=(
            '                        <li><a href="https://play.google.com/store/apps/'
            'details?id=hexaword.mehmetokur.com">Google Play</a></li>'
        ),
        title_en="HexaWord Privacy Policy | Meok Apps",
        title_tr="HexaWord Gizlilik Politikası | Meok Apps",
        desc_en=(
            "The privacy policy for HexaWord: what the game stores on your device, what "
            "Google AdMob receives, and your rights under the KVKK and the GDPR."
        ),
        desc_tr=(
            "HexaWord gizlilik politikası: oyunun cihazınızda ne sakladığı, Google AdMob'un "
            "ne aldığı ve KVKK ile GDPR kapsamındaki haklarınız."
        ),
    ),
    "pitch-tactics": dict(
        game_name="Pitch Tactics",
        game_path="/pitch-tactics/",
        path="/pitch-tactics/privacy/",
        body_class="t-pitch",
        theme_color="#0E2A20",
        extra_style="",
        hw_current="",
        pt_current=' aria-current="page"',
        other_name="HexaWord",
        other_path="/hexaword/",
        other_privacy="/hexaword/privacy/",
        favicon=(
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
            "%3Crect width='32' height='32' rx='8' fill='%232E7D5B'/%3E%3Cg fill='none' "
            "stroke='%23ffffff' stroke-width='2' opacity='.85'%3E%3Cpath d='M4 16h24'/%3E"
            "%3Ccircle cx='16' cy='16' r='5.5'/%3E%3C/g%3E%3C/svg%3E"
        ),
        store_link=(
            '                        <li><span lang="en">Coming soon to Google Play</span>'
            '<span lang="tr">Yakında Google Play\'de</span></li>'
        ),
        title_en="Pitch Tactics Privacy Policy | Meok Apps",
        title_tr="Pitch Tactics Gizlilik Politikası | Meok Apps",
        desc_en=(
            "The privacy policy for Pitch Tactics: Soccer Manager — the game collects nothing, "
            "saves stay on your device, and what Google AdMob receives is set out in full."
        ),
        desc_tr=(
            "Pitch Tactics: Soccer Manager gizlilik politikası — oyun hiçbir şey toplamıyor, "
            "kayıtlar cihazda kalıyor, Google AdMob'un ne aldığı ise eksiksiz anlatılıyor."
        ),
    ),
}


def build(key: str, md_tr: str, md_en: str) -> str:
    cfg = GAMES[key]
    body = "\n".join(
        render_policy(parse(md, lang), lang, cfg["game_path"], cfg["game_name"])
        for lang, md in (("en", md_en), ("tr", md_tr))
    )
    return PAGE.format(
        body=body,
        title_en_js=js(cfg["title_en"]),
        title_tr_js=js(cfg["title_tr"]),
        desc_en_js=js(cfg["desc_en"]),
        desc_tr_js=js(cfg["desc_tr"]),
        **cfg,
    )


def write(key: str, markup: str) -> None:
    out_dir = os.path.join(ROOT, key, "privacy")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(markup)
    print(f"wrote {os.path.relpath(out, ROOT)} ({len(markup):,} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hexaword", help="path to a Simsek00/HexaWord checkout")
    ap.add_argument("--pitch-tactics", help="path to a Simsek00/Mobil checkout")
    args = ap.parse_args()

    if not args.hexaword and not args.pitch_tactics:
        ap.error("give at least one of --hexaword / --pitch-tactics")

    if args.hexaword:
        src = os.path.join(args.hexaword, "docs", "privacy-policy.md")
        text = open(src, encoding="utf-8").read()
        parts = re.split(r"\n---\s*\n---\s*\n", text)
        if len(parts) != 2:
            print(f"error: expected one `---/---` language break in {src}, found {len(parts) - 1}", file=sys.stderr)
            return 1
        write("hexaword", build("hexaword", md_tr=parts[0], md_en=parts[1]))

    if args.pitch_tactics:
        base = os.path.join(args.pitch_tactics, "futbol_menajer", "docs", "privacy")
        md_tr = open(os.path.join(base, "gizlilik-politikasi.md"), encoding="utf-8").read()
        md_en = open(os.path.join(base, "privacy-policy.md"), encoding="utf-8").read()
        write("pitch-tactics", build("pitch-tactics", md_tr=md_tr, md_en=md_en))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
