"""Tests for the engine, against a two-language fixture site.

    python -m unittest discover tests

Deliberately no pytest: this package's only dependency is Flask, and a test suite
that needs installing something to run is a test suite people skip.
"""

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from campaignlanding import Config, Language, create_app

PAGE = """<!doctype html>
<html lang="{code}">
<head><title>{title}</title><link rel="stylesheet" href="{up}style.css"></head>
<body>
<nav class="sectionnav"><a href="#why" data-slug="{why_slug}">Why</a></nav>
<section id="why" data-section="why"><div role="tablist">
  <button class="tab" role="tab" id="tab-one" aria-selected="true">One</button>
</div></section>
<form method="post" action="/api/signup"><input name="contact"></form>
<!--JOIN-INLINE-->
<!--JOIN-TAG-->
<script src="{up}campaignlanding.js"></script>
</body></html>
"""


class Base(unittest.TestCase):
    founder_offset = 0
    show_count_above = 0
    secrets = False

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        site, data = self.root / "site", self.root / "data"
        (site / "es").mkdir(parents=True)
        data.mkdir()
        (site / "index.html").write_text(
            PAGE.format(code="en", title="Fixture", up="", why_slug="why"), encoding="utf-8"
        )
        (site / "es" / "index.html").write_text(
            PAGE.format(code="es", title="Prueba", up="../", why_slug="por-que"), encoding="utf-8"
        )
        (site / "style.css").write_text("/* the campaign's own */\n", encoding="utf-8")

        config = Config(
            name="Fixture",
            site_dir=site,
            data_dir=data,
            languages=[
                Language(code="en", page="index.html"),
                Language(code="es", page="es/index.html", prefix="es", thanks_path="/es/gracias"),
            ],
            help_choices=frozenset({"updates", "board"}),
            sections={"why": "why", "por-que": "why"},
            tabs={"one": "tab-one", "uno": "tab-one"},
            tabs_section="why",
            founder_offset=self.founder_offset,
            show_count_above=self.show_count_above,
            secret_key="test-key" if self.secrets else "",
            admin_password_hash=generate_password_hash("hunter2") if self.secrets else "",
        )
        self.app = create_app(config, read_env=False)
        self.app.config["SESSION_COOKIE_SECURE"] = False  # the test client speaks http
        self.client = self.app.test_client()
        self.signups = data / "signups.jsonl"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def post(self, **fields):
        body = {"contact": "someone@example.com", "t": str(time.time() - 30)}
        body.update(fields)
        return self.client.post("/api/signup", data=body)

    def records(self):
        if not self.signups.exists():
            return []
        return [json.loads(l) for l in self.signups.read_text(encoding="utf-8").splitlines() if l]


class Language_(Base):
    def lang_of(self, resp):
        return resp.get_data(as_text=True).split('<html lang="')[1][:2]

    def test_no_preference_gets_the_primary(self):
        self.assertEqual(self.lang_of(self.client.get("/")), "en")

    def test_accept_language_is_honoured_once(self):
        r = self.client.get("/", headers={"Accept-Language": "es-MX,es;q=0.9,en;q=0.8"})
        self.assertEqual(self.lang_of(r), "es")

    def test_a_tie_goes_to_the_primary(self):
        r = self.client.get("/", headers={"Accept-Language": "es;q=0.8,en;q=0.8"})
        self.assertEqual(self.lang_of(r), "en")

    def test_the_cookie_outranks_the_header(self):
        self.client.set_cookie("lang", "es")
        self.assertEqual(self.lang_of(self.client.get("/", headers={"Accept-Language": "en"})), "es")

    def test_each_language_has_an_address_that_means_itself(self):
        """The regression this exists for: with only '/' and '/es/', the English
        flag points at '/', which negotiates, so a reader whose cookie says
        Spanish clicks it and gets Spanish. The switch was one-way."""
        self.client.set_cookie("lang", "es")
        self.assertEqual(self.lang_of(self.client.get("/en/")), "en")

    def test_a_prefixed_url_never_negotiates(self):
        r = self.client.get("/es/", headers={"Accept-Language": "en"})
        self.assertEqual(self.lang_of(r), "es")

    def test_bare_prefix_redirects_to_the_slashed_form(self):
        self.assertEqual(self.client.get("/es").status_code, 301)

    def test_pages_vary_on_language_and_cookie(self):
        vary = self.client.get("/").headers["Vary"]
        self.assertIn("Accept-Language", vary)
        self.assertIn("Cookie", vary)

    def test_thanks_pages_answer_in_their_own_language(self):
        self.assertEqual(self.client.get("/thanks").status_code, 200)
        self.assertEqual(self.client.get("/es/gracias").status_code, 200)


class Islands(Base):
    def test_the_config_island_carries_this_language(self):
        html = self.client.get("/es/").get_data(as_text=True)
        blob = html.split('id="cl-config">')[1].split("</script>")[0]
        payload = json.loads(blob)
        self.assertEqual(payload["lang"], "es")
        self.assertEqual(payload["strings"]["copied"], "Copiado al portapapeles")
        self.assertEqual([l["path"] for l in payload["languages"]], ["/", "/es/"])

    def test_section_slugs_mark_the_body(self):
        html = self.client.get("/why").get_data(as_text=True)
        self.assertIn('<body data-scroll-to="why">', html)

    def test_tab_slugs_mark_the_body_in_both_languages(self):
        for slug in ("one", "uno"):
            html = self.client.get(f"/{slug}").get_data(as_text=True)
            self.assertIn('data-scroll-to="why"', html)
            self.assertIn('data-open-tab="tab-one"', html)

    def test_a_slug_serves_the_readers_own_language(self):
        self.client.set_cookie("lang", "es")
        html = self.client.get("/why").get_data(as_text=True)
        self.assertIn('<html lang="es"', html)

    def test_trailing_slash_on_a_slug_redirects(self):
        self.assertEqual(self.client.get("/why/").status_code, 301)


class Assets(Base):
    def test_references_are_content_hashed(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertRegex(html, r'href="style\.css\?v=[0-9a-f]{10}"')
        self.assertRegex(html, r'src="campaignlanding\.js\?v=[0-9a-f]{10}"')

    def test_relative_references_from_a_subdirectory_are_hashed_too(self):
        html = self.client.get("/es/").get_data(as_text=True)
        self.assertRegex(html, r'href="\.\./style\.css\?v=[0-9a-f]{10}"')

    def test_the_package_ships_the_system_files(self):
        self.assertEqual(self.client.get("/campaignlanding.css").status_code, 200)
        self.assertEqual(self.client.get("/campaignlanding.js").status_code, 200)

    def test_a_sites_own_file_wins(self):
        body = self.client.get("/style.css").get_data(as_text=True)
        self.assertIn("the campaign's own", body)

    def test_only_a_hashed_url_is_immutable(self):
        self.assertIn("no-cache", self.client.get("/style.css").headers["Cache-Control"])
        self.assertIn("immutable", self.client.get("/style.css?v=abc").headers["Cache-Control"])

    def test_no_climbing_out_of_the_site_directory(self):
        self.assertEqual(self.client.get("/../pyproject.toml").status_code, 404)


class Signup(Base):
    def test_a_signup_is_stored(self):
        self.assertEqual(self.post().status_code, 303)
        (rec,) = self.records()
        self.assertEqual(rec["contact"], "someone@example.com")
        self.assertEqual(rec["kind"], "email")
        self.assertEqual(rec["lang"], "en")

    def test_a_phone_number_is_recognised(self):
        self.post(contact="+1 915 555 0147")
        self.assertEqual(self.records()[0]["kind"], "phone")

    def test_nonsense_is_refused(self):
        self.assertEqual(self.post(contact="not a contact").status_code, 400)
        self.assertEqual(self.records(), [])

    def test_an_empty_contact_is_refused(self):
        self.assertEqual(self.post(contact="").status_code, 400)

    def test_faster_than_a_person_can_type_is_refused(self):
        self.assertEqual(self.post(t=str(time.time())).status_code, 429)
        self.assertEqual(self.records(), [])

    def test_the_honeypot_answers_success_and_stores_nothing(self):
        """Answered with success on purpose: a bot that learns it failed tries
        something else."""
        self.assertEqual(self.post(website="http://spam.example").status_code, 303)
        self.assertEqual(self.records(), [])

    def test_only_declared_help_values_are_kept(self):
        self.post(help=["updates", "board", "president-for-life"])
        self.assertEqual(self.records()[0]["help"], ["board", "updates"])

    def test_the_language_field_wins_over_the_referrer(self):
        self.post(lang="es")
        self.assertEqual(self.records()[0]["lang"], "es")

    def test_the_referrer_decides_when_the_field_is_absent(self):
        self.client.post(
            "/api/signup",
            data={"contact": "a@b.co", "t": str(time.time() - 30)},
            headers={"Referer": "https://example.org/es/"},
        )
        self.assertEqual(self.records()[0]["lang"], "es")

    def test_fetch_gets_json_rather_than_a_redirect(self):
        r = self.client.post(
            "/api/signup",
            data={"contact": "a@b.co", "t": str(time.time() - 30)},
            headers={"X-Requested-With": "fetch"},
        )
        self.assertEqual(r.get_json(), {"ok": True})

    def test_the_rate_limit_stops_a_script(self):
        for _ in range(5):
            self.post()
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(len(self.records()), 5)

    def test_the_file_is_not_world_readable(self):
        self.post()
        self.assertEqual(self.signups.stat().st_mode & 0o777, 0o600)


class Count(Base):
    founder_offset = 1
    show_count_above = 2

    def test_an_empty_list_does_not_advertise_itself(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("jointag", html)
        self.assertNotIn("<!--JOIN-TAG-->", html)  # the marker is always consumed

    def test_a_small_count_is_withheld(self):
        self.post()
        self.assertNotIn("jointag", self.client.get("/").get_data(as_text=True))

    def test_past_the_threshold_it_appears_with_the_offset(self):
        for i in range(3):
            self.post(contact=f"p{i}@example.com")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('<span class="jt-n">4</span>', html)  # 3 stored + the founder
        self.assertIn('href="#signup"', html)


class NoAdmin(Base):
    def test_the_routes_do_not_exist(self):
        for path in ("/login", "/admin"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_the_page_carries_no_trace_of_them(self):
        self.assertNotIn("/admin", self.client.get("/").get_data(as_text=True))


class Admin(Base):
    secrets = True

    def sign_in(self, password="hunter2"):
        return self.client.post("/login", data={"password": password})

    def test_a_wrong_password_is_refused(self):
        self.assertEqual(self.sign_in("wrong").status_code, 401)
        self.assertEqual(self.client.get("/admin").status_code, 303)

    def test_the_right_password_reaches_the_list(self):
        self.assertEqual(self.sign_in().status_code, 303)
        page = self.client.get("/admin")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Mailing list", page.get_data(as_text=True))

    def test_the_list_is_never_cached_or_indexed(self):
        self.sign_in()
        headers = self.client.get("/admin").headers
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("noindex", headers["X-Robots-Tag"])

    def test_signing_out_closes_the_door(self):
        self.sign_in()
        self.client.post("/logout")
        self.assertEqual(self.client.get("/admin").status_code, 303)

    def test_login_attempts_are_rate_limited(self):
        for _ in range(8):
            self.sign_in("wrong")
        self.assertEqual(self.sign_in("wrong").status_code, 429)

    def test_the_watermark_moves_only_after_the_list_is_rendered(self):
        self.post()
        self.sign_in()
        page = self.client.get("/admin").get_data(as_text=True)
        self.assertIn("1 new since you last looked", page)
        self.assertIn("Nothing new", self.client.get("/admin").get_data(as_text=True))

    def test_the_administrators_tag_points_at_the_list(self):
        self.post()
        self.sign_in()
        self.assertIn('href="/admin"', self.client.get("/").get_data(as_text=True))

    def test_a_visitor_sees_no_admin_tag_after_the_administrator_did(self):
        self.post()
        self.sign_in()
        self.client.get("/")
        self.client.post("/logout")
        self.assertNotIn("is-admin", self.client.get("/").get_data(as_text=True))


class Names(Base):
    def build(self, **kw):
        cfg = Config(
            name="Fixture",
            site_dir=self.root / "site",
            data_dir=self.root / "data",
            languages=[Language(code="en", page="index.html")],
            canonical_host="example.org",
            legacy_hosts=frozenset({"old.example.net"}),
            **kw,
        )
        app = create_app(cfg, read_env=False)
        return app.test_client()

    def test_a_legacy_host_is_left_alone_until_the_switch_is_on(self):
        c = self.build()
        self.assertEqual(c.get("/", headers={"Host": "old.example.net"}).status_code, 200)

    def test_the_switch_sends_a_legacy_host_to_the_canonical_one(self):
        c = self.build(redirect_legacy_hosts=True)
        r = c.get("/why", headers={"Host": "old.example.net"})
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r.headers["Location"], "https://example.org/why")

    def test_the_api_is_exempt_because_a_301_would_eat_the_post(self):
        c = self.build(redirect_legacy_hosts=True)
        r = c.post("/api/signup", data={"contact": "a@b.co"}, headers={"Host": "old.example.net"})
        self.assertNotEqual(r.status_code, 301)

    def test_the_health_check_is_exempt(self):
        c = self.build(redirect_legacy_hosts=True)
        self.assertEqual(c.get("/healthz", headers={"Host": "old.example.net"}).status_code, 200)

    def test_cors_is_granted_to_known_origins_only(self):
        c = self.build()
        allowed = c.get("/", headers={"Origin": "https://old.example.net"})
        self.assertIn("Access-Control-Allow-Origin", allowed.headers)
        # and the page's own Vary survives it
        self.assertIn("Cookie", allowed.headers["Vary"])
        self.assertNotIn(
            "Access-Control-Allow-Origin",
            c.get("/", headers={"Origin": "https://elsewhere.example"}).headers,
        )


class Validation(unittest.TestCase):
    def config(self, **kw):
        base = dict(name="x", site_dir=".", languages=[Language(code="en", page="index.html")])
        base.update(kw)
        return Config(**base)

    def test_the_primary_language_must_live_at_the_root(self):
        with self.assertRaises(ValueError):
            self.config(languages=[Language(code="en", page="index.html", prefix="en")])

    def test_at_least_one_language_is_required(self):
        with self.assertRaises(ValueError):
            self.config(languages=[])

    def test_a_language_cannot_be_declared_twice(self):
        with self.assertRaises(ValueError):
            self.config(
                languages=[
                    Language(code="en", page="a.html"),
                    Language(code="en", page="b.html", prefix="x"),
                ]
            )

    def test_tabs_need_to_say_which_section_they_are_in(self):
        with self.assertRaises(ValueError):
            self.config(tabs={"one": "tab-one"})

    def test_the_session_cookie_is_named_after_the_campaign(self):
        self.assertEqual(self.config(name="Tool Library").session_cookie_name, "tool_library_admin")


if __name__ == "__main__":
    unittest.main()
