import random

from django.contrib import messages
from django.contrib.messages import get_messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Count
from django.contrib.auth import logout
from django.contrib.auth.decorators import user_passes_test, login_required

from .bewertung import bewerte_aufgabe
from .models import ThemenBereich, Kapitel, Aufgabe, FehlerLog, AufgabeOption, Profil

from django.db.models import Count, Q
from .models import ThemenBereich, Aufgabe, Protokoll

from django.http import JsonResponse

def ist_mitarbeiter(user):
    return user.is_staff

def berechne_sperre(total, f1_bestand, f2_bestand, ziel_fach, f3_bestand=0):
    ready = True
    hint = ""
    
    if ziel_fach == 2:
        bestand = f2_bestand
        if bestand > 0 and total > 0:
            erledigt = total - f1_bestand
            if (erledigt / total) < 0.75:
                ready = False
                hint = f"Noch {int(0.75 * total - erledigt) + 1} in Fach 1 lösen."
        return bestand, ready, hint
        
    if ziel_fach == 3:
        bestand = f3_bestand
        if bestand > 0 and total > 0:
            erledigt = total - f1_bestand - f2_bestand
            if (erledigt / total) < 0.75:
                ready = False
                hint = f"Noch {int(0.75 * total - erledigt) + 1} in Fach 2 lösen."
        return bestand, ready, hint

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
    profil = None
    if request.user.is_authenticated:
        profil, created = Profil.objects.get_or_create(user=request.user)
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

    # 5. tb_totals berechnen UND die Sperr-Logik
    tb_totals = {}
    kum_stats = {
        "1": {"total": 0, "f1": 0, "f2": 0, "f3": 0},
        "2": {"total": 0, "f1": 0, "f2": 0, "f3": 0},
        "3": {"total": 0, "f1": 0, "f2": 0, "f3": 0},
    }

    for tb in themenbereiche:
        t_sum = {"1": 0, "2": 0, "3": 0}
        
        for kap in tb.kapitel.all().order_by("zeile"):
            if tb.id not in counts: counts[tb.id] = {}
            if kap.id not in counts[tb.id]: counts[tb.id][kap.id] = {}
            
            # Rohdaten für dieses Kapitel kumulieren
            for lvl in ["1", "2", "3"]:
                if lvl not in counts[tb.id][kap.id]:
                    counts[tb.id][kap.id][lvl] = {'0':0, '1':0, '2':0, 'total':0}
                
                c_raw = counts[tb.id][kap.id][lvl]
                kum_stats[lvl]["total"] += c_raw.get('total', 0)
                kum_stats[lvl]["f1"]    += c_raw.get('0', 0)
                kum_stats[lvl]["f2"]    += c_raw.get('1', 0)
                kum_stats[lvl]["f3"]    += c_raw.get('2', 0)

            # Jetzt die Vererbung: Mittel erbt von Einfach, Profi erbt von Mittel
            # Level 1 (Einfach)
            t1 = kum_stats["1"]["total"]
            f1_1 = kum_stats["1"]["f1"]
            f2_1 = kum_stats["1"]["f2"]
            f3_1 = kum_stats["1"]["f3"]
            
            # Level 2 (Mittel) = Lvl 1 + Lvl 2
            t2 = t1 + kum_stats["2"]["total"]
            f1_2 = f1_1 + kum_stats["2"]["f1"]
            f2_2 = f2_1 + kum_stats["2"]["f2"]
            f3_2 = f3_1 + kum_stats["2"]["f3"]

            # Level 3 (Profi) = Lvl 2 + Lvl 3
            t3 = t2 + kum_stats["3"]["total"]
            f1_3 = f1_2 + kum_stats["3"]["f1"]
            f2_3 = f2_2 + kum_stats["3"]["f2"]
            f3_3 = f3_2 + kum_stats["3"]["f3"]

            # Ergebnisse in das counts-Objekt zurückschreiben
            # -- Daten für Level 1 --
            res1 = counts[tb.id][kap.id]["1"]
            res1["kum_f2"], res1["f2_ready"], res1["f2_hint"] = berechne_sperre(t1, f1_1, f2_1, 2)
            res1["kum_f3"], res1["f3_ready"], res1["f3_hint"] = berechne_sperre(t1, f1_1, f2_1, 3, f3_1)

            # -- Daten für Level 2 --
            res2 = counts[tb.id][kap.id]["2"]
            res2["kum_f2"], res2["f2_ready"], res2["f2_hint"] = berechne_sperre(t2, f1_2, f2_2, 2)
            res2["kum_f3"], res2["f3_ready"], res2["f3_hint"] = berechne_sperre(t2, f1_2, f2_2, 3, f3_2)

            # -- Daten für Level 3 --
            res3 = counts[tb.id][kap.id]["3"]
            res3["kum_f2"], res3["f2_ready"], res3["f2_hint"] = berechne_sperre(t3, f1_3, f2_3, 2)
            res3["kum_f3"], res3["f3_ready"], res3["f3_hint"] = berechne_sperre(t3, f1_3, f2_3, 3, f3_3)

            # Summen für die Balkenanzeige (bleibt wie es war)
            for s_key in ["1", "2", "3"]:
                t_sum[s_key] += counts[tb.id][kap.id].get(s_key, {}).get('total', 0)

        tb_totals[tb.id] = t_sum 

    return render(request, "physik/index.html", {
            "themenbereiche": themenbereiche,
            "counts": counts,
            "kapitel_map": kapitel_map,
            'profil': profil,
        })

def force_logout(request):
    logout(request)
    return redirect('/')

@login_required
def update_view_settings(request, slug):
    try:
        # Sicherer Weg: Profil über das Model suchen
        profil, created = Profil.objects.get_or_create(user=request.user)
        
        # Feldname: Physik_einstellungen
        einstellungen = profil.physik_einstellungen if isinstance(profil.physik_einstellungen, dict) else {}
        
        versteckt = list(einstellungen.get("versteckt", []))
        
        if slug in versteckt:
            versteckt.remove(slug)
        else:
            versteckt.append(slug)
            if slug == "mittel" and "profi" not in versteckt:
                versteckt.append("profi")
        
        einstellungen["versteckt"] = versteckt
        profil.physik_einstellungen = einstellungen
        profil.save()
        
        return JsonResponse({"status": "ok", "versteckt": versteckt})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
    
@login_required
def update_row_settings(request, slug):
    profil, created = Profil.objects.get_or_create(user=request.user)
    einstellungen = profil.physik_einstellungen if isinstance(profil.physik_einstellungen, dict) else {}
    
    if 'zeilen_versteckt' not in einstellungen:
        einstellungen['zeilen_versteckt'] = []
    
    if slug in einstellungen['zeilen_versteckt']:
        einstellungen['zeilen_versteckt'].remove(slug)
    else:
        einstellungen['zeilen_versteckt'].append(slug)
    
    profil.physik_einstellungen = einstellungen
    profil.save()
    
    return JsonResponse({'status': 'ok', 'versteckt': einstellungen['zeilen_versteckt']})
    
@login_required
def aufgaben(request):
    anmerkung_fuer_template = ""
    
    # NEU: Wenn 'tb' in der URL steht, wollen wir IMMER eine neue Serie starten,
    # auch wenn 'aufgaben_ids' schon in der Session existieren.
    if request.GET.get("tb"):
        # 0. Vorbereitung: Alte Session & Messages aufräumen
        for k in ("aufgaben_ids", "index", "p_richtig", "letzte_antwort", "warte_auf_weiter"):
            request.session.pop(k, None)
        
        storage = get_messages(request)
        for message in storage: pass

        # 1. Parameter aus GET holen
        tb_id = request.GET.get("tb")
        level_param = request.GET.get("level", "3") # Standard 3
        bis_kap_zeile = request.GET.get("bis_kap")
        
        # Diese bleiben für das Overlay wichtig:
        start_kap = int(request.GET.get("start", 0))
        end_kap = int(request.GET.get("end", 999))
        fach_int = int(request.GET.get("fach", 1))

        # 2. Grundfilterung
        aufgaben_qs = Aufgabe.objects.filter(thema_id=tb_id)

        # --- NEU: Kapitel-Logik unterscheiden ---
        if bis_kap_zeile:
            # Weg über die Index-Tabelle (kumulativ)
            aufgaben_qs = aufgaben_qs.filter(kapitel__zeile__lte=int(bis_kap_zeile))
        else:
            # Klassischer Weg über das Overlay (Bereich)
            aufgaben_qs = aufgaben_qs.filter(
                kapitel__zeile__gte=start_kap,
                kapitel__zeile__lte=end_kap
            )

        # --- NEU: Level-Logik (kumuliert für 1,2 etc.) ---
        if isinstance(level_param, str) and "," in level_param:
            levels = [int(l) for l in level_param.split(",")]
            aufgaben_qs = aufgaben_qs.filter(schwierigkeit__in=levels)
        else:
            aufgaben_qs = aufgaben_qs.filter(schwierigkeit__lte=int(level_param))

        # 3. Spezifische Fach-Filterung (DEIN BESTEHENDER CODE)
        if fach_int == 1: 
            aufgaben_qs = aufgaben_qs.filter(
                Q(protokoll__user=request.user, protokoll__fach=1) | 
                ~Q(protokoll__user=request.user)
            ).distinct()
        else:
            aufgaben_qs = aufgaben_qs.filter(
                protokoll__user=request.user, 
                protokoll__fach=fach_int
            )

        # 3. Spezifische Fach-Filterung
        # fach_int kommt oben aus request.GET.get("fach")
        if fach_int == 1: 
            # Zeigt nur Aufgaben, die noch "neu" sind oder explizit in Fach 1 liegen
            aufgaben_qs = aufgaben_qs.filter(
                Q(protokoll__user=request.user, protokoll__fach=1) | 
                ~Q(protokoll__user=request.user)
            ).distinct()
        else:
            # Filtert exakt auf Fach 2, 3 oder 4
            aufgaben_qs = aufgaben_qs.filter(
                protokoll__user=request.user, 
                protokoll__fach=fach_int
            )
            
        # 4. IDs extrahieren & initialisieren
        all_ids = list(aufgaben_qs.values_list("id", flat=True))
        
        if not all_ids:
            messages.info(request, f"Keine Aufgaben in diesem Bereich gefunden.")
            return redirect('physik:index')

        random.shuffle(all_ids)
        request.session["aufgaben_ids"] = all_ids[:10]
        request.session["index"] = 0
        request.session["warte_auf_weiter"] = False
        
        # WICHTIG: Redirect auf die URL ohne Parameter, damit ein Refresh 
        # nicht die Serie neu startet
        return redirect("physik:aufgaben")
    
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
    
# -------- Medien (Bilder & Videos) --------
    bilder_anzeige = None
    
    # Wir holen die Bilder/Videos immer, wenn welche da sind
    bilder = list(aufgabe.bilder.order_by("position"))
    
    if bilder:
        # ---- Fall 1: Echte Bildfrage (Typ enthält 'p') ----
        if "p" in aufgabe.typ:
            # Nur bei Typ genau 'p' setzen wir die richtige Bild-Antwort
            if aufgabe.typ == "p":
                p_richtig = bilder[0].id
                request.session["p_richtig"] = p_richtig
            
            # Bilder mischen, damit das richtige nicht immer an Platz 1 steht
            random.shuffle(bilder)
        
        # ---- Fall 2: Illustration / Video (z.B. Typ 'a' oder 'va') ----
        else:
            request.session.pop("p_richtig", None)
            # Bei Videos oder normalen Illustrationen NICHT mischen? 
            # Meistens will man Videos an Position 1 behalten.
            pass 

        bilder_anzeige = bilder

    optionen_liste = []
    anzeigen = []
    if "r" in aufgabe.typ:
        # 1. Optionen nach Position sortiert holen
        optionen = aufgabe.optionen.all().order_by('position')
        
        if optionen.exists():
            # 2. Anzahl der Werte aus der ersten Option ermitteln
            # Wir splitten den Text und zählen die Elemente
            erstes_opt_text = optionen[0].text
            anzahl_werte = len(erstes_opt_text.split(';'))

            # 3. Zufallsindex bestimmen
            # Wir versuchen den Index aus der Session zu holen, damit er stabil bleibt
            idx = request.session.get('aktiver_index')
            
            # Falls kein Index da ist oder er nicht mehr zu den Daten passt, neu würfeln
            if idx is None or idx >= anzahl_werte:
                idx = random.randrange(anzahl_werte)
                request.session['aktiver_index'] = idx

            # 4. Die Werte-Liste für .format() zusammenstellen
            # Wir nehmen von jeder Option den Wert an der Stelle 'idx'
            auswahl_liste = []
            for opt in optionen:
                werte = [v.strip() for v in opt.text.split(';')]
                if idx < len(werte):
                    auswahl_liste.append(werte[idx])
                else:
                    # Fallback, falls eine Liste mal kürzer ist
                    auswahl_liste.append("???")

            # 5. Fragetext formatieren
            # Hier werden {0}, {1}, {2} etc. durch die Liste ersetzt
            try:
                # Wichtig: Der Stern * entpackt die Liste für die Positions-Platzhalter
                aufgabe.frage = aufgabe.frage.format(*auswahl_liste)
            except (IndexError, TypeError):
                # Falls die Anzahl der {} im Text nicht zur Anzahl der Optionen passt
                pass

    if "a" in aufgabe.typ:
        # Wir bauen eine Liste aus (Index, Text) Paaren
        optionen_liste = [(0, aufgabe.loesung)] # Index 0 ist immer die richtige Antwort
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
        if not antwort and not bild_antwort:# and not request.session.get("warte_auf_weiter"):
            if not request.session.get("warte_auf_weiter"):
                messages.info(request, "Letzte Aufgabe übersprungen.")
            request.session["index"] += 1
            request.session.pop('aktiver_index', None)
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
            request.session.pop('aktiver_index', None)
            request.session["warte_auf_weiter"] = False
            request.session.pop("letzte_antwort", None)

        # ---- ungültig ----
        elif ergebnis.get("ungueltig"):
            messages.warning(request, ergebnis["hinweis"])
            request.session["warte_auf_weiter"] = False
            request.session.pop("letzte_antwort", None)

        # ---- falsch ----
        else:
            hinweis_text = ergebnis.get("hinweis", "Leider falsch.")
            if aufgabe.typ != "p":
                hinweis_text = (
                    f"{hinweis_text} "
                    f"Deine Eingabe: »{antwort}« | "
                    f"Richtige Lösung: »{aufgabe.loesung}«"
                )
            if aufgabe.erklaerung:
                hinweis_text += f"\n\nBegründung: {aufgabe.erklaerung}"
            
            messages.warning(request, hinweis_text)
            
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

from django.shortcuts import render, get_object_or_404
from .models import Aufgabe, ThemenBereich, Kapitel

@user_passes_test(ist_mitarbeiter)
def aufgaben_liste(request):
    themenbereiche = ThemenBereich.objects.all()
    thema_id = request.GET.get('thema')
    kapitel_id = request.GET.get('kapitel')
    
    # Kapitel für den Filter laden
    if thema_id:
        kapitel_liste = Kapitel.objects.filter(thema_id=thema_id).order_by('zeile')
    else:
        kapitel_liste = Kapitel.objects.all().order_by('thema', 'zeile')

    # Aufgaben filtern und effizient laden (ForeignKey-Beziehungen vorladen)
    aufgaben = Aufgabe.objects.select_related('kapitel__thema').all().order_by('kapitel__thema', 'kapitel__zeile', 'lfd_nr')
    
    if thema_id:
        aufgaben = aufgaben.filter(kapitel__thema_id=thema_id)
    if kapitel_id:
        aufgaben = aufgaben.filter(kapitel_id=kapitel_id)

    return render(request, 'physik/aufgaben_liste.html', {
        'aufgaben': aufgaben,
        'themenbereiche': themenbereiche,
        'kapitel_liste': kapitel_liste,
    })

@user_passes_test(ist_mitarbeiter)
def aufgabe_einstellungen(request, pk):
    # Holt die Aufgabe oder zeigt 404, wenn die ID nicht existiert
    aufgabe = get_object_or_404(Aufgabe, pk=pk)
    return render(request, 'physik/aufgabe_einstellungen.html', {'aufgabe': aufgabe})

@user_passes_test(ist_mitarbeiter)
def call(request, lfd_nr):
    try:
        aufgabe = Aufgabe.objects.get(lfd_nr=lfd_nr)
    except Aufgabe.DoesNotExist:
        try:
            aufgabe = Aufgabe.objects.get(lfd_nr__iexact=lfd_nr)
        except Aufgabe.DoesNotExist:
            return HttpResponse(f"Aufgabe mit der Bezeichnung '{lfd_nr}' wurde nicht gefunden.")
    request.session.pop('aktiver_index', None)

    request.session["aufgaben_ids"] = [aufgabe.id]
    request.session["index"] = 0
    request.session["warte_auf_weiter"] = False
    request.session.pop("letzte_antwort", None)

    return redirect("physik:aufgaben")

@user_passes_test(ist_mitarbeiter)
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

@user_passes_test(ist_mitarbeiter)
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
            aufgabe.loesung = request.POST.get("antwort")
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

@user_passes_test(ist_mitarbeiter)
def howto():
    pass