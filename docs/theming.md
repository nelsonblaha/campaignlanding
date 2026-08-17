# Theming

Every colour, face and measure in the system is a custom property, and no rule
below the `:root` blocks reaches past one. So a retheme is a block of tokens in
your own stylesheet, not a fork of `campaignlanding.css`.

## The tokens

| Token | Role |
|---|---|
| `--ground` | The page. |
| `--surface` | Raised areas: the hero, cards, the modal. |
| `--sunken` | Recessed areas: input fields, bar tracks, code. |
| `--ink` / `--ink-2` / `--ink-3` | Body text, secondary text, quiet text. Keep the ladder monotonic against `--ground` or things stop reading as a hierarchy. |
| `--rule` | Hairlines and borders. |
| `--accent` | The one loud colour: buttons, links on hover, the current tab, the mark. |
| `--accent-soft` | Its low-contrast fill, for tinted backgrounds. |
| `--btn-ink` | Text on top of `--accent`. Must contrast with `--accent`, not with `--ground`. |
| `--verified` | Figures a reader can check. |
| `--alarm` | Figures that should worry them. |
| `--focus` | Keyboard focus rings. Deliberately not `--accent`: a focus ring that matches the accent is invisible on accent-coloured controls. |
| `--font-display` | Headings, labels, numbers. |
| `--font-body` | Reading text. |
| `--measure` | Width of the reading column. |
| `--wide` | Width of the hero, which carries a second column for the image. |
| `--h1-ratio`, `--eyebrow-ratio` | How wide the headline and eyebrow run per 1px of font size. Measured, per language. See below. |

`--verified` and `--alarm` are semantic, not decorative. If your page makes no
checkable claims, you probably do not need them; if it does, do not spend them on
anything else.

## Both themes, three states

The viewer has three, not two: an explicit dark choice, an explicit light choice,
and — the common case — no choice at all, where only `prefers-color-scheme`
separates them. The system defines the dark palette on bare `:root`, redefines the
tokens under `@media (prefers-color-scheme: light)` guarded as
`:root:not([data-theme="dark"])`, and redefines them again under
`:root[data-theme="light"]` so an explicit choice wins in both directions.

Dark is the base rather than the alternative for a reason worth knowing: some
in-app browsers — Facebook's among them — report no colour preference at all, and
with a light-first stylesheet they hand every reader arriving from a shared post
the wrong palette.

Follow the same shape when you override, and **never give a colour its only
definition inside a media query or a `[data-theme]` block**. A token defined only
under `prefers-color-scheme: dark` does not exist in the un-stamped state, and the
page renders one theme's text on the other theme's ground.

```css
:root {                                         /* your dark palette */
  --ground: #0E1411;
  --accent: #7BD389;
  --btn-ink: #06170B;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {              /* only the tokens that change */
    --ground: #F2F5F1;
    --accent: #1F7A35;
    --btn-ink: #FFFFFF;
  }
}
:root[data-theme="light"] {
  --ground: #F2F5F1;
  --accent: #1F7A35;
  --btn-ink: #FFFFFF;
}
```

## The headline ratio

The hero sizes its headline from the space actually available rather than a
guess, so on a wide screen it fills the column and never wraps. That needs one
number: how wide your headline runs per 1px of font size, including any mark
beside it.

Measure it, in the browser, at a wide window:

```js
const h1 = document.querySelector('.hero h1');
h1.scrollWidth / parseFloat(getComputedStyle(h1).fontSize)
```

Round it up slightly — a font that renders a hair wider on another machine would
wrap — and set it per language, because two headlines are never the same length:

```css
:root           { --h1-ratio: 24.0; }
html[lang="es"] { --h1-ratio: 29.15; }
```

Below 62rem the headline wraps normally and the ratio is unused: fitting 39
characters on one line at 390px would mean a 15px headline, smaller than the body
text.

## Fonts

The system ships system fonts on purpose — nothing is fetched from a CDN, which
is both a privacy claim and one less thing to fail. To use your own, self-host it,
`@font-face` it in your stylesheet, and set `--font-display` / `--font-body`.
Re-measure `--h1-ratio` afterwards: it is a property of the face, not the words.
