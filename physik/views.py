from django.shortcuts import render

# physik/views.py
from django.shortcuts import render
from .models import ThemenBereich


def index(request):
    themenbereiche = ThemenBereich.objects.filter(eingeblendet=True).prefetch_related("kapitel").all()
    return render(
        request,
        "physik/index.html",
        {
            "themenbereiche": themenbereiche,
        },
    )

