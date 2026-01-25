from django.urls import path
from . import views

#app_name = "physik"

urlpatterns = [
    path("", views.index, name="index"),
    path("aufgaben/", views.aufgaben, name="aufgaben"),
    path("call/<str:lfd_nr>/", views.call, name="call"),
    path('analyse/', views.fehler_liste, name='fehler_liste'),
    path('analyse/edit/<int:log_id>/', views.fehler_edit, name='fehler_edit'),
]


