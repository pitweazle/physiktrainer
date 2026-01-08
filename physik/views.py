from django.shortcuts import render
from django.http import HttpResponse

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

def index(request):
    themenbereiche = (
        ThemenBereich.objects
        .filter(eingeblendet=True)
        .prefetch_related("kapitel")
        .order_by("ordnung")
    )

    # fürs JS: {tb_id: [{"zeile":1,"name":"..."}, ...], ...}
    kapitel_map = {
        tb.id: [{"zeile": k.zeile, "name": k.kapitel} for k in tb.kapitel.all().order_by("zeile")]
        for tb in themenbereiche
    }

    return render(request, "physik/index.html", {
        "themenbereiche": themenbereiche,
        "kapitel_map": kapitel_map,
    })



def aufgaben(request):
    return HttpResponse(
        f"tb={request.GET.get('tb')} level={request.GET.get('level')} "
        f"start={request.GET.get('start')} end={request.GET.get('end')}"
    )