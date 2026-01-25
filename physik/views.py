import random

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Count
from django.contrib.auth.decorators import user_passes_test

from .bewertung import bewerte_aufgabe
from .models import ThemenBereich, Kapitel, Aufgabe, FehlerLog, AufgabeOption

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
    anmerkung_fuer_template = aufgabe.anmerkung

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
    optionen_liste = []
    anzeigen = []
    if "l" in aufgabe.typ:
        # Wir bauen eine Liste aus (Index, Text) Paaren
        optionen_liste = [(0, aufgabe.antwort)] # Index 0 ist immer die richtige Antwort
        for i, o in enumerate(aufgabe.optionen.order_by("position"), start=1):
            optionen_liste.append((i, o.text))
        random.shuffle(optionen_liste)

        # Spezialfall: Überschreibe für Typ 'e'
        if "e" in (aufgabe.typ or "").lower():
            anmerkung_fuer_template = "Bitte beide Begriffe mit ';' oder '...' trennen."

        # ... beim Render-Aufruf einfach mitgeben ...
        return render(request, "physik/aufgabe.html", {
            "aufgabe": aufgabe,
            "anmerkung": anmerkung_fuer_template,
            # ... andere Variablen ...
        })
        
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
        "anmerkung": anmerkung_fuer_template,
        "anzeigen": anzeigen,
        "bilder": bilder_anzeige,
        "auswahl_optionen": optionen_liste,
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

@user_passes_test(lambda u: u.is_superuser)
@user_passes_test(lambda u: u.is_superuser)
def fehler_liste(request):
    # Basis-Queryset
    logs = FehlerLog.objects.all().select_related('aufgabe__thema', 'aufgabe__kapitel')

    # 1. Suche (lfd_nr oder Frage)
    q = request.GET.get('q')
    if q:
        logs = logs.filter(
            Q(aufgabe__lfd_nr__icontains=q) | 
            Q(aufgabe__frage__icontains=q) |
            Q(eingegebene_antwort__icontains=q)
        )

    # 2. Filter nach Thema
    thema_id = request.GET.get('thema')
    if thema_id:
        logs = logs.filter(aufgabe__thema_id=thema_id)

    # 3. Filter nach Kapitel
    kapitel_id = request.GET.get('kapitel')
    if kapitel_id:
        logs = logs.filter(aufgabe__kapitel_id=kapitel_id)

    # Daten für die Dropdowns
    themen = ThemenBereich.objects.all().order_by('ordnung')
    # Kapitel nur für das gewählte Thema (optional, für bessere UX)
    kapitel = Kapitel.objects.filter(thema_id=thema_id) if thema_id else Kapitel.objects.all()

    context = {
        'logs': logs,
        'themen': themen,
        'kapitel': kapitel,
        's_thema': int(thema_id) if thema_id else None,
        's_kapitel': int(kapitel_id) if kapitel_id else None,
        'query': q or '',
    }
    return render(request, 'physik/fehler_liste.html', context)

@user_passes_test(lambda u: u.is_superuser)
def fehler_edit(request, log_id):
    log = get_object_or_404(FehlerLog, id=log_id)
    aufgabe = log.aufgabe

    if request.method == "POST":
        if "just_delete" in request.POST:
            log.delete()
        else:
            # 1. Hauptfelder der Aufgabe speichern
            aufgabe.typ = request.POST.get("typ")
            aufgabe.frage = request.POST.get("frage")
            aufgabe.antwort = request.POST.get("antwort")
            aufgabe.anmerkung = request.POST.get("anmerkung")
            aufgabe.erklaerung = request.POST.get("erklaerung")
            aufgabe.hilfe = request.POST.get("hilfe")
            aufgabe.save()

            # 2. Bestehende Optionen aktualisieren oder löschen
            for key, value in request.POST.items():
                if key.startswith("opt_"):
                    opt_id = key.split("_")[1]
                    option = AufgabeOption.objects.get(id=opt_id)
                    
                    if value.strip(): # Falls Text vorhanden: Update
                        option.text = value.strip()
                        option.position = request.POST.get(f"pos_{opt_id}") or 0
                        option.save()
                    else: # Falls Text leer: Weg damit
                        option.delete()

            # 3. Neue Optionen anlegen (die 3 leeren Felder)
            for i in range(1, 4):
                new_text = request.POST.get(f"new_opt_{i}")
                new_pos = request.POST.get(f"new_pos_{i}")
                
                if new_text and new_text.strip():
                    AufgabeOption.objects.create(
                        aufgabe=aufgabe,
                        text=new_text.strip(),
                        position=new_pos if new_pos else 0
                    )

            # Erst wenn alles gespeichert ist, löschen wir den Fehler-Log
            log.delete()

        return redirect('fehler_liste')

    return render(request, 'physik/fehler_edit.html', {'log': log})