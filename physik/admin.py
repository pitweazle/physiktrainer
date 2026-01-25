from django.contrib import admin
from django import forms 
from .models import ThemenBereich, Kapitel, Aufgabe, AufgabeOption, AufgabeBild

@admin.register(ThemenBereich)
class ThemenBereichAdmin(admin.ModelAdmin):
    list_display = ("ordnung", "thema", "kurz", "eingeblendet")
    list_filter = ("eingeblendet",)
    search_fields = ("thema",)
    ordering = ("ordnung",)

@admin.register(Kapitel)
class KapitelAdmin(admin.ModelAdmin):
    list_display = ("thema", "zeile", "kapitel")
    list_filter = ("thema",)
    search_fields = ("kapitel", "thema__thema")
    ordering = ("thema__ordnung", "zeile")

class AufgabeBildInline(admin.TabularInline):
    model = AufgabeBild
    extra = 0
    can_delete = True
    verbose_name = "Bild"
    verbose_name_plural = "Bilder"
    fields = ("bild",)

class AufgabeOptionInline(admin.TabularInline):
    model = AufgabeOption
    extra = 3
    fields = ("position", "text")
    ordering = ("position",)

class AufgabeAdminForm(forms.ModelForm):
    class Meta:
        model = Aufgabe
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # alle bisher verwendeten Typen sammeln
        typen = (
            Aufgabe.objects
            .exclude(typ__isnull=True)
            .exclude(typ__exact="")
            .values_list("typ", flat=True)
            .distinct()
            .order_by("typ")
        )

        # datalist-ID setzen
        self.fields["typ"].widget.attrs.update({
            "list": "typ-vorschlaege"
        })

        # HTML für datalist erzeugen
        self.typ_datalist = list(typen)

@admin.register(Aufgabe)

class AufgabeAdmin(admin.ModelAdmin):
    form = AufgabeAdminForm
    inlines = [AufgabeOptionInline, AufgabeBildInline]  
    def get_readonly_fields(self, request, obj=None):
        if obj:   # bestehendes Objekt → bearbeiten
            return ("lfd_nr", "erstellt")
        else:     # NEUE Aufgabe → anlegen
            return ("lfd_nr", "erstellt", "von")
    list_display = ("frage", "lfd_nr", "typ", "thema", "kapitel", "schwierigkeit" )
    #list_editable = ("typ",)
    list_filter = ("thema", "kapitel", "schwierigkeit", "typ")
    search_fields = ("frage", "antwort", "typ", "anmerkung", "erklaerung", "hilfe")
    ordering = ("thema__ordnung", "kapitel__zeile", "id")
    date_hierarchy = "erstellt"

    fieldsets = (
        (None, {"fields": ("thema", "kapitel", "schwierigkeit", "typ")}),

        ("Frage", {"fields": ("frage",)}),

        ("Einheit (optional)", {
            "fields": ("einheit",),
            "classes": ("collapse",),
            "description": "Optional – wird hinter dem Eingabefeld angezeigt (z.B. cm, kg, °C).",
        }),

        ("Antwort", {"fields": ("antwort",)}),

        ("Zusatzinformationen", {
            "fields": ("anmerkung", "erklaerung", "hilfe"),
            "classes": ("collapse",),
        }),

        ("Admin", {
            "fields": ("lfd_nr","erstellt","von" ),
            "classes": ("collapse",),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.von = request.user
        super().save_model(request, obj, form, change)

from .models import FehlerLog

@admin.register(FehlerLog)
class FehlerLogAdmin(admin.ModelAdmin):
    list_display = ('zeitpunkt', 'aufgabe', 'eingegebene_antwort')
    list_filter = ('aufgabe__thema', 'zeitpunkt')
    search_fields = ('eingegebene_antwort', 'aufgabe__lfd_nr')
