"""What one campaign knows about itself.

Everything specific to a campaign lives in a Config. Everything that is not lives
in the engine. The split is the whole point of the package: if you find yourself
wanting to edit engine code to launch a page, something belongs here that isn't
here yet.

Nothing in this module imports Flask, so a config can be built and checked
without starting anything.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping, Sequence


# The strings the server says on its own, in the language the reader was reading.
# A campaign overrides any subset; what it does not override falls back to these.
#
# Only two languages ship with translations, because those are the two I could
# check word by word. Any other language works the same way — declare it and pass
# its strings — and it is better to make that visible than to ship a machine
# translation nobody has read.
DEFAULT_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # server-rendered
        "too_fast": "That submitted faster than a person can type. Try again.",
        "rate": "Too many signups from this address. Try again later.",
        "required": "An email address or phone number is required.",
        "invalid": "That doesn't look like an email address or a phone number.",
        "links": "Please leave links out of that message.",
        "stale": "That form had been open a while. Reload the page and try again.",
        "oops_title": "Something went wrong",
        "thanks_title": "You're on the list.",
        "thanks_body": "We'll write when there's something real to report.",
        "back": "Back to the page",
        # sent to the browser
        "sending": "Sending…",
        "ok": "You're on the list. We'll write when there's something real to report.",
        "failed": "That did not go through. Try again in a moment.",
        "unreachable": "Could not reach the server. Try again in a moment.",
        "signedUp": "Signed up",
        "tiers": "Access tiers",
        "close": "Close",
        "copied": "Copied to clipboard",
    },
    "es": {
        "too_fast": "Eso se envió más rápido de lo que alguien puede escribir. Intenta de nuevo.",
        "rate": "Demasiados registros desde esta dirección. Intenta más tarde.",
        "required": "Hace falta un correo electrónico o un teléfono.",
        "invalid": "Eso no parece un correo electrónico ni un teléfono.",
        "links": "Por favor deja los enlaces fuera de ese mensaje.",
        "stale": "Ese formulario llevaba tiempo abierto. Recarga la página e inténtalo de nuevo.",
        "oops_title": "Algo salió mal",
        "thanks_title": "Ya estás en la lista.",
        "thanks_body": "Te escribiremos cuando haya algo real que contar.",
        "back": "Volver a la página",
        "sending": "Enviando…",
        "ok": "Ya estás en la lista. Te escribiremos cuando haya algo real que contar.",
        "failed": "No se pudo enviar. Inténtalo de nuevo en un momento.",
        "unreachable": "No se pudo conectar con el servidor. Inténtalo de nuevo en un momento.",
        "signedUp": "Listo",
        "tiers": "Niveles de acceso",
        "close": "Cerrar",
        "copied": "Copiado al portapapeles",
    },
}

# The subset the browser needs. The rest never leaves the server, so it stays out
# of the page: strings the reader will never see are still weight they download.
CLIENT_KEYS = ("sending", "ok", "failed", "unreachable", "signedUp", "tiers", "close", "copied")

# The invitation beside the signup count, which has to agree with its number
# grammatically, so it cannot be one string with a placeholder in it.
DEFAULT_JOIN_WORDS: dict[str, dict[str, str]] = {
    "en": {"lead": "join", "one": "other", "many": "others"},
    "es": {"lead": "únete a", "one": "persona", "many": "personas"},
}


@dataclass(frozen=True)
class Language:
    """One language, at one address.

    The first language in a Config is the primary one and lives at "/", which
    also negotiates: a reader who has expressed no preference gets whichever
    language their browser asks for. Every other language gets a prefix of its
    own, so "/es/" always means Spanish no matter who opens it.

    That distinction matters more than it looks. In a bilingual place the
    sender's language says nothing about the recipient's, so the link people
    copy and paste around should be the neutral one, and the language-specific
    URLs should exist for anyone who wants to send a language deliberately.
    """

    code: str
    page: str
    prefix: str = ""
    thanks_path: str = ""
    strings: Mapping[str, str] = field(default_factory=dict)
    join_words: Mapping[str, str] = field(default_factory=dict)

    @property
    def home(self) -> str:
        return f"/{self.prefix}/" if self.prefix else "/"

    def text(self, key: str) -> str:
        """This language's word for something, falling back through the shipped
        translations to English, so a missing key is a plain sentence in the
        wrong language rather than a KeyError in front of a reader."""
        if key in self.strings:
            return self.strings[key]
        shipped = DEFAULT_STRINGS.get(self.code, {})
        if key in shipped:
            return shipped[key]
        return DEFAULT_STRINGS["en"][key]

    def join_word(self, key: str) -> str:
        if key in self.join_words:
            return self.join_words[key]
        return DEFAULT_JOIN_WORDS.get(self.code, DEFAULT_JOIN_WORDS["en"])[key]

    @property
    def client_strings(self) -> dict[str, str]:
        return {k: self.text(k) for k in CLIENT_KEYS}


# What the engine itself reads from the form or writes to a stored signup. A
# repeat group may not use any of these as its key.
RESERVED_FIELDS = frozenset(
    {"ts", "kind", "contact", "name", "note", "help", "lang", "t", "website", "company"}
)


@dataclass(frozen=True)
class Repeat:
    """Rows a reader can add to the form: a name, and its own checkboxes.

    For things a signup can have more than one of, such as a reader's AI
    companions. Row n is `<key>-<n>-name` and `<key>-<n>-help` in the markup, and
    the stored signup gets `<key>: [{"name": ..., "help": [...]}, ...]`. A row with
    no name is dropped; a ticked box is kept only if it is in `choices`; rows past
    `max_rows` are ignored. See docs/markup-contract.md for the markup.
    """

    label: str  # the column heading in /admin
    choices: frozenset[str] = frozenset()
    max_rows: int = 10


@dataclass(frozen=True)
class Config:
    """Everything the engine needs to know about one campaign.

    Only `name`, `site_dir` and `languages` have no sensible default. The rest is
    off unless you turn it on, so the smallest usable config is three lines and
    the page it serves has no admin, no canonical redirect and no section URLs.
    """

    name: str
    site_dir: Path
    languages: Sequence[Language]
    data_dir: Path = Path("/data")

    # ---- names -----------------------------------------------------------
    # The host this campaign is meant to be reached at, and the ones that used to
    # reach it. The redirect is deliberately a separate switch: pointing a 301 at
    # a name that does not resolve yet is the most durable mistake available,
    # because a 301 is the response browsers cache hardest.
    canonical_host: str = ""
    legacy_hosts: frozenset[str] = frozenset()
    redirect_legacy_hosts: bool = False
    # Origins allowed to post the signup form. The canonical and legacy hosts are
    # added for you; this is for anything else, and it is worth being stingy: an
    # allowance for an origin you no longer control the content of is worth
    # nothing to you and something to an attacker.
    extra_cors_origins: frozenset[str] = frozenset()

    # ---- the form --------------------------------------------------------
    # Free text that contains a link is refused. Almost all form spam exists to
    # deliver a URL, and almost no genuine signup contains one, which makes this
    # the cheapest filter available that costs a real person nothing: they are
    # told why, in their own language, and can send the same words without it.
    reject_links: bool = True
    # How long a rendered form stays valid. The stamp that proves a page was
    # actually fetched is signed by the server and carries its own issue time, so
    # this is the window in which it may be submitted. Long, because a reader who
    # opens the page and comes back after lunch is not a bot.
    form_max_age: int = 86400
    # The values the "how can you help" checkboxes may submit. Anything else is
    # dropped rather than stored, so the file only ever contains values you named.
    help_choices: frozenset[str] = frozenset()
    # Groups of rows a reader can add to, keyed by the prefix their fields use in
    # the markup. Each is a Repeat. Empty by default: no group, no fields read.
    repeats: Mapping[str, Repeat] = field(default_factory=dict)

    # ---- addresses for parts of the page ---------------------------------
    # slug -> the data-section it scrolls to. "/why" serves the page already at
    # that section. Give the same section a slug per language and a reader can
    # share the one in the language they are reading.
    sections: Mapping[str, str] = field(default_factory=dict)
    # slug -> the id of a tab to select, for tabs inside a section. Keyed by
    # element id because ids are the same in both languages while labels are not.
    tabs: Mapping[str, str] = field(default_factory=dict)
    tabs_section: str = ""

    # ---- the signup count ------------------------------------------------
    # Counts people who are on the list in every sense except having filled in
    # the form: usually whoever is running the campaign. /admin shows the stored
    # rows and says so, so the two numbers never look like a discrepancy.
    founder_offset: int = 0
    # Below this the invitation is not shown at all. A small number is worse than
    # no number: "join 2 others" tells a reader the list is nearly empty at the
    # moment they are deciding whether to be on it. The administrator sees it at
    # any count, because for them it is not social proof, it is the notification.
    show_count_above: int = 0

    # ---- budgets ---------------------------------------------------------
    # Generous for humans, useless for scripts.
    rate_max: int = 5
    rate_window: int = 3600
    # Anything submitted faster than this was not typed by a person.
    min_fill_seconds: float = 2.0
    max_field: int = 500
    max_note: int = 2000
    # The one password field on the site gets a tighter budget than the form.
    login_max: int = 8
    login_window: int = 900

    # ---- secrets ---------------------------------------------------------
    # Both empty is a valid state and means "no admin here": /login and /admin
    # 404, no session can be minted, and the page carries no admin markup at all,
    # so a copy of your repo run by someone else exposes nothing.
    #
    # Left blank, these are read from the environment at create_app() time using
    # env_prefix, and the hash is read from a file first. See load_secrets().
    secret_key: str = ""
    admin_password_hash: str = ""
    admin_hash_file: Path | None = None
    env_prefix: str = "CAMPAIGN"
    # Distinct per campaign, so two of these on neighbouring hostnames cannot
    # confuse each other's sessions.
    session_cookie_name: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "site_dir", Path(self.site_dir))
        object.__setattr__(self, "data_dir", Path(self.data_dir))
        object.__setattr__(self, "languages", tuple(self.languages))
        if not self.languages:
            raise ValueError("a campaign needs at least one language")
        if self.languages[0].prefix:
            raise ValueError(
                "the first language is the primary one and lives at '/', so its "
                f"prefix must be empty (got {self.languages[0].prefix!r})"
            )
        seen = set()
        for lang in self.languages:
            if lang.code in seen:
                raise ValueError(f"language {lang.code!r} is declared twice")
            seen.add(lang.code)
        for slug, section in self.tabs.items():
            if not self.tabs_section:
                raise ValueError(
                    f"tab slug /{slug} needs tabs_section, the data-section the tabs live in"
                )
            del section
        for key, rep in self.repeats.items():
            # A group's rows land in the stored signup under its key, beside the
            # fields the engine writes itself, so a key must not be able to take one
            # of those over; and it is spliced into field names in the markup, so it
            # must be something that can be.
            if not re.fullmatch(r"[a-z][a-z0-9_]*", key) or key in RESERVED_FIELDS:
                raise ValueError(
                    f"repeat group {key!r} needs a lowercase identifier that is not one "
                    f"of the form's own fields ({', '.join(sorted(RESERVED_FIELDS))})"
                )
            if not rep.label:
                raise ValueError(f"repeat group {key!r} needs a label for /admin")
            if not 1 <= rep.max_rows <= 50:
                raise ValueError(f"repeat group {key!r}: max_rows must be 1 to 50")
        if not self.session_cookie_name:
            safe = "".join(c if c.isalnum() else "_" for c in self.name.lower())
            object.__setattr__(self, "session_cookie_name", f"{safe}_admin")

    # ---- lookups the engine does constantly ------------------------------

    @property
    def primary(self) -> Language:
        return self.languages[0]

    def language(self, code: str) -> Language | None:
        for lang in self.languages:
            if lang.code == code:
                return lang
        return None

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(lang.code for lang in self.languages)

    def thanks_path(self, lang: Language) -> str:
        if lang.thanks_path:
            return lang.thanks_path
        return f"/{lang.prefix}/thanks" if lang.prefix else "/thanks"

    @property
    def cors_origins(self) -> frozenset[str]:
        hosts = {h for h in (self.canonical_host, *self.legacy_hosts) if h}
        return frozenset({f"https://{h}" for h in hosts} | set(self.extra_cors_origins))

    def with_secrets(self, **kwargs) -> "Config":
        return replace(self, **kwargs)


def load_secrets(config: Config) -> Config:
    """Fill in whatever the config left blank, from the environment.

    The password hash comes from a file by preference, for a reason worth
    recording: a Werkzeug hash contains '$' as its field separator, and Docker
    Compose interpolates $VAR inside a project .env file. That silently removes
    the salt from the middle of the hash, so the value the container sees is
    well-formed, non-empty, and wrong, and every correct password is rejected.
    A file also keeps the hash out of `docker inspect` and out of the process
    environment.

    The environment variable still works for deployments that are not Compose,
    but it must not contain an unescaped '$'.
    """
    p = config.env_prefix
    hash_file = config.admin_hash_file or Path(
        os.environ.get(f"{p}_ADMIN_HASH_FILE", str(config.data_dir / "admin_password_hash"))
    )
    try:
        from_file = Path(hash_file).read_text(encoding="utf-8").strip()
    except OSError:
        from_file = ""
    return config.with_secrets(
        secret_key=config.secret_key or os.environ.get(f"{p}_SECRET_KEY", "").strip(),
        admin_password_hash=(
            config.admin_password_hash
            or from_file
            or os.environ.get(f"{p}_ADMIN_PASSWORD_HASH", "").strip()
        ),
        admin_hash_file=Path(hash_file),
        redirect_legacy_hosts=(
            config.redirect_legacy_hosts or os.environ.get(f"{p}_CANONICAL_REDIRECT") == "1"
        ),
        site_dir=Path(os.environ.get(f"{p}_SITE", str(config.site_dir))),
        data_dir=Path(os.environ.get(f"{p}_DATA", str(config.data_dir))),
    )
