# campaignlanding

A landing page for pitching an idea to the public before the idea exists.

The shape is specific: one long page that makes an argument, in more than one
language, with an invitation at the end and a list of the people who accepted it.
It is what you put up when the honest answer to "does this exist yet?" is no, and
the next thing you need to know is whether anyone wants it.

The page is HTML you write and own. This package is the machinery behind it.

## What you get

- **Two languages at three addresses.** `/` adapts to the reader's browser and
  stays `/`. `/en/` and `/es/` mean themselves. The link people copy and paste
  around is the neutral one, so it doesn't force a language on whoever opens it.
- **A language switch that doesn't reload the page.** It fetches the other
  language, swaps the body, and restores your scroll position and open tab.
- **Addresses for parts of the page.** `/why`, `/roadmap`, `/services` — in both
  languages — arrive pre-scrolled and then quietly become `/` again.
- **A signup form that posts to you.** No Google Form, no Mailchimp, no embedded
  third party. It writes JSONL to a file on disk you can read with `cat`, with a
  honeypot, a fill-time floor and a per-IP rate limit in front of it.
- **One password-protected view of that list**, and a count on the public page
  that turns into an unread-notification badge for you alone. Configure no
  password and those routes do not exist.
- **A design system that already handles the hard parts:** a section rail that
  becomes a sticky bar on phones, tabs that survive a language swap, a modal that
  works with JavaScript off, tap-to-copy links, and a dark theme that is the
  default rather than the afterthought.
- **No trackers, no analytics, no fonts from a CDN, no build step.** A campaign
  arguing that its claims can be checked cannot afford to load a tracker.

## Five minutes

```sh
git clone https://github.com/nelsonblaha/campaignlanding
cd campaignlanding
pip install -e .
CAMPAIGN_DATA=/tmp/campaign flask --app example/app run --port 8100
```

`http://127.0.0.1:8100/` is a complete campaign for an invented tool library,
written out in full in English and Spanish, because a template full of
`Lorem ipsum` tells you nothing about how the thing reads when it is finished.
Copy `example/`, replace the words, and you have a campaign.

## What you write

Three things.

**`site/index.html`** and one file per other language. Plain HTML — there is no
template language and nothing to compile. It has to carry a handful of hooks the
script and stylesheet look for (`data-section`, `role="tablist"`,
`<!--JOIN-TAG-->`, a couple more), all of which are listed in
[docs/markup-contract.md](docs/markup-contract.md).

**`site/style.css`**, which loads after the system's and usually stays under
thirty lines: your headline's measured width, and any colour you want to change.
Every colour in the system is a custom property, so a retheme is a block of
tokens rather than a fork.

**`app.py`**, which is one `Config`:

```python
from campaignlanding import Config, Language, create_app

app = create_app(Config(
    name="Ridgeline Tool Library",
    site_dir="site",
    languages=[
        Language(code="en", page="index.html"),
        Language(code="es", page="es/index.html", prefix="es",
                 thanks_path="/es/gracias"),
    ],
    help_choices=frozenset({"updates", "board", "spread"}),
    sections={"why": "why", "por-que": "why"},
))
```

Everything else has a default, and the defaults are off: no admin, no canonical
redirect, no section URLs until you name them.

## The parts, and why they are like that

**Language.** A reader who has expressed no preference gets whichever language
their browser asks for, at `/`, once. After that a cookie remembers what they
chose and `/` stops guessing. Prefixed URLs never negotiate — a shared `/es/`
always opens in Spanish, which is what someone sending it deliberately meant.

The reason `/` doesn't redirect to `/es/` is that a redirect puts the language in
the address bar and therefore into every link copied from it. Where the sender's
language says nothing about the recipient's, that is the wrong thing to pass
around.

**Section URLs.** `/roadmap` serves the whole page with an attribute on `<body>`
saying where to scroll. The client scrolls without animation — the reader didn't
press anything — and then replaces the address with `/`. So the link works when
shared and disappears when used.

**Signups.** One JSONL file, appended under a lock, mode 0600. No database,
because the operational cost of a database is real and the benefit at this size
is zero, and because "you can read the list with `cat`" is a claim worth being
able to make.

**Admin.** One password, one signed cookie, one list view: no search, no export,
no API. The list is the most sensitive thing the box holds. With no secret and no
password hash configured — the default — `/login` and `/admin` return 404 and the
page contains no reference to them, so somebody else's copy of your repo exposes
nothing.

**Assets.** Every `.css` and `.js` reference in your HTML is rewritten with a
content hash at serve time, and the hashed URL is immutable while the bare one
revalidates. Pages are `no-cache`. A returning visitor can never run new HTML
against an old stylesheet.

## Deploying

`example/Dockerfile` and `example/docker-compose.yml` are a working deployment:
gunicorn with one worker (the rate limiter is in memory on purpose), a host
directory for the data so the signup file is a file you can back up with `cp`,
and a health check. `example/.env.example` explains the secrets, including the
one that costs everybody an hour: **do not put the password hash in a Compose
`.env` file** — Compose interpolates `$VAR`, a Werkzeug hash contains `$` as its
field separator, and the result is a hash with its salt removed that is
well-formed, non-empty, and wrong.

## Tests

```sh
python -m unittest discover tests
```

55 of them, no pytest, no fixtures library. They cover the parts that are easy to
get subtly wrong: negotiation and the one-way-switch regression, the honeypot
answering success, the watermark moving only after the list renders, `/api/`
staying exempt from the canonical redirect because a 301 turns a POST into a GET.

## In use

[chucodata.org](https://chucodata.org) — a proposal for a nonprofit AI service
owned by El Paso and Ciudad Juárez, which is where all of this was written first.
This package is that page with the campaign taken out.

## License

MIT. See [LICENSE](LICENSE).
