from difflib import SequenceMatcher
import re

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

def bewerte_aufgabe(aufgabe, text_antwort=None, bild_antwort=None, session=None):
    typ_roh = (aufgabe.typ or "").strip()
    norm = normalisiere(text_antwort)

    case_sensitiv = "X" in typ_roh
    # Y=Level 1 (0.85), Z=Level 2 (0.70)
    fuzzy_level = 1 if "Y" in typ_roh else 2 if "Z" in typ_roh else 0
    
    # Reinigungs-Logik für den Typ-String
    typ = typ_roh.replace("X", "").replace("Y", "").replace("Z", "")

    # ---- Bildtyp (p) ----
    if typ == "p":
        ok = bewerte_bildauswahl(aufgabe, bild_antwort, session)
        return {"richtig": ok, "hinweis": "Richtig!" if ok else "Falsches Bild."}

    # ---- Wahr/Falsch (w) ----
    if typ == "w":
        return bewerte_wahr_falsch(aufgabe, norm)

    # ---- Listen (l) ----
    if typ.startswith("l"):
        return bewerte_liste(aufgabe, norm)

    # ---- Verbotene Begriffe (f) ----
    if "f" in typ:
        ok, hinweis = pruefe_verbotene_begriffe(aufgabe, norm, text_antwort)
        if not ok:
            return {"richtig": False, "hinweis": hinweis}

    # ---- REINER ZAHLENTYP (z.B. "3") ----
    # PRÜFUNG: Exakter Vergleich (==) von Feld 1 bis N
    if typ.isdigit():
        max_index = int(typ)
        for i in range(1, max_index + 1):
            # contain=False bewirkt den exakten Vergleich (soll == ist)
            ok, _ = vergleich_streng(i, aufgabe, norm, text_antwort, case_sensitiv, False)
            if ok:
                return {"richtig": True, "hinweis": "Richtig!"}

        if fuzzy_level:
            ratio = 0.85 if fuzzy_level == 1 else 0.70
            for i in range(1, max_index + 1):
                ok, hinw = vergleich_fuzzy(i, aufgabe, norm, text_antwort, ratio)
                if ok:
                    return {"richtig": True, "hinweis": hinw}

        return {"richtig": False, "hinweis": f"Leider falsch. Richtige Antwort: {aufgabe.antwort}"}

    # ---- E-TYP (Getrennte Felder) ----
    if "e" in typ:
            # Hier definieren wir den Standard-Vergleich für die Einzelbegriffe
            def e_vergleich(idx, aufg, n, o):
                return vergleich_streng(idx, aufg, n, o, case_sensitiv, True)
                
            ok, hinweis = bewerte_e_typ(typ, aufgabe, text_antwort, e_vergleich)
            return {"richtig": ok, "hinweis": hinweis}

    # ---- O/U-PARSER (Logische Verknüpfungen) ----
    # Hier wird contain=True genutzt (Teilstring-Suche)
    streng_ok, _ = bewerte_booleschen_ausdruck(
        typ, aufgabe, norm, text_antwort,
        lambda i, a, n, o: vergleich_streng(i, a, n, o, case_sensitiv, True)
    )

    if streng_ok:
        return {"richtig": True, "hinweis": "Richtig!"}

    # Wenn streng falsch, aber Fuzzy erlaubt

# ===========================================================
# PARSER
# ===========================================================

def bewerte_booleschen_ausdruck(typ, aufgabe, antwort_norm, antwort_original, vergleich):
    # 1. Tokenizer: Zerlegt den String in Einheiten (Zahlen, Operatoren, Klammern)
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

    # expr handles 'o' (lowest precedence)
    def expr():
        res_ok, res_hinweis = term()
        while peek() and peek()[0] == "o":
            eat("o")
            ok2, hinw2 = term()
            res_ok = res_ok or ok2
            # Bei ODER nehmen wir den Hinweis der ersten richtigen Komponente
            if ok2 and not res_hinweis:
                res_hinweis = hinw2
        return res_ok, res_hinweis

    # term handles 'u'
    def term():
        res_ok, res_hinweis = factor()
        while peek() and peek()[0] == "u":
            eat("u")
            ok2, hinw2 = factor()
            res_ok = res_ok and ok2
            # Bei UND sammeln wir Hinweise, falls etwas fehlt
            if hinw2:
                res_hinweis = hinw2
        return res_ok, res_hinweis

    # factor handles Parentheses and Numbers
    def factor():
        tok = peek()
        if not tok:
            return False, None
        
        if tok[0] == "(":
            eat("(")
            res = expr() # Rekursion: fängt wieder bei ODER an
            eat(")")
            return res
        
        if tok[0] == "NUM":
            num = tok[1]
            eat("NUM")
            # Führt den Vergleich (streng oder fuzzy) für die Zahl aus
            return vergleich(num, aufgabe, antwort_norm, antwort_original)
        
        return False, None

    return expr()

# ===========================================================
# BEWERTUNGSLOGIK (Die Brücke zwischen Parser und Vergleich)
# ===========================================================

def bewerte_aufgabe(aufgabe, text_antwort=None, bild_antwort=None, session=None):
    typ_roh = (aufgabe.typ or "").strip()
    norm = normalisiere(text_antwort)
    
    # Flags extrahieren
    case_sensitiv = "X" in typ_roh
    fuzzy_level = 1 if "Y" in typ_roh else 2 if "Z" in typ_roh else 0
    typ = typ_roh.replace("X", "").replace("Y", "").replace("Z", "")

    # 1. Vorab-Prüfung: f (Verbotene Begriffe)
    if "f" in typ:
        ok, hinweis = pruefe_verbotene_begriffe(aufgabe, norm, text_antwort)
        if not ok:
            return {"richtig": False, "hinweis": hinweis}

    # 2. Sonderfall: Reiner Zahlentyp (Exakter Vergleich 1 bis N)
    if typ.isdigit():
        max_idx = int(typ)
        for i in range(1, max_idx + 1):
            ok, _ = vergleich_streng(i, aufgabe, norm, text_antwort, case_sensitiv, False)
            if ok: return {"richtig": True, "hinweis": "Richtig!"}
        
        if fuzzy_level:
            r = 0.85 if fuzzy_level == 1 else 0.7
            for i in range(1, max_idx + 1):
                ok, h = vergleich_fuzzy(i, aufgabe, norm, text_antwort, r)
                if ok: return {"richtig": True, "hinweis": h}
        
        return {"richtig": False, "hinweis": f"Leider falsch. Lösung: {aufgabe.antwort}"}

    # 3. Haupt-Parser: Streng (Teilstring)
    # Wir nutzen ein Lambda, um die Vergleichs-Parameter sauber zu übergeben
    streng_ok, hinweis = bewerte_booleschen_ausdruck(
        typ, aufgabe, norm, text_antwort,
        lambda idx, aufg, n, o: vergleich_streng(idx, aufg, n, o, case_sensitiv, True)
    )

    if streng_ok:
        return {"richtig": True, "hinweis": "Richtig!"}

    # 4. Haupt-Parser: Fuzzy (Falls streng gescheitert)
    if fuzzy_level:
        ratio = 0.85 if fuzzy_level == 1 else 0.7
        fuzzy_ok, fuzzy_hinweis = bewerte_booleschen_ausdruck(
            typ, aufgabe, norm, text_antwort,
            lambda idx, aufg, n, o: vergleich_fuzzy(idx, aufg, n, o, ratio)
        )
        if fuzzy_ok:
            return {"richtig": True, "hinweis": fuzzy_hinweis}

    # 5. Finale: Wenn nichts gegriffen hat
    return {"richtig": False, "hinweis": f"Leider falsch. Lösung: {aufgabe.antwort}"}

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

