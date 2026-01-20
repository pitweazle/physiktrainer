import random

from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.db.models import Count

from .bewertung import bewerte_aufgabe
from .models import ThemenBereich, Aufgabe, Kapitel

def index(request):
    # Nur resetten, wenn der Nutzer wirklich neu startet
    if "aufgaben_ids" in request.session:
        request.session.pop("aufgaben_ids", None)
        request.session.pop("index", None)
        request.session.pop("p_richtig", None)
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
    if "aufgaben_ids" not in request.session and request.method == "GET":
        tb_id = request.GET.get("tb")
        level = request.GET.get("level")
        start = request.GET.get("start")
        end = request.GET.get("end")
        qs = Aufgabe.objects.filter(
            thema_id=tb_id,
            schwierigkeit__lte=level,
            kapitel__zeile__gte=start,
            kapitel__zeile__lte=end,
        )
        alle = list(qs)
        ziel = min(10, len(alle))
        serie = random.sample(alle, ziel)
        request.session["aufgaben_ids"] = [a.id for a in serie]
        request.session["index"] = 0
    ids = request.session["aufgaben_ids"]
    index = request.session["index"]
    # Serie beendet?
    # ---------------------------------------------------------
    if index >= len(ids):
        del request.session["aufgaben_ids"]
        del request.session["index"]
        return redirect("physik:index")

    aufgabe = Aufgabe.objects.get(id=ids[index])
    bilder_anzeige = None
    # ---------------------------------------------------------
    # p-Typ (Bilder)
    # ---------------------------------------------------------
    if "p" in aufgabe.typ:
        bilder = list(aufgabe.bilder.order_by("position"))
        if bilder:
            # ---- Fall 1: echte Bildfrage ----
            if aufgabe.typ == "p":
                p_richtig = bilder[0].id
                request.session["p_richtig"] = p_richtig
            # ---- Fall 2: Bilder nur als Illustration ----
            else:
                request.session.pop("p_richtig", None)
            random.shuffle(bilder)
            bilder_anzeige = bilder
    # ---------------------------------------------------------
    # l vorbereiten
    # ---------------------------------------------------------
    anzeigen = []
    if aufgabe.typ == "l":
        # 1 = richtige Antwort
        anzeigen = [{"text": aufgabe.antwort, "richtig": True}]
        opts = list(aufgabe.optionen.order_by("position"))
        for o in opts:
            anzeigen.append({"text": o.text, "richtig": False})
        random.shuffle(anzeigen)

    # ---------------------------------------------------------
    # POST: Antwort auswerten + IMMER zur nächsten Aufgabe
    # ---------------------------------------------------------
    if request.method == "POST":
        antwort = request.POST.get("antwort", "")
        bild_antwort = request.POST.get("bild_antwort")
        # ========== SKIP-FALL ==========
        if not antwort and not bild_antwort:
            messages.info(request, "Letzte Aufgabe übersprungen.")

            request.session["index"] += 1
            request.session["warte_auf_weiter"] = False
            request.session.modified = True
            return redirect("physik:aufgaben")
        # ========== BEWERTEN ==========
        ergebnis = bewerte_aufgabe(
            aufgabe,
            text_antwort=antwort,
            bild_antwort=bild_antwort,
            session=request.session,
        )
        if ergebnis["richtig"]:
            messages.success(
                request,
                ergebnis.get("hinweis", "Deine letzte Antwort war richtig.")
            )
            request.session["index"] += 1
            request.session["warte_auf_weiter"] = False
            request.session.pop("letzte_antwort", None)
        elif ergebnis.get("ungueltig"):
            messages.warning(request, ergebnis["hinweis"])
            request.session["warte_auf_weiter"] = False
            request.session["letzte_antwort"] = antwort
        else:
            messages.warning(
                request,
                ergebnis.get("hinweis", "Deine letzte Antwort war leider falsch.")
            )
            request.session["warte_auf_weiter"] = True
            request.session["letzte_antwort"] = antwort

        request.session.modified = True
        return redirect("physik:aufgaben")
    # ---------------------------------------------------------
    # GET: Aufgabe anzeigen
    # ---------------------------------------------------------
    return render(request, "physik/aufgabe.html", {
        "aufgabe": aufgabe,
        "anzeigen": anzeigen,
        "bilder": bilder_anzeige,
        "fragenummer": index + 1,
        "anzahl": len(ids),
        "warte_auf_weiter": request.session.get("warte_auf_weiter", False),
        "letzte_antwort": request.session.get("letzte_antwort", ""),
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
