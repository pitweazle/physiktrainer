import difflib
from difflib import SequenceMatcher

def vergleich_streng(index, aufgabe, antwort_norm, antwort_original):

    # ----------- Sichere Bestimmung des Soll-Textes -----------
    if index == 1:
        text = aufgabe.antwort
    else:
        opts = list(aufgabe.optionen.order_by("position"))

        # 🔹 WICHTIGER FIX: Index prüfen
        if index - 2 >= len(opts):
            return False   # ungültiger Index → NICHT richtig

        text = opts[index-2].text
    # -----------------------------------------------------------

    case_sens = text.startswith("$")
    text = text.lstrip("$")

    soll = "".join(text.split())
    ist_norm = "".join(antwort_norm.split())
    ist_orig = "".join(antwort_original.split())

    if case_sens:
        return soll == ist_orig

    # Streng = echte Gleichheit (kein "in")
    return soll.lower() == ist_norm.lower()

def fuzzy_passend(wort_soll, wort_ist, toleranz):
    if toleranz <= 0:
        return False

    soll = "".join(wort_soll.lower().split())
    ist  = "".join(wort_ist.lower().split())

    schwelle = 0.75 if toleranz == 1 else 0.70
    return difflib.SequenceMatcher(None, soll, ist).ratio() >= schwelle

def vergleich_fuzzy(index, aufgabe, antwort_norm, antwort_original):
    text = (
        aufgabe.antwort
        if index == 1
        else aufgabe.optionen.order_by("position")[index-2].text
    )

    text = text.lstrip("$")
    soll = "".join(text.split()).lower()
    ist_raw  = antwort_original or ""
    ist      = "".join(ist_raw.split()).lower()

    # 🔹 Schwellenwert abhängig von fuzzy_toleranz
    if getattr(aufgabe, "fuzzy_toleranz", 0) == 1:
        ratio_threshold = 0.85     # normale Toleranz
    elif getattr(aufgabe, "fuzzy_toleranz", 0) >= 2:
        ratio_threshold = 0.70     # großzügige Toleranz
    else:
        ratio_threshold = 1.00     # streng = exakt gleich

    # --- 1️⃣ Harte Übereinstimmung zuerst ---
    if soll in ist or ist in soll:
        ratio = SequenceMatcher(None, soll, ist).ratio()
        if ratio >= ratio_threshold:
            return True, "Fast richtig, achte auf die richtige Schreibweise."

    # --- 2️⃣ Fuzzy-Vergleich: jedes einzelne Wort ---
    for teil in ist_raw.split():
        teil_clean = "".join(teil.split()).lower()
        ratio = SequenceMatcher(None, soll, teil_clean).ratio()
        if ratio >= ratio_threshold:
            return True, "Fast richtig, achte auf die richtige Schreibweise."

    return False, None


def bewerte_aufgabe(aufgabe, text_antwort=None, bild_antwort=None, session=None):
    typ = (aufgabe.typ or "").strip()
    norm = normalisiere(text_antwort)

    # ==============================
    # Ebene 1: Form / Sondertypen
    # ==============================

    if "p" in typ:
        if not bewerte_bildauswahl(aufgabe, bild_antwort, session):
            return {"richtig": False, "hinweis": "Falsches Bild gewählt."}

    if typ == "w":
        return bewerte_wahr_falsch(aufgabe, norm)

    if typ.startswith("l"):
        return bewerte_liste(aufgabe, norm)

    if typ.startswith("a"):
        return bewerte_multiple_choice(aufgabe, norm)

    # ==============================
    # Ebene 2: HARTE Fachlogik
    # ==============================

    if "f" in typ:
        ok, hinweis = pruefe_verbotene_begriffe(aufgabe, norm, text_antwort)
        if not ok:
            return {"richtig": False, "hinweis": hinweis}

    streng_richtig = bewerte_booleschen_ausdruck(
        typ, aufgabe, norm, text_antwort, vergleich_streng
    )
    # Wenn streng_richtig ein Tupel ist -> auspacken
    if isinstance(streng_richtig, tuple):
        streng_ok, streng_hinweis = streng_richtig
    else:
        streng_ok, streng_hinweis = streng_richtig, None

    # ==============================
    # Ebene 3: Fuzzy (tolerant richtig + Soll/Ist-Hinweis)
    # ==============================

    if not streng_ok and getattr(aufgabe, "fuzzy_toleranz", 0) > 0:
        fuzzy_richtig = bewerte_booleschen_ausdruck(
            typ, aufgabe, norm, text_antwort, vergleich_fuzzy
        )
    # 🔍 DEBUG-Ausgabe:
        print("🟡 FUZZY-ERGEBNIS:", fuzzy_richtig)
        print("Aufgabe:", aufgabe.frage)
        print("Antwort (User):", text_antwort)
        print("Typ:", typ)
        if isinstance(fuzzy_richtig, tuple):
            ok, hinweis = fuzzy_richtig
        else:
            ok, hinweis = fuzzy_richtig, None

        if ok:
            return {
                "richtig": True,
                "hinweis": (
                    hinweis
                    or "Fast richtig! Bitte beachte die Schreibweise oder kleine Details."
                ),
            }

    # ==============================
    # Falschfall
    # ==============================

    return {
        "richtig": False,
        "hinweis": f"Leider falsch. Richtige Antwort: {aufgabe.antwort}"
    }

# ===========================================================
# HILFSFUNKTIONEN (TEILWEISE IMPLEMENTIERT – ALLE EXISTIEREN)
# ===========================================================

def normalisiere(text):
    if not text:
        return ""
    t = text.strip().lower()
    return "".join(t.split())   # Leerzeichen raus

def bewerte_bildauswahl(aufgabe, bild_antwort, session):
    # Minimal: vergleicht mit gespeicherter Session-ID
    if not session:
        return False
    richtiges = str(session.get("p_richtig"))
    return bild_antwort == richtiges

def bewerte_wahr_falsch(aufgabe, norm):
    loesung = normalisiere(aufgabe.antwort)
    ok = norm == loesung
    return {
        "richtig": ok,
        "hinweis": "Richtig!" if ok else "Falsch."
    }

def bewerte_liste(aufgabe, norm):
    # Platzhalter
    return {"richtig": False, "hinweis": "Listenprüfung noch nicht implementiert."}

def bewerte_multiple_choice(aufgabe, norm):
    # Minimal: prüft nur gegen offizielle Antwort
    return {
        "richtig": norm == normalisiere(aufgabe.antwort),
        "hinweis": "Richtig!" if norm == normalisiere(aufgabe.antwort) else "Leider falsch."
    }

def pruefe_verbotene_begriffe(aufgabe, norm, text_antwort):
    """
    Wertet den Teil RECHTS von 'f' aus.
    Wenn dieser Ausdruck WAHR ist → Verbot verletzt → falsch.
    """

    typ = (aufgabe.typ or "").strip()

    if "f" not in typ:
        return True, ""

    haupt, verbot = typ.split("f", 1)  # nur beim ERSTEN f teilen

    # Falls hinter f nichts steht -> kein Verbot
    if not verbot:
        return True, ""

    # Wir nutzen DEINEN bestehenden Parser,
    # aber hier bedeutet True = VERBOTEN kommt vor!
    kommt_verbot_vor = bewerte_booleschen_ausdruck(
        verbot,
        aufgabe,
        norm,
        text_antwort,
        vergleich_streng
    )


    if kommt_verbot_vor:
        return False, "Unzulässiger Begriff in der Antwort."

    return True, ""

    # Platzhalter für f(...)
    return True, ""

def pruefe_nicht_erlaubte_begriffe(aufgabe, norm):
    # Platzhalter für n(...)
    return True, ""

def bewerte_booleschen_ausdruck(
    typ, aufgabe, antwort_norm, antwort_original, vergleich
):
    tokens = []
    i = 0
    while i < len(typ):
        c = typ[i]
        if c.isdigit():
            j = i
            while j < len(typ) and typ[j].isdigit():
                j += 1
            tokens.append(("NUM", int(typ[i:j])))
            i = j
        elif c in "ou()":
            tokens.append((c, c))
            i += 1
        else:
            i += 1

    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def eat(kind):
        nonlocal pos
        if pos < len(tokens) and tokens[pos][0] == kind:
            pos += 1

    def parse_expr():
        ok = parse_term()
        while peek() and peek()[0] == "o":
            eat("o")
            ok = ok or parse_term()
        return ok

    def parse_term():
        ok = parse_factor()
        while peek() and peek()[0] == "u":
            eat("u")
            ok = ok and parse_factor()
        return ok

    def parse_factor():
        tok = peek()

        if tok and tok[0] == "(":
            eat("(")
            val = parse_expr()
            eat(")")
            return val

        if tok and tok[0] == "NUM":
            start = tok[1]
            eat("NUM")

            if peek() and peek()[0] in ("o", "u"):
                op = peek()[0]
                eat(op)

                if not peek() or peek()[0] != "NUM":
                    return False

                end = int(peek()[1])
                eat("NUM")

                if op == "o":
                    results = [
                        vergleich(k, aufgabe, antwort_norm, antwort_original)
                        for k in range(start, end + 1)
                    ]
                    # Für Fuzzy-Funktion (Tupel) abfangen:
                    if isinstance(results[0], tuple):
                        ok_any = any(r[0] for r in results)
                        if ok_any:
                            hinweis = next(r[1] for r in results if r[0])
                            return True, hinweis
                        return False, None
                    else:
                        if isinstance(results[0], tuple):   # <-- Fuzzy-Fall
                            for ok, hinweis in results:
                                if ok:
                                    return True, hinweis
                            return False, None
                        else:
                            return any(results)

                else:  # "u"
                    results = [
                        vergleich(k, aufgabe, antwort_norm, antwort_original)
                        for k in range(start, end + 1)
                    ]
                    if isinstance(results[0], tuple):
                        ok_all = all(r[0] for r in results)
                        if ok_all:
                            hinweis = results[-1][1]
                            return True, hinweis
                        return False, None
                    else:
                        return all(results)

            res = vergleich(start, aufgabe, antwort_norm, antwort_original)
            if isinstance(res, tuple):
                return res
            return res, None

        return False, None

    result = parse_expr()
    return result if isinstance(result, tuple) else (result, None)

def einfache_textpruefung(aufgabe, norm):
    return norm == normalisiere(aufgabe.antwort)

def pruefe_fuzzy(aufgabe, norm):
    # Später: Rechtschreib-/Ähnlichkeitsprüfung
    return False

def generiere_lehrer_feedback(aufgabe, text_antwort):
    # Später: individuelle Hinweise
    return "Individuelles Feedback noch nicht implementiert."

def option_liste(aufgabe):
    """
    Baut die gedankliche Liste:
    [Antwort, Option1, Option2, ...]
    passend zu deiner Zählung:
    1 = Antwort, 2 = erste Option, ...
    """
    liste = [normalisiere(aufgabe.antwort)]
    for opt in aufgabe.optionen.order_by("position"):
        liste.append(normalisiere(opt.text))
    return liste

