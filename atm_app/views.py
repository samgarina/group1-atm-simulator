from django.http import HttpResponse
from django.shortcuts import render
from .session_state import load_state


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
def deposit(request):
    return HttpResponse("Deposit Placeholder")


# Withdraw placeholder
def withdraw(request):
    return HttpResponse("Withdraw Placeholder")


# Reset placeholder
def reset(request):
    return HttpResponse("Reset Placeholder")