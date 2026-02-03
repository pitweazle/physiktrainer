from django.urls import path, include
from . import views

app_name = "physik"

urlpatterns = [
    path("", views.index, name="index"),
    path("aufgaben/", views.aufgaben, name="aufgaben"),
    path('inventar/', views.aufgaben_liste, name='aufgaben_liste'),
    path('aufgabe/<int:pk>/', views.aufgabe_einstellungen, name='aufgabe_einstellungen'),
    path("call/<str:lfd_nr>/", views.call, name="call"),
    path('analyse/', views.fehler_liste, name='fehler_liste'),
    path('analyse/edit/<int:log_id>/', views.fehler_edit, name='fehler_edit'),
    path('accounts/', include('django.contrib.auth.urls')),
]


