import random

from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Count

from .models import ThemenBereich, Aufgabe, Kapitel

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
    tb_id = request.GET.get("tb")
    level = request.GET.get("level")
    start = request.GET.get("start")
    end = request.GET.get("end")

    aufgaben = Aufgabe.objects.filter(
        thema_id=tb_id,
        schwierigkeit=level,
        kapitel__id__gte=start,
        kapitel__id__lte=end,
    )

    aufgabe = None
    anzeigen = []

    if aufgaben.exists():
        aufgabe = random.choice(list(aufgaben))

        # a3-Logik
        if aufgabe.typ.startswith("a3"):
            anzeigen = [
                {"text": aufgabe.antwort, "richtig": True},
            ]

            # erste zwei Optionen aus der DB
            optionen = list(aufgabe.optionen.order_by("position")[:2])
            for opt in optionen:
                anzeigen.append({"text": opt.text, "richtig": False})

            random.shuffle(anzeigen)

    return render(request, "physik/aufgabe.html", {
        "aufgabe": aufgabe,
        "anzeigen": anzeigen,
    })


