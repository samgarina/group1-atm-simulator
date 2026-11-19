"""Helpers that keep one ATMService in the Django session.

The session holds only a plain dict (from ATMService.to_dict()).
Views call load_service() and save_service(). They never touch
the session key directly.
"""
import os
import secrets
from django.core import signing
from .atm_classes import ATMService
from .atm_flow import ATMFlow
from .exceptions import ATMError

SESSION_KEY = "atm_state"
FLOW_KEY = "atm_flow"
RUN_KEY = "atm_run"

# A new random id every time the web app starts. A saved screen from an earlier
# run is dropped, so the ATM always starts at the welcome screen after a restart.
# Balances are not touched.
RUN_ID = secrets.token_hex(8)

# On Vercel, every serverless instance has its own RUN_ID, so a request that
# lands on another instance would send the user back to the welcome screen in
# the middle of a transaction. Vercel sets VERCEL=1, so the check is OFF there.
# Locally (VERCEL not set) it stays ON, as before.
RESET_FLOW_ON_SERVER_START = not os.environ.get("VERCEL")

# Browsers drop cookies above about 4096 bytes. Stay well under that.
MAX_SESSION_CHARS = 3500


def save_service(request, service):
    """Save the service state in the session as a plain dict.

    Raises ATMError if the data is too big for a cookie.
    In that case the session is not changed.
    """
    data = service.to_dict()

    # Measure size the way Django stores it: signed and compressed.
    size = len(signing.dumps(data, compress=True))
    if size > MAX_SESSION_CHARS:
        raise ATMError("Session data is too large to save. Please reset the demo.")

    # Assign the whole dict. Changing a nested value would not mark
    # the session as modified, and the change would be lost.
    request.session[SESSION_KEY] = data


def _fresh_service(request):
    """Make sample accounts and save them."""
    service = ATMService.with_sample_accounts()
    save_service(request, service)
    return service


def load_service(request):
    """Return the ATMService for this browser session."""
    data = request.session.get(SESSION_KEY)

    # First visit: no saved data yet. Create samples once.
    if data is None:
        return _fresh_service(request)

    # Later visits: rebuild from the saved dict. Never reset here.
    try:
        return ATMService.from_dict(data)
    except (ATMError, KeyError, TypeError, ValueError):
        # Saved data has the wrong shape (for example, an old format).
        # Start fresh instead of crashing.
        return _fresh_service(request)

def save_flow(request, flow):
    """Save where the user is on the ATM screens (plain dict, no PIN)."""
    request.session[FLOW_KEY] = flow.to_dict()
    request.session[RUN_KEY] = RUN_ID


def load_flow(request, service):
    """Return the ATMFlow for this browser session.

    No saved data, data from an earlier run of the web app, or data that does
    not fit the service, starts a fresh flow at the welcome screen. Balances
    are not touched.
    """
    data = request.session.get(FLOW_KEY)
    if data is None:
        return ATMFlow(service)
    if RESET_FLOW_ON_SERVER_START and request.session.get(RUN_KEY) != RUN_ID:
        return ATMFlow(service)  # the web app was restarted: start at the welcome screen
    try:
        return ATMFlow.from_dict(service, data)
    except ATMError:
        return ATMFlow(service)