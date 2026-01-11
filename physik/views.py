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

import random
from django.shortcuts import render, redirect
from .models import Aufgabe


def aufgaben(request):
    tb_id = request.GET.get("tb")
    level = request.GET.get("level")
    start = request.GET.get("start")
    end = request.GET.get("end")

    qs = Aufgabe.objects.filter(
        thema_id=tb_id,
        schwierigkeit=level,
        kapitel__id__gte=start,
        kapitel__id__lte=end,
    )

    aufgabe = None
    if qs.exists():
        aufgabe = random.choice(list(qs))

    # Buttons auswerten
    action = request.POST.get("action")

    show_loesung = False
    show_hilfe = False

    if action == "loesung":
        show_loesung = True
    elif action == "hilfe":
        show_hilfe = True
    elif action == "stop":
        return redirect("physik:index")
    elif action == "weiter":
        return redirect(
            f"{request.path}?tb={tb_id}&level={level}&start={start}&end={end}"
        )

    return render(request, "physik/aufgabe.html", {
        "aufgabe": aufgabe,
        "show_loesung": show_loesung,
        "show_hilfe": show_hilfe,
        "tb": tb_id,
        "level": level,
        "start": start,
        "end": end,
    })

