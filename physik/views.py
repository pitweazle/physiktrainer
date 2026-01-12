import random

from django.shortcuts import render, redirect
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
    # Wenn noch keine Serie existiert → neu erzeugen
    if "aufgaben_ids" not in request.session:

        tb_id = request.GET.get("tb")
        level = request.GET.get("level")
        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = Aufgabe.objects.filter(
            thema_id=tb_id,
            schwierigkeit=level,
            kapitel__zeile__gte=start,
            kapitel__zeile__lte=end,
        )

        alle = list(qs)
        if not alle:
            return render(request, "physik/aufgabe.html", {
                "aufgabe": None
            })

        ziel = min(10, len(alle))
        serie = random.sample(alle, ziel)

        request.session["aufgaben_ids"] = [a.id for a in serie]
        request.session["index"] = 0

    ids = request.session["aufgaben_ids"]
    index = request.session["index"]

    # Wenn am Ende → Session löschen (später kommt hier Auswertung)
    if index >= len(ids):
        del request.session["aufgaben_ids"]
        del request.session["index"]
        return redirect("physik:index")

    aufgabe = Aufgabe.objects.get(id=ids[index])

    # a3 vorbereiten
    anzeigen = []
    if aufgabe.typ == "a3":
        anzeigen = [{"text": aufgabe.antwort, "richtig": True}]
        opts = list(aufgabe.optionen.order_by("position")[:2])
        for o in opts:
            anzeigen.append({"text": o.text, "richtig": False})
        random.shuffle(anzeigen)

    # Wenn „Weiter“ gedrückt wurde → zur nächsten Aufgabe
    if request.method == "POST":
        request.session["index"] += 1
        return redirect("physik:aufgaben")

    return render(request, "physik/aufgabe.html", {
        "aufgabe": aufgabe,
        "anzeigen": anzeigen,
        "fragenummer": index + 1,
        "anzahl": len(ids),
    })

def call(request, lfd_nr):
    try:
        aufgabe = Aufgabe.objects.get(lfd_nr=lfd_nr)
    except Aufgabe.DoesNotExist:
        return HttpResponse(f"Aufgabe {lfd_nr} nicht gefunden")

    # Serie aus genau dieser einen Aufgabe
    request.session["aufgaben_ids"] = [aufgabe.id]
    request.session["index"] = 0

    return redirect("physik:aufgaben")
