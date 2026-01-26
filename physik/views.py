import random

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Count
from django.contrib.auth.decorators import user_passes_test

from .bewertung import bewerte_aufgabe
from .models import ThemenBereich, Kapitel, Aufgabe, FehlerLog, AufgabeOption

from django.db.models import Count, Q
from .models import ThemenBereich, Aufgabe, Protokoll

def index(request):
    # Reset Session
    for k in ("aufgaben_ids", "index", "p_richtig", "letzte_antwort", "warte_auf_weiter"):
        request.session.pop(k, None)

    themenbereiche = ThemenBereich.objects.filter(eingeblendet=True).prefetch_related("kapitel").order_by("ordnung")

    # 1. Die kapitel_map für das JavaScript-Modal
    kapitel_map = {
            str(tb.id): [{"zeile": k.zeile, "name": k.kapitel} for k in tb.kapitel.all().order_by("zeile")]
            for tb in themenbereiche
        }

    # 2. Alle Aufgaben zählen (Gesamtbestand)
    qs_gesamt = (
        Aufgabe.objects.filter(thema__in=themenbereiche)
        .values("thema_id", "kapitel_id", "schwierigkeit")
        .annotate(cnt=Count("id"))
    )

    # 3. Lernstand des Users abrufen (nur wenn eingeloggt)
    user_protokoll = {}
    if request.user.is_authenticated:
        qp = (
            Protokoll.objects.filter(user=request.user, aufgabe__thema__in=themenbereiche)
            .values("aufgabe__thema_id", "aufgabe__kapitel_id", "aufgabe__schwierigkeit", "fach")
            .annotate(cnt=Count("id"))
        )
        for r in qp:
            t_id = r["aufgabe__thema_id"]
            k_id = r["aufgabe__kapitel_id"]
            s = str(r["aufgabe__schwierigkeit"])
            f = r["fach"]
            user_protokoll.setdefault(t_id, {}).setdefault(k_id, {}).setdefault(s, {})
            user_protokoll[t_id][k_id][s][f] = r["cnt"]

    # 4. Counts-Dict aufbauen (mit Differenzrechnung für Fach 0)
    counts = {}
    for r in qs_gesamt:
        t_id = r["thema_id"]
        k_id = r["kapitel_id"]
        s = str(r["schwierigkeit"])
        gesamt = r["cnt"]

        p_data = user_protokoll.get(t_id, {}).get(k_id, {}).get(s, {})
        f2 = p_data.get(2, 0)
        f3 = p_data.get(3, 0)
        f4 = p_data.get(4, 0)

        f0 = gesamt - (f2 + f3 + f4)

        counts.setdefault(t_id, {}).setdefault(k_id, {})
        counts[t_id][k_id][s] = {
            '0': f0,
            '1': f2,
            '2': f3,
            '3': f4,
            'total': gesamt
        }

    # 5. tb_totals berechnen (Summen für die farbigen Themen-Balken)
    tb_totals = {}
    for tb in themenbereiche:
        # Wir summieren hier die 'total' Werte pro Schwierigkeit (1, 2, 3)
        t_sum = {"1": 0, "2": 0, "3": 0}
        for kap in tb.kapitel.all():
            kap_counts = counts.get(tb.id, {}).get(kap.id, {})
            for s in ["1", "2", "3"]:
                t_sum[s] += kap_counts.get(s, {}).get('total', 0)
        tb_totals[tb.id] = t_sum

    return render(request, "physik/index.html", {
            "themenbereiche": themenbereiche,
            "counts": counts,
            "kapitel_map": kapitel_map,
        })

def aufgaben(request):
    anmerkung_fuer_template = ""
    if "aufgaben_ids" not in request.session:
        # 1. Parameter aus GET holen
        tb_id = request.GET.get("tb")
        level = int(request.GET.get("level", 3))
        start_kap = int(request.GET.get("start", 0))
        end_kap = int(request.GET.get("end", 999))
        fach_int = int(request.GET.get("fach", 1))

        # 2. Grundfilterung der Aufgaben (Thema, Kapitel, Schwierigkeit)
        aufgaben_qs = Aufgabe.objects.filter(
            thema_id=tb_id,
            kapitel__zeile__gte=start_kap,
            kapitel__zeile__lte=end_kap,
            schwierigkeit__lte=level
        )

        # 3. Spezifische Fach-Filterung (WICHTIG: distinct() wegen des Joins zum Protokoll)
        if fach_int == 1:   
            # Fach 1: 
            # Aufgaben, die ENTWEDER ein Protokoll für diesen User mit Fach 1 haben
            # ODER die überhaupt kein Protokoll für diesen User haben
            aufgaben_qs = aufgaben_qs.filter(
                Q(protokoll__user=request.user, protokoll__fach=1) | 
                ~Q(protokoll__user=request.user) # Das ~ Symbol bedeutet "NOT"
            ).distinct()
        else:
            # Fach 2 oder 3: Exakter Match
            aufgaben_qs = aufgaben_qs.filter(
                protokoll__user=request.user, 
                protokoll__fach=fach_int
            )

        # 4. IDs extrahieren
        all_ids = list(aufgaben_qs.values_list("id", flat=True))
        
        # 5. Check: Wenn leer, zurück zur Index
        if not all_ids:
            messages.info(request, f"In Fach {fach_int} gibt es momentan keine Aufgaben für diesen Bereich.")
            return redirect('physik:index')

        # 6. Serie initialisieren (nur wenn wir nicht schon mitten drin sind)
        if "aufgaben_ids" not in request.session:
            random.shuffle(all_ids)
            selektierte_ids = all_ids[:10]
            request.session["aufgaben_ids"] = selektierte_ids
            request.session["index"] = 0
            request.session["warte_auf_weiter"] = False
            request.session.pop("letzte_antwort", None)

    # 7. Aktuellen Stand aus der Session holen
    ids_in_session = request.session.get("aufgaben_ids", [])
    index = request.session.get("index", 0)

    # 8. Check: Serie beendet?
    if index >= len(ids_in_session):
        for k in ("aufgaben_ids", "index", "p_richtig", "letzte_antwort", "warte_auf_weiter"):
            request.session.pop(k, None)
        return redirect("physik:index")

    # 9. Aktuelle Aufgabe laden
    aufgabe = Aufgabe.objects.get(id=ids_in_session[index])
    
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

    optionen_liste = []
    anzeigen = []
    if "a" in aufgabe.typ:
        # Wir bauen eine Liste aus (Index, Text) Paaren
        optionen_liste = [(0, aufgabe.antwort)] # Index 0 ist immer die richtige Antwort
        for i, o in enumerate(aufgabe.optionen.order_by("position"), start=1):
            optionen_liste.append((i, o.text))
        random.shuffle(optionen_liste)

    # Spezialfall: Überschreibe für Typ 'e'
    elif "e" in (aufgabe.typ or "").lower():
        anmerkung_fuer_template = "Bitte beide Begriffe mit ';' oder '...' trennen."

    # -------- POST --------
    if request.method == "POST":
        # Hier definierst du 'antwort'
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
            request,
            aufgabe,
            antwort,
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
        "anzahl": len(ids_in_session),
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
def fehler_liste(request):
    # Basis-Queryset
    logs = FehlerLog.objects.all().select_related('aufgabe__thema', 'aufgabe__kapitel')
    # --- NEU: Sortierung ---
    sort = request.GET.get('sort', '-id')  # Standard: Neueste Fehlermeldungen oben
    if sort == 'fachlich':
        # Sortiert nach Thema-Reihenfolge -> Kapitel-Reihenfolge -> Aufgabennummer
        #logs = logs.order_by('aufgabe__thema__ordnung', 'aufgabe__kapitel__ordnung', 'aufgabe__lfd_nr')
        logs = logs.order_by('aufgabe__thema__ordnung', 'aufgabe__lfd_nr')

    else:
        logs = logs.order_by('-id')
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
        'sort': sort,
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
                    
                    if value.strip(): 
                        option.text = value.strip()
                        option.save()
                    else: # Falls Text leer: Weg damit
                        option.delete()

            # 3. Neue Optionen anlegen (die 3 leeren Felder)
            for i in range(1, 4):
                new_text = request.POST.get(f"new_opt_{i}")
                
                if new_text and new_text.strip():
                    # Wir ignorieren new_pos aus dem POST und berechnen es selbst:
                    # Suche die höchste vorhandene Position für diese Aufgabe
                    last_opt = AufgabeOption.objects.filter(aufgabe=aufgabe).order_by('-position').first()
                    
                    # Start bei 2, wenn noch nichts da ist (wegen offizieller Antwort = 1)
                    next_pos = (last_opt.position + 1) if last_opt else 2
                    
                    AufgabeOption.objects.create(
                        aufgabe=aufgabe,
                        text=new_text.strip(),
                        position=next_pos
                    )

        # Erst wenn alles gespeichert ist, löschen wir den Fehler-Log
        log.delete()

        return redirect('physik:fehler_liste')

    return render(request, 'physik/fehler_edit.html', {'log': log})