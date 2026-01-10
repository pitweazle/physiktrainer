from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Count

from .models import ThemenBereich, Aufgabe

def index(request):
    themenbereiche = (
        ThemenBereich.objects
        .filter(eingeblendet=True)
        .prefetch_related("kapitel")
        .order_by("ordnung")
    )

    kapitel_map = {
        tb.id: [{"zeile": k.zeile, "name": k.kapitel} for k in tb.kapitel.all().order_by("zeile")]
        for tb in themenbereiche
    }

    qs = (
        Aufgabe.objects
        .filter(thema__in=themenbereiche)
        .values("thema_id", "kapitel_id", "schwierigkeit")
        .annotate(cnt=Count("id"))
    )

    counts = {}
    for r in qs:
        tb_id = r["thema_id"]
        kap_id = r["kapitel_id"]
        s = str(r["schwierigkeit"])  # "1","2","3"
        counts.setdefault(tb_id, {}).setdefault(kap_id, {"1": 0, "2": 0, "3": 0})
        counts[tb_id][kap_id][s] = r["cnt"]

    # Summen pro Themenbereich (für die farbige Themenzeile)
    tb_totals = {}
    for tb in themenbereiche:
        tot = {"1": 0, "2": 0, "3": 0}
        for kap in tb.kapitel.all():
            d = counts.get(tb.id, {}).get(kap.id, {"1": 0, "2": 0, "3": 0})
            tot["1"] += d["1"]
            tot["2"] += d["2"]
            tot["3"] += d["3"]
        tb_totals[tb.id] = tot

    return render(request, "physik/index.html", {
        "themenbereiche": themenbereiche,
        "kapitel_map": kapitel_map,
        "counts": counts,
        "tb_totals": tb_totals,
    })



def aufgaben(request):
    return HttpResponse(
        f"tb={request.GET.get('tb')} level={request.GET.get('level')} "
        f"start={request.GET.get('start')} end={request.GET.get('end')}"
    )