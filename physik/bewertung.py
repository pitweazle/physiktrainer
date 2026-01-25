from difflib import SequenceMatcher
import re
from .models import Protokoll

# ===========================================================
# VERGLEICHE
# ===========================================================

def vergleich_streng(index, aufgabe, antwort_norm, antwort_original,
                     case_sensitiv, contain):
    if index == 1:
        text = aufgabe.antwort
    else:
        opts = list(aufgabe.optionen.order_by("position"))
        pos = index - 2
        if pos < 0 or pos >= len(opts):
            return False, None
        text = opts[pos].text

    # Leerzeichen entfernen
    soll = "".join((text or "").split())
    ist = "".join((antwort_original or "").split())

    if not case_sensitiv:
        # casefold() ist besser als upper()/lower() für Sonderzeichen wie °
        soll = soll.casefold()
        ist = ist.casefold()
    #print(f"   -> Vergleiche: '{soll}' mit '{ist}' (Ergebnis: {soll in ist})")
    # Logik: Entweder Teilstring-Suche (contain) oder exakter Vergleich
    if contain:
        return (soll in ist), None
    else:
        return (soll == ist), None

def vergleich_fuzzy(index, aufgabe, antwort_norm, antwort_original, ratio):
    if index == 1:
        text = aufgabe.antwort
    else:
        opts = list(aufgabe.optionen.order_by("position"))
        text = opts[index-2].text if (index-2) < len(opts) else ""

    soll = "".join((text or "").split()).casefold()
    ist = "".join((antwort_original or "").split()).casefold()

    # Direkter Vergleich der Ähnlichkeit
    if SequenceMatcher(None, soll, ist).ratio() >= ratio:
        return True, f"Fast richtig – gemeint war: {text}"

    # Bonus: Falls eines im anderen enthalten ist, aber Ratio knapp drunter
    if (soll in ist or ist in soll) and SequenceMatcher(None, soll, ist).ratio() >= ratio * 0.9:
        return True, f"Fast richtig – achte auf die Schreibweise von: {text}"

    return False, None

# ===========================================================
# HAUPTFUNKTION
# ===========================================================
def bewerte_aufgabe(request, aufgabe, user_antwort, text_antwort=None, bild_antwort=None, session=None):
    # 1. Initialisierung
    ergebnis = None
    typ_roh = (aufgabe.typ or "").strip()
    norm = normalisiere(text_antwort) if text_antwort else ""
    
    # Flags extrahieren
    case_sensitiv = "X" in typ_roh
    fuzzy_level = 1 if "Y" in typ_roh else 2 if "Z" in typ_roh else 0
    typ = typ_roh.replace("X", "").replace("Y", "").replace("Z", "")

    # -----------------------------------------------------------
    # A. SPEZIAL-TYPEN (Priorität vor Text-Parsing)
    # -----------------------------------------------------------

    # 1. Bilderauswahl (p)
    if "p" in typ:
        # Hier nutzen wir die session, um die ID des richtigen Bildes zu vergleichen
        ergebnis = bewerte_bildauswahl(aufgabe, bild_antwort, session)

    # 2. Wahr/Falsch (w)
    elif "w" in typ:
        ergebnis = bewerte_wahr_falsch(aufgabe, text_antwort)

    # 3. Auswahl-Liste / Multiple Choice (a)
    elif "a" in typ:
        ergebnis = bewerte_liste(aufgabe, text_antwort)

    # 4. Einheiten-Spezialfall (e)
    elif "e" in typ:
        ergebnis = bewerte_e_typ(aufgabe, text_antwort)

    # -----------------------------------------------------------
    # B. TEXT-PARSER (Nur wenn oben noch nichts entschieden wurde)
    # -----------------------------------------------------------

    # 1. Vorab-Prüfung: f (Verbotene Begriffe)
    if not ergebnis and "f" in typ:
        ok, hinweis = pruefe_verbotene_begriffe(aufgabe, norm, text_antwort)
        if not ok:
            ergebnis = {"richtig": False, "hinweis": hinweis}

    # 2. Sonderfall: Reiner Zahlentyp (1, 2, 3...)
    if not ergebnis and typ.isdigit():
        max_idx = int(typ)
        found = False
        # Streng
        for i in range(1, max_idx + 1):
            ok, _ = vergleich_streng(i, aufgabe, norm, text_antwort, case_sensitiv, False)
            if ok: 
                ergebnis = {"richtig": True, "hinweis": "Richtig!"}
                found = True
                break
        
        # Fuzzy (falls nötig)
        if not found and fuzzy_level:
            r = 0.85 if fuzzy_level == 1 else 0.7
            for i in range(1, max_idx + 1):
                ok, h = vergleich_fuzzy(i, aufgabe, norm, text_antwort, r)
                if ok: 
                    ergebnis = {"richtig": True, "hinweis": h}
                    found = True
                    break
        
        if not found:
            ergebnis = {"richtig": False, "hinweis": f"Leider falsch. Lösung: {aufgabe.antwort}"}

    # 3. Haupt-Parser: Streng
    if not ergebnis:
        streng_ok, hinweis = bewerte_booleschen_ausdruck(
            typ, aufgabe, norm, text_antwort,
            lambda idx, aufg, n, o: vergleich_streng(idx, aufg, n, o, case_sensitiv, True)
        )
        if streng_ok:
            ergebnis = {"richtig": True, "hinweis": "Richtig!"}

    # 4. Haupt-Parser: Fuzzy
    if not ergebnis and fuzzy_level:
        ratio = 0.85 if fuzzy_level == 1 else 0.7
        fuzzy_ok, fuzzy_hinweis = bewerte_booleschen_ausdruck(
            typ, aufgabe, norm, text_antwort,
            lambda idx, aufg, n, o: vergleich_fuzzy(idx, aufg, n, o, ratio)
        )
        if fuzzy_ok:
            ergebnis = {"richtig": True, "hinweis": fuzzy_hinweis}

    # -----------------------------------------------------------
    # C. FINALE & LOGGING
    # -----------------------------------------------------------
    if request.user.is_authenticated:
        from .models import Protokoll # Import hier, falls oben Probleme
        protokoll, created = Protokoll.objects.get_or_create(
            user=request.user, 
            aufgabe=aufgabe
        )

        if ergebnis:
            if protokoll.fach < 4:
                protokoll.fach += 1
            ergebnis = {"richtig": True, "hinweis": "Super, das war richtig!"}
        else:
            protokoll.fach = 2 # Zurück in den Lernvorrat
            ergebnis = {"richtig": False, "hinweis": f"Leider falsch. Lösung: {aufgabe.antwort}"}
            
        protokoll.save()
        print(f"Protokoll aktualisiert: Aufgabe {aufgabe.id} jetzt in Fach {protokoll.fach}")
    
    # Wenn bis hierhin nichts gegriffen hat
    if not ergebnis:
        ergebnis = {"richtig": False, "hinweis": f"Leider falsch. Lösung: {aufgabe.antwort}"}

    # Sahnehäubchen: Fehlerlogging
    if not ergebnis.get("richtig") and text_antwort:
        reine_auswahl_typen = ['p', 'a', 'w']
        if typ not in reine_auswahl_typen:
            from .models import FehlerLog
            # Wir speichern nur echte Texteingaben (auch wenn ein Bild 'p104' dabei steht)
            FehlerLog.objects.get_or_create(
                aufgabe=aufgabe,
                eingegebene_antwort=text_antwort.strip()
            )

    return ergebnis

# ===========================================================
# PARSER
# ===========================================================
def bewerte_booleschen_ausdruck(typ, aufgabe, antwort_norm, antwort_original, vergleich):
    tokens = []
    i = 0
    while i < len(typ):
        if typ[i].isdigit():
            j = i
            while j < len(typ) and typ[j].isdigit():
                j += 1
            tokens.append(("NUM", int(typ[i:j])))
            i = j
        elif typ[i] in "ou()":
            tokens.append((typ[i], typ[i]))
            i += 1
        else:
            i += 1

    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def eat(k):
        nonlocal pos
        if peek() and peek()[0] == k:
            pos += 1
            return True
        return False

    def expr():
        res_ok, res_hinweis = term()
        while peek() and peek()[0] == "o":
            eat("o")
            ok2, hinw2 = term()
            res_ok = res_ok or ok2
            if ok2 and not res_hinweis:
                res_hinweis = hinw2
        return res_ok, res_hinweis

    def term():
        res_ok, res_hinweis = factor()
        while peek() and peek()[0] == "u":
            eat("u")
            ok2, hinw2 = factor()
            res_ok = res_ok and ok2
            if not ok2: res_hinweis = hinw2
        return res_ok, res_hinweis

    def factor():
        nonlocal pos
        tok = peek()
        if not tok: return False, None
        
        if tok[0] == "(":
            eat("(")
            res = expr()
            eat(")")
            return res
        
        if tok[0] == "NUM":
            num1 = tok[1]
            eat("NUM")
            
            # PRÜFUNG: Folgt ein 'o' und eine weitere NUM? (Bereichs-Check)
            if peek() and peek()[0] == "o":
                # Schauen, ob das Token nach dem 'o' eine Zahl ist
                if pos + 1 < len(tokens) and tokens[pos+1][0] == "NUM":
                    eat("o") # 'o' essen
                    num2 = tokens[pos][1]
                    eat("NUM") # zweite Zahl essen
                    
                    #print(f" !!! BEREICH GEFUNDEN: {num1} bis {num2}")
                    for n in range(num1, num2 + 1):
                        ok, hinw = vergleich(n, aufgabe, antwort_norm, antwort_original)
                        if ok: return True, hinw
                    return False, None

            # Normalfall
            #print(f" -> Einzelvergleich NUM {num1}")
            return vergleich(num1, aufgabe, antwort_norm, antwort_original)
        
        return False, None
    return expr()

# ===========================================================
# HILFSFUNKTIONEN
# ===========================================================

def normalisiere(text):
    return "".join(text.split()) if text else ""

def bewerte_bildauswahl(aufgabe, bild_antwort, session):
    return session and str(session.get("p_richtig")) == str(bild_antwort)

def bewerte_wahr_falsch(aufgabe, norm):
    """
    Vergleicht die Bedeutung der User-Eingabe mit der Bedeutung der Lösung in der DB.
    'f' (User) wird gegen 'falsch' (Datenbank) korrekt als WAHR gewertet.
    """

    t = (norm or "").lower()

    # Lösung aus Feld 1 (antwort) radikal bereinigen (entfernt auch Punkte/Leerzeichen)
    db_lsg = "".join((aufgabe.antwort or "").lower().split()).rstrip(".")

    # 2. Bedeutungsgruppen definieren
    WAHR_GRUPPE = {"w", "wahr", "ja", "j", "richtig", "ok", "stimmt"}
    FALSCH_GRUPPE = {"f", "falsch", "nein", "n", "stimmtnicht"}

    # 3. Bestimmen, was gemeint ist
    user_meint_wahr = t in WAHR_GRUPPE
    user_meint_falsch = t in FALSCH_GRUPPE
    
    db_ist_wahr = db_lsg in WAHR_GRUPPE
    db_ist_falsch = db_lsg in FALSCH_GRUPPE

    # 4. Der eigentliche Vergleich der Bedeutung
    if user_meint_wahr:
        # User sagt 'Ja' -> Richtig, wenn DB auch 'Ja'-Bedeutung hat
        return {"richtig": db_ist_wahr, "hinweis": "Richtig!" if db_ist_wahr else "Leider falsch."}
    
    if user_meint_falsch:
        return {"richtig": db_ist_falsch, "hinweis": "Richtig!" if db_ist_falsch else "Leider falsch."}

    # 5. Pech gehabt (Quatsch geschrieben)
    return {
        "richtig": False,
        "hinweis": "Bitte mit w/f, wahr/falsch oder ja/nein antworten."
    }

def bewerte_liste(aufgabe, antwort):
    # 1. Versuch: Ist 'antwort' ein Index (0 für richtig)?
    try:
        if int(antwort) == 0:
            return {"richtig": True, "hinweis": "Richtig!"}
    except (ValueError, TypeError):
        # 2. Fallback: Falls doch Text kommt (alte Logik)
        if normalisiere(antwort) == normalisiere(aufgabe.antwort):
            return {"richtig": True, "hinweis": "Richtig!"}

    return {
        "richtig": False,
        "hinweis": f"Leider falsch. Richtige Antwort: {aufgabe.antwort}"
    }

def bewerte_e_typ(typ, aufgabe, antwort, vergleich):
    # Typ am 'e' splitten
    links, rechts = typ.split("e", 1)
    
    # Trennung bei ';' oder '...' (Regulärer Ausdruck)
    # Das fängt "Begriff1;Begriff2" und "Begriff1...Begriff2" ab
    teile = re.split(r';|\.\.\.', antwort)
    
    if len(teile) >= 2:
        a = teile[0].strip()
        b = teile[1].strip()
    else:
        return False, "Bitte zwei Begriffe mit ';' oder '...' trennen."

    # WICHTIG: Wir übergeben die normalisierten Teil-Strings an den Parser
    norm_a = normalisiere(a)
    norm_b = normalisiere(b)

    ok1, _ = bewerte_booleschen_ausdruck(links, aufgabe, norm_a, a, vergleich)
    ok2, _ = bewerte_booleschen_ausdruck(rechts, aufgabe, norm_b, b, vergleich)
    
    # Präzises Feedback für den User
    if ok1 and ok2:
        return True, "Beide Begriffe sind richtig!"
    if ok1:
        return False, "Der erste Begriff ist richtig, der zweite fehlt oder ist falsch."
    if ok2:
        return False, "Der zweite Begriff ist richtig, der erste fehlt oder ist falsch."
    
    return False, "Beide Begriffe sind leider falsch."

def pruefe_verbotene_begriffe(aufgabe, norm, text_antwort):
    typ = (aufgabe.typ or "").strip()

    if "f" not in typ:
        return True, ""

    _, verbot = typ.split("f", 1)
    if not verbot:
        return True, ""

    # prüfen, ob verbotener Ausdruck zutrifft
    kommt_vor, _ = bewerte_booleschen_ausdruck(
        verbot,
        aufgabe,
        norm,
        text_antwort,
        lambda i, a, n, o: vergleich_streng(
            i, a, n, o,
            case_sensitiv=False,
            contain=True
        )
    )

    if not kommt_vor:
        return True, ""

    # konkreten Begriff bestimmen
    verbotener_begriff = None
    i = 0
    indices = []
    while i < len(verbot):
        if verbot[i].isdigit():
            j = i
            while j < len(verbot) and verbot[j].isdigit():
                j += 1
            indices.append(int(verbot[i:j]))
            i = j
        else:
            i += 1

    for k in indices:
        ok, _ = vergleich_streng(
            k, aufgabe, norm, text_antwort,
            case_sensitiv=False,
            contain=True
        )
        if ok:
            if k == 1:
                verbotener_begriff = aufgabe.antwort
            else:
                opts = list(aufgabe.optionen.order_by("position"))
                if k - 2 < len(opts):
                    verbotener_begriff = opts[k - 2].text
            break

    if not verbotener_begriff:
        verbotener_begriff = text_antwort

    erklaerung = getattr(aufgabe, "erklaerung", "").strip()
    if erklaerung:
        hinweis = (
            f"Das ist hier falsch: „{verbotener_begriff}“\n\n"
            f"Begründung: {erklaerung}"
        )
    else:
        hinweis = f"Das ist hier falsch: „{verbotener_begriff}“"

    return False, hinweis

