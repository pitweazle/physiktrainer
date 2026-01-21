import difflib
from difflib import SequenceMatcher

# ===========================================================
# VERGLEICHE
# ===========================================================

def vergleich_streng(index, aufgabe, antwort_norm, antwort_original, case_sensitiv):
    if index == 1:
        text = aufgabe.antwort
    else:
        opts = list(aufgabe.optionen.order_by("position"))
        if index - 1 >= len(opts):
            return False, None
        text = opts[index - 1].text


    soll = "".join((text or "").split())
    ist_norm = "".join((antwort_norm or "").split())
    ist_orig = "".join((antwort_original or "").split())

    print("------ VERGLEICH DEBUG ------")
    print(f"soll roh        : {text!r}")
    print(f"soll ohne LZ    : {soll!r}")
    print(f"ist_norm        : {ist_norm!r}")
    print(f"ist_orig        : {ist_orig!r}")
    print(f"case_sensitiv   : {case_sensitiv}")
    print("-----------------------------")

    if case_sensitiv:
        return (soll == ist_orig), None

    ok = soll.upper() in ist_norm.upper()
    return ok, None

def vergleich_fuzzy(index, aufgabe, antwort_norm, antwort_original, ratio_threshold):
    # Soll bestimmen
    if index == 1:
        text = aufgabe.antwort
    else:
        text = aufgabe.optionen.order_by("position")[index-2].text
    text = text.lstrip("$")
    soll = "".join(text.split()).lower()
    ist_raw = antwort_original or ""
    ist = "".join(ist_raw.split()).lower()
    # 1) direkter Vergleich
    if soll in ist or ist in soll:
        ratio = SequenceMatcher(None, soll, ist).ratio()
        if ratio >= ratio_threshold:
            return True, "Fast richtig – achte auf die Schreibweise."
    # 2) Wortweise prüfen
    for teil in ist_raw.split():
        teil_clean = "".join(teil.split()).lower()
        ratio = SequenceMatcher(None, soll, teil_clean).ratio()
        if ratio >= ratio_threshold:
            return True, "Fast richtig – achte auf die Schreibweise."
    return False, None

# ===========================================================
# HAUPTFUNKTION
# ===========================================================

def bewerte_aufgabe(aufgabe, text_antwort=None, bild_antwort=None, session=None):
    typ_roh = (aufgabe.typ or "").strip()
    norm = normalisiere(text_antwort)
    # --------- Flags aus Typ lesen ----------
    case_sensitiv = "X" in typ_roh
    fuzzy_level = 0
    if "Y" in typ_roh:
        fuzzy_level = 1
    if "Z" in typ_roh:
        fuzzy_level = 2
    # Parser-Typ säubern
    typ = typ_roh.replace("X", "").replace("Y", "").replace("Z", "")
    # ---------------------------------------
    # ==================================================
    # Ebene 1: Form / Sondertypen
    # ==================================================
    # Fall A: reine Bildfrage
    if typ_roh == "p":
        bild_ok = bewerte_bildauswahl(aufgabe, bild_antwort, session)
        if not bild_ok:
            return {"richtig": False, "hinweis": "Falsches Bild gewählt."}
        else:
            return {"richtig": True, "hinweis": "Richtig!"}

    # Fall B: p ist NUR Illustration → p AUS Typ entfernen
    if "p" in typ_roh:
        typ = typ_roh.replace("p", "")   # 👈 wichtig!
    else:
        typ = typ_roh

    if typ == "w":
        return bewerte_wahr_falsch(aufgabe, norm)

    if typ.startswith("l"):
        return bewerte_liste(aufgabe, norm)

    # ==================================================
    # Ebene 2: Verbotene Begriffe (f)
    # ==================================================

    if "f" in typ:
        ok, hinweis = pruefe_verbotene_begriffe(aufgabe, norm, text_antwort)
        if not ok:
            return {"richtig": False, "hinweis": hinweis}

    # ==================================================
    # Ebene 3: REINE GANZZAHL-TYPEN (z.B. 2, 3Y, 2X)
    # ==================================================

    if typ.isdigit():
        max_index = int(typ)

        # ---- 1) Streng prüfen ----
        for i in range(1, max_index + 1):
            if vergleich_streng(i, aufgabe, norm, text_antwort, case_sensitiv):
                return {"richtig": True, "hinweis": "Richtig!"}

        # ---- 2) Fuzzy NUR wenn streng falsch ----
        if fuzzy_level > 0:
            ratio_threshold = 0.85 if fuzzy_level == 1 else 0.70

            for i in range(1, max_index + 1):
                ok, hinweis = vergleich_fuzzy(
                    i, aufgabe, norm, text_antwort, ratio_threshold
                )
                if ok:
                    return {
                        "richtig": True,
                        "hinweis": (
                            "Fast richtig — bitte auf die Schreibweise achten.\n\n"
                            f"Richtige Antwort: {aufgabe.antwort}\n"
                            f"Deine Eingabe: {text_antwort}"
                        )
                    }

        return {
            "richtig": False,
            "hinweis": f"Leider falsch. Richtige Antwort: {aufgabe.antwort}"
        }
    
    if "e" in typ:
        ok, hinweis = bewerte_e_typ(
            typ, aufgabe, text_antwort, 
            lambda i, a, n, o: vergleich_streng(i, a, n, o, case_sensitiv)
        )

        if ok:
            return {"richtig": True, "hinweis": "Richtig!"}
        else:
            return {"richtig": False, "hinweis": hinweis}

    # ==================================================
    # Ebene 4: u/o-Parser (komplexe Logik)
    # ==================================================

    streng_ok, streng_hinweis = bewerte_booleschen_ausdruck(
        typ,
        aufgabe,
        norm,
        text_antwort,
        lambda i, a, n, o: vergleich_streng(i, a, n, o, case_sensitiv)
    )

    # ❗️ENTSCHEIDENDER FIX: streng gewinnt IMMER zuerst
    if streng_ok:
        return {"richtig": True, "hinweis": "Richtig!"}


    # ==================================================
    # Ebene 5: Fuzzy ALS ZWEITE CHANCE
    # ==================================================

    if fuzzy_level > 0:
        ratio_threshold = 0.85 if fuzzy_level == 1 else 0.70

        ok_fuzzy, hinweis = bewerte_booleschen_ausdruck(
            typ,
            aufgabe,
            norm,
            text_antwort,
            lambda i, a, n, o: vergleich_fuzzy(i, a, n, o, ratio_threshold)
        )


        if ok_fuzzy:
            return {
                "richtig": True,
                "hinweis": (
                    "Fast richtig — bitte auf die Schreibweise achten.\n\n"
                    f"Richtige Antwort: {aufgabe.antwort}\n"
                    f"Deine Eingabe: {text_antwort}"
                )
            }

    # ==================================================
    # Ebene 6: Endgültig falsch
    # ==================================================

    return {
        "richtig": False,
        "hinweis": f"Leider falsch. Richtige Antwort: {aufgabe.antwort}"
    }
# ===========================================================
# Dein EXISTIERENDER Parser – nur Signatur angepasst
# ===========================================================
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
        ok, hinw = parse_term()
        while peek() and peek()[0] == "o":
            eat("o")
            ok2, hinw2 = parse_term()
            ok = ok or ok2
            hinw = hinw or hinw2
        return ok, hinw

    def parse_term():
        ok, hinw = parse_factor()
        while peek() and peek()[0] == "u":
            eat("u")
            ok2, hinw2 = parse_factor()
            ok = ok and ok2
            hinw = hinw or hinw2
        return ok, hinw

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
                    return False, None

                end = int(peek()[1])
                eat("NUM")

                results = [
                    vergleich(k, aufgabe, antwort_norm, antwort_original)
                    for k in range(start, end + 1)
                ]

                if op == "o":
                    for r in results:
                        if isinstance(r, tuple) and r[0]:
                            return True, r[1]
                    return any(r if not isinstance(r, tuple) else r[0] for r in results), None

                else:  # u
                    if all(r if not isinstance(r, tuple) else r[0] for r in results):
                        return True, None
                    return False, None

            r = vergleich(start, aufgabe, antwort_norm, antwort_original)
            if isinstance(r, tuple):
                return r
            return r, None

        return False, None

    return parse_expr()


# ===========================================================
# Hilfsfunktionen
# ===========================================================

def normalisiere(text):
    if not text:
        return ""
    t = text.strip()
    return "".join(t.split())

def bewerte_bildauswahl(aufgabe, bild_antwort, session):
    if not session:
        return False
    richtiges = str(session.get("p_richtig"))
    return bild_antwort == richtiges

def bewerte_wahr_falsch(aufgabe, norm):
    """
    Akzeptierte Eingaben (case-insensitiv, Leerzeichen egal):

    WAHR:   w, wahr, ja, richtig, ok, stimmt
    FALSCH: f, falsch, nein, n, stimmt nicht
    """

    # Normalisieren der User-Eingabe
    t = (norm or "").strip().lower()

    WAHR = {"w", "wahr", "ja", "j", "richtig", "ok", "stimmt"}
    FALSCH = {"f", "falsch", "nein", "n", "stimmt nicht"}

    # Was ist die offizielle Lösung in der DB?
    loesung = (aufgabe.antwort or "").strip().lower()

    # 1) User sagt "wahr"
    if t in WAHR:
        ok = loesung in {"w", "wahr", "ja", "richtig"}
        return {
            "richtig": ok,
            "hinweis": "Richtig!" if ok else "Falsch."
        }

    # 2) User sagt "falsch"
    if t in FALSCH:
        ok = loesung in {"f", "falsch", "nein"}
        return {
            "richtig": ok,
            "hinweis": "Richtig!" if ok else "Falsch."
        }

    # 3) Alles andere → ungültige Eingabe
    return {
        "richtig": False,
        "ungueltig": True, 
        "hinweis": (
            "Bitte antworte mit: w/wahr/ja/richtig oder f/falsch/nein."
        )
    }

def bewerte_liste(aufgabe, antwort):
    """
    Bei l: genau EINE richtige Lösung = aufgabe.antwort
    Die Optionen wurden im View gemischt.
    """

    richtige = normalisiere(aufgabe.antwort)
    ausgewaehlt = normalisiere(antwort)

    ok = (ausgewaehlt == richtige)

    if ok:
        return {"richtig": True, "hinweis": "Richtig!"}
    else:
        return {
            "richtig": False,
            "hinweis": f"Leider falsch. Richtige Antwort: {aufgabe.antwort}"
        }

def bewerte_e_typ(typ, aufgabe, antwort, vergleich_funktion):
    """
    Beispiel: typ = '1o3e4o6'
    Erwartet: 'Begriff1; Begriff2' oder 'Begriff1 ... Begriff2'
    """

    if "e" not in typ:
        return False, "Interner Fehler: kein e-Typ"

    links, rechts = typ.split("e", 1)

    # -------- 1) Antwort aufteilen --------
    if ";" in antwort:
        teile = [t.strip() for t in antwort.split(";")]
    elif "..." in antwort:
        teile = [t.strip() for t in antwort.split("...")]
    else:
        return False, "Bitte zwei Begriffe mit ';' oder '...' trennen."

    if len(teile) != 2:
        return False, "Bitte GENAU zwei Begriffe angeben (getrennt durch ';' oder '...')."

    teil1, teil2 = teile

    # -------- 2) Links-Bereich prüfen --------
    ok_links, _ = bewerte_booleschen_ausdruck(
        links, aufgabe, teil1, teil1, vergleich_funktion
    )

    # -------- 3) Rechts-Bereich prüfen --------
    ok_rechts, _ = bewerte_booleschen_ausdruck(
        rechts, aufgabe, teil2, teil2, vergleich_funktion
    )

    if ok_links and ok_rechts:
        return True, None

    return False, "Mindestens einer der beiden Begriffe passt nicht."


def pruefe_verbotene_begriffe(aufgabe, norm, text_antwort):
    """
    Wertet den Teil RECHTS von 'f' aus.
    Wenn dieser Ausdruck WAHR ist → Verbot verletzt → falsch,
    UND gibt den gefundenen Begriff + ggf. Begründung zurück.
    """

    typ = (aufgabe.typ or "").strip()

    if "f" not in typ:
        return True, ""

    haupt, verbot = typ.split("f", 1)  # nur beim ERSTEN f teilen

    if not verbot:
        return True, ""

    # Prüfen, ob ein verbotener Ausdruck vorkommt
    kommt_vor, _ = bewerte_booleschen_ausdruck(
        verbot,
        aufgabe,
        norm,
        text_antwort,
        lambda i, a, n, o: vergleich_streng(i, a, n, o, False)
    )

    if not kommt_vor:
        return True, ""

    # ---------------------------------------------------------
    # Konkreten verbotenen Begriff ermitteln
    # ---------------------------------------------------------
    verbotener_begriff = None

    # Wir suchen in den f-Spalten nach dem ersten Treffer
    f_indices = []
    i = 0
    while i < len(verbot):
        if verbot[i].isdigit():
            j = i
            while j < len(verbot) and verbot[j].isdigit():
                j += 1
            f_indices.append(int(verbot[i:j]))
            i = j
        else:
            i += 1

    # Jetzt schauen wir, welcher davon wirklich in der Antwort steckt
    for k in f_indices:
        if vergleich_streng(k, aufgabe, norm, text_antwort, False):
            # Soll-Text holen
            if k == 1:
                verbotener_begriff = aufgabe.antwort
            else:
                opts = list(aufgabe.optionen.order_by("position"))
                if k - 2 < len(opts):
                    verbotener_begriff = opts[k-2].text
            break

    if not verbotener_begriff:
        verbotener_begriff = text_antwort  # Fallback
    # Begründung einbauen (falls vorhanden)
    begruendung = getattr(aufgabe, "begruendung", "").strip()
    if begruendung:
        hinweis = (
            f"Das ist hier falsch: „{verbotener_begriff}“\n\n"
            f"Begründung: {begruendung}"
        )
    else:
        hinweis = f"Das ist hier falsch: „{verbotener_begriff}“"
    return False, hinweis

