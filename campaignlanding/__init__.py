"""campaignlanding — a bilingual landing page for pitching an idea in public.

    from campaignlanding import Config, Language, create_app

    app = create_app(Config(
        name="Your Campaign",
        site_dir="site",
        languages=[Language(code="en", page="index.html")],
    ))

The page itself is HTML you write and own. This package is the machinery behind
it: language negotiation that keeps the shared link neutral, a signup endpoint
that writes to a file you can read over SSH, addresses for parts of the page, and
one password-protected view of who has signed up.
"""

from .config import Config, Language, load_secrets
from .app import create_app
from .store import SignupStore

__all__ = ["Config", "Language", "create_app", "load_secrets", "SignupStore"]
__version__ = "0.1.0"
