# The markup contract

Your page is plain HTML. There is no template language, nothing compiles, and you
can open the file in a browser and see most of it work. What the stylesheet and
the script need from it is this list, and nothing beyond it.

Anything marked **required** breaks something if it is missing. Everything else is
a component you use if you want it. `example/site/index.html` uses all of it.

## The page

```html
<html lang="en">                              <!-- required: picks the strings -->
<head>
  <meta name="color-scheme" content="dark light">
  <link rel="stylesheet" href="/campaignlanding.css">   <!-- required: the system -->
  <link rel="stylesheet" href="/style.css">             <!-- yours, loaded after -->
</head>
<body>
  …
  <!--JOIN-TAG-->                             <!-- replaced with the edge tag -->
  <script src="/campaignlanding.js"></script> <!-- required, last in body -->
</body>
```

Two things are injected at serve time and need somewhere to go:

| Hook | Becomes |
|---|---|
| `<!--JOIN-TAG-->` | The floating "join *n* others" tag, or nothing when the list is empty or below `show_count_above`. Put it just before the script. |
| `<!--JOIN-INLINE-->` | The same count as inline text, for inside a button. Use it as many times as you like. |
| `</body>` | The config island — this language's strings and where the other languages live — is inserted before it. **Required**: without a `</body>` the script falls back to built-in English. |

Both `JOIN` markers are replaced unconditionally, so a page never ships a stray
comment or a stale count. Neither is required.

## Sections

**Required** on every top-level section, including the hero:

```html
<section id="roadmap" data-section="roadmap">
```

`id` is what `#anchors` point at and may be translated (`id="hoja-de-ruta"`).
`data-section` is the key the server and the scroll-spy use and must be **the
same in every language** — that is the whole reason both attributes exist. It is
what `sections={"roadmap": "roadmap", "hoja-de-ruta": "roadmap"}` maps onto.

By convention the hero is `data-section="hero"`.

Inside, `.wrap` centres the column, `.col` holds it to a readable measure, and
`.stack` / `.stack-sm` / `.stack-lg` are flex columns with a gap. Use them instead
of margins on children.

## The section rail

One nav, two presentations: a fixed rail at the left edge on wide screens, a
sticky strip at the top on phones. Plain anchors, so it works with JavaScript off.

```html
<nav class="sectionnav" aria-label="Sections">
  <div class="nav-top">
    <div class="nav-dock">
      <button class="nav-icon nav-home" type="button" aria-label="Back to top">
        <img class="nav-logo" src="/img/mark.svg" alt="" width="64" height="64">
      </button>
      <div class="nav-lang" aria-hidden="true">
        <span class="nav-flag is-current" aria-current="page" lang="en">🇺🇸</span>
        <a class="nav-flag" href="/es/" lang="es" hreflang="es" tabindex="-1">🇲🇽</a>
      </div>
    </div>
    <div class="nav-social">
      <a class="nav-icon nav-fb" href="…">…</a>          <!-- optional -->
      <button class="nav-icon nav-copy" type="button">…</button>
    </div>
  </div>
  <a href="#roadmap" data-slug="roadmap">
    <span class="nav-long">Roadmap</span>                <!-- desktop rail -->
    <span class="nav-short">Plan</span>                  <!-- narrow bar -->
    <span class="nav-min" aria-hidden="true">?</span>    <!-- optional, tiny screens -->
  </a>
</nav>
```

- `data-slug` is the address this section has (`/roadmap`). Give the same slug to
  `sections` in your config. Without it the link still scrolls; it just isn't
  shareable and doesn't copy on a second tap.
- The three label spans are a size ladder, not alternatives: the bar picks one by
  width. One label is fine — repeat it, or omit the others.
- `.nav-home` scrolls to the top rather than navigating, so it leaves no history
  entry and no `#` in the address.
- `.nav-copy` copies the page URL with no fragment.
- Anything with `class="nav-brand"` is excluded from the scroll-spy.

## Language switch

The script binds to **`a[hreflang]`**, anywhere on the page. That is the only
hook. Both the rail flags and the hero's `.langbar` use it:

```html
<nav class="langbar" aria-label="Language">
  <span aria-current="page" lang="en"><span class="flag">🇺🇸</span><span class="lang-word">English</span></span>
  <span class="sep" aria-hidden="true">/</span>
  <a href="/es/" lang="es" hreflang="es"><span class="flag">🇲🇽</span><span class="lang-word">Español</span></a>
</nav>
```

Point the *other* language's link at its prefixed URL (`/es/`), and the current
language's marker at nothing — it is not a link. On the non-primary page, link
back to the primary language's explicit address (`/en/`), **not** to `/`, which
negotiates and would hand a reader the language they were trying to leave.

## Tabs

Several arguments in one section, one visible at a time. Standard ARIA:

```html
<div class="tabs" id="reason-tabs">
  <div class="tablist" role="tablist" aria-label="Reasons">
    <button class="tab" role="tab" id="tab-cost" data-slug="cost"
            aria-controls="panel-cost" aria-selected="true">
      <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true">…</svg><span>Cost</span>
    </button>
  </div>
  <div class="panel stack-lg" role="tabpanel" id="panel-cost"
       aria-labelledby="tab-cost" tabindex="0">…</div>
</div>
```

- `[role="tablist"]` is what the script looks for, and the wrapper it sits in is
  found from it, so the wrapper's `id` is yours to name — but **the wrapper needs
  `class="tabs"`**. Without JavaScript every panel is shown, stacked, and the bar
  is hidden by `.tabs:not(.js-tabs) .tablist { display: none }`, because a bar
  that cannot switch anything is worse than no bar. The script adds `.js-tabs` to
  opt into the collapsed presentation, so nothing is ever hidden from a reader
  who has no JavaScript — and if that class lands on the wrong element, the bar
  stays hidden from everyone.
- Tab **ids must be identical across languages** — that is what `tabs={"cost":
  "tab-cost", "costo": "tab-cost"}` keys on, since the labels differ and the ids
  do not.
- Mark inactive panels `hidden`. The script manages `hidden`, `aria-selected` and
  roving `tabindex` from there.
- `data-slug` gives the tab an address that opens the section with it selected,
  and makes a second tap on the selected tab copy that address.

## The signup form

```html
<div class="modal" id="signup" role="dialog" aria-modal="true" aria-labelledby="signup-title">
  <a class="modal-scrim" href="#" tabindex="-1" aria-hidden="true"></a>
  <div class="modal-card">
    <a class="modal-close" href="#" aria-label="Close">&times;</a>
    <h3 id="signup-title">Add your name</h3>
    <form class="form-card" method="post" action="/api/signup">
      <div class="field"><label for="contact">…</label><input id="contact" name="contact" required></div>
      <div class="field"><label for="name">…</label><input id="name" name="name"></div>
      <fieldset class="checks">
        <legend>I might be able to help with</legend>
        <label class="check"><input type="checkbox" name="help" value="updates" checked> …</label>
      </fieldset>
      <div class="field"><label for="note">…</label><textarea id="note" name="note" rows="3"></textarea></div>

      <div class="hp" aria-hidden="true">
        <label for="website">Leave this empty</label>
        <input type="text" id="website" name="website" tabindex="-1" autocomplete="off">
      </div>
      <input type="hidden" name="t" id="t" value="">
      <input type="hidden" name="lang" value="en">

      <p class="form-msg" id="form-msg" role="status" aria-live="polite"></p>
      <div class="cta-row">
        <button class="btn" type="submit">Sign me up &rarr;</button>
        <a class="btn btn-quiet" href="#" data-modal-close>Cancel</a>
      </div>
    </form>
  </div>
</div>
```

| Part | Why it is not optional |
|---|---|
| `id="signup"` | The modal opens on `:target`, so `href="#signup"` works with JavaScript off. |
| `action="/api/signup"` | How the script finds the form. An absolute URL ending the same way works; so does `data-signup` on the form. |
| `name="contact"` | The only required field. Accepts an email address or a phone number; anything else is refused. |
| `name="website"` in `.hp` | The honeypot. Hidden from people, irresistible to bots, and a filled one is answered with success so a bot learns nothing. |
| `name="t"` | The script stamps it on load. A submission faster than `min_fill_seconds` is refused. |
| `name="lang"` | Which language the reader was reading. Stored with the signup. |
| `#form-msg` | Where the in-place response goes. |
| `[data-modal-close]` | Closes without navigating. |

`help` checkbox values must appear in `help_choices` or they are dropped.

## Components

| Class | What it is |
|---|---|
| `.btn`, `.btn-quiet`, `.btn-arrow` | Buttons; `.cta-row` lays a group of them out. |
| `.btn-with-sub` + `.btn-stack` | A button with a second line, for `<!--JOIN-INLINE-->`. |
| `.hero-mark` | A logo sized to the headline's text height, inline inside the `h1`. |
| `.hero-figure`, `.hero-credit` | The image column beside the hero text, with its credit. |
| `.sunline` | The small line above the headline. |
| `.lede`, `.fine`, `.eyebrow`, `.num`, `.clause` | Type roles. `.clause` marks a sentence so a two-sentence heading breaks between them. |
| `.meter` + `.bar-row`/`.bar-track`/`.bar-fill[data-w]` | Comparison bars. `data-w` is a percentage; they fill as they scroll into view. |
| `.tiers` + `.tier`/`.tier-name`/`.tier-price` | Price or membership cards. |
| `.phase` + `.phase-n`/`.phase-title`/`.phase-body` | Numbered roadmap steps. |
| `.asks` + `.ask`/`.ask-n` | A numbered list of requests. |
| `.quote` + `<cite>` | A pull quote. |
| `.callout` | A boxed aside. |
| `.svc` + `.svc-item` | A two-column list of things and what they are. |
| `.ref` / `.refs` | Superscript citations and the numbered source list they point at. |
| `.scroll-x` | Wraps anything wide so the page body never scrolls sideways. |

## Copy-to-clipboard, which is undocumented on the page itself

Three things copy a link when tapped, on the same rule: **clicking what you are
already on has nothing to navigate to, so it hands you the address instead.**

- a rail link for the section you are already at
- a tab that is already selected
- any section heading — the first `.eyebrow` and the first `h2` in a section,
  which copy on every click, since a heading has no other meaning

All three confirm with a tooltip afterwards, because an action with no feedback
is indistinguishable from a dead click. None of them advertise themselves.

## What the script does not need

No `data-` attributes for behaviour beyond the ones above, no initialisation
call, no ordering requirements among sections, and no JavaScript in your page.
Everything binds on load and re-binds after a language swap.
