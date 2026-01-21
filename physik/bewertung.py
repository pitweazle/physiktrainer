from difflib import SequenceMatcher

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

    soll = "".join((text or "").split())
    ist = "".join((antwort_original or "").split())

    if not case_sensitiv:
        soll = soll.casefold()
        ist = ist.casefold()


    return (soll in ist if contain else soll == ist), None


def vergleich_fuzzy(index, aufgabe, antwort_norm, antwort_original, ratio):
    if index == 1:
        text = aufgabe.antwort
    else:
        text = aufgabe.optionen.order_by("position")[index-2].text

    soll = "".join((text or "").split()).casefold()
    ist = "".join((antwort_original or "").split()).casefold()

    if SequenceMatcher(None, soll, ist).ratio() >= ratio:
        return True, "Fast richtig – achte auf die Schreibweise."

    if soll in ist or ist in soll:
        if SequenceMatcher(None, soll, ist).ratio() >= ratio * 0.9:
            return True, "Fast richtig – achte auf die Schreibweise."

    return False, None



# ===========================================================
# HAUPTFUNKTION
# ===========================================================

def bewerte_aufgabe(aufgabe, text_antwort=None, bild_antwort=None, session=None):
    typ_roh = (aufgabe.typ or "").strip()
    norm = normalisiere(text_antwort)

    case_sensitiv = "X" in typ_roh
    fuzzy_level = 1 if "Y" in typ_roh else 2 if "Z" in typ_roh else 0

    typ = typ_roh.replace("X", "").replace("Y", "").replace("Z", "")

    # ---- Bildtyp ----
    if typ == "p":
        ok = bewerte_bildauswahl(aufgabe, bild_antwort, session)
        return {"richtig": ok, "hinweis": "Richtig!" if ok else "Falsches Bild."}

    if typ == "w":
        return bewerte_wahr_falsch(aufgabe, norm)

    if typ.startswith("l"):
        return bewerte_liste(aufgabe, norm)

    # ---- f prüfen ----
    if "f" in typ:
        ok, hinweis = pruefe_verbotene_begriffe(aufgabe, norm, text_antwort)
        if not ok:
            return {"richtig": False, "hinweis": hinweis}

    # ---- reiner Zahlentyp ----
    if typ.isdigit():
        max_index = int(typ)

        for i in range(1, max_index + 1):
            ok, _ = vergleich_streng(
                i, aufgabe, norm, text_antwort,
                case_sensitiv, False
            )
            if ok:
                return {"richtig": True, "hinweis": "Richtig!"}

        if fuzzy_level:
            ratio = 0.85 if fuzzy_level == 1 else 0.7
            for i in range(1, max_index + 1):
                ok, hinw = vergleich_fuzzy(i, aufgabe, norm, text_antwort, ratio)
                if ok:
                    return {"richtig": True, "hinweis": hinw}

        return {"richtig": False, "hinweis": f"Leider falsch. Richtige Antwort: {aufgabe.antwort}"}

    # ---- e-Typ ----
    if "e" in typ:
        ok, hinw = bewerte_e_typ(
            typ, aufgabe, text_antwort,
            lambda i, a, n, o: vergleich_streng(i, a, n, o, case_sensitiv, True)
        )
        return {"richtig": ok, "hinweis": hinw or "Richtig!"}

    # ---- o/u-Parser ----
    streng_ok, _ = bewerte_booleschen_ausdruck(
        typ, aufgabe, norm, text_antwort,
        lambda i, a, n, o: vergleich_streng(i, a, n, o, case_sensitiv, True)
    )

    if streng_ok:
        return {"richtig": True, "hinweis": "Richtig!"}

    if fuzzy_level:
        ratio = 0.85 if fuzzy_level == 1 else 0.7
        ok, hinw = bewerte_booleschen_ausdruck(
            typ, aufgabe, norm, text_antwort,
            lambda i, a, n, o: vergleich_fuzzy(i, a, n, o, ratio)
        )
        if ok:
            return {"richtig": True, "hinweis": hinw}

    return {"richtig": False, "hinweis": f"Leider falsch. Richtige Antwort: {aufgabe.antwort}"}


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

    def expr():
        ok, _ = term()
        while peek() and peek()[0] == "o":
            eat("o")
            ok2, _ = term()
            ok = ok or ok2
        return ok, None

    def term():
        ok, _ = factor()
        while peek() and peek()[0] == "u":
            eat("u")
            ok2, _ = factor()
            ok = ok and ok2
        return ok, None

    def factor():
        tok = peek()
        if not tok:
            return False, None
        if tok[0] == "(":
            eat("(")
            ok, _ = expr()
            eat(")")
            return ok, None
        if tok[0] == "NUM":
            eat("NUM")
            return vergleich(tok[1], aufgabe, antwort_norm, antwort_original)
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
    loesung = aufgabe.antwort.lower()
    return {"richtig": norm.lower() in loesung, "hinweis": "Richtig!"}

def bewerte_liste(aufgabe, antwort):
    ok = normalisiere(antwort) == normalisiere(aufgabe.antwort)
    return {"richtig": ok, "hinweis": "Richtig!" if ok else f"Leider falsch. Richtige Antwort: {aufgabe.antwort}"}

def bewerte_e_typ(typ, aufgabe, antwort, vergleich):
    links, rechts = typ.split("e", 1)
    if ";" in antwort:
        a, b = [x.strip() for x in antwort.split(";")]
    else:
        return False, "Bitte zwei Begriffe mit ';' trennen."

    ok1, _ = bewerte_booleschen_ausdruck(links, aufgabe, a, a, vergleich)
    ok2, _ = bewerte_booleschen_ausdruck(rechts, aufgabe, b, b, vergleich)
    return ok1 and ok2, None

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

    begruendung = getattr(aufgabe, "begruendung", "").strip()
    if begruendung:
        hinweis = (
            f"Das ist hier falsch: „{verbotener_begriff}“\n\n"
            f"Begründung: {begruendung}"
        )
    else:
        hinweis = f"Das ist hier falsch: „{verbotener_begriff}“"

    return False, hinweis

