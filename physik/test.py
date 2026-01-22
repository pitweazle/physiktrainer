from django.test import TestCase
from difflib import SequenceMatcher


# =============================== Hilfsklassen ===============================

class AufgabeOption:
    def __init__(self, position, text):
        self.position = position
        self.text = text


class Aufgabe:
    """Minimale Simulation des Modells, nur für Tests."""
    def __init__(self, typ, antwort, optionen):
        self.typ = typ
        self.antwort = antwort
        self.optionen = optionen
        self.fuzzy_toleranz = 1


# =============================== Funktionen ===============================

def normalisiere(text):
    return "".join((text or "").split())


def vergleich_streng(index, aufgabe, antwort_norm, antwort_original,
                     case_sensitiv=False, contain=True):
    if index == 1:
        text = aufgabe.antwort
    else:
        opts = list(sorted(aufgabe.optionen, key=lambda o: o.position))
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
            ok, _ = vergleich(tok[1], aufgabe, antwort_norm, antwort_original)
            return ok, None
        return False, None

    ergebnis, _ = expr()
    return bool(ergebnis), None


# =============================== Testklasse ===============================

# class ParserTests(TestCase):
#     def setUp(self):
#         # Dummy-Aufgabe wie deine Beispielzeile
#         def setUp(self):
#             self.aufgabe = Aufgabe(
#                 typ="3u(4o6)Y",
#                 antwort="Die Luft in der Wolle ist",
#                 optionen=[
#                     AufgabeOption(2, "xxx"),       # Index 2
#                     AufgabeOption(3, "Luft"),       # Index 2
#                     AufgabeOption(4, "mehr"),       # 3
#                     AufgabeOption(5, "isoliert"),   # 4
#                     AufgabeOption(6, "schlechter"), # 5
#                     AufgabeOption(7, "Wärmeleiter")     # 6
#                 ]
#             )
class ParserTests(TestCase):
    def setUp(self):
        # ---- Aufgabe W042 nachbauen ----
        self.a = Aufgabe.objects.create(
            lfd_nr="W042",
            themea_id=5,                      # Dummy-Thema
            kapitel_id=1,                   # Dummy-Kapitel
            schwierigkeit=1,
            typ="2o3e4o6",
            frage="... Flächen nehmen mehr Strahlung auf als ... Flächen.",
            antwort="Dunkle … helle"
        )

        # Optionen (Spalten 2–6)
        AufgabeOption.objects.create(aufgabe=self.a, position=1, text="dunkle")
        AufgabeOption.objects.create(aufgabe=self.a, position=2, text="schwarze")
        AufgabeOption.objects.create(aufgabe=self.a, position=3, text="helle")
        AufgabeOption.objects.create(aufgabe=self.a, position=4, text="weiße")
        AufgabeOption.objects.create(aufgabe=self.a, position=5, text="weisse")


    def pruefe(self, typ, text):
        ok, _ = bewerte_booleschen_ausdruck(
            typ.replace("Y", ""),       # Y entfernst du temporär
            self.aufgabe,
            normalisiere(text),
            text,
            lambda i, a, n, o: vergleich_streng(i, a, n, o, False, True),
        )
        return ok

    def test_luft_und_isoliert(self):
        self.assertTrue(self.pruefe("3u(4o6)", "Luft und isoliert"))

    def test_luft_und_schlechter(self):
        self.assertTrue(self.pruefe("3u(4o6)", "Luft und schlechter"))

    def test_nur_isoliert_falsch(self):
        self.assertFalse(self.pruefe("3u(4o6)", "isoliert"))

    def test_keine_passenden_begriffe(self):
        self.assertFalse(self.pruefe("3u(4o6)", "beschichtet"))