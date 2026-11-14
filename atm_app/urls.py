from django.urls import path
from . import views

app_name = "atm_app"
urlpatterns = [
    path("", views.home, name="home"),
    path("insert-card/", views.insert_card, name="insert_card"),
    path("pin/", views.submit_pin, name="submit_pin"),
    path("choose/", views.choose, name="choose"),
    path("amount/", views.submit_amount, name="submit_amount"),
    path("change-pin/", views.change_pin, name="change_pin"),
    path("cancel/", views.cancel, name="cancel"),
    path("eject/", views.eject, name="eject"),
    path("colctle/", views.collect, name="collect"),
    path("reset/", views.reset, name="reset"),
]