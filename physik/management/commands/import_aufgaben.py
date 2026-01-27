import csv
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from physik.models import ThemenBereich, Kapitel, Aufgabe, AufgabeOption 

# HIER NEU: thema_id muss jetzt in der CSV sein
REQUIRED_COLUMNS = [
    "lfd_nr",
    "thema_id",  # <--- Neu in der Liste
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
    help = "Importiert Aufgaben aus CSV. Thema wird aus Spalte 'thema_id' gelesen."

    def add_arguments(self, parser):
        parser.add_argument("file", type=str, help="Pfad zur CSV-Datei")
        # thema-ordnung entfernt, da es jetzt in der CSV steht
        parser.add_argument("--commit", action="store_true", help="Schreibt in die DB")
        parser.add_argument("--encoding", type=str, default="utf-8", help="CSV-Encoding")
        parser.add_argument("--delimiter", type=str, default=";", help="CSV-Trennzeichen")

    def handle(self, *args, **options):
        path = options["file"]
        commit = options["commit"]
        encoding = options["encoding"]
        delimiter = options["delimiter"]

        if not os.path.exists(path):
            raise CommandError(f"Datei nicht gefunden: {path}")

        # CSV lesen
        with open(path, "r", encoding=encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = list(reader)

        if not rows:
            raise CommandError("Keine Datenzeilen gefunden.")

        # Header prüfen
        header_set = {h.strip() for h in rows[0].keys() if h}
        missing = [c for c in REQUIRED_COLUMNS if c not in header_set]
        if missing:
            raise CommandError(f"Fehlende Spalten in CSV: {missing}")

        errors = []
        warnings = []
        created_chapters = 0
        created_tasks = 0
        updated_tasks = 0
        created_options = 0

        # Caches für Performance
        thema_cache = {}
        kap_cache = {}

        @transaction.atomic
        def run():
            nonlocal created_chapters, created_tasks, updated_tasks, created_options

            for i, row in enumerate(rows, start=2):
                row_hint = f"Zeile {i}"
                lfd_nr = norm(row.get("lfd_nr"))
                
                # 1. Thema ermitteln
                t_id_raw = norm(row.get("thema_id"))
                if not t_id_raw:
                    errors.append(f"{row_hint}: thema_id fehlt")
                    continue
                
                if t_id_raw not in thema_cache:
                    try:
                        thema_cache[t_id_raw] = ThemenBereich.objects.get(ordnung=int(t_id_raw))
                    except (ThemenBereich.DoesNotExist, ValueError):
                        errors.append(f"{row_hint}: ThemenBereich mit ordnung={t_id_raw} existiert nicht.")
                        continue
                
                aktuel_thema = thema_cache[t_id_raw]

                # 2. Validierung Pflichtfelder
                frage = norm(row.get("frage"))
                zeile_raw = norm(row.get("zeile"))
                kapitel_name = norm(row.get("kapitel"))
                schwierigkeit_raw = norm(row.get("schwierigkeit"))

                if not frage or not zeile_raw or not kapitel_name or not schwierigkeit_raw:
                    errors.append(f"{row_hint} ({lfd_nr}): Pflichtfelder unvollständig")
                    continue

                try:
                    zeile = int(zeile_raw)
                    schwierigkeit = int(schwierigkeit_raw)
                except ValueError:
                    errors.append(f"{row_hint}: Zeile/Schwierigkeit keine Zahl")
                    continue

                # 3. Kapitel holen/erstellen (jetzt mit dynamischem Thema)
                kap_key = (aktuel_thema.id, zeile)
                kap = kap_cache.get(kap_key)
                if kap is None:
                    kap, created = Kapitel.objects.get_or_create(
                        thema=aktuel_thema,
                        zeile=zeile,
                        defaults={"kapitel": kapitel_name},
                    )
                    if created:
                        created_chapters += 1
                    kap_cache[kap_key] = kap

                # 4. Aufgabe upsert
                obj, created = Aufgabe.objects.update_or_create(
                    lfd_nr=lfd_nr,
                    defaults={
                        "thema": aktuel_thema,
                        "kapitel": kap,
                        "schwierigkeit": schwierigkeit,
                        "typ": norm(row.get("typ")),
                        "frage": frage,
                        "antwort": norm(row.get("antwort")),
                        "erklaerung": norm(row.get("erklaerung")),
                        "anmerkung": norm(row.get("anmerkung")),
                        "hilfe": norm(row.get("hilfe")),
                    },
                )
                if created: created_tasks += 1
                else: updated_tasks += 1

                # 5. Optionen
                AufgabeOption.objects.filter(aufgabe=obj).delete()
                for col in OPTION_COLUMNS:
                    val = norm(row.get(col))
                    if val:
                        AufgabeOption.objects.create(aufgabe=obj, position=int(col), text=val)
                        created_options += 1

            if not commit:
                raise RuntimeError("DRY_RUN_ROLLBACK")

        try:
            run()
        except RuntimeError as e:
            if str(e) != "DRY_RUN_ROLLBACK": raise

        # Zusammenfassung (gekürzt)
        self.stdout.write(self.style.MIGRATE_HEADING("\nImport abgeschlossen"))
        self.stdout.write(f"Modus: {'COMMIT' if commit else 'TROCKENLAUF'}")
        self.stdout.write(f"Aufgaben neu/update: {created_tasks}/{updated_tasks}")
        
        if errors:
            self.stdout.write(self.style.ERROR(f"\nFEHLER gefunden: {len(errors)}"))
            for err in errors[:10]: self.stdout.write(f" - {err}")