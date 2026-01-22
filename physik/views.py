import random

from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.db.models import Count

from .bewertung import bewerte_aufgabe
from .models import ThemenBereich, Aufgabe

def index(request):
    # kompletter Reset beim echten Neustart
    for k in ("aufgaben_ids", "index", "p_richtig", "letzte_antwort", "warte_auf_weiter"):
        request.session.pop(k, None)

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
        tb = r["thema_id"]
        kap = r["kapitel_id"]
        s = str(r["schwierigkeit"])
        counts.setdefault(tb, {}).setdefault(kap, {"1": 0, "2": 0, "3": 0})
        counts[tb][kap][s] = r["cnt"]

    tb_totals = {}
    for tb in themenbereiche:
        tot = {"1": 0, "2": 0, "3": 0}
        for kap in tb.kapitel.all():
            d = counts.get(tb.id, {}).get(kap.id, {"1": 0, "2": 0, "3": 0})
            for k in tot:
                tot[k] += d[k]
        tb_totals[tb.id] = tot

    return render(request, "physik/index.html", {
        "themenbereiche": themenbereiche,
        "kapitel_map": kapitel_map,
        "counts": counts,
        "tb_totals": tb_totals,
    })

def aufgaben(request):
    # -------- Serie starten --------
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

        serie = random.sample(list(qs), min(10, qs.count()))
        request.session["aufgaben_ids"] = [a.id for a in serie]
        request.session["index"] = 0
        request.session["warte_auf_weiter"] = False
        request.session.pop("letzte_antwort", None)

    ids = request.session["aufgaben_ids"]
    index = request.session["index"]

    # -------- Serie beendet --------
    if index >= len(ids):
        for k in ("aufgaben_ids", "index", "p_richtig", "letzte_antwort", "warte_auf_weiter"):
            request.session.pop(k, None)
        return redirect("physik:index")

    aufgabe = Aufgabe.objects.get(id=ids[index])

    # -------- Bilder --------
    bilder_anzeige = None
    if "p" in aufgabe.typ:
        bilder = list(aufgabe.bilder.order_by("position"))
        if bilder:
            if aufgabe.typ == "p":
                request.session["p_richtig"] = bilder[0].id
            else:
                request.session.pop("p_richtig", None)
            random.shuffle(bilder)
            bilder_anzeige = bilder

    # -------- Liste --------
    anzeigen = []
    # Wir bauen eine Liste aus (Index, Text) Paaren
    optionen_liste = [(0, aufgabe.antwort)] # Index 0 ist immer die richtige Antwort
    for i, o in enumerate(aufgabe.optionen.order_by("position"), start=1):
        optionen_liste.append((i, o.text))

    random.shuffle(optionen_liste)

# -------- POST --------
    if request.method == "POST":
        # Wir holen die Antwort. Bei Radio-Buttons heißt das Feld im Template "user_antwort"
        antwort = request.POST.get("user_antwort") or request.POST.get("antwort", "")
        bild_antwort = request.POST.get("bild_antwort")

        # ---- Skip ----
        if not antwort and not bild_antwort:
            messages.info(request, "Letzte Aufgabe übersprungen.")
            request.session["index"] += 1
            request.session["warte_auf_weiter"] = False
            request.session.pop("letzte_antwort", None)
            return redirect("physik:aufgaben")
        
        ergebnis = bewerte_aufgabe(
            aufgabe,
            text_antwort=antwort,
            bild_antwort=bild_antwort,
            session=request.session,
        )

        # ---- richtig ----
        if ergebnis.get("richtig"):
            messages.success(request, ergebnis.get("hinweis", "Richtig!"))
            request.session["index"] += 1
            request.session["warte_auf_weiter"] = False
            request.session.pop("letzte_antwort", None)

        # ---- ungültig ----
        elif ergebnis.get("ungueltig"):
            messages.warning(request, ergebnis["hinweis"])
            request.session["warte_auf_weiter"] = False
            request.session.pop("letzte_antwort", None)

        # ---- falsch ----
        else:
            messages.warning(request, ergebnis.get("hinweis", "Leider falsch."))
            request.session["warte_auf_weiter"] = True
            request.session["letzte_antwort"] = antwort

        return redirect("physik:aufgaben")

    # -------- GET anzeigen --------
    return render(request, "physik/aufgabe.html", {
        "aufgabe": aufgabe,
        "anzeigen": anzeigen,
        "bilder": bilder_anzeige,
        "fragenummer": index + 1,
        "anzahl": len(ids),
        "warte_auf_weiter": request.session.get("warte_auf_weiter", False),
        "letzte_antwort": request.session.get("letzte_antwort", "") 
            if request.session.get("warte_auf_weiter") else "",
    })


def call(request, lfd_nr):
    try:
        aufgabe = Aufgabe.objects.get(lfd_nr=lfd_nr)
    except Aufgabe.DoesNotExist:
        return HttpResponse(f"Aufgabe {lfd_nr} nicht gefunden")

    request.session["aufgaben_ids"] = [aufgabe.id]
    request.session["index"] = 0
    request.session["warte_auf_weiter"] = False
    request.session.pop("letzte_antwort", None)

    return redirect("physik:aufgaben")
