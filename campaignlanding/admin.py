"""Admin: one password, one signed cookie, one list view.

Deliberately self-contained, and deliberately small. The list is the most
sensitive thing the box holds, so it stays behind a single route that does one
thing, with no search, no export and no API.

Nothing here knows what hostname the site is served from: the session cookie is
scoped to whatever host served the page, so moving to another domain means
setting a new secret and signing in once.

Without both a secret key and a password hash, every route in this module 404s
and no session can be minted. That is the default. A copy of a campaign's repo,
run by someone else, has no administrator.
"""

from __future__ import annotations

from flask import Response, redirect, request, session
from markupsafe import escape
from werkzeug.security import check_password_hash


def shell(title: str, site_name: str, inner: str) -> str:
    """The whole admin stylesheet, inline, because it is two screens of CSS that
    nobody should have to cache-bust or notice."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{escape(title)} &middot; {escape(site_name)}</title>
<style>
:root {{ color-scheme: light dark; --bg:#ECEDF1; --fg:#15171E; --dim:#4C5164;
  --line:#D2D5DE; --card:#FFFFFF; --sun:#C77503; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#101219; --fg:#E9EBF1;
  --dim:#A2A8BC; --line:#2B2F3B; --card:#181B23; --sun:#F0A32C; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); padding:1.5rem;
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; line-height:1.5; }}
main {{ max-width:60rem; margin:0 auto; display:flex; flex-direction:column; gap:1.25rem; }}
h1 {{ font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace; font-size:1.3rem;
  letter-spacing:-0.02em; margin:0; }}
a {{ color:inherit; text-underline-offset:3px; }}
.row {{ display:flex; gap:1rem; align-items:baseline; flex-wrap:wrap; }}
.dim {{ color:var(--dim); font-size:.85rem; }}
label {{ display:block; font-size:.8rem; color:var(--dim); margin-bottom:.35rem;
  text-transform:uppercase; letter-spacing:.08em; }}
input[type=password] {{ width:100%; padding:.7rem .8rem; font-size:1rem; color:var(--fg);
  background:var(--card); border:1px solid var(--line); border-radius:.35rem; }}
button {{ padding:.7rem 1.1rem; font:inherit; font-weight:600; cursor:pointer;
  color:#15171E; background:var(--sun); border:0; border-radius:.35rem; }}
form.inline {{ display:inline; }}
form.inline button {{ background:none; color:var(--dim); border:1px solid var(--line);
  font-weight:400; font-size:.85rem; padding:.35rem .7rem; }}
.err {{ color:#E4776A; font-size:.9rem; }}
table {{ width:100%; border-collapse:collapse; font-size:.9rem; }}
th,td {{ text-align:left; padding:.55rem .6rem; border-bottom:1px solid var(--line);
  vertical-align:top; }}
th {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:var(--dim);
  font-weight:600; }}
td.ts {{ white-space:nowrap; font-variant-numeric:tabular-nums; color:var(--dim);
  font-size:.82rem; }}
td.contact {{ font-family:ui-monospace,Menlo,monospace; word-break:break-all; }}
tr.new td {{ background:color-mix(in srgb, var(--sun) 12%, transparent); }}
.tags {{ display:flex; flex-wrap:wrap; gap:.25rem; }}
.tag {{ font-size:.72rem; padding:.1rem .4rem; border:1px solid var(--line);
  border-radius:.25rem; color:var(--dim); }}
.scroll {{ overflow-x:auto; }}
.empty {{ padding:2rem; text-align:center; color:var(--dim); border:1px dashed var(--line);
  border-radius:.4rem; }}
</style></head>
<body><main>{inner}</main></body></html>"""


def register(app, rt) -> None:
    cfg = rt.config

    def private(resp: Response) -> Response:
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    def login_response(error: str = "", status: int = 200) -> Response:
        msg = f'<p class="err">{escape(error)}</p>' if error else ""
        body = f"""<h1>Sign in</h1>
<p class="dim">Administrator access to the mailing list.</p>
{msg}
<form method="post" action="/login">
  <label for="p">Password</label>
  <input id="p" name="password" type="password" autocomplete="current-password" required>
  <p><button type="submit">Sign in</button></p>
</form>
<p class="dim"><a href="/">&larr; Back to the site</a></p>"""
        return private(
            Response(shell("Sign in", cfg.name, body), status=status, mimetype="text/html")
        )

    @app.get("/login")
    def login_form():
        if not rt.admin_enabled():
            return Response("Not found", status=404, mimetype="text/plain")
        if rt.is_admin():
            return redirect("/admin", code=303)
        return login_response()

    @app.post("/login")
    def login():
        if not rt.admin_enabled():
            return Response("Not found", status=404, mimetype="text/plain")
        if rt.login_limiter.hit(rt.client_ip()):
            return login_response("Too many attempts. Try again later.", 429)
        supplied = request.form.get("password") or ""
        # check_password_hash compares in constant time and the failure text is
        # the same either way, so neither timing nor wording says whether a
        # password exists to guess at.
        if not check_password_hash(cfg.admin_password_hash, supplied):
            app.logger.warning("admin login failed from %s", rt.client_ip())
            return login_response("That password is not right.", 401)
        session.clear()
        session.permanent = True
        session["admin"] = True
        app.logger.info("admin signed in from %s", rt.client_ip())
        return redirect("/admin", code=303)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect("/", code=303)

    @app.get("/admin")
    def admin():
        if not rt.admin_enabled():
            return Response("Not found", status=404, mimetype="text/plain")
        if not rt.is_admin():
            return redirect("/login", code=303)

        st = rt.store.state()
        recs = st["records"]
        # Newest first, and mark the ones that arrived since the last visit
        # before the watermark moves.
        fresh_from = len(recs) - st["unseen"]
        rows = []
        for i, r in reversed(list(enumerate(recs))):
            tags = "".join(
                f'<span class="tag">{escape(h)}</span>' for h in (r.get("help") or [])
            )
            rows.append(
                "<tr{cls}>"
                '<td class="ts">{ts}</td>'
                '<td class="contact">{contact}</td>'
                "<td>{name}</td>"
                '<td><div class="tags">{tags}</div></td>'
                "<td>{note}</td>"
                '<td class="ts">{lang}</td>'
                "</tr>".format(
                    cls=' class="new"' if i >= fresh_from else "",
                    ts=escape(str(r.get("ts") or "")).replace("T", " ").replace("Z", ""),
                    contact=escape(str(r.get("contact") or "")),
                    name=escape(str(r.get("name") or "")) or '<span class="dim">&mdash;</span>',
                    tags=tags or '<span class="dim">&mdash;</span>',
                    note=escape(str(r.get("note") or "")) or '<span class="dim">&mdash;</span>',
                    lang=escape(str(r.get("lang") or "")),
                )
            )

        table = (
            '<div class="scroll"><table><thead><tr>'
            "<th>When (UTC)</th><th>Contact</th><th>Name</th><th>Offered to help</th>"
            "<th>Note</th><th>Filled in</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
            if rows
            else '<p class="empty">No signups yet.</p>'
        )
        since = (
            f"{st['unseen']} new since you last looked."
            if st["unseen"]
            else "Nothing new since you last looked."
        )
        offset_note = (
            f"""<p class="dim">The public page says <strong>{st['total'] + cfg.founder_offset}</strong>,
which is these {st['total']} plus {cfg.founder_offset}: founder_offset in the config counts
whoever is on the list without having submitted the form. Set it to 0 to publish the stored
count alone.</p>"""
            if cfg.founder_offset
            else ""
        )
        body = f"""<div class="row">
  <h1>Mailing list</h1>
  <span class="dim">{st['total']} stored &middot; {escape(since)}</span>
  <span style="margin-left:auto">
    <form class="inline" method="post" action="/logout"><button type="submit">Sign out</button></form>
  </span>
</div>
{table}
{offset_note}
<p class="dim">Stored at {escape(str(rt.store.file))} on the host, mode 0600, and readable
over SSH. This page is the only route that returns any of it.</p>
<p class="dim"><a href="/">&larr; Back to the site</a></p>"""

        # The watermark moves only once the list has actually been rendered.
        rt.store.write_seen(st["newest"], st["total"])
        return private(Response(shell("Mailing list", cfg.name, body), mimetype="text/html"))
