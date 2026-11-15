from django.shortcuts import render
from .session_state import load_state
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from .session_state import reset_state

from .atm_flow import deposit_flow, withdraw_flow


# Dashboard placeholder
def dashboard(request):
    # Load the account and transaction history from the session
    state = load_state(request.session)

    account = state["account"]
    history = state.get("history", [])

    # Data that will be displayed in the dashboard
    context = {
        "account": account,
        "balance": account.balance,
        "history": history,
    }

    return render(request, "index.html", context)


# Deposit placeholder
@require_POST
def deposit(request):
    # Get the amount entered in the deposit form
    raw_amount = request.POST.get("amount", "")

    # Process the deposit through the ATM flow
    success, message = deposit_flow(request.session, raw_amount)

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("atm_app:dashboard")


@require_POST
def withdraw(request):
    # Get the amount entered in the withdraw form
    raw_amount = request.POST.get("amount", "")

    # Process the withdrawal through the ATM flow
    success, message = withdraw_flow(request.session, raw_amount)

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("atm_app:dashboard")


# Reset placeholder
@require_POST
def reset(request):
    # Restore the account and transaction history
    reset_state(request.session)

    messages.success(request, "ATM session has been reset.")

    return redirect("atm_app:dashboard")