"""The engine: serves the page, accepts signups, and knows nothing about yours.

Small on purpose. There is no database, no third-party form service, no
analytics and no trackers, and adding any of them would cost a campaign the one
thing a page like this is trying to establish, which is that its claims can be
checked.

Everything specific to a campaign arrives as a Config. If you find yourself
editing this file to launch a page, that is a bug in the package.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, request, send_from_directory, session
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from . import admin as admin_module
from .config import Config, Language, load_secrets
from .store import SignupStore

PACKAGE_STATIC = Path(__file__).parent / "static"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9\-.() ]{6,19}$")
# Anything that reads as a link. Deliberately loose about the scheme, because the
# spam that motivated it wrote a bare "searchindex.net" with no scheme at all.
LINK_RE = re.compile(
    r"(https?://|www\.|\b[a-z0-9-]+\.(com|net|org|io|ru|cn|info|biz|xyz|top|shop|club|online|site)\b)",
    re.IGNORECASE,
)
# Every file the page loads, not only its stylesheet and script. A picture changed
# behind an unchanged URL is exactly what a cache in front of the site keeps
# serving: Cloudflare's browser TTL rewrites even `no-cache` on static types to
# four hours, so the only reference no cache can hold back is a new one. A
# reference that already carries a query string is the author versioning by hand,
# and is left alone.
ASSET_RE = re.compile(
    r'\b(href|src)="([^"?#]+\.(?:css|js|svg|png|jpe?g|gif|webp|avif|ico|woff2?|ttf|otf|webmanifest))"',
    re.IGNORECASE,
)
BODY_RE = re.compile(r"<body([^>]*)>", re.IGNORECASE)
# Written literally into the form's hidden field by the page author; replaced with
# a signed stamp at render time.
FORM_TOKEN_MARKER = "<!--FORM-TOKEN-->"

# What the reader's choice of language is written to. Its single job is to mean
# "stop guessing for me", in either direction.
CHOICE_COOKIE = "lang"


class RateLimiter:
    """Per-IP sliding window, in memory.

    In memory is a deliberate limit, not an oversight: it means one worker
    process. For a page like this that is the right shape, and if it ever isn't,
    the limiter belongs in the proxy rather than in a shared store here.
    """

    def __init__(self, maximum: int, window: int, cap: int = 5000):
        self.maximum = maximum
        self.window = window
        self.cap = cap
        self._hits: dict[str, deque] = {}

    def hit(self, key: str) -> bool:
        now = time.time()
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.maximum:
            return True
        q.append(now)
        if len(self._hits) > self.cap:  # bound memory; oldest buckets are stale anyway
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                self._hits.pop(k, None)
        return False


class Runtime:
    """The per-app state the views share. One instance per create_app()."""

    def __init__(self, config: Config):
        self.config = config
        self.store = SignupStore(config.data_dir)
        self.signup_limiter = RateLimiter(config.rate_max, config.rate_window)
        self.login_limiter = RateLimiter(config.login_max, config.login_window, cap=2000)
        self._versions: dict[str, str] = {}

    # ---- who is asking ---------------------------------------------------

    def client_ip(self) -> str:
        # A reverse proxy sets X-Forwarded-For; take the leftmost entry.
        fwd = request.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() or (request.remote_addr or "unknown")

    def admin_enabled(self) -> bool:
        return bool(self.config.secret_key and self.config.admin_password_hash)

    def is_admin(self) -> bool:
        return self.admin_enabled() and session.get("admin") is True

    # ---- files -----------------------------------------------------------

    def asset_path(self, relative: str) -> Path | None:
        """A site's own file wins over the package's.

        That is the entire override mechanism: drop a file with the same name in
        your site directory and yours is served. There is no build step and
        nothing to configure.
        """
        clean = relative.lstrip("/")
        if ".." in clean.split("/"):
            return None
        for root in (self.config.site_dir, PACKAGE_STATIC):
            candidate = root / clean
            if candidate.is_file():
                return candidate
        return None

    def version(self, relative: str) -> str:
        """A content hash, computed once per process.

        The pages are served no-cache and their asset references carry this, which
        makes the assets safely immutable and any change visible immediately. The
        alternative — a stylesheet with a max-age — means a returning visitor runs
        new HTML against an old stylesheet until it expires.
        """
        if relative not in self._versions:
            path = self.asset_path(relative)
            self._versions[relative] = (
                hashlib.sha256(path.read_bytes()).hexdigest()[:10] if path else ""
            )
        return self._versions[relative]


def create_app(config: Config, *, read_env: bool = True) -> Flask:
    if read_env:
        config = load_secrets(config)
    rt = Runtime(config)
    app = Flask(__name__, static_folder=None)
    app.config["campaign"] = rt

    # A random key when none is configured: unforgeable, and unusable, which is
    # what "no admin" should mean. Sessions are a signed cookie, so there is no
    # store to keep.
    app.secret_key = config.secret_key or os.urandom(32)
    app.config.update(
        SESSION_COOKIE_NAME=config.session_cookie_name,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=365),
    )

    # ------------------------------------------------------------------
    # Proof the page was actually fetched
    #
    # The form carries a stamp the server signed when it rendered the page. It
    # replaces a timestamp that JavaScript used to write into the same field,
    # which had two problems: it made the check depend on JavaScript, and a script
    # that never loaded the page simply omitted the field, which read as "filled
    # in long ago" and sailed through.
    #
    # Signed and server-issued, it is the opposite: a submission cannot carry one
    # without having asked for the page, JavaScript or not, and the age it
    # measures is the server's own clock rather than the client's word for it.
    #
    # A campaign whose markup predates this keeps the old behaviour, because
    # silently refusing every signup on an upgrade would be a worse failure than
    # the one this fixes. The warning below is how you find out.
    # ------------------------------------------------------------------

    signer = TimestampSigner(app.secret_key, salt="campaignlanding-form")
    token_in_markup = all(
        FORM_TOKEN_MARKER in (config.site_dir / lang.page).read_text(encoding="utf-8")
        for lang in config.languages
        if (config.site_dir / lang.page).exists()
    )
    if not token_in_markup:
        app.logger.warning(
            "no %s in the signup form: falling back to the client-supplied stamp, "
            "which a script that never loads the page can omit entirely",
            FORM_TOKEN_MARKER,
        )

    def form_age(raw: str) -> float | None:
        """Seconds since this form was rendered, or None if it cannot be trusted."""
        if not raw:
            return None
        try:
            _, issued = signer.unsign(raw, max_age=config.form_max_age, return_timestamp=True)
        except (BadSignature, SignatureExpired):
            return None
        return (datetime.now(timezone.utc) - issued).total_seconds()

    # ------------------------------------------------------------------
    # Language
    #
    # "/" adapts to Accept-Language exactly once: if the visitor has never chosen
    # a language, and their browser ranks another configured language above the
    # primary one, they get that language at "/". Everything else is
    # deterministic.
    #
    # Why here and not in the browser: on first load there is no scroll position
    # to preserve, so choosing on the server costs nothing that the in-place swap
    # was built to protect, and it avoids showing a reader a page of the wrong
    # language before JavaScript can replace it. Doing it client-side would
    # either flash the wrong language or need a blocking script in <head>.
    #
    # Why it is this narrow:
    #   - A prefixed URL NEVER negotiates, so a shared "/es/" always lands on
    #     Spanish.
    #   - "/" with a `lang` cookie never negotiates either. Asking for the
    #     neutral URL after having made a choice gets the choice. That also makes
    #     the no-JS path loop-free.
    #   - The cookie is written only by the client, when the reader switches.
    # ------------------------------------------------------------------

    def negotiate(header: str) -> Language:
        """The configured language this browser ranks highest.

        Absent or unparseable headers mean no preference, which means the primary
        language. A tie means the primary language too: a reader who has said
        nothing gets the page's own language.
        """
        best: dict[str, float] = {}
        for part in (header or "").split(","):
            piece = part.strip()
            if not piece:
                continue
            tag, _, params = piece.partition(";")
            tag = tag.strip().lower()
            quality = 1.0
            for param in params.split(";"):
                key, _, value = param.partition("=")
                if key.strip() == "q":
                    try:
                        quality = float(value)
                    except ValueError:
                        quality = 0.0
            primary_tag = tag.split("-")[0]
            if primary_tag in config.codes:
                best[primary_tag] = max(best.get(primary_tag, 0.0), quality)
        floor = best.get(config.primary.code, 0.0)
        winner = config.primary
        for lang in config.languages[1:]:
            if best.get(lang.code, 0.0) > floor:
                floor = best[lang.code]
                winner = lang
        return winner

    def page_config(lang: Language) -> str:
        """What the browser needs that only the server knows.

        One JSON island rather than a dozen data attributes: the strings, and
        where each language lives. Without it the script falls back to its own
        built-in English, so a page saved to disk still behaves.
        """
        payload = {
            "lang": lang.code,
            "strings": lang.client_strings,
            "languages": [{"code": l.code, "path": l.home} for l in config.languages],
            "endpoint": "/api/signup",
        }
        blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        # A literal "</" inside a script element ends it, whatever the quoting.
        blob = blob.replace("</", "<\\/")
        return f'<script type="application/json" id="cl-config">{blob}</script>'

    def render_page(lang: Language) -> Response:
        html = (config.site_dir / lang.page).read_text(encoding="utf-8")

        def stamp(m: re.Match) -> str:
            attr, ref = m.group(1), m.group(2)
            if "//" in ref or ref.startswith("data:"):
                return m.group(0)  # someone else's file; not ours to version
            digest = rt.version(re.sub(r"^(\.\./)+", "", ref))
            return m.group(0) if not digest else f'{attr}="{ref}?v={digest}"'

        html = ASSET_RE.sub(stamp, html)

        # Placement is in the markup, at <!--JOIN-TAG--> and <!--JOIN-INLINE-->;
        # the count and the destination are decided here. Both markers are
        # replaced unconditionally, so a page never ships a stray comment or a
        # stale count.
        tag, inline = join_markup(lang)
        html = html.replace("<!--JOIN-TAG-->", tag).replace("<!--JOIN-INLINE-->", inline)
        html = html.replace(FORM_TOKEN_MARKER, signer.sign(b"f").decode("ascii"))
        html = html.replace("</body>", page_config(lang) + "\n</body>", 1)
        return Response(
            html,
            mimetype="text/html",
            headers={
                "Cache-Control": "no-cache, must-revalidate",
                # Cookie is load-bearing twice over: the language choice, and the
                # admin variant of the join tag. A shared cache must never hand
                # one visitor's copy to another.
                "Vary": "Accept-Language, Cookie",
            },
        )

    # ------------------------------------------------------------------
    # The signup count
    # ------------------------------------------------------------------

    def join_markup(lang: Language) -> tuple[str, str]:
        """(edge tag, inline text) for the join count.

        Public: every visitor sees the same words and the same number. What
        differs is where it goes. A visitor's tag opens the signup form, which is
        the whole point of showing a count next to an invitation; the
        administrator's goes to the list, and is the only trace of /admin
        anywhere in the markup.

        Empty strings when there is nothing to count, so an empty list never
        advertises itself.
        """
        st = rt.store.state()
        if not st["total"]:
            return "", ""
        total = st["total"] + config.founder_offset
        unit = lang.join_word("one") if total == 1 else lang.join_word("many")
        is_admin = rt.is_admin()
        if total <= config.show_count_above and not is_admin:
            return "", ""
        # The lit state is only ever visible to the administrator: a visitor has
        # no watermark, so their tag is never in it.
        lit = " is-new" if is_admin and st["active"] else ""
        inner = (
            f'<span class="jt-lead">{lang.join_word("lead")}</span>'
            f'<span class="jt-n">{total}</span>'
            f'<span class="jt-unit">{unit}</span>'
        )
        tag = (
            f'<a class="jointag{lit}{" is-admin" if is_admin else ""}" '
            f'href="{"/admin" if is_admin else "#signup"}">{inner}</a>'
        )
        # Always a span: this renders inside the signup button, and an anchor
        # nested in an anchor is invalid and behaves unpredictably.
        inline = (
            f'<span class="joininline">{lang.join_word("lead")} '
            f"<b>{total}</b> {unit}</span>"
        )
        return tag, inline

    # ------------------------------------------------------------------
    # Names
    # ------------------------------------------------------------------

    @app.before_request
    def canonical_redirect():
        """Send old hostnames to the canonical one, preserving path and query.

        Deliberately not applied to /api/ or /healthz. The API is posted to
        cross-origin by anything still holding an old copy of the page, and a
        redirect there loses the body, because browsers downgrade a POST through
        a 301 to a GET. The health check is called with a bare host header and
        has nothing to do with names.
        """
        if not (config.redirect_legacy_hosts and config.canonical_host):
            return None
        host = (request.host or "").split(":")[0].lower()
        if host not in config.legacy_hosts:
            return None
        if request.path.startswith("/api/") or request.path == "/healthz":
            return None
        target = f"https://{config.canonical_host}{request.full_path.rstrip('?') or '/'}"
        resp = redirect(target, code=301)
        resp.headers["Cache-Control"] = "public, max-age=3600"
        return resp

    @app.after_request
    def cors(resp):
        origin = request.headers.get("Origin")
        if origin in config.cors_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            # Append rather than assign: assigning discards the Accept-Language
            # and Cookie the page responses set, which with an admin variant in
            # play is a cache-poisoning bug rather than a cosmetic one.
            existing = [v.strip() for v in resp.headers.get("Vary", "").split(",") if v.strip()]
            if "Origin" not in existing:
                existing.append("Origin")
            resp.headers["Vary"] = ", ".join(existing)
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Requested-With"
        return resp

    # ------------------------------------------------------------------
    # The form
    # ------------------------------------------------------------------

    def submitted() -> dict:
        return request.form if request.form else (request.get_json(silent=True) or {})

    def pick_lang() -> Language:
        """Language for this request: the explicit form field first, then the
        referring path, then the primary. Never Accept-Language — a visitor who
        chose a language by clicking should not be second-guessed by their
        browser."""
        raw = str(submitted().get("lang") or "").strip().lower()
        chosen = config.language(raw)
        if chosen:
            return chosen
        referrer = request.referrer or ""
        for lang in config.languages:
            if lang.prefix and f"/{lang.prefix}/" in referrer:
                return lang
        return config.primary

    def wants_json() -> bool:
        return (
            request.headers.get("X-Requested-With") == "fetch"
            or "application/json" in request.headers.get("Accept", "")
        )

    def fail(key: str, code: int, lang: Language):
        if wants_json():
            return jsonify({"ok": False, "error": lang.text(key)}), code
        return Response(
            plain_page(lang.text("oops_title"), lang.text(key), lang),
            status=code,
            mimetype="text/html",
        )

    def form_list(form, key: str) -> list[str]:
        """Every value submitted under one name: a form's repeated checkbox, or a
        JSON body's list or single string."""
        raw = form.getlist(key) if hasattr(form, "getlist") else (form.get(key) or [])
        return [raw] if isinstance(raw, str) else [str(v) for v in raw]

    def classify(contact: str) -> str | None:
        if EMAIL_RE.match(contact):
            return "email"
        if PHONE_RE.match(contact):
            return "phone"
        return None

    @app.post("/api/signup")
    def signup():
        form = submitted()
        lang = pick_lang()
        thanks = config.thanks_path(lang)

        # Honeypots: fields hidden from people and irresistible to bots. Two of
        # them, with names a form-filler expects to find, because one is a pattern
        # worth recognising and two is a coincidence. Answered with success on
        # purpose — a bot that learns it failed tries something else.
        if any(str(form.get(name) or "").strip() for name in ("website", "company")):
            return jsonify({"ok": True}) if wants_json() else redirect(thanks, code=303)

        raw_stamp = str(form.get("t") or "")
        if token_in_markup:
            elapsed = form_age(raw_stamp)
            if elapsed is None:
                # No stamp, a forged one, or one older than the window. The first
                # is the interesting case: it means this arrived without the page
                # ever being fetched.
                return fail("stale", 400, lang)
        else:
            try:
                elapsed = time.time() - float(raw_stamp or 0)
            except (TypeError, ValueError):
                elapsed = 0.0
        if elapsed < config.min_fill_seconds:
            return fail("too_fast", 429, lang)

        if rt.signup_limiter.hit(rt.client_ip()):
            return fail("rate", 429, lang)

        contact = str(form.get("contact") or "").strip()[: config.max_field]
        if not contact:
            return fail("required", 400, lang)
        kind = classify(contact)
        if not kind:
            return fail("invalid", 400, lang)

        name = str(form.get("name") or "").strip()[: config.max_field]
        note = str(form.get("note") or "").strip()[: config.max_note]
        # Rows the reader added, read by index up to each group's limit. Indexes
        # with no name are skipped rather than ending the scan, so a row removed
        # from the middle can't hide the ones after it.
        groups = {
            key: [
                {
                    "name": row_name,
                    "help": sorted(
                        {h for h in form_list(form, f"{key}-{i}-help") if h in rep.choices}
                    ),
                }
                for i in range(rep.max_rows)
                if (row_name := str(form.get(f"{key}-{i}-name") or "").strip()[: config.max_field])
            ]
            for key, rep in config.repeats.items()
        }
        row_names = [row["name"] for rows in groups.values() for row in rows]
        # Refused rather than silently dropped: a person who wrote a link gets told
        # so and can send the same words without it, while a script gets a 400 it
        # will not read. Checking after the contact field means a bot cannot use
        # this to probe which addresses are already valid.
        if config.reject_links and any(LINK_RE.search(text) for text in (note, name, *row_names)):
            return fail("links", 400, lang)


        rt.store.append(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "kind": kind,
                "contact": contact,
                "name": name or None,
                "note": note or None,
                "help": sorted({h for h in form_list(form, "help") if h in config.help_choices}),
                **groups,
                # Which language they were reading. Tells you what the list speaks.
                "lang": lang.code,
            }
        )
        # Never log the contact itself — container logs are not a place for PII.
        app.logger.info("signup recorded (%s, %s)", kind, lang.code)

        if wants_json():
            return jsonify({"ok": True})
        return redirect(thanks, code=303)

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    def plain_page(title: str, body: str, lang: Language) -> str:
        """The thanks and error pages. No stylesheet, no script, nothing to load:
        these are seen once, often on a bad connection, sometimes after a
        failure."""
        return f"""<!doctype html>
<html lang="{lang.code}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} &middot; {config.name}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ margin:0; min-height:100vh; display:grid; place-items:center;
  background:#ECEDF1; color:#15171E; padding:2rem;
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; line-height:1.6; }}
@media (prefers-color-scheme: dark) {{ body {{ background:#101219; color:#E9EBF1; }} }}
main {{ max-width:32rem; display:flex; flex-direction:column; gap:1rem; }}
h1 {{ font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  font-size:1.6rem; letter-spacing:-0.03em; margin:0; }}
a {{ color:inherit; text-underline-offset:3px; }}
</style></head>
<body><main>
<h1>{title}</h1>
<p>{body}</p>
<p><a href="{lang.home}">&larr; {lang.text("back")}</a></p>
</main></body></html>"""

    @app.get("/")
    def index():
        """Whichever language fits, at one address.

        It would be easier to redirect a Spanish-preferring browser to /es/, but
        that puts the language into the address bar and therefore into every link
        anyone copies from it. Where the sender's language says nothing about the
        recipient's, that is the wrong thing to hand around. "/" negotiates and
        stays "/", so what gets pasted into a group chat lets each reader's own
        browser decide, while the prefixed URLs stay indexable and stay available
        to anyone sending a language deliberately.
        """
        chosen = config.language(request.cookies.get(CHOICE_COOKIE) or "")
        lang = chosen or negotiate(request.headers.get("Accept-Language", ""))
        return render_page(lang)

    for _lang in config.languages:
        # Every language gets an address that means itself, including the primary
        # one. Without that, the primary language's flag points at "/", which
        # negotiates, so a reader whose cookie says otherwise clicks it and gets
        # the language they were trying to leave: the switch is one-way.
        app.add_url_rule(
            f"/{_lang.code}/",
            endpoint=f"page_{_lang.code}",
            view_func=(lambda lang=_lang: render_page(lang)),
        )
        app.add_url_rule(
            f"/{_lang.code}",
            endpoint=f"page_{_lang.code}_bare",
            view_func=(lambda code=_lang.code: redirect(f"/{code}/", code=301)),
        )
        app.add_url_rule(
            config.thanks_path(_lang),
            endpoint=f"thanks_{_lang.code}",
            view_func=(
                lambda lang=_lang: Response(
                    plain_page(lang.text("thanks_title"), lang.text("thanks_body"), lang),
                    mimetype="text/html",
                )
            ),
        )

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "signups_file": rt.store.file.exists()})

    # ------------------------------------------------------------------
    # Addresses for parts of the page
    #
    # "/why" serves the home page already scrolled to that section, and the tab
    # slugs also select a tab. The client scrolls and then replaces the address
    # with "/", so what gets copied out of the bar afterwards is the neutral link.
    #
    # Sections are named by their data-section key rather than an element id,
    # because ids differ per language while the key does not.
    # ------------------------------------------------------------------

    def section_page(section: str, tab: str = ""):
        resp = index()
        # Injected into the served HTML rather than passed as a fragment: a
        # fragment would sit in the address bar and be shared, which is the thing
        # this avoids.
        attrs = f' data-scroll-to="{section}"' + (f' data-open-tab="{tab}"' if tab else "")
        html = BODY_RE.sub(lambda m: f"<body{m.group(1)}{attrs}>", resp.get_data(as_text=True), 1)
        resp.set_data(html)
        return resp

    for _slug, _tab in config.tabs.items():
        app.add_url_rule(
            f"/{_slug}",
            endpoint=f"tab_{_slug}",
            view_func=(lambda tab=_tab: section_page(config.tabs_section, tab)),
        )
        app.add_url_rule(
            f"/{_slug}/",
            endpoint=f"tab_{_slug}_slash",
            view_func=(lambda slug=_slug: redirect(f"/{slug}", code=301)),
        )

    for _slug, _section in config.sections.items():
        app.add_url_rule(
            f"/{_slug}",
            endpoint=f"section_{_slug}",
            view_func=(lambda section=_section: section_page(section)),
        )
        app.add_url_rule(
            f"/{_slug}/",
            endpoint=f"section_{_slug}_slash",
            view_func=(lambda slug=_slug: redirect(f"/{slug}", code=301)),
        )

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    @app.get("/<path:path>")
    def static_files(path: str):
        found = rt.asset_path(path)
        if not found:
            return Response("Not found", status=404, mimetype="text/plain")
        resp = send_from_directory(found.parent, found.name)
        # Immutable only when addressed by the hash of the file as it is now;
        # anything else revalidates. A bare link can then never pin a stale copy,
        # and neither can an old hash: answering one with today's bytes and
        # "immutable" would file those bytes under the old address for a year,
        # which is what a rollback would then be served.
        current = rt.version(path)
        resp.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable"
            if current and request.args.get("v") == current
            else "no-cache, must-revalidate"
        )
        return resp

    admin_module.register(app, rt)
    return app
