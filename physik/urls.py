from django.urls import path
from . import views

app_name = "physik"

urlpatterns = [
    path("", views.index, name="index"),
]


