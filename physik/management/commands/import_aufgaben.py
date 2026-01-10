import csv
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from physik.models import ThemenBereich, Kapitel, Aufgabe, AufgabeOption  # ggf. App-Name anpassen


REQUIRED_COLUMNS = [
    "lfd_nr",
    "erklaerung",
    "anmerkung",
    "hilfe",
    "zeile",
    "kapitel",
    "schwierigkeit",
    "typ",
    "frage",
    "antwort",
]

OPTION_COLUMNS = ["2", "3", "4", "5", "6", "7", "8", "9"]


def norm(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


class Command(BaseCommand):
    help = "Importiert Aufgaben aus CSV. Standard: Trockenlauf. Mit --commit wird in die DB geschrieben."

    # ✅ WICHTIG: add_arguments muss auf Klassenebene stehen
    def add_arguments(self, parser):
        parser.add_argument("file", type=str, help="Pfad zur CSV-Datei")
        parser.add_argument("--thema-ordnung", type=int, required=True, help="ThemenBereich.ordnung (z.B. 1)")
        parser.add_argument("--commit", action="store_true", help="Schreibt in die DB (sonst Trockenlauf)")
        parser.add_argument("--encoding", type=str, default="utf-8", help="CSV-Encoding (default: utf-8)")
        parser.add_argument("--delimiter", type=str, default=";", help="CSV-Trennzeichen (default: ';')")

    def handle(self, *args, **options):
        path = options["file"]
        thema_ordnung = options["thema_ordnung"]
        commit = options["commit"]
        encoding = options["encoding"]
        delimiter = options["delimiter"]

        if not os.path.exists(path):
            raise CommandError(f"Datei nicht gefunden: {path}")

        try:
            thema = ThemenBereich.objects.get(ordnung=thema_ordnung)
        except ThemenBereich.DoesNotExist:
            raise CommandError(f"ThemenBereich mit ordnung={thema_ordnung} nicht gefunden.")

        # CSV lesen
        with open(path, "r", encoding=encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = list(reader)

        if not rows:
            raise CommandError("Keine Datenzeilen gefunden (CSV leer?).")

        # Header prüfen
        header_set = {h.strip() for h in rows[0].keys() if h}
        missing = [c for c in REQUIRED_COLUMNS if c not in header_set]
        if missing:
            raise CommandError(f"Fehlende Spalten: {missing}")
        for c in OPTION_COLUMNS:
            if c not in header_set:
                raise CommandError(f"Fehlende Options-Spalte: {c}")

        errors = []
        warnings = []

        created_chapters = 0
        created_tasks = 0
        updated_tasks = 0
        created_options = 0

        # Cache: (thema_id, zeile) -> Kapitel
        kap_cache = {}

        @transaction.atomic
        def run():
            nonlocal created_chapters, created_tasks, updated_tasks, created_options

            for i, row in enumerate(rows, start=2):  # Daten beginnen in Zeile 2
                row_hint = f"Zeile {i}"
                lfd_nr = norm(row.get("lfd_nr"))

                if not lfd_nr:
                    warnings.append(f"{row_hint}: lfd_nr leer -> übersprungen")
                    continue

                frage = norm(row.get("frage"))
                if not frage:
                    warnings.append(f"{row_hint} ({lfd_nr}): frage leer -> übersprungen")
                    continue

                # Pflichtfelder
                zeile_raw = norm(row.get("zeile"))
                kapitel_name = norm(row.get("kapitel"))
                schwierigkeit_raw = norm(row.get("schwierigkeit"))

                if not zeile_raw:
                    errors.append(f"{row_hint} ({lfd_nr}): zeile fehlt")
                    continue
                if not kapitel_name:
                    errors.append(f"{row_hint} ({lfd_nr}): kapitel fehlt")
                    continue
                if not schwierigkeit_raw:
                    errors.append(f"{row_hint} ({lfd_nr}): schwierigkeit fehlt")
                    continue

                try:
                    zeile = int(zeile_raw)
                except Exception:
                    errors.append(f"{row_hint} ({lfd_nr}): zeile ist keine Zahl: {zeile_raw!r}")
                    continue

                try:
                    schwierigkeit = int(schwierigkeit_raw)
                except Exception:
                    errors.append(f"{row_hint} ({lfd_nr}): schwierigkeit ist keine Zahl: {schwierigkeit_raw!r}")
                    continue

                if schwierigkeit not in (1, 2, 3):
                    errors.append(f"{row_hint} ({lfd_nr}): schwierigkeit muss 1/2/3 sein, ist {schwierigkeit}")
                    continue

                typ = norm(row.get("typ"))
                antwort = norm(row.get("antwort"))
                erklaerung = norm(row.get("erklaerung"))
                anmerkung = norm(row.get("anmerkung"))
                hilfe = norm(row.get("hilfe"))

                # Kapitel holen/erstellen
                kap_key = (thema.id, zeile)
                kap = kap_cache.get(kap_key)
                if kap is None:
                    kap, created = Kapitel.objects.get_or_create(
                        thema=thema,
                        zeile=zeile,
                        defaults={"kapitel": kapitel_name},
                    )
                    if created:
                        created_chapters += 1
                    else:
                        if kap.kapitel.strip() != kapitel_name.strip():
                            warnings.append(
                                f"{row_hint} ({lfd_nr}): Kapitel zeile={zeile} existiert als {kap.kapitel!r}, "
                                f"CSV hat {kapitel_name!r}"
                            )
                    kap_cache[kap_key] = kap

                # Aufgabe upsert
                obj, created = Aufgabe.objects.update_or_create(
                    lfd_nr=lfd_nr,
                    defaults={
                        "thema": thema,
                        "kapitel": kap,
                        "schwierigkeit": schwierigkeit,
                        "typ": typ,
                        "frage": frage,
                        "antwort": antwort,
                        "erklaerung": erklaerung,
                        "anmerkung": anmerkung,
                        "hilfe": hilfe,
                    },
                )
                if created:
                    created_tasks += 1
                else:
                    updated_tasks += 1

                # Optionen 2..9 neu schreiben (Antwort bleibt nur in Aufgabe.antwort)
                AufgabeOption.objects.filter(aufgabe=obj).delete()

                opt_count = 0
                for col in OPTION_COLUMNS:
                    val = norm(row.get(col))
                    if not val:
                        continue
                    AufgabeOption.objects.create(aufgabe=obj, position=int(col), text=val)
                    opt_count += 1

                created_options += opt_count

            if not commit:
                # Trockenlauf -> rollback
                raise RuntimeError("DRY_RUN_ROLLBACK")

        try:
            run()
        except RuntimeError as e:
            if str(e) != "DRY_RUN_ROLLBACK":
                raise

        # Zusammenfassung
        self.stdout.write(self.style.MIGRATE_HEADING("Import-Zusammenfassung"))
        self.stdout.write(f"Thema: {thema.ordnung} – {thema.thema}")
        self.stdout.write(f"Datei: {path}")
        self.stdout.write(f"Modus: {'COMMIT' if commit else 'TROCKENLAUF'}\n")

        self.stdout.write(f"Kapitel neu: {created_chapters}")
        self.stdout.write(f"Aufgaben neu: {created_tasks}")
        self.stdout.write(f"Aufgaben aktualisiert: {updated_tasks}")
        self.stdout.write(f"Optionen (2..9) neu: {created_options}\n")

        if warnings:
            self.stdout.write(self.style.WARNING(f"WARNUNGEN ({len(warnings)}):"))
            for w in warnings[:30]:
                self.stdout.write(f" - {w}")
            if len(warnings) > 30:
                self.stdout.write(" - ... (weitere Warnungen gekürzt)")
            self.stdout.write("")

        if errors:
            self.stdout.write(self.style.ERROR(f"FEHLER ({len(errors)}):"))
            for err in errors[:30]:
                self.stdout.write(f" - {err}")
            if len(errors) > 30:
                self.stdout.write(" - ... (weitere Fehler gekürzt)")
            if commit:
                raise CommandError("Import abgebrochen wegen Fehlern.")
        else:
            self.stdout.write(self.style.SUCCESS("Keine Fehler gefunden."))
            if not commit:
                self.stdout.write(self.style.WARNING("Trockenlauf war erfolgreich. Nutze --commit zum Schreiben in die DB."))

