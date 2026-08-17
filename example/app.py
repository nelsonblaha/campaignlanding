"""The example campaign, entire.

This is the whole of what a campaign writes in Python. Everything else it owns is
HTML, images, and a short stylesheet.

Run it:

    pip install -e ..
    CAMPAIGN_DATA=/tmp/ridgeline flask --app app run --port 8100

Then open http://127.0.0.1:8100/. There is no admin until you give it a secret and
a password hash — see the README — and until then /login and /admin do not exist.
"""

import os
from pathlib import Path

from campaignlanding import Config, Language, create_app

HERE = Path(__file__).parent

app = create_app(
    Config(
        name="Ridgeline Tool Library",
        site_dir=HERE / "site",
        data_dir=Path(os.environ.get("CAMPAIGN_DATA", "/data")),
        # The first language lives at "/" and is what a browser with no
        # preference gets. Every other one gets an address of its own.
        languages=[
            Language(
                code="en",
                page="index.html",
                strings={
                    "thanks_body": (
                        "That's the whole thing. We'll write when there is a shelf, "
                        "a board, and something on it worth borrowing."
                    ),
                    "back": "Back to the proposal",
                },
            ),
            Language(
                code="es",
                page="es/index.html",
                prefix="es",
                thanks_path="/es/gracias",
                strings={
                    "thanks_body": (
                        "Eso es todo. Te escribimos cuando haya una repisa, una junta "
                        "directiva y algo en ella que valga la pena prestar."
                    ),
                    "back": "Volver a la propuesta",
                },
            ),
        ],
        # Anything the form submits that is not in here is dropped rather than
        # stored, so the file only ever holds values you named.
        help_choices=frozenset({"updates", "board", "space", "tools", "spread"}),
        # Addresses for parts of the page. The slug is what a reader shares; the
        # value is the data-section attribute in the markup, which is the same in
        # every language while the element ids are not.
        sections={
            "why": "why",
            "the-proposal": "proposal",
            "roadmap": "roadmap",
            "how-to-help": "help",
            "por-que": "why",
            "la-propuesta": "proposal",
            "hoja-de-ruta": "roadmap",
            "como-ayudar": "help",
        },
        # The four arguments are tabs inside one section, so their slugs open that
        # section and select a tab. Keyed by the tab's element id, which is shared
        # across languages while the labels are not.
        tabs={
            "cost": "tab-cost",
            "space": "tab-space",
            "skills": "tab-skills",
            "repair": "tab-repair",
            "costo": "tab-cost",
            "espacio": "tab-space",
            "oficio": "tab-skills",
            "reparacion": "tab-repair",
        },
        tabs_section="why",
        # Show the count from the first signup. A real campaign usually wants
        # show_count_above set to something like 16: a small number is worse than
        # no number in front of someone deciding whether to be on the list.
        show_count_above=0,
    )
)
