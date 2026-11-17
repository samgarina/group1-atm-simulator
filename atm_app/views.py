from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .atm_classes import ATMService, format_money
from .atm_flow import ATMFlow
from .exceptions import ATMError
from .session_state import load_flow, load_service, save_flow, save_service


def _slots(screen, slot_names):
    """The 4 side slots of one side. Every slot is always listed.

    A slot without an option is not enabled: the button stays visible but disabled.
    """
    items = []
    for slot in slot_names:
        option = screen.options.get(slot)
        items.append({"slot": slot, "option": option, "enabled": option is not None})
    return items


def _wallet(service):
    """Cards for the card slot. Display data only."""
    wallet = []
    for card in service.list_cards():
        account = service.get_account(card.account_number)
        wallet.append({
            "card_number": card.card_number,
            "last_four": card.card_number[-4:],
            "owner": account.holder_name,
            "account_type": account.account_type,
            "blocked": card.is_blocked,
        })
    return wallet


def home(request):
    """Show the ATM. What is on the monitor comes from ATMFlow."""
    service = load_service(request)
    flow = load_flow(request, service)
    screen = flow.screen()
    wallet = _wallet(service)

    # Starting PINs of the demo cards, for the demo help panel only.
    start_pins = {number: pin for number, _account, pin in ATMService.SAMPLE_CARDS}
    demo_help = [
        {**item, "pin": start_pins[item["card_number"]]}
        for item in wallet
        if item["card_number"] in start_pins
    ]

    cash = flow.cash_amount()
    # The card that waits in the slot on the collect screen.
    card_info = next((c for c in wallet if c["card_number"] == flow.card_number), None)
    context = {
        "screen": screen,
        "left": _slots(screen, screen.LEFT_SLOTS),
        "right": _slots(screen, screen.RIGHT_SLOTS),
        "wallet": wallet,
        "demo_help": demo_help,
        "card_inserted": flow.card_inserted,
        "receipt": flow.receipt_paper(),
        "cash_text": format_money(cash) if cash is not None else "",
        "card_info": card_info,
    }
    return render(request, "atm_app/index.html", context)


def _apply(request, step):
    """Run one step on the flow, then save service and flow.

    Both are always saved, even after an error message: a wrong PIN changes
    the attempt counter, and that change must not be lost.
    """
    service = load_service(request)
    flow = load_flow(request, service)
    step(flow, request.POST)
    try:
        save_service(request, service)
    except ATMError as error:
        # Data too big for the cookie. Nothing was saved, so the flow is not saved either.
        messages.error(request, error.message)
        return redirect("atm_app:home")
    save_flow(request, flow)
    return redirect("atm_app:home")


@require_POST
def insert_card(request):
    return _apply(request, lambda flow, post: flow.insert_card(post.get("card_number", "")))


@require_POST
def submit_pin(request):
    return _apply(request, lambda flow, post: flow.submit_pin(post.get("pin", "")))


@require_POST
def choose(request):
    return _apply(request, lambda flow, post: flow.choose(post.get("slot", "")))


@require_POST
def submit_amount(request):
    return _apply(request, lambda flow, post: flow.submit_amount(post.get("amount", "")))


@require_POST
def change_pin(request):
    return _apply(request, lambda flow, post: flow.submit_change_pin(
        post.get("current_pin", ""),
        post.get("new_pin", ""),
        post.get("confirm_pin", ""),
    ))


@require_POST
def cancel(request):
    return _apply(request, lambda flow, post: flow.cancel())


@require_POST
def eject(request):
    return _apply(request, lambda flow, post: flow.eject())

@require_POST
def collect(request):
    """The card, receipt and cash were taken: back to the welcome screen."""
    return _apply(request, lambda flow, post: flow.finish())

@require_POST
def reset(request):
    """Demo reset: new sample accounts and cards, and a fresh ATM at the welcome screen."""
    service = ATMService.with_sample_accounts()
    save_service(request, service)
    save_flow(request, ATMFlow(service))
    messages.success(request, "Demo reset. Sample accounts restored.")
    return redirect("atm_app:home")