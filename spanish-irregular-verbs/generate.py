#!/usr/bin/env python3
"""Generate the standalone Spanish irregular-conjugation atlas.

The source regular chart is read only to inherit its exact CSS palette and table
grammar.  It is never modified.  Paradigms are bounded by the RAE/ASALE model
inventory; the small override layer below records only departures from the
ordinary -ar/-er/-ir recipes.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
from html import escape
from pathlib import Path
import json
import re
import unicodedata


ROOT = Path(__file__).resolve().parent
REGULAR_CHART = ROOT.parent / "spanish-conjugation-chart.html"
PERSONS = ["yo", "tú", "él/ella/Ud.", "nosotros/as", "ellos/ellas/Uds."]
COMMAND_PERSONS = ["tú", "usted", "nosotros/as", "ustedes"]

SOURCES = [
    ("RAE/ASALE · modelos e índice", "https://www.rae.es/buen-uso-español/conjugación-española"),
    ("RAE/ASALE · alternancias vocálicas", "https://www.rae.es/gramática/morfología/verbos-irregulares-ii-verbos-con-alternancia-vocálica"),
    ("RAE/ASALE · alternancias consonánticas", "https://www.rae.es/gramática/morfología/verbos-irregulares-iii-verbos-con-alternancia-consonántica-su-concurrencia-con-las-vocálicas"),
    ("RAE/ASALE · pretéritos y participios", "https://www.rae.es/gramática/morfología/verbos-irregulares-iv-pretéritos-fuertes-y-participios-irregulares"),
    ("RAE/ASALE · paradigmas especiales", "https://www.rae.es/gramática/morfología/verbos-irregulares-v-verbos-de-conjugación-especial-haber-ser-ir-estar-dar-raíces-verbales-supletivas"),
    ("Instituto Cervantes · inventario gramatical", "https://cvc.cervantes.es/Ensenanza/biblioteca_ele/plan_curricular/niveles/02_gramatica_inventario_a1-a2.htm"),
]


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def unaccent(value: str) -> str:
    # Remove acute stress only; ñ must remain ñ (its tilde is lexical, not stress).
    decomposed = unicodedata.normalize("NFD", value)
    return unicodedata.normalize("NFC", "".join(ch for ch in decomposed if ch != "\u0301"))


def verb_class(lemma: str) -> str:
    plain = unaccent(lemma.lower())
    for ending in ("ar", "er", "ir"):
        if plain.endswith(ending):
            return ending
    raise ValueError(f"No conjugation class for {lemma}")


def regular_forms(lemma: str) -> dict[str, object]:
    """Naive regular Latin-American paradigm, with only universal spelling accents."""
    cls = verb_class(lemma)
    stem = unaccent(lemma)[:-2] if lemma.endswith(("ír", "ér", "ár")) else lemma[:-2]
    future_base = unaccent(lemma)

    if cls == "ar":
        present = [stem + x for x in ("o", "as", "a", "amos", "an")]
        preterite = [stem + x for x in ("é", "aste", "ó", "amos", "aron")]
        imperfect = [stem + x for x in ("aba", "abas", "aba", "ábamos", "aban")]
        subj = [stem + x for x in ("e", "es", "e", "emos", "en")]
        gerund, participle = stem + "ando", stem + "ado"
    elif cls == "er":
        present = [stem + x for x in ("o", "es", "e", "emos", "en")]
        preterite = [stem + x for x in ("í", "iste", "ió", "imos", "ieron")]
        imperfect = [stem + x for x in ("ía", "ías", "ía", "íamos", "ían")]
        subj = [stem + x for x in ("a", "as", "a", "amos", "an")]
        gerund, participle = stem + "iendo", stem + "ido"
    else:
        present = [stem + x for x in ("o", "es", "e", "imos", "en")]
        preterite = [stem + x for x in ("í", "iste", "ió", "imos", "ieron")]
        imperfect = [stem + x for x in ("ía", "ías", "ía", "íamos", "ían")]
        subj = [stem + x for x in ("a", "as", "a", "amos", "an")]
        gerund, participle = stem + "iendo", stem + "ido"

    future = [future_base + x for x in ("é", "ás", "á", "emos", "án")]
    conditional = [future_base + x for x in ("ía", "ías", "ía", "íamos", "ían")]
    imperative = [present[2], subj[2], subj[3], subj[4]]
    result: dict[str, object] = {
        "infinitive": lemma,
        "ind_present": present,
        "ind_preterite": preterite,
        "ind_imperfect": imperfect,
        "ind_future": future,
        "ind_conditional": conditional,
        "subj_present": subj,
        "imperative": imperative,
        "gerund": gerund,
        "participle": participle,
        "marks": {},
    }
    derive_past_subjunctives(result)
    return result


def acute_final_vowel(base: str) -> str:
    replacements = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}
    if not base or base[-1] not in replacements:
        raise ValueError(f"Expected preterite base ending in a vowel: {base}")
    return base[:-1] + replacements[base[-1]]


def derive_past_subjunctives(forms: dict[str, object]) -> None:
    plural = forms["ind_preterite"][4]
    if not isinstance(plural, str) or not plural.endswith("ron"):
        raise ValueError(f"Cannot derive past subjunctive from {plural!r}")
    base = plural[:-3]
    accented = acute_final_vowel(base)
    forms["subj_ra"] = [base + "ra", base + "ras", base + "ra", accented + "ramos", base + "ran"]
    forms["subj_se"] = [base + "se", base + "ses", base + "se", accented + "semos", base + "sen"]
    forms["subj_future"] = [base + "re", base + "res", base + "re", accented + "remos", base + "ren"]


def override(
    forms: dict[str, object], key: str, values: object, reason: str,
    *, indices: list[int] | None = None, kind: str = "irregular",
) -> None:
    forms[key] = values
    marks = forms["marks"]
    if isinstance(values, list):
        chosen = range(len(values)) if indices is None else indices
        marks[key] = {str(i): {"reason": reason, "kind": kind} for i in chosen}
    else:
        marks[key] = {"value": {"reason": reason, "kind": kind}}


def mark_derived(forms: dict[str, object], reason: str, kind: str = "irregular") -> None:
    derive_past_subjunctives(forms)
    for key in ("subj_ra", "subj_se", "subj_future"):
        forms["marks"][key] = {
            str(i): {"reason": reason, "kind": kind} for i in range(5)
        }


def strong_preterite(stem: str, *, third: str | None = None, j_stem: bool = False) -> list[str]:
    return [
        stem + "e", stem + "iste", third or stem + "o", stem + "imos",
        stem + ("eron" if j_stem else "ieron"),
    ]


def future_from(stem: str) -> list[str]:
    return [stem + x for x in ("é", "ás", "á", "emos", "án")]


def conditional_from(stem: str) -> list[str]:
    return [stem + x for x in ("ía", "ías", "ía", "íamos", "ían")]


@dataclass(frozen=True)
class Family:
    number: int
    lemma: str
    slug: str
    title: str
    category: str
    signature: str
    members: tuple[str, ...]
    note: str = ""
    keys: tuple[tuple[str, str], ...] = ()

    @property
    def filename(self) -> str:
        return f"{self.number:02d}-{self.slug}.html"


FAMILIES = [
    Family(4, "acertar", "acertar", "e → ie · presente", "Alternancias vocálicas", "aciert- / acert-", ("acertar", "pensar", "cerrar", "empezar", "despertar", "negar", "recomendar", "regar", "tropezar")),
    Family(5, "actuar", "actuar", "hiato en -uar", "Acentuación vocálica", "actú- / actu-", ("actuar", "acentuar", "continuar", "efectuar", "evaluar", "graduar", "habituar", "perpetuar", "puntuar", "situar")),
    Family(7, "adquirir", "adquirir", "i → ie · presente", "Alternancias vocálicas", "adquier- / adquir-", ("adquirir", "inquirir")),
    Family(8, "agradecer", "agradecer", "-ecer → -ezc-", "Presente especial", "agradezc- / agradec-", ("agradecer", "aparecer", "carecer", "conocer", "crecer", "merecer", "nacer", "obedecer", "ofrecer", "parecer", "permanecer", "pertenecer"), "Mecer y remecer no insertan -zc-."),
    Family(9, "aislar", "aislar", "ai → aí · raíz tónica", "Acentuación vocálica", "aísl- / aisl-", ("aislar", "airar", "enraizar")),
    Family(10, "andar", "andar", "pretérito anduv-", "Pretéritos fuertes", "anduv-", ("andar", "desandar")),
    Family(13, "asir", "asir", "yo/subjuntivo asg-", "Presente especial", "asg- / as-", ("asir", "desasir")),
    Family(14, "aunar", "aunar", "au → aú · raíz tónica", "Acentuación vocálica", "aún- / aun-", ("aunar", "ahumar", "aullar", "aupar", "maullar")),
    Family(17, "bendecir", "bendecir", "bendigo · bendije", "Familias mixtas", "bendig- / bendij-", ("bendecir", "maldecir"), "Mantienen futuro y condicional completos: bendeciré, maldeciría."),
    Family(18, "caber", "caber", "quep- · cup- · cabr-", "Familias mixtas", "quep- / cup- / cabr-", ("caber",)),
    Family(19, "caer", "caer", "caig- · cay-", "Presente y gerundio", "caig- / cay- / ca-", ("caer", "decaer", "recaer")),
    Family(21, "ceñir", "ceñir", "e → i · formas de pretérito", "Alternancias vocálicas", "ciñ- / ceñ-", ("ceñir", "constreñir", "estreñir", "reñir", "teñir")),
    Family(23, "conducir", "conducir", "-duzc- · -duj-", "Familias mixtas", "conduzc- / conduj- / conduc-", ("conducir", "aducir", "deducir", "inducir", "introducir", "producir", "reducir", "reproducir", "seducir", "traducir")),
    Family(24, "construir", "construir", "-uir → y", "Presente y gerundio", "construy- / constru-", ("construir", "atribuir", "concluir", "constituir", "destruir", "diluir", "disminuir", "fluir", "huir", "incluir", "instituir", "obstruir", "restituir", "sustituir")),
    Family(25, "contar", "contar", "o → ue · presente", "Alternancias vocálicas", "cuent- / cont-", ("contar", "acordar", "almorzar", "aprobar", "encontrar", "mostrar", "probar", "recordar", "rodar", "soñar", "volar", "volcar")),
    Family(26, "dar", "dar", "doy · dé · di/die-", "Paradigmas especiales", "doy / dé / di- / die-", ("dar",)),
    Family(27, "decir", "decir", "dig- · dij- · dir- · dicho", "Familias mixtas", "dig- / dij- / dir-", ("decir",), "Los compuestos con otra firma completa se separan en bendecir y predecir."),
    Family(28, "descafeinar", "descafeinar", "ei → eí · raíz tónica", "Acentuación vocálica", "descafeín- / descafein-", ("descafeinar", "cafeinar")),
    Family(29, "discernir", "discernir", "e → ie · solo presente", "Alternancias vocálicas", "disciern- / discern-", ("discernir", "cernir", "hendir")),
    Family(30, "dormir", "dormir", "o → ue / u", "Alternancias vocálicas", "duerm- / durm- / dorm-", ("dormir",)),
    Family(31, "entender", "entender", "e → ie · presente", "Alternancias vocálicas", "entiend- / entend-", ("entender", "ascender", "atender", "defender", "descender", "encender", "extender", "perder", "tender", "trascender", "verter")),
    Family(32, "enviar", "enviar", "ia → ía · raíz tónica", "Acentuación vocálica", "enví- / envi-", ("enviar", "aliar", "confiar", "criar", "desviar", "enfriar", "espiar", "fiar", "guiar", "liar", "rociar", "vaciar", "variar")),
    Family(33, "erguir", "erguir", "yerg- · irg-", "Familias mixtas", "yerg- / irg- / ergu-", ("erguir",), "La norma admite las series yerg- e irg-; la tabla muestra ambas."),
    Family(34, "errar", "errar", "err- → yerr-", "Presente especial", "yerr- / err-", ("errar",), "En América se admite también la conjugación regular: erro, erras, erra; erre; erra."),
    Family(35, "estar", "estar", "estoy · esté · estuv-", "Paradigmas especiales", "estoy / est- / estuv-", ("estar",), "El imperativo de tú está se usa solo con pronombre: estate."),
    Family(36, "haber", "haber", "he/hay · hay- · hub- · habr-", "Paradigmas especiales", "he/ha- / hay- / hub- / habr-", ("haber",)),
    Family(37, "hacer", "hacer", "hag- · hic-/hiz- · har- · hecho", "Familias mixtas", "hag- / hic- / hiz- / har-", ("hacer", "contrahacer", "deshacer", "rehacer")),
    Family(38, "ir", "ir", "voy · ib- · fu- · vay- · yendo", "Paradigmas especiales", "formas supletivas", ("ir",)),
    Family(39, "jugar", "jugar", "u → ue · presente", "Alternancias vocálicas", "jueg- / jug-", ("jugar",)),
    Family(40, "leer", "leer", "vocal + y", "Presente y gerundio", "le- / ley-", ("leer", "creer", "poseer", "sobreseer")),
    Family(41, "lucir", "lucir", "yo/subjuntivo luzc-", "Presente especial", "luzc- / luc-", ("lucir", "deslucir", "enlucir", "relucir", "traslucir")),
    Family(42, "mover", "mover", "o → ue · presente", "Alternancias vocálicas", "muev- / mov-", ("mover", "cocer", "conmover", "demoler", "doler", "llover", "moler", "morder", "promover", "torcer")),
    Family(43, "mullir", "mullir", "pérdida de i tras ll/ñ", "Ajustes fonológicos", "mull-", ("mullir", "bullir", "bruñir", "engullir", "escabullir", "tullir", "zambullir")),
    Family(44, "oír", "oir", "oig- · oy- · oí-", "Familias mixtas", "oig- / oy- / oí-", ("oír", "desoír", "entreoír", "trasoír")),
    Family(45, "oler", "oler", "ol- → huel-", "Alternancias vocálicas", "huel- / ol-", ("oler",)),
    Family(46, "pedir", "pedir", "e → i", "Alternancias vocálicas", "pid- / ped-", ("pedir", "competir", "conseguir", "corregir", "despedir", "impedir", "medir", "perseguir", "regir", "rendir", "repetir", "seguir", "servir", "vestir")),
    Family(48, "poder", "poder", "pued- · pud- · podr-", "Familias mixtas", "pued- / pud- / podr-", ("poder",)),
    Family(49, "poner", "poner", "pong- · pus- · pondr- · puesto", "Familias mixtas", "pong- / pus- / pondr-", ("poner", "componer", "disponer", "exponer", "imponer", "oponer", "posponer", "proponer", "reponer", "suponer")),
    Family(50, "predecir", "predecir", "predig- · predij- · futuro doble", "Familias mixtas", "predig- / predij- / predecir-~predir-", ("predecir", "condecir", "contradecir", "desdecir")),
    Family(51, "prohibir", "prohibir", "oi → oí · raíz tónica", "Acentuación vocálica", "prohíb- / prohib-", ("prohibir", "cohibir")),
    Family(52, "prohijar", "prohijar", "oi → oí · raíz tónica", "Acentuación vocálica", "prohíj- / prohij-", ("prohijar",)),
    Family(53, "pudrir", "pudrir", "pudr- / podr-", "Variantes de paradigma", "pudr- / podr-", ("pudrir", "podrir"), "Pudrir es la variante general. Podrir sigue admitido; sus variantes finitas con podr- se documentan principalmente en áreas de América."),
    Family(54, "querer", "querer", "quier- · quis- · querr-", "Familias mixtas", "quier- / quis- / querr-", ("querer",), "El imperativo afirmativo es poco frecuente fuera de usos fijados."),
    Family(55, "rehusar", "rehusar", "eu → eú · raíz tónica", "Acentuación vocálica", "rehús- / rehus-", ("rehusar", "reuntar")),
    Family(56, "reunir", "reunir", "eu → eú · raíz tónica", "Acentuación vocálica", "reún- / reun-", ("reunir",)),
    Family(57, "roer", "roer", "roo / roigo / royo", "Variantes de paradigma", "ro- / roig- / roy-", ("roer", "corroer")),
    Family(58, "saber", "saber", "sé · sep- · sup- · sabr-", "Familias mixtas", "sé / sep- / sup- / sabr-", ("saber", "resaber")),
    Family(59, "salir", "salir", "salg- · saldr- · sal", "Familias mixtas", "salg- / saldr- / sal-", ("salir", "resalir", "sobresalir")),
    Family(60, "sentir", "sentir", "e → ie / i", "Alternancias vocálicas", "sient- / sint- / sent-", ("sentir", "adherir", "advertir", "asentir", "consentir", "convertir", "diferir", "divertir", "herir", "hervir", "mentir", "preferir", "referir", "sugerir")),
    Family(61, "ser", "ser", "soy · er- · se- · fu-", "Paradigmas especiales", "formas supletivas", ("ser",)),
    Family(62, "sonreír", "sonreir", "e → i · hiato", "Familias mixtas", "sonrí- / sonri- / sonre-", ("sonreír", "reír", "desleír", "engreír")),
    Family(63, "tañer", "taner", "pérdida de i tras ñ", "Ajustes fonológicos", "tañ-", ("tañer", "atañer"), "Atañer es defectivo y se usa sobre todo en terceras personas."),
    Family(64, "tener", "tener", "teng- · tien- · tuv- · tendr- · ten", "Familias mixtas", "teng- / tien- / tuv- / tendr-", ("tener", "abstener", "atener", "contener", "detener", "entretener", "mantener", "obtener", "retener", "sostener")),
    Family(65, "traer", "traer", "traig- · traj- · tray-", "Familias mixtas", "traig- / traj- / tray-", ("traer", "abstraer", "atraer", "contraer", "detraer", "distraer", "extraer", "retraer", "sustraer")),
    Family(66, "valer", "valer", "valg- · valdr-", "Familias mixtas", "valg- / valdr- / val-", ("valer", "equivaler", "revaler"), "Revaler es un derivado gramaticalmente registrado, pero de uso extremadamente raro y ausente del índice actual del DLE."),
    Family(67, "venir", "venir", "veng- · vien- · vin- · vendr- · ven", "Familias mixtas", "veng- / vien- / vin- / vendr-", ("venir", "advenir", "convenir", "devenir", "intervenir", "prevenir", "provenir", "reconvenir", "sobrevenir")),
    Family(68, "ver", "ver", "ve- · vi- · visto", "Paradigmas especiales", "ve- / vi-", ("ver", "antever", "entrever", "prever", "rever"), "Proveer no pertenece a esta familia."),
    Family(69, "yacer", "yacer", "yazc- / yazg- / yag-", "Variantes de paradigma", "yazc- / yazg- / yag- / yac-", ("yacer", "subyacer")),
    Family(70, "abrir", "abrir", "participio abierto", "Participios irregulares", "abr- / abierto", ("abrir", "entreabrir", "reabrir")),
    Family(71, "cubrir", "cubrir", "participio cubierto", "Participios irregulares", "cubr- / cubierto", ("cubrir", "descubrir", "encubrir", "recubrir", "redescubrir")),
    Family(72, "escribir", "escribir", "participio escrito", "Participios irregulares", "escrib- / escrito", ("escribir", "adscribir", "circunscribir", "describir", "inscribir", "prescribir", "suscribir", "transcribir"), "En Argentina, Uruguay y Paraguay, los derivados —no escribir— admiten también participios en -scripto (descripto, inscripto…), incluso en tiempos compuestos."),
    Family(73, "romper", "romper", "participio roto", "Participios irregulares", "romp- / roto", ("romper",)),
    Family(74, "imprimir", "imprimir", "participios imprimido / impreso", "Participios irregulares", "imprim- / imprimido~impreso", ("imprimir",), "Imprimido e impreso son participios válidos; ambos aparecen en tiempos compuestos."),
    Family(75, "morir", "morir", "o → ue / u · muerto", "Familias mixtas", "muer- / mur- / mor- / muerto", ("morir",)),
    Family(76, "volver", "volver", "o → ue · vuelto", "Familias mixtas", "vuelv- / volv- / vuelto", ("volver", "devolver", "desenvolver", "envolver", "revolver")),
    Family(77, "resolver", "resolver", "o → ue · resuelto", "Familias mixtas", "resuelv- / resolv- / resuelto", ("resolver", "absolver", "disolver")),
    Family(78, "freír", "freir", "e → i · freído / frito", "Familias mixtas", "frí- / fri- / fre- / frito", ("freír", "refreír", "sofreír"), "Freído y frito son participios válidos; ambos se usan en tiempos compuestos."),
    Family(79, "proveer", "proveer", "vocal + y · proveído / provisto", "Familias mixtas", "prove- / provey- / provisto", ("proveer",), "Proveído y provisto son participios válidos."),
    Family(80, "elegir", "elegir", "e → i · elegido / electo", "Familias mixtas", "elij- / elig- / eleg- / electo", ("elegir", "reelegir"), "Electo funciona también como adjetivo; su uso como participio verbal varía regionalmente."),
    Family(81, "satisfacer", "satisfacer", "satisfag- · satisfic-/satisfiz- · satisfar-", "Familias mixtas", "satisfag- / satisfic- / satisfiz- / satisfar-", ("satisfacer",), "El imperativo de tú admite satisface y satisfaz."),
]


EXCLUDED_CONTROLS = {
    6: "adeudar", 11: "anunciar", 12: "aplaudir", 15: "averiguar",
    16: "bailar", 20: "causar", 22: "coitar", 47: "peinar",
}


def set_marks(
    forms: dict[str, object], key: str, indices: list[int], reason: str,
    kind: str = "irregular",
) -> None:
    forms["marks"].setdefault(key, {})
    for index in indices:
        forms["marks"][key][str(index)] = {"reason": reason, "kind": kind}


def set_value_mark(forms: dict[str, object], key: str, reason: str, kind: str = "irregular") -> None:
    forms["marks"][key] = {"value": {"reason": reason, "kind": kind}}


def variants(*items: tuple[str, str | None, str | None]) -> list[dict[str, str | None]]:
    """Create independently styled accepted alternatives.

    Each item is (text, kind, reason); kind is None for the regular alternative.
    """
    return [{"text": text, "kind": kind, "reason": reason} for text, kind, reason in items]


def paradigm(family: Family) -> dict[str, object]:
    """Return the RAE model paradigm for one family representative."""
    n = family.number
    f = regular_forms(family.lemma)

    if n == 4:
        override(f, "ind_present", ["acierto", "aciertas", "acierta", "acertamos", "aciertan"], "e → ie", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["acierte", "aciertes", "acierte", "acertemos", "acierten"], "e → ie", indices=[0, 1, 2, 4])
    elif n == 5:
        override(f, "ind_present", ["actúo", "actúas", "actúa", "actuamos", "actúan"], "hiato léxico ú-o/ú-a", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["actúe", "actúes", "actúe", "actuemos", "actúen"], "hiato léxico ú-e", indices=[0, 1, 2, 4])
    elif n == 7:
        override(f, "ind_present", ["adquiero", "adquieres", "adquiere", "adquirimos", "adquieren"], "i → ie", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["adquiera", "adquieras", "adquiera", "adquiramos", "adquieran"], "i → ie", indices=[0, 1, 2, 4])
    elif n == 8:
        override(f, "ind_present", ["agradezco", "agradeces", "agradece", "agradecemos", "agradecen"], "inserción -zc-", indices=[0])
        override(f, "subj_present", ["agradezca", "agradezcas", "agradezca", "agradezcamos", "agradezcan"], "inserción -zc-")
    elif n == 9:
        override(f, "ind_present", ["aíslo", "aíslas", "aísla", "aislamos", "aíslan"], "hiato léxico aí", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["aísle", "aísles", "aísle", "aislemos", "aíslen"], "hiato léxico aí", indices=[0, 1, 2, 4])
    elif n == 10:
        override(f, "ind_preterite", strong_preterite("anduv"), "pretérito fuerte anduv-")
        mark_derived(f, "tema de pretérito anduv-")
    elif n == 13:
        override(f, "ind_present", ["asgo", "ases", "ase", "asimos", "asen"], "inserción de g", indices=[0])
        override(f, "subj_present", ["asga", "asgas", "asga", "asgamos", "asgan"], "tema asg-")
    elif n == 14:
        override(f, "ind_present", ["aúno", "aúnas", "aúna", "aunamos", "aúnan"], "hiato léxico aú", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["aúne", "aúnes", "aúne", "aunemos", "aúnen"], "hiato léxico aú", indices=[0, 1, 2, 4])
    elif n == 17:
        override(f, "ind_present", ["bendigo", "bendices", "bendice", "bendecimos", "bendicen"], "temas dig-/dic-", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite("bendij", j_stem=True), "pretérito fuerte dij-")
        override(f, "subj_present", ["bendiga", "bendigas", "bendiga", "bendigamos", "bendigan"], "tema dig-")
        override(f, "gerund", "bendiciendo", "e → i en gerundio")
        mark_derived(f, "tema de pretérito bendij-")
    elif n == 18:
        override(f, "ind_present", ["quepo", "cabes", "cabe", "cabemos", "caben"], "forma quepo", indices=[0])
        override(f, "ind_preterite", strong_preterite("cup"), "pretérito fuerte cup-")
        override(f, "ind_future", future_from("cabr"), "futuro sincopado cabr-")
        override(f, "ind_conditional", conditional_from("cabr"), "condicional sincopado cabr-")
        override(f, "subj_present", ["quepa", "quepas", "quepa", "quepamos", "quepan"], "tema quep-")
        mark_derived(f, "tema de pretérito cup-")
    elif n == 19:
        override(f, "ind_present", ["caigo", "caes", "cae", "caemos", "caen"], "tema caig-", indices=[0])
        override(f, "ind_preterite", ["caí", "caíste", "cayó", "caímos", "cayeron"], "i → y entre vocales", indices=[2, 4], kind="orthographic")
        override(f, "subj_present", ["caiga", "caigas", "caiga", "caigamos", "caigan"], "tema caig-")
        override(f, "gerund", "cayendo", "i → y entre vocales", kind="orthographic")
        override(f, "participle", "caído", "tilde de hiato", kind="orthographic")
        mark_derived(f, "i → y entre vocales", "orthographic")
    elif n == 21:
        override(f, "ind_present", ["ciño", "ciñes", "ciñe", "ceñimos", "ciñen"], "e → i", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", ["ceñí", "ceñiste", "ciñó", "ceñimos", "ciñeron"], "e → i", indices=[2, 4])
        override(f, "subj_present", ["ciña", "ciñas", "ciña", "ciñamos", "ciñan"], "e → i")
        override(f, "gerund", "ciñendo", "e → i")
        mark_derived(f, "tema de pretérito ciñ-")
    elif n == 23:
        override(f, "ind_present", ["conduzco", "conduces", "conduce", "conducimos", "conducen"], "tema -duzc-", indices=[0])
        override(f, "ind_preterite", strong_preterite("conduj", j_stem=True), "pretérito fuerte -duj-")
        override(f, "subj_present", ["conduzca", "conduzcas", "conduzca", "conduzcamos", "conduzcan"], "tema -duzc-")
        mark_derived(f, "tema de pretérito conduj-")
    elif n == 24:
        override(f, "ind_present", ["construyo", "construyes", "construye", "construimos", "construyen"], "i → y entre vocales", indices=[0, 1, 2, 4], kind="orthographic")
        override(f, "ind_preterite", ["construí", "construiste", "construyó", "construimos", "construyeron"], "i → y entre vocales", indices=[2, 4], kind="orthographic")
        override(f, "subj_present", ["construya", "construyas", "construya", "construyamos", "construyan"], "i → y entre vocales", kind="orthographic")
        override(f, "gerund", "construyendo", "i → y entre vocales", kind="orthographic")
        mark_derived(f, "i → y entre vocales", "orthographic")
    elif n == 25:
        override(f, "ind_present", ["cuento", "cuentas", "cuenta", "contamos", "cuentan"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["cuente", "cuentes", "cuente", "contemos", "cuenten"], "o → ue", indices=[0, 1, 2, 4])
    elif n == 26:
        override(f, "ind_present", ["doy", "das", "da", "damos", "dan"], "forma doy", indices=[0])
        override(f, "ind_preterite", ["di", "diste", "dio", "dimos", "dieron"], "pretérito propio di-/die-")
        override(f, "subj_present", ["dé", "des", "dé", "demos", "den"], "subjuntivo propio dé", indices=[0, 2])
        mark_derived(f, "tema de pretérito die-")
    elif n == 27:
        override(f, "ind_present", ["digo", "dices", "dice", "decimos", "dicen"], "temas dig-/dic-", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite("dij", j_stem=True), "pretérito fuerte dij-")
        override(f, "ind_future", future_from("dir"), "futuro sincopado dir-")
        override(f, "ind_conditional", conditional_from("dir"), "condicional sincopado dir-")
        override(f, "subj_present", ["diga", "digas", "diga", "digamos", "digan"], "tema dig-")
        override(f, "gerund", "diciendo", "tema dici-")
        override(f, "participle", "dicho", "participio irregular dicho")
        mark_derived(f, "tema de pretérito dij-")
    elif n == 28:
        override(f, "ind_present", ["descafeíno", "descafeínas", "descafeína", "descafeinamos", "descafeínan"], "hiato léxico eí", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["descafeíne", "descafeínes", "descafeíne", "descafeinemos", "descafeínen"], "hiato léxico eí", indices=[0, 1, 2, 4])
    elif n == 29:
        override(f, "ind_present", ["discierno", "disciernes", "discierne", "discernimos", "disciernen"], "e → ie", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["discierna", "disciernas", "discierna", "discernamos", "disciernan"], "e → ie", indices=[0, 1, 2, 4])
    elif n == 30:
        override(f, "ind_present", ["duermo", "duermes", "duerme", "dormimos", "duermen"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", ["dormí", "dormiste", "durmió", "dormimos", "durmieron"], "o → u", indices=[2, 4])
        override(f, "subj_present", ["duerma", "duermas", "duerma", "durmamos", "duerman"], "o → ue/u")
        override(f, "gerund", "durmiendo", "o → u")
        mark_derived(f, "tema de pretérito durm-")
    elif n == 31:
        override(f, "ind_present", ["entiendo", "entiendes", "entiende", "entendemos", "entienden"], "e → ie", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["entienda", "entiendas", "entienda", "entendamos", "entiendan"], "e → ie", indices=[0, 1, 2, 4])
    elif n == 32:
        override(f, "ind_present", ["envío", "envías", "envía", "enviamos", "envían"], "hiato léxico ía", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["envíe", "envíes", "envíe", "enviemos", "envíen"], "hiato léxico íe", indices=[0, 1, 2, 4])
    elif n == 33:
        f["ind_present"] = [
            variants(("yergo", "irregular", "variante yerg-"), ("irgo", "irregular", "variante irg-")),
            variants(("yergues", "irregular", "variante yerg-"), ("irgues", "irregular", "variante irg-")),
            variants(("yergue", "irregular", "variante yerg-"), ("irgue", "irregular", "variante irg-")),
            "erguimos",
            variants(("yerguen", "irregular", "variante yerg-"), ("irguen", "irregular", "variante irg-")),
        ]
        override(f, "ind_preterite", ["erguí", "erguiste", "irguió", "erguimos", "irguieron"], "e → i", indices=[2, 4])
        f["subj_present"] = [
            variants(("yerga", "irregular", "variante yerg-"), ("irga", "irregular", "variante irg-")),
            variants(("yergas", "irregular", "variante yerg-"), ("irgas", "irregular", "variante irg-")),
            variants(("yerga", "irregular", "variante yerg-"), ("irga", "irregular", "variante irg-")),
            variants(("yergamos", "irregular", "variante yerg-"), ("irgamos", "irregular", "variante irg-")),
            variants(("yergan", "irregular", "variante yerg-"), ("irgan", "irregular", "variante irg-")),
        ]
        override(f, "gerund", "irguiendo", "e → i")
        mark_derived(f, "tema de pretérito irgu-")
    elif n == 34:
        f["ind_present"] = [
            variants(("yerro", "irregular", "tema yerr-"), ("erro", None, None)),
            variants(("yerras", "irregular", "tema yerr-"), ("erras", None, None)),
            variants(("yerra", "irregular", "tema yerr-"), ("erra", None, None)),
            "erramos",
            variants(("yerran", "irregular", "tema yerr-"), ("erran", None, None)),
        ]
        f["subj_present"] = [
            variants(("yerre", "irregular", "tema yerr-"), ("erre", None, None)),
            variants(("yerres", "irregular", "tema yerr-"), ("erres", None, None)),
            variants(("yerre", "irregular", "tema yerr-"), ("erre", None, None)),
            "erremos",
            variants(("yerren", "irregular", "tema yerr-"), ("erren", None, None)),
        ]
    elif n == 35:
        override(f, "ind_present", ["estoy", "estás", "está", "estamos", "están"], "presente propio", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite("estuv"), "pretérito fuerte estuv-")
        override(f, "subj_present", ["esté", "estés", "esté", "estemos", "estén"], "subjuntivo esté", indices=[0, 1, 2, 4])
        mark_derived(f, "tema de pretérito estuv-")
    elif n == 36:
        override(f, "ind_present", ["he", "has", "ha · impersonal: hay", "hemos", "han"], "presente propio")
        override(f, "ind_preterite", strong_preterite("hub"), "pretérito fuerte hub-")
        override(f, "ind_future", future_from("habr"), "futuro sincopado habr-")
        override(f, "ind_conditional", conditional_from("habr"), "condicional sincopado habr-")
        override(f, "subj_present", ["haya", "hayas", "haya", "hayamos", "hayan"], "subjuntivo hay-")
        override(f, "imperative", ["he / habe", "haya", "hayamos", "hayan"], "imperativo propio")
        mark_derived(f, "tema de pretérito hub-")
    elif n == 37:
        override(f, "ind_present", ["hago", "haces", "hace", "hacemos", "hacen"], "tema hag-", indices=[0])
        override(f, "ind_preterite", ["hice", "hiciste", "hizo", "hicimos", "hicieron"], "pretérito fuerte hic-/hiz-")
        override(f, "ind_future", future_from("har"), "futuro sincopado har-")
        override(f, "ind_conditional", conditional_from("har"), "condicional sincopado har-")
        override(f, "subj_present", ["haga", "hagas", "haga", "hagamos", "hagan"], "tema hag-")
        override(f, "participle", "hecho", "participio irregular hecho")
        mark_derived(f, "tema de pretérito hic-")
    elif n == 38:
        override(f, "ind_present", ["voy", "vas", "va", "vamos", "van"], "presente supletivo")
        override(f, "ind_imperfect", ["iba", "ibas", "iba", "íbamos", "iban"], "imperfecto ib-")
        override(f, "ind_preterite", ["fui", "fuiste", "fue", "fuimos", "fueron"], "pretérito supletivo fu-")
        override(f, "subj_present", ["vaya", "vayas", "vaya", "vayamos", "vayan"], "subjuntivo vay-")
        override(f, "gerund", "yendo", "gerundio yendo")
        override(f, "imperative", ["ve", "vaya", variants(("vayamos", "irregular", "imperativo vayamos"), ("vamos", "irregular", "variante exhortativa vamos")), "vayan"], "imperativo propio")
        mark_derived(f, "tema de pretérito fu-")
    elif n == 39:
        override(f, "ind_present", ["juego", "juegas", "juega", "jugamos", "juegan"], "u → ue", indices=[0, 1, 2, 4])
        f["ind_preterite"][0] = "jugué"
        set_marks(f, "ind_preterite", [0], "g → gu ante e", "orthographic")
        override(f, "subj_present", ["juegue", "juegues", "juegue", "juguemos", "jueguen"], "u → ue", indices=[0, 1, 2, 4])
        set_marks(f, "subj_present", [0, 1, 2, 4], "u → ue; g → gu ante e")
        set_marks(f, "subj_present", [3], "g → gu ante e", "orthographic")
    elif n == 40:
        override(f, "ind_preterite", ["leí", "leíste", "leyó", "leímos", "leyeron"], "i → y entre vocales", indices=[2, 4], kind="orthographic")
        override(f, "gerund", "leyendo", "i → y entre vocales", kind="orthographic")
        override(f, "participle", "leído", "tilde de hiato", kind="orthographic")
        mark_derived(f, "i → y entre vocales", "orthographic")
    elif n == 41:
        override(f, "ind_present", ["luzco", "luces", "luce", "lucimos", "lucen"], "tema luzc-", indices=[0])
        override(f, "subj_present", ["luzca", "luzcas", "luzca", "luzcamos", "luzcan"], "tema luzc-")
    elif n == 42:
        override(f, "ind_present", ["muevo", "mueves", "mueve", "movemos", "mueven"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["mueva", "muevas", "mueva", "movamos", "muevan"], "o → ue", indices=[0, 1, 2, 4])
    elif n == 43:
        override(f, "ind_preterite", ["mullí", "mulliste", "mulló", "mullimos", "mulleron"], "pérdida regular de i tras ll", indices=[2, 4], kind="orthographic")
        override(f, "gerund", "mullendo", "pérdida regular de i tras ll", kind="orthographic")
        mark_derived(f, "pérdida de i tras ll", "orthographic")
    elif n == 44:
        f["ind_present"] = ["oigo", "oyes", "oye", "oímos", "oyen"]
        set_marks(f, "ind_present", [0], "tema oig-")
        set_marks(f, "ind_present", [1, 2, 4], "i → y entre vocales", "orthographic")
        override(f, "ind_preterite", ["oí", "oíste", "oyó", "oímos", "oyeron"], "i → y entre vocales", indices=[2, 4], kind="orthographic")
        override(f, "subj_present", ["oiga", "oigas", "oiga", "oigamos", "oigan"], "tema oig-")
        override(f, "gerund", "oyendo", "i → y entre vocales", kind="orthographic")
        override(f, "participle", "oído", "tilde de hiato", kind="orthographic")
        mark_derived(f, "i → y entre vocales", "orthographic")
    elif n == 45:
        override(f, "ind_present", ["huelo", "hueles", "huele", "olemos", "huelen"], "o → hue", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["huela", "huelas", "huela", "olamos", "huelan"], "o → hue", indices=[0, 1, 2, 4])
    elif n == 46:
        override(f, "ind_present", ["pido", "pides", "pide", "pedimos", "piden"], "e → i", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", ["pedí", "pediste", "pidió", "pedimos", "pidieron"], "e → i", indices=[2, 4])
        override(f, "subj_present", ["pida", "pidas", "pida", "pidamos", "pidan"], "e → i")
        override(f, "gerund", "pidiendo", "e → i")
        mark_derived(f, "tema de pretérito pid-")
    elif n == 48:
        override(f, "ind_present", ["puedo", "puedes", "puede", "podemos", "pueden"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite("pud"), "pretérito fuerte pud-")
        override(f, "ind_future", future_from("podr"), "futuro sincopado podr-")
        override(f, "ind_conditional", conditional_from("podr"), "condicional sincopado podr-")
        override(f, "subj_present", ["pueda", "puedas", "pueda", "podamos", "puedan"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "gerund", "pudiendo", "o → u")
        mark_derived(f, "tema de pretérito pud-")
    elif n == 49:
        override(f, "ind_present", ["pongo", "pones", "pone", "ponemos", "ponen"], "tema pong-", indices=[0])
        override(f, "ind_preterite", strong_preterite("pus"), "pretérito fuerte pus-")
        override(f, "ind_future", future_from("pondr"), "futuro sincopado pondr-")
        override(f, "ind_conditional", conditional_from("pondr"), "condicional sincopado pondr-")
        override(f, "subj_present", ["ponga", "pongas", "ponga", "pongamos", "pongan"], "tema pong-")
        override(f, "participle", "puesto", "participio irregular puesto")
        mark_derived(f, "tema de pretérito pus-")
    elif n == 50:
        override(f, "ind_present", ["predigo", "predices", "predice", "predecimos", "predicen"], "temas predig-/predic-", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite("predij", j_stem=True), "pretérito fuerte predij-")
        f["ind_future"] = [variants((f"predecir{x}", None, None), (f"predir{x}", "irregular", "variante sincopada predir-")) for x in ("é", "ás", "á", "emos", "án")]
        f["ind_conditional"] = [variants((f"predecir{x}", None, None), (f"predir{x}", "irregular", "variante sincopada predir-")) for x in ("ía", "ías", "ía", "íamos", "ían")]
        override(f, "subj_present", ["prediga", "predigas", "prediga", "predigamos", "predigan"], "tema predig-")
        override(f, "gerund", "prediciendo", "tema predici-")
        override(f, "participle", "predicho", "participio irregular predicho")
        mark_derived(f, "tema de pretérito predij-")
    elif n == 51:
        override(f, "ind_present", ["prohíbo", "prohíbes", "prohíbe", "prohibimos", "prohíben"], "hiato léxico oí", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["prohíba", "prohíbas", "prohíba", "prohibamos", "prohíban"], "hiato léxico oí", indices=[0, 1, 2, 4])
    elif n == 52:
        override(f, "ind_present", ["prohíjo", "prohíjas", "prohíja", "prohijamos", "prohíjan"], "hiato léxico oí", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["prohíje", "prohíjes", "prohíje", "prohijemos", "prohíjen"], "hiato léxico oí", indices=[0, 1, 2, 4])
    elif n == 53:
        f["infinitive_display"] = variants(
            ("pudrir", None, None),
            ("podrir", "irregular", "variante podrir"),
        )
        f["ind_present"][3] = variants(
            ("pudrimos", None, None),
            ("podrimos", "irregular", "variante podr-"),
        )
        imperfect_pudr = ["pudría", "pudrías", "pudría", "pudríamos", "pudrían"]
        imperfect_podr = ["podría", "podrías", "podría", "podríamos", "podrían"]
        preterite_pudr = ["pudrí", "pudriste", "pudrió", "pudrimos", "pudrieron"]
        preterite_podr = ["podrí", "podriste", "podrió", "podrimos", "podrieron"]
        future_pudr = future_from("pudrir")
        future_podr = future_from("podrir")
        conditional_pudr = conditional_from("pudrir")
        conditional_podr = conditional_from("podrir")
        f["ind_imperfect"] = [
            variants((imperfect_pudr[i], None, None), (imperfect_podr[i], "irregular", "variante podr-"))
            for i in range(5)
        ]
        f["ind_preterite"] = [
            variants((preterite_pudr[i], None, None), (preterite_podr[i], "irregular", "variante podr-"))
            for i in range(5)
        ]
        f["ind_future"] = [
            variants((future_pudr[i], None, None), (future_podr[i], "irregular", "variante podrir-"))
            for i in range(5)
        ]
        f["ind_conditional"] = [
            variants((conditional_pudr[i], None, None), (conditional_podr[i], "irregular", "variante podrir-"))
            for i in range(5)
        ]
        override(f, "participle", "podrido", "participio con podr-")
    elif n == 54:
        override(f, "ind_present", ["quiero", "quieres", "quiere", "queremos", "quieren"], "e → ie", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite("quis"), "pretérito fuerte quis-")
        override(f, "ind_future", future_from("querr"), "futuro sincopado querr-")
        override(f, "ind_conditional", conditional_from("querr"), "condicional sincopado querr-")
        override(f, "subj_present", ["quiera", "quieras", "quiera", "queramos", "quieran"], "e → ie", indices=[0, 1, 2, 4])
        mark_derived(f, "tema de pretérito quis-")
    elif n == 55:
        override(f, "ind_present", ["rehúso", "rehúsas", "rehúsa", "rehusamos", "rehúsan"], "hiato léxico eú", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["rehúse", "rehúses", "rehúse", "rehusemos", "rehúsen"], "hiato léxico eú", indices=[0, 1, 2, 4])
    elif n == 56:
        override(f, "ind_present", ["reúno", "reúnes", "reúne", "reunimos", "reúnen"], "hiato léxico eú", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["reúna", "reúnas", "reúna", "reunamos", "reúnan"], "hiato léxico eú", indices=[0, 1, 2, 4])
    elif n == 57:
        f["ind_present"][0] = variants(
            ("roo", None, None),
            ("roigo", "irregular", "variante roig-"),
            ("royo", "irregular", "variante roy-"),
        )
        override(f, "ind_preterite", ["roí", "roíste", "royó", "roímos", "royeron"], "i → y entre vocales", indices=[2, 4], kind="orthographic")
        regular_subj = ["roa", "roas", "roa", "roamos", "roan"]
        roig_subj = ["roiga", "roigas", "roiga", "roigamos", "roigan"]
        roy_subj = ["roya", "royas", "roya", "royamos", "royan"]
        f["subj_present"] = [
            variants((regular_subj[i], None, None), (roig_subj[i], "irregular", "variante roig-"), (roy_subj[i], "irregular", "variante roy-"))
            for i in range(5)
        ]
        override(f, "gerund", "royendo", "i → y entre vocales", kind="orthographic")
        override(f, "participle", "roído", "tilde de hiato", kind="orthographic")
        mark_derived(f, "i → y entre vocales", "orthographic")
    elif n == 58:
        override(f, "ind_present", ["sé", "sabes", "sabe", "sabemos", "saben"], "forma sé", indices=[0])
        override(f, "ind_preterite", strong_preterite("sup"), "pretérito fuerte sup-")
        override(f, "ind_future", future_from("sabr"), "futuro sincopado sabr-")
        override(f, "ind_conditional", conditional_from("sabr"), "condicional sincopado sabr-")
        override(f, "subj_present", ["sepa", "sepas", "sepa", "sepamos", "sepan"], "tema sep-")
        mark_derived(f, "tema de pretérito sup-")
    elif n == 59:
        override(f, "ind_present", ["salgo", "sales", "sale", "salimos", "salen"], "tema salg-", indices=[0])
        override(f, "ind_future", future_from("saldr"), "futuro sincopado saldr-")
        override(f, "ind_conditional", conditional_from("saldr"), "condicional sincopado saldr-")
        override(f, "subj_present", ["salga", "salgas", "salga", "salgamos", "salgan"], "tema salg-")
    elif n == 60:
        override(f, "ind_present", ["siento", "sientes", "siente", "sentimos", "sienten"], "e → ie", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", ["sentí", "sentiste", "sintió", "sentimos", "sintieron"], "e → i", indices=[2, 4])
        override(f, "subj_present", ["sienta", "sientas", "sienta", "sintamos", "sientan"], "e → ie/i")
        override(f, "gerund", "sintiendo", "e → i")
        mark_derived(f, "tema de pretérito sint-")
    elif n == 61:
        override(f, "ind_present", ["soy", "eres", "es", "somos", "son"], "presente supletivo")
        override(f, "ind_imperfect", ["era", "eras", "era", "éramos", "eran"], "imperfecto er-")
        override(f, "ind_preterite", ["fui", "fuiste", "fue", "fuimos", "fueron"], "pretérito supletivo fu-")
        override(f, "subj_present", ["sea", "seas", "sea", "seamos", "sean"], "subjuntivo se-")
        override(f, "imperative", ["sé", "sea", "seamos", "sean"], "imperativo propio")
        mark_derived(f, "tema de pretérito fu-")
    elif n == 62:
        override(f, "ind_present", ["sonrío", "sonríes", "sonríe", "sonreímos", "sonríen"], "e → i y hiato", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", ["sonreí", "sonreíste", "sonrió", "sonreímos", "sonrieron"], "e → i", indices=[2, 4])
        override(f, "subj_present", ["sonría", "sonrías", "sonría", "sonriamos", "sonrían"], "e → i")
        override(f, "gerund", "sonriendo", "e → i")
        override(f, "participle", "sonreído", "tilde de hiato", kind="orthographic")
        mark_derived(f, "tema de pretérito sonri-")
    elif n == 63:
        override(f, "ind_preterite", ["tañí", "tañiste", "tañó", "tañimos", "tañeron"], "pérdida regular de i tras ñ", indices=[2, 4], kind="orthographic")
        override(f, "gerund", "tañendo", "pérdida regular de i tras ñ", kind="orthographic")
        mark_derived(f, "pérdida de i tras ñ", "orthographic")
    elif n == 64:
        override(f, "ind_present", ["tengo", "tienes", "tiene", "tenemos", "tienen"], "temas teng-/tien-", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite("tuv"), "pretérito fuerte tuv-")
        override(f, "ind_future", future_from("tendr"), "futuro sincopado tendr-")
        override(f, "ind_conditional", conditional_from("tendr"), "condicional sincopado tendr-")
        override(f, "subj_present", ["tenga", "tengas", "tenga", "tengamos", "tengan"], "tema teng-")
        mark_derived(f, "tema de pretérito tuv-")
    elif n == 65:
        override(f, "ind_present", ["traigo", "traes", "trae", "traemos", "traen"], "tema traig-", indices=[0])
        override(f, "ind_preterite", strong_preterite("traj", j_stem=True), "pretérito fuerte traj-")
        override(f, "subj_present", ["traiga", "traigas", "traiga", "traigamos", "traigan"], "tema traig-")
        override(f, "gerund", "trayendo", "i → y entre vocales", kind="orthographic")
        override(f, "participle", "traído", "tilde de hiato", kind="orthographic")
        mark_derived(f, "tema de pretérito traj-")
    elif n == 66:
        override(f, "ind_present", ["valgo", "vales", "vale", "valemos", "valen"], "tema valg-", indices=[0])
        override(f, "ind_future", future_from("valdr"), "futuro sincopado valdr-")
        override(f, "ind_conditional", conditional_from("valdr"), "condicional sincopado valdr-")
        override(f, "subj_present", ["valga", "valgas", "valga", "valgamos", "valgan"], "tema valg-")
    elif n == 67:
        override(f, "ind_present", ["vengo", "vienes", "viene", "venimos", "vienen"], "temas veng-/vien-", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite("vin"), "pretérito fuerte vin-")
        override(f, "ind_future", future_from("vendr"), "futuro sincopado vendr-")
        override(f, "ind_conditional", conditional_from("vendr"), "condicional sincopado vendr-")
        override(f, "subj_present", ["venga", "vengas", "venga", "vengamos", "vengan"], "tema veng-")
        override(f, "gerund", "viniendo", "e → i")
        mark_derived(f, "tema de pretérito vin-")
    elif n == 68:
        override(f, "ind_present", ["veo", "ves", "ve", "vemos", "ven"], "forma veo", indices=[0])
        override(f, "ind_imperfect", ["veía", "veías", "veía", "veíamos", "veían"], "tema ve-")
        override(f, "ind_preterite", ["vi", "viste", "vio", "vimos", "vieron"], "pretérito vi-/vie-")
        override(f, "subj_present", ["vea", "veas", "vea", "veamos", "vean"], "tema ve-")
        override(f, "participle", "visto", "participio irregular visto")
        mark_derived(f, "tema de pretérito vie-")
    elif n == 69:
        f["ind_present"][0] = variants(
            ("yazco", "irregular", "variante yazc-"),
            ("yazgo", "irregular", "variante yazg-"),
            ("yago", "irregular", "variante yag-"),
        )
        yazc = ["yazca", "yazcas", "yazca", "yazcamos", "yazcan"]
        yazg = ["yazga", "yazgas", "yazga", "yazgamos", "yazgan"]
        yag = ["yaga", "yagas", "yaga", "yagamos", "yagan"]
        f["subj_present"] = [
            variants((yazc[i], "irregular", "variante yazc-"), (yazg[i], "irregular", "variante yazg-"), (yag[i], "irregular", "variante yag-"))
            for i in range(5)
        ]
    elif n == 70:
        override(f, "participle", "abierto", "participio irregular abierto")
    elif n == 71:
        override(f, "participle", "cubierto", "participio irregular cubierto")
    elif n == 72:
        override(f, "participle", "escrito", "participio irregular escrito")
    elif n == 73:
        override(f, "participle", "roto", "participio irregular roto")
    elif n == 74:
        f["participle"] = variants(
            ("imprimido", None, None),
            ("impreso", "irregular", "participio irregular impreso"),
        )
    elif n == 75:
        override(f, "ind_present", ["muero", "mueres", "muere", "morimos", "mueren"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", ["morí", "moriste", "murió", "morimos", "murieron"], "o → u", indices=[2, 4])
        override(f, "subj_present", ["muera", "mueras", "muera", "muramos", "mueran"], "o → ue/u")
        override(f, "gerund", "muriendo", "o → u")
        override(f, "participle", "muerto", "participio irregular muerto")
        mark_derived(f, "tema de pretérito mur-")
    elif n == 76:
        override(f, "ind_present", ["vuelvo", "vuelves", "vuelve", "volvemos", "vuelven"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["vuelva", "vuelvas", "vuelva", "volvamos", "vuelvan"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "participle", "vuelto", "participio irregular vuelto")
    elif n == 77:
        override(f, "ind_present", ["resuelvo", "resuelves", "resuelve", "resolvemos", "resuelven"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "subj_present", ["resuelva", "resuelvas", "resuelva", "resolvamos", "resuelvan"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "participle", "resuelto", "participio irregular resuelto")
    elif n == 78:
        override(f, "ind_present", ["frío", "fríes", "fríe", "freímos", "fríen"], "e → i y hiato", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", ["freí", "freíste", "frio", "freímos", "frieron"], "e → i; rio sin tilde por ser monosílabo", indices=[2, 4])
        override(f, "subj_present", ["fría", "frías", "fría", "friamos", "frían"], "e → i")
        override(f, "gerund", "friendo", "e → i")
        f["participle"] = variants(
            ("freído", "orthographic", "tilde de hiato"),
            ("frito", "irregular", "participio irregular frito"),
        )
        mark_derived(f, "tema de pretérito fri-")
    elif n == 79:
        override(f, "ind_preterite", ["proveí", "proveíste", "proveyó", "proveímos", "proveyeron"], "i → y entre vocales", indices=[2, 4], kind="orthographic")
        override(f, "gerund", "proveyendo", "i → y entre vocales", kind="orthographic")
        f["participle"] = variants(
            ("proveído", "orthographic", "tilde de hiato"),
            ("provisto", "irregular", "participio irregular provisto"),
        )
        mark_derived(f, "i → y entre vocales", "orthographic")
    elif n == 80:
        override(f, "ind_present", ["elijo", "eliges", "elige", "elegimos", "eligen"], "e → i", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", ["elegí", "elegiste", "eligió", "elegimos", "eligieron"], "e → i", indices=[2, 4])
        override(f, "subj_present", ["elija", "elijas", "elija", "elijamos", "elijan"], "tema elij-")
        override(f, "gerund", "eligiendo", "e → i")
        f["participle"] = variants(
            ("elegido", None, None),
            ("electo", "irregular", "participio irregular electo"),
        )
        mark_derived(f, "tema de pretérito elig-")
    elif n == 81:
        override(f, "ind_present", ["satisfago", "satisfaces", "satisface", "satisfacemos", "satisfacen"], "tema satisfag-", indices=[0])
        override(f, "ind_preterite", ["satisfice", "satisficiste", "satisfizo", "satisficimos", "satisficieron"], "pretérito fuerte satisfic-/satisfiz-")
        override(f, "ind_future", future_from("satisfar"), "futuro sincopado satisfar-")
        override(f, "ind_conditional", conditional_from("satisfar"), "condicional sincopado satisfar-")
        override(f, "subj_present", ["satisfaga", "satisfagas", "satisfaga", "satisfagamos", "satisfagan"], "tema satisfag-")
        override(f, "participle", "satisfecho", "participio irregular satisfecho")
        mark_derived(f, "tema de pretérito satisfic-")
    else:
        raise ValueError(f"Missing paradigm implementation for model {n}")

    # Imperative defaults follow indicative 3sg and the present subjunctive.
    if n not in {36, 38, 61}:
        present = f["ind_present"]
        subj = f["subj_present"]
        f["imperative"] = [present[2], subj[2], subj[3], subj[4]]
        for idx, source in enumerate((("ind_present", 2), ("subj_present", 2), ("subj_present", 3), ("subj_present", 4))):
            source_mark = f["marks"].get(source[0], {}).get(str(source[1]))
            if source_mark:
                f["marks"].setdefault("imperative", {})[str(idx)] = deepcopy(source_mark)

    special_tu = {
        27: ("di", "imperativo di"), 37: ("haz", "imperativo haz"),
        49: ("pon", "imperativo pon"), 59: ("sal", "imperativo sal"),
        64: ("ten", "imperativo ten"), 67: ("ven", "imperativo ven"),
        69: ("yace / yaz", "variantes de imperativo"),
    }
    if n in special_tu:
        if n == 69:
            f["imperative"][0] = variants(
                ("yace", None, None),
                ("yaz", "irregular", "variante de imperativo yaz"),
            )
        else:
            f["imperative"][0] = special_tu[n][0]
            f["marks"].setdefault("imperative", {})["0"] = {"reason": special_tu[n][1], "kind": "irregular"}
    elif n == 81:
        f["imperative"][0] = variants(
            ("satisface", None, None),
            ("satisfaz", "irregular", "variante de imperativo satisfaz"),
        )

    return f


def replace_last(value: str, old: str, new: str) -> str:
    """Replace the final occurrence of a lexical vowel or cluster."""
    position = value.rfind(old)
    if position < 0:
        raise ValueError(f"Cannot replace {old!r} in {value!r}")
    return value[:position] + new + value[position + len(old):]


def accent_last_vowel(value: str, vowel: str | None = None) -> str:
    """Accent the last requested vowel (or simply the last vowel)."""
    targets = vowel or "aeiou"
    replacements = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}
    for position in range(len(value) - 1, -1, -1):
        if value[position] in targets:
            return value[:position] + replacements[value[position]] + value[position + 1:]
    raise ValueError(f"No accentable vowel in {value!r}")


def before_e(stem: str, spelling: str | None) -> str:
    """Apply the predictable c/qu, g/gu or z/c spelling before e."""
    if spelling == "c_qu" and stem.endswith("c"):
        return stem[:-1] + "qu"
    if spelling == "g_gu" and stem.endswith("g"):
        return stem + "u"
    if spelling == "z_c" and stem.endswith("z"):
        return stem[:-1] + "c"
    return stem


def recompute_imperative(
    forms: dict[str, object], *, tu: str | list[dict[str, str | None]] | None = None,
    tu_reason: str | None = None,
) -> None:
    """Rebuild the Latin-American affirmative imperative from the target verb."""
    present = forms["ind_present"]
    subj = forms["subj_present"]
    forms["imperative"] = [present[2], subj[2], subj[3], subj[4]]
    forms["marks"].pop("imperative", None)
    for target, (key, source) in enumerate((
        ("ind_present", 2), ("subj_present", 2),
        ("subj_present", 3), ("subj_present", 4),
    )):
        mark = forms["marks"].get(key, {}).get(str(source))
        if mark:
            forms["marks"].setdefault("imperative", {})[str(target)] = deepcopy(mark)
    if tu is not None:
        forms["imperative"][0] = tu
        if tu_reason:
            forms["marks"].setdefault("imperative", {})["0"] = {
                "reason": tu_reason, "kind": "irregular",
            }


def spelling_rule(lemma: str) -> str | None:
    return {
        "empezar": "z_c", "tropezar": "z_c", "enraizar": "z_c",
        "almorzar": "z_c", "negar": "g_gu", "regar": "g_gu",
        "volcar": "c_qu", "jugar": "g_gu",
    }.get(lemma)


def spelling_reason(spelling: str) -> str:
    return {
        "c_qu": "c → qu ante e",
        "g_gu": "g → gu ante e",
        "z_c": "z → c ante e",
    }[spelling]


def clone_value_with_prefix(value: object, prefix: str) -> object:
    if isinstance(value, str):
        return prefix + value
    if is_variants(value):
        return [
            {
                **item,
                "text": prefix + item["text"],
                "reason": prefixed_reason(item["reason"], prefix) if item.get("reason") else item.get("reason"),
            }
            for item in value
        ]
    if isinstance(value, list):
        return [clone_value_with_prefix(item, prefix) for item in value]
    return deepcopy(value)


def prefixed_reason(reason: str, prefix: str) -> str:
    # Exact derivatives add the prefix to lexical allomorphs such as caig-,
    # hic-/hiz- and puesto, but never to grammatical descriptions.
    reason = re.sub(
        r"(?<![\wáéíóúüñ])([a-záéíóúüñ]{2,})-",
        lambda match: prefix + match.group(1) + "-",
        reason,
    )
    return reason


def prefixed_paradigm(family: Family, member: str) -> dict[str, object]:
    """Clone a truly transparent prefixed derivative, lexical tokens only."""
    prefix = member[:-len(family.lemma)]
    source = paradigm(family)
    result: dict[str, object] = {}
    for key, value in source.items():
        if key == "marks":
            result[key] = deepcopy(value)
        elif key.startswith("_"):
            result[key] = deepcopy(value)
        else:
            result[key] = clone_value_with_prefix(value, prefix)

    source_parts = source["participle"]
    target_parts = result["participle"]
    source_part_texts = [item["text"] for item in source_parts] if is_variants(source_parts) else [source_parts]
    target_part_texts = [item["text"] for item in target_parts] if is_variants(target_parts) else [target_parts]
    if is_variants(source_parts) and is_variants(target_parts):
        for source_item, target_item in zip(source_parts, target_parts):
            if target_item.get("reason"):
                for source_part, target_part in zip(source_part_texts, target_part_texts):
                    target_item["reason"] = re.sub(
                        rf"(?<![\wáéíóúüñ]){re.escape(source_part)}(?![\wáéíóúüñ])",
                        target_part,
                        target_item["reason"],
                    )
    for marks in result["marks"].values():
        for mark in marks.values():
            mark["reason"] = prefixed_reason(mark["reason"], prefix)
            for source_part, target_part in zip(source_part_texts, target_part_texts):
                mark["reason"] = re.sub(
                    rf"(?<![\wáéíóúüñ]){re.escape(source_part)}(?![\wáéíóúüñ])",
                    target_part,
                    mark["reason"],
                )
            source_yo = source["ind_present"][0]
            target_yo = result["ind_present"][0]
            if isinstance(source_yo, str) and isinstance(target_yo, str):
                mark["reason"] = re.sub(
                    rf"(?<![\wáéíóúüñ]){re.escape(source_yo)}(?![\wáéíóúüñ])",
                    target_yo,
                    mark["reason"],
                )

    result["infinitive"] = member
    n = family.number
    if n in {49, 64, 67}:
        base = {49: "pon", 64: "ten", 67: "ven"}[n]
        command = accent_last_vowel(prefix + base) if prefix else base
        recompute_imperative(result, tu=command, tu_reason=f"imperativo {command}")
    elif n == 37:
        command = prefix + "haz"
        recompute_imperative(result, tu=command, tu_reason=f"imperativo {command}")
    elif n == 59:
        recompute_imperative(result, tu=prefix + "sal", tu_reason=f"imperativo {prefix}sal")
    elif n == 69:
        regular = prefix + "yace"
        short = prefix + "yaz"
        recompute_imperative(
            result,
            tu=variants((regular, None, None), (short, "irregular", f"variante de imperativo {short}")),
        )
    else:
        # The cloned representative already has the right lexical forms, but
        # rebuilding guarantees agreement with the cloned target subjunctive.
        recompute_imperative(result)
    return result


def vowel_boot_ar(member: str, old: str, new: str) -> dict[str, object]:
    f = regular_forms(member)
    stem = member[:-2]
    boot = replace_last(stem, old, new)
    spelling = spelling_rule(member)
    override(f, "ind_present", [boot + x for x in ("o", "as", "a")] + [stem + "amos", boot + "an"], f"{old} → {new}", indices=[0, 1, 2, 4])
    subj_boot = before_e(boot, spelling)
    subj_stem = before_e(stem, spelling)
    override(f, "subj_present", [subj_boot + "e", subj_boot + "es", subj_boot + "e", subj_stem + "emos", subj_boot + "en"], f"{old} → {new}", indices=[0, 1, 2, 4])
    if spelling:
        spelling_note = spelling_reason(spelling)
        f["ind_preterite"][0] = before_e(stem, spelling) + "é"
        set_marks(f, "ind_preterite", [0], spelling_note, "orthographic")
        set_marks(f, "subj_present", [0, 1, 2, 4], f"{old} → {new}; {spelling_note}")
        set_marks(f, "subj_present", [3], spelling_note, "orthographic")
    recompute_imperative(f)
    return f


def stressed_stem(member: str, vowel: str, reason: str) -> dict[str, object]:
    f = regular_forms(member)
    stem = member[:-2]
    boot = accent_last_vowel(stem, vowel)
    cls = verb_class(member)
    if cls == "ar":
        present_endings = ("o", "as", "a", "amos", "an")
        subj_endings = ("e", "es", "e", "emos", "en")
    else:
        present_endings = ("o", "es", "e", "imos", "en")
        subj_endings = ("a", "as", "a", "amos", "an")
    override(f, "ind_present", [
        boot + present_endings[0], boot + present_endings[1], boot + present_endings[2],
        stem + present_endings[3], boot + present_endings[4],
    ], reason, indices=[0, 1, 2, 4])
    override(f, "subj_present", [
        boot + subj_endings[0], boot + subj_endings[1], boot + subj_endings[2],
        stem + subj_endings[3], boot + subj_endings[4],
    ], reason, indices=[0, 1, 2, 4])
    recompute_imperative(f)
    return f


def e_to_i_ir(member: str, *, loss_after: str | None = None) -> dict[str, object]:
    f = regular_forms(member)
    stem = member[:-2]
    changed = replace_last(stem, "e", "i")
    override(f, "ind_present", [changed + "o", changed + "es", changed + "e", stem + "imos", changed + "en"], "e → i", indices=[0, 1, 2, 4])
    if loss_after and changed.endswith(loss_after):
        third, plural, gerund = changed + "ó", changed + "eron", changed + "endo"
        reason = f"e → i; pérdida de i tras {loss_after}"
    else:
        third, plural, gerund = changed + "ió", changed + "ieron", changed + "iendo"
        reason = "e → i"
    override(f, "ind_preterite", [stem + "í", stem + "iste", third, stem + "imos", plural], reason, indices=[2, 4])
    override(f, "subj_present", [changed + x for x in ("a", "as", "a", "amos", "an")], "e → i")
    override(f, "gerund", gerund, reason)
    mark_derived(f, f"tema de pretérito {changed}-")
    recompute_imperative(f)
    return f


def member_paradigm(family: Family, member: str) -> dict[str, object]:
    """Return a complete, independently generated paradigm for a family chip."""
    if member not in family.members:
        raise ValueError(f"{member!r} is not in the {family.lemma} family")
    if member == family.lemma:
        return paradigm(family)

    n = family.number
    if member.endswith(family.lemma):
        # Exact derivatives are numerous, but a handful below have independent
        # accentuation or allomorph boundaries and therefore bypass this path.
        if n not in {63, 68, 72, 78}:
            return prefixed_paradigm(family, member)

    if n == 4:
        return vowel_boot_ar(member, "e", "ie")
    if n == 5:
        return stressed_stem(member, "u", "hiato léxico con ú tónica")
    if n == 7:
        f = regular_forms(member)
        stem, boot = member[:-2], replace_last(member[:-2], "i", "ie")
        override(f, "ind_present", [boot + "o", boot + "es", boot + "e", stem + "imos", boot + "en"], "i → ie", indices=[0, 1, 2, 4])
        override(f, "subj_present", [boot + x for x in ("a", "as", "a")] + [stem + "amos", boot + "an"], "i → ie", indices=[0, 1, 2, 4])
        recompute_imperative(f)
        return f
    if n == 8:
        f = regular_forms(member)
        stem = member[:-2]
        special = stem[:-1] + "zc"
        override(f, "ind_present", [special + "o", stem + "es", stem + "e", stem + ("emos" if verb_class(member) == "er" else "imos"), stem + "en"], "inserción -zc-", indices=[0])
        override(f, "subj_present", [special + x for x in ("a", "as", "a", "amos", "an")], "inserción -zc-")
        recompute_imperative(f)
        return f
    if n == 9:
        f = stressed_stem(member, "i", "hiato léxico con í tónica")
        if member == "enraizar":
            stem = member[:-2]
            f["ind_preterite"][0] = before_e(stem, "z_c") + "é"
            set_marks(f, "ind_preterite", [0], "z → c ante e", "orthographic")
            boot = accent_last_vowel(stem, "i")
            f["subj_present"] = [before_e(boot, "z_c") + x for x in ("e", "es", "e")] + [before_e(stem, "z_c") + "emos", before_e(boot, "z_c") + "en"]
            set_marks(f, "subj_present", [0, 1, 2, 4], "hiato léxico con í tónica; z → c ante e")
            set_marks(f, "subj_present", [3], "z → c ante e", "orthographic")
            recompute_imperative(f)
        return f
    if n == 14:
        return stressed_stem(member, "u", "hiato léxico con ú tónica")
    if n == 17:
        prefix = member[:-5]
        f = regular_forms(member)
        override(f, "ind_present", [prefix + "digo", prefix + "dices", prefix + "dice", prefix + "decimos", prefix + "dicen"], f"temas {prefix}dig-/{prefix}dic-", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite(prefix + "dij", j_stem=True), f"pretérito fuerte {prefix}dij-")
        override(f, "subj_present", [prefix + "dig" + x for x in ("a", "as", "a", "amos", "an")], f"tema {prefix}dig-")
        override(f, "gerund", prefix + "diciendo", "e → i en gerundio")
        mark_derived(f, f"tema de pretérito {prefix}dij-")
        recompute_imperative(f)
        return f
    if n == 21:
        return e_to_i_ir(member, loss_after="ñ")
    if n == 23:
        f = regular_forms(member)
        prefix = member[:-5]
        present_stem, past_stem = prefix + "duzc", prefix + "duj"
        regular_stem = member[:-2]
        override(f, "ind_present", [present_stem + "o", regular_stem + "es", regular_stem + "e", regular_stem + "imos", regular_stem + "en"], "tema -duzc-", indices=[0])
        override(f, "ind_preterite", strong_preterite(past_stem, j_stem=True), "pretérito fuerte -duj-")
        override(f, "subj_present", [present_stem + x for x in ("a", "as", "a", "amos", "an")], "tema -duzc-")
        mark_derived(f, f"tema de pretérito {past_stem}-")
        recompute_imperative(f)
        return f
    if n == 24:
        f = regular_forms(member)
        stem = member[:-2]
        override(f, "ind_present", [stem + x for x in ("yo", "yes", "ye", "imos", "yen")], "i → y entre vocales", indices=[0, 1, 2, 4], kind="orthographic")
        first = stem + ("i" if member in {"fluir", "huir"} else "í")
        override(f, "ind_preterite", [first, stem + "iste", stem + "yó", stem + "imos", stem + "yeron"], "i → y entre vocales", indices=[2, 4], kind="orthographic")
        if member in {"fluir", "huir"}:
            set_marks(f, "ind_preterite", [0], "monosílabo sin tilde según la ortografía vigente", "orthographic")
        override(f, "subj_present", [stem + x for x in ("ya", "yas", "ya", "yamos", "yan")], "i → y entre vocales", kind="orthographic")
        override(f, "gerund", stem + "yendo", "i → y entre vocales", kind="orthographic")
        f["participle"] = stem + "ido"
        mark_derived(f, "i → y entre vocales", "orthographic")
        recompute_imperative(f)
        return f
    if n == 25:
        return vowel_boot_ar(member, "o", "ue")
    if n == 28:
        return stressed_stem(member, "i", "hiato léxico con í tónica")
    if n in {29, 31}:
        f = regular_forms(member)
        stem, boot = member[:-2], replace_last(member[:-2], "e", "ie")
        present_nos = "imos" if verb_class(member) == "ir" else "emos"
        override(f, "ind_present", [boot + "o", boot + "es", boot + "e", stem + present_nos, boot + "en"], "e → ie", indices=[0, 1, 2, 4])
        override(f, "subj_present", [boot + "a", boot + "as", boot + "a", stem + "amos", boot + "an"], "e → ie", indices=[0, 1, 2, 4])
        recompute_imperative(f)
        return f
    if n == 32:
        f = stressed_stem(member, "i", "hiato léxico con í tónica")
        if member in {"criar", "fiar", "guiar", "liar"}:
            stem = member[:-2]
            f["ind_preterite"][0] = stem + "e"
            f["ind_preterite"][2] = stem + "o"
            set_marks(f, "ind_preterite", [0, 2], "monosílabos sin tilde según la ortografía vigente", "orthographic")
        recompute_imperative(f)
        return f
    if n == 40:
        f = regular_forms(member)
        stem = member[:-2]
        override(f, "ind_preterite", [stem + "í", stem + "íste", stem + "yó", stem + "ímos", stem + "yeron"], "i → y entre vocales", indices=[2, 4], kind="orthographic")
        override(f, "gerund", stem + "yendo", "i → y entre vocales", kind="orthographic")
        override(f, "participle", stem + "ído", "tilde de hiato", kind="orthographic")
        mark_derived(f, "i → y entre vocales", "orthographic")
        recompute_imperative(f)
        return f
    if n == 42:
        f = regular_forms(member)
        stem, boot = member[:-2], replace_last(member[:-2], "o", "ue")
        before_a = boot[:-1] + "z" if member in {"cocer", "torcer"} else boot
        unstressed_before_a = stem[:-1] + "z" if member in {"cocer", "torcer"} else stem
        override(f, "ind_present", [before_a + "o", boot + "es", boot + "e", stem + "emos", boot + "en"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "subj_present", [before_a + x for x in ("a", "as", "a")] + [unstressed_before_a + "amos", before_a + "an"], "o → ue", indices=[0, 1, 2, 4])
        if member in {"cocer", "torcer"}:
            set_marks(f, "ind_present", [0], "o → ue; c → z ante o")
            set_marks(f, "subj_present", [0, 1, 2, 4], "o → ue; c → z ante a")
            set_marks(f, "subj_present", [3], "c → z ante a", "orthographic")
        recompute_imperative(f)
        return f
    if n == 43:
        f = regular_forms(member)
        stem = member[:-2]
        override(f, "ind_preterite", [stem + "í", stem + "iste", stem + "ó", stem + "imos", stem + "eron"], "pérdida regular de i tras ll/ñ", indices=[2, 4], kind="orthographic")
        override(f, "gerund", stem + "endo", "pérdida regular de i tras ll/ñ", kind="orthographic")
        mark_derived(f, "pérdida de i tras ll/ñ", "orthographic")
        recompute_imperative(f)
        return f
    if n == 46:
        f = regular_forms(member)
        stem, changed = member[:-2], replace_last(member[:-2], "e", "i")
        if member.endswith("guir"):
            oa_stem = changed[:-1]
        elif member.endswith("gir"):
            oa_stem = changed[:-1] + "j"
        else:
            oa_stem = changed
        override(f, "ind_present", [oa_stem + "o", changed + "es", changed + "e", stem + "imos", changed + "en"], "e → i", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", [stem + "í", stem + "iste", changed + "ió", stem + "imos", changed + "ieron"], "e → i", indices=[2, 4])
        override(f, "subj_present", [oa_stem + x for x in ("a", "as", "a", "amos", "an")], "e → i")
        if member.endswith("guir"):
            set_marks(f, "ind_present", [0], "e → i; pérdida de u ante o")
            set_marks(f, "subj_present", [0, 1, 2, 3, 4], "e → i; pérdida de u ante a")
        elif member.endswith("gir"):
            set_marks(f, "ind_present", [0], "e → i; g → j ante o")
            set_marks(f, "subj_present", [0, 1, 2, 3, 4], "e → i; g → j ante a")
        override(f, "gerund", changed + "iendo", "e → i")
        mark_derived(f, f"tema de pretérito {changed}-")
        recompute_imperative(f)
        return f
    if n == 50:
        prefix = member[:-5]
        f = regular_forms(member)
        override(f, "ind_present", [prefix + x for x in ("digo", "dices", "dice", "decimos", "dicen")], f"temas {prefix}dig-/{prefix}dic-", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", strong_preterite(prefix + "dij", j_stem=True), f"pretérito fuerte {prefix}dij-")
        short = prefix + "dir"
        f["ind_future"] = [variants((member + x, None, None), (short + x, "irregular", f"variante sincopada {short}-")) for x in ("é", "ás", "á", "emos", "án")]
        f["ind_conditional"] = [variants((member + x, None, None), (short + x, "irregular", f"variante sincopada {short}-")) for x in ("ía", "ías", "ía", "íamos", "ían")]
        override(f, "subj_present", [prefix + "dig" + x for x in ("a", "as", "a", "amos", "an")], f"tema {prefix}dig-")
        override(f, "gerund", prefix + "diciendo", f"tema {prefix}dici-")
        override(f, "participle", prefix + "dicho", f"participio irregular {prefix}dicho")
        mark_derived(f, f"tema de pretérito {prefix}dij-")
        recompute_imperative(f)
        return f
    if n == 51:
        return stressed_stem(member, "i", "hiato léxico con í tónica")
    if n == 53:
        f = paradigm(family)
        # The two infinitives belong to one asymmetric paradigm.  Selection
        # changes which admitted variant is presented first; it does not invent
        # nonstandard *podro/*podra series.
        for key, value in list(f.items()):
            if is_variants(value):
                f[key] = list(reversed(value))
            elif isinstance(value, list):
                f[key] = [list(reversed(item)) if is_variants(item) else item for item in value]
        f["infinitive"] = member
        return f
    if n == 55:
        return stressed_stem(member, "u", "hiato léxico con ú tónica")
    if n == 60:
        f = regular_forms(member)
        stem = member[:-2]
        boot, changed = replace_last(stem, "e", "ie"), replace_last(stem, "e", "i")
        override(f, "ind_present", [boot + "o", boot + "es", boot + "e", stem + "imos", boot + "en"], "e → ie", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", [stem + "í", stem + "iste", changed + "ió", stem + "imos", changed + "ieron"], "e → i", indices=[2, 4])
        override(f, "subj_present", [boot + "a", boot + "as", boot + "a", changed + "amos", boot + "an"], "e → ie/i")
        override(f, "gerund", changed + "iendo", "e → i")
        mark_derived(f, f"tema de pretérito {changed}-")
        recompute_imperative(f)
        return f
    if n == 62:
        f = regular_forms(member)
        stem = unaccent(member)[:-2]
        root, boot = stem[:-1], stem[:-1] + "í"
        override(f, "ind_present", [boot + "o", boot + "es", boot + "e", stem + "ímos", boot + "en"], "e → i y hiato", indices=[0, 1, 2, 4])
        third = root + ("io" if member == "reír" else "ió")
        override(f, "ind_preterite", [stem + "í", stem + "íste", third, stem + "ímos", root + "ieron"], "e → i", indices=[2, 4])
        override(f, "subj_present", [root + x for x in ("ía", "ías", "ía", "iamos", "ían")], "e → i")
        override(f, "gerund", root + "iendo", "e → i")
        override(f, "participle", stem + "ído", "tilde de hiato", kind="orthographic")
        mark_derived(f, f"tema de pretérito {root}i-")
        recompute_imperative(f)
        return f
    if n == 63:
        f = regular_forms(member)
        stem = member[:-2]
        override(f, "ind_preterite", [stem + "í", stem + "iste", stem + "ó", stem + "imos", stem + "eron"], "pérdida regular de i tras ñ", indices=[2, 4], kind="orthographic")
        override(f, "gerund", stem + "endo", "pérdida regular de i tras ñ", kind="orthographic")
        mark_derived(f, "pérdida de i tras ñ", "orthographic")
        recompute_imperative(f)
        if member == "atañer":
            finite = ("ind_present", "ind_preterite", "ind_imperfect", "ind_future", "ind_conditional", "subj_present", "subj_ra", "subj_se", "subj_future")
            f["_unavailable"] = {key: [0, 1, 3] for key in finite}
            f["_unavailable"]["imperative"] = [0, 1, 2, 3]
            f["_compound_unavailable"] = [0, 1, 3]
        return f
    if n == 68:
        prefix = member[:-3]
        f = regular_forms(member)
        base = prefix + "v"
        override(f, "ind_present", [prefix + "veo", base + "és", base + "é", prefix + "vemos", base + "én"], "acentuación de ver prefijado", indices=[1, 2, 4])
        override(f, "ind_preterite", [base + "í", prefix + "viste", base + "ió", prefix + "vimos", prefix + "vieron"], "acentuación de ver prefijado", indices=[0, 2])
        override(f, "ind_imperfect", [prefix + x for x in ("veía", "veías", "veía", "veíamos", "veían")], f"tema {prefix}ve-")
        override(f, "subj_present", [prefix + x for x in ("vea", "veas", "vea", "veamos", "vean")], f"tema {prefix}ve-")
        override(f, "participle", prefix + "visto", f"participio irregular {prefix}visto")
        mark_derived(f, f"tema de pretérito {prefix}vie-")
        recompute_imperative(f, tu=base + "é", tu_reason=f"imperativo {base}é")
        return f
    if n == 72:
        f = regular_forms(member)
        canonical = {
            "adscribir": "adscrito", "circunscribir": "circunscrito",
            "describir": "descrito", "inscribir": "inscrito",
            "prescribir": "prescrito", "suscribir": "suscrito",
            "transcribir": "transcrito",
        }[member]
        regional = canonical[:-2] + "pto"
        f["participle"] = variants(
            (canonical, "irregular", f"participio irregular {canonical}"),
            (regional, "irregular", f"variante regional {regional}"),
        )
        recompute_imperative(f)
        return f
    if n == 77:
        f = regular_forms(member)
        prefix = member[:-6]
        stem, boot = prefix + "solv", prefix + "suelv"
        override(f, "ind_present", [boot + "o", boot + "es", boot + "e", stem + "emos", boot + "en"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "subj_present", [boot + "a", boot + "as", boot + "a", stem + "amos", boot + "an"], "o → ue", indices=[0, 1, 2, 4])
        override(f, "participle", prefix + "suelto", f"participio irregular {prefix}suelto")
        recompute_imperative(f)
        return f
    if n == 78:
        f = regular_forms(member)
        stem = unaccent(member)[:-2]
        root, boot = stem[:-1], stem[:-1] + "í"
        override(f, "ind_present", [boot + "o", boot + "es", boot + "e", stem + "ímos", boot + "en"], "e → i y hiato", indices=[0, 1, 2, 4])
        override(f, "ind_preterite", [stem + "í", stem + "íste", root + "ió", stem + "ímos", root + "ieron"], "e → i", indices=[2, 4])
        override(f, "subj_present", [root + x for x in ("ía", "ías", "ía", "iamos", "ían")], "e → i")
        override(f, "gerund", root + "iendo", "e → i")
        prefix = member[:-len("freír")]
        f["participle"] = variants(
            (stem + "ído", "orthographic", "tilde de hiato"),
            (prefix + "frito", "irregular", f"participio irregular {prefix}frito"),
        )
        mark_derived(f, f"tema de pretérito {root}i-")
        recompute_imperative(f)
        return f

    raise ValueError(f"Missing member paradigm for model {n}: {member}")


CUSTOM_CSS = r"""
    main { max-width: 1180px; }
    .page-head { margin-bottom: 0.75rem; }
    .topline { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
    .back-link, .source-links a, .family-card a { color: #355c91; text-underline-offset: 0.15em; }
    .back-link { font-size: 0.78rem; font-weight: 750; text-decoration: none; }
    .model-number { color: var(--muted); font: 700 0.72rem/1 ui-monospace, monospace; }
    h1 { margin: 0.34rem 0 0.28rem; font-size: clamp(1.35rem, 2.7vw, 2rem); line-height: 1.06; letter-spacing: -0.03em; }
    .signature { margin: 0; color: #5c2f42; font: 800 0.84rem/1.35 ui-monospace, monospace; }
    .scope-note { max-width: 78ch; margin: 0.6rem 0 0; color: var(--muted); font-size: 0.76rem; line-height: 1.45; }
    .member-list { display: flex; flex-wrap: wrap; gap: 0.28rem; margin: 0.65rem 0 0; padding: 0; list-style: none; }
    .member-list > li { padding: 0.2rem 0.42rem; border: 1px solid #d5dbe5; border-radius: 999px; background: #f7f9fc; font: 700 0.69rem/1.1 ui-monospace, monospace; }
    .member-list.is-switcher > li { padding: 0; border: 0; background: transparent; }
    .member-list button { appearance: none; padding: 0.22rem 0.46rem; border: 1px solid #c8d0dc; border-radius: 999px; color: #3f4c60; background: #f7f9fc; font: inherit; cursor: pointer; }
    .member-list button:hover { border-color: #8e9caf; background: #eef3f9; }
    .member-list button[aria-pressed="true"] { border-color: #77364e; color: #fff; background: #77364e; box-shadow: 0 0 0 1px #77364e; }
    .member-list button:focus-visible { outline: 3px solid #f2b84b; outline-offset: 2px; }
    .member-status { margin-top: 0.35rem; }
    .family-note { margin: 0.45rem 0 0; padding: 0.38rem 0.55rem; border-left: 3px solid #8f6172; background: #fbf3f6; color: #5d3b48; font-size: 0.73rem; line-height: 1.35; }
    .legend-row { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; margin-top: 0.55rem; color: var(--muted); font: 650 0.71rem/1.25 ui-monospace, monospace; }
    .swatch { display: inline-block; width: 0.9rem; height: 0.7rem; margin-right: 0.22rem; vertical-align: -0.06rem; border-radius: 2px; }
    .swatch.irregular { background: #ffdedf; border: 1px solid #bd3f4b; }
    .swatch.orthographic { background: #fff2cf; border: 1px dashed #9b6b12; }
    .is-irregular { background: #ffdedf !important; box-shadow: inset 0 0 0 1.5px #bd3f4b; }
    .is-orthographic { background: #fff2cf !important; box-shadow: inset 0 0 0 1.5px #9b6b12; }
    .form-variant { display: inline-block; padding: 0.05rem 0.18rem; border-radius: 3px; }
    .variant-sep { color: #778196; font-weight: 500; }
    /* Contain absolutely positioned accessibility labels in the scroll area. */
    .table-wrap { position: relative; }
    .indicative-table { min-width: 760px; }
    .subjunctive-table { min-width: 600px; table-layout: fixed; }
    /* Full compounds and alternate participles must determine column widths. */
    .compound-table { min-width: 1080px; table-layout: auto; }
    .command-table { min-width: 310px; }
    .nonfinite-table { min-width: 390px; }
    .rare-table { min-width: 670px; table-layout: auto; }
    .indicative-table .person, .subjunctive-table .person, .rare-table .person { width: 142px; }
    .indicative-table tbody td, .subjunctive-table tbody td { text-align: left; }
    .stem-key { min-height: 1.55em; overflow-wrap: anywhere; }
    .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
    .sources { padding-top: 0.8rem; border-top: 1px dashed #cdd3dc; }
    .sources h2 { color: #4c586c; }
    .source-links { display: flex; flex-wrap: wrap; gap: 0.35rem 0.8rem; margin: 0; padding: 0; list-style: none; font-size: 0.72rem; }
    .index-main { max-width: 1160px; }
    .index-intro { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1rem; align-items: end; }
    .count-box { padding: 0.55rem 0.72rem; border: 1px solid #d6dce6; border-radius: 8px; background: #f7f9fc; font: 800 0.74rem/1.35 ui-monospace, monospace; text-align: right; }
    .search-box { width: 100%; margin-top: 0.8rem; padding: 0.56rem 0.7rem; border: 1px solid #aeb9c8; border-radius: 7px; color: var(--ink); background: white; font: 650 0.82rem/1.2 ui-monospace, monospace; }
    .family-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.52rem; }
    .family-card { min-width: 0; padding: 0.62rem 0.68rem; border: 1px solid #d7dde6; border-radius: 8px; background: #fafbfd; }
    .family-card h3 { margin: 0; font-size: 0.86rem; line-height: 1.2; }
    .family-card p { margin: 0.28rem 0 0; color: var(--muted); font-size: 0.7rem; line-height: 1.3; }
    .family-card .mini-signature { color: #70445a; font-family: ui-monospace, monospace; font-weight: 750; }
    .control-note { padding: 0.6rem 0.7rem; border: 1px dashed #a9b4c2; border-radius: 8px; background: #f5f7fa; color: var(--muted); font-size: 0.74rem; line-height: 1.4; }
    .defective-table { min-width: 820px; }
    .unavailable { background: #edf0f4 !important; color: #6d7685; text-align: center !important; }
    @media (forced-colors: active) { .is-irregular, .is-orthographic { outline: 2px solid CanvasText; outline-offset: -3px; } }
    @media (max-width: 720px) { .index-intro { grid-template-columns: 1fr; } .count-box { text-align: left; } }
"""


def extract_base_css() -> str:
    text = REGULAR_CHART.read_text(encoding="utf-8")
    match = re.search(r"<style>(.*?)</style>", text, re.S)
    if not match:
        raise RuntimeError("Could not extract CSS from the regular chart")
    return match.group(1) + CUSTOM_CSS


def mark_for(forms: dict[str, object], key: str, index: int | None = None) -> dict[str, str] | None:
    marks = forms["marks"].get(key, {})
    return marks.get("value" if index is None else str(index))


def is_variants(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) and "text" in item for item in value)


def plain_value(value: object) -> str:
    if is_variants(value):
        return " / ".join(item["text"] for item in value)
    return str(value)


def render_variants(
    value: list[dict[str, str | None]], formatter,
    *, styled_kinds: set[str] | None = None,
) -> str:
    if styled_kinds is None:
        styled_kinds = {"irregular", "orthographic"}
    rendered = []
    for item in value:
        raw_kind = item.get("kind")
        kind = raw_kind if raw_kind in styled_kinds else None
        classes = ["form-variant"]
        attrs = ""
        prefix = ""
        if kind:
            classes.append("is-irregular" if kind == "irregular" else "is-orthographic")
            reason = item.get("reason") or kind
            attrs = f' data-reason="{escape(reason, quote=True)}" title="{escape(reason, quote=True)}"'
            prefix = f'<span class="sr-only">{"forma irregular" if kind == "irregular" else "ajuste ortográfico"}: </span>'
        rendered.append(f'<span class="{" ".join(classes)}"{attrs}>{prefix}{formatter(item["text"])}</span>')
    return '<span class="variant-sep"> / </span>'.join(rendered)


def styled_pattern(value: str, black_shift: bool = False) -> str:
    if not black_shift:
        return f'<span class="pattern">{escape(value)}</span>'
    pieces: list[str] = []
    for char in unicodedata.normalize("NFD", value):
        if char == "\u0301":
            pieces.append('<span class="shift-accent">&#x301;</span>')
        else:
            pieces.append(escape(char))
    return f'<span class="pattern">{"".join(pieces)}</span>'


def nucleus_for(key: str, cls: str, index: int) -> str | None:
    if key == "ind_present":
        return ({"ar": [None, "a", "a", "a", "a"], "er": [None, "e", "e", "e", "e"], "ir": [None, "e", "e", "i", "e"]}[cls])[index]
    if key == "ind_preterite":
        return ([None, "a", None, "a", "a"] if cls == "ar" else ["í", "i", "i", "i", "i"])[index]
    if key == "ind_imperfect":
        return (["aba", "aba", "aba", "ába", "aba"] if cls == "ar" else ["ía"] * 5)[index]
    if key == "ind_future":
        return None
    if key == "ind_conditional":
        return "ía"
    if key == "subj_present":
        return ("e" if cls == "ar" else "a")
    if key == "subj_ra":
        return (["ara", "ara", "ara", "ára", "ara"] if cls == "ar" else ["iera", "iera", "iera", "iéra", "iera"])[index]
    if key == "subj_se":
        return (["ase", "ase", "ase", "áse", "ase"] if cls == "ar" else ["iese", "iese", "iese", "iése", "iese"])[index]
    if key == "subj_future":
        return (["are", "are", "are", "áre", "are"] if cls == "ar" else ["iere", "iere", "iere", "iére", "iere"])[index]
    if key == "imperative":
        return (["a", "e", "e", "e"] if cls == "ar" else ["e", "a", "a", "a"])[index]
    return None


def surface_nucleus(value: str, key: str, cls: str, index: int) -> tuple[str | None, bool]:
    """Return the nucleus actually visible in a form and whether its acute is a
    nosotros-only stress shift.

    Past subjunctives are built from the third-person plural preterite, so their
    surface endings do not always follow the infinitive class: andar has
    anduviera, decir has dijera, and ser/ir have fuera.  Detecting the visible
    suffix also keeps the black stress mark attached to the right nucleus.
    """
    def match(specs: tuple[tuple[str, str, bool], ...]) -> tuple[str | None, bool]:
        plain = unaccent(value)
        for ending, nucleus, black_shift in specs:
            if plain.endswith(unaccent(ending)):
                start = len(value) - len(ending)
                return value[start:start + len(nucleus)], black_shift
        return None, False

    if key == "ind_present":
        endings = {
            "ar": ((), (("as", "a", False),), (("a", "a", False),), (("amos", "a", False),), (("an", "a", False),)),
            "er": ((), (("es", "e", False),), (("e", "e", False),), (("emos", "e", False),), (("en", "e", False),)),
            "ir": ((), (("es", "e", False),), (("e", "e", False),), (("imos", "i", False),), (("en", "e", False),)),
        }
        return match(endings[cls][index])

    if key == "ind_preterite":
        ar_endings = {
            0: (),
            1: (("aste", "a", False), ("iste", "i", False)),
            2: (),
            3: (("amos", "a", False), ("imos", "i", False)),
            4: (("aron", "a", False), ("ieron", "i", False)),
        }
        ir_endings = {
            0: (("í", "í", False),),
            1: (("iste", "i", False),),
            2: (("ió", "i", False),),
            3: (("imos", "i", False),),
            4: (("ieron", "i", False),),
        }
        return match((ar_endings if cls == "ar" else ir_endings)[index])

    if key == "ind_imperfect":
        endings = {
            0: (("aba", "aba", False), ("ía", "ía", False), ("era", "era", False), ("iba", "iba", False)),
            1: (("abas", "aba", False), ("ías", "ía", False), ("eras", "era", False), ("ibas", "iba", False)),
            2: (("aba", "aba", False), ("ía", "ía", False), ("era", "era", False), ("iba", "iba", False)),
            3: (("ábamos", "ába", True), ("íamos", "ía", False), ("éramos", "éra", True), ("íbamos", "íba", True)),
            4: (("aban", "aba", False), ("ían", "ía", False), ("eran", "era", False), ("iban", "iba", False)),
        }
        return match(endings[index])

    if key == "ind_future":
        return None, False

    if key == "ind_conditional":
        endings = {
            0: (("ía", "ía", False),),
            1: (("ías", "ía", False),),
            2: (("ía", "ía", False),),
            3: (("íamos", "ía", False),),
            4: (("ían", "ía", False),),
        }
        return match(endings[index])

    if key == "subj_present":
        vowel = "e" if cls == "ar" else "a"
        endings = {
            0: ((vowel, vowel, False),),
            1: ((vowel + "s", vowel, False),),
            2: ((vowel, vowel, False),),
            3: ((vowel + "mos", vowel, False),),
            4: ((vowel + "n", vowel, False),),
        }
        return match(endings[index])

    subjunctive_nuclei = {
        "subj_ra": ("iera", "ara", "era"),
        "subj_se": ("iese", "ase", "ese"),
        "subj_future": ("iere", "are", "ere"),
    }
    if key in subjunctive_nuclei:
        for nucleus in subjunctive_nuclei[key]:
            if index in (0, 2):
                ending = nucleus
                visible_nucleus = nucleus
            elif index == 1:
                ending = nucleus + "s"
                visible_nucleus = nucleus
            elif index == 3:
                visible_nucleus = acute_final_vowel(nucleus[:-2]) + nucleus[-2:]
                ending = visible_nucleus + "mos"
            else:
                ending = nucleus + "n"
                visible_nucleus = nucleus
            matched, _ = match(((ending, visible_nucleus, index == 3),))
            if matched:
                return matched, index == 3

    if key == "imperative":
        vowel = ("a", "e", "e", "e") if cls == "ar" else ("e", "a", "a", "a")
        tails = ("", "", "mos", "n")
        return match(((vowel[index] + tails[index], vowel[index], False),))

    return None, False


def highlight_form(value: str, key: str, cls: str, index: int) -> str:
    nucleus, shift = surface_nucleus(value, key, cls, index)
    if not nucleus:
        return escape(value)
    position = value.rfind(nucleus)
    if position < 0:
        # Accent-insensitive fallback keeps the visible spelling intact.
        plain_value, plain_nucleus = unaccent(value), unaccent(nucleus)
        plain_position = plain_value.rfind(plain_nucleus)
        if plain_position < 0 or len(plain_value) != len(value):
            return escape(value)
        position = plain_position
        nucleus = value[position:position + len(nucleus)]
    before, after = value[:position], value[position + len(nucleus):]
    return escape(before) + styled_pattern(nucleus, shift) + escape(after)


def cell(
    forms: dict[str, object], key: str, index: int, css_class: str,
    *, group_start: bool = False,
) -> str:
    unavailable = forms.get("_unavailable", {}).get(key, [])
    if index in unavailable:
        classes = [css_class, "unavailable"]
        if group_start:
            classes.append("group-start")
        return f'<td class="{" ".join(classes)}" aria-label="forma no disponible">—</td>'
    value = forms[key][index]
    mark = None if is_variants(value) else mark_for(forms, key, index)
    classes = [css_class]
    if group_start:
        classes.append("group-start")
    attrs = ""
    prefix = ""
    if mark:
        classes.append("is-irregular" if mark["kind"] == "irregular" else "is-orthographic")
        attrs = f' data-reason="{escape(mark["reason"], quote=True)}" title="{escape(mark["reason"], quote=True)}"'
        prefix = f'<span class="sr-only">{"forma irregular" if mark["kind"] == "irregular" else "ajuste ortográfico"}: </span>'
    cls = verb_class(forms["infinitive"])
    if is_variants(value):
        content = render_variants(value, lambda text: highlight_form(text, key, cls, index))
    else:
        content = highlight_form(value, key, cls, index)
    return f'<td class="{" ".join(classes)}"{attrs}>{prefix}{content}</td>'


HEADER_BASE_OVERRIDES: dict[tuple[int, str], tuple[str, ...]] = {
    (75, "ind_preterite"): ("mur",),
    (75, "subj_present"): ("muer", "mur"),
    (78, "ind_preterite"): ("fri",),
    (79, "ind_preterite"): ("provey",),
    (80, "ind_preterite"): ("elig",),
}

HEADER_TEXT_OVERRIDES: dict[tuple[int, str], str] = {
    (19, "ind_preterite"): "tema cay- · superficie: ca- + núcleo i → y ante o/eron",
    (21, "ind_preterite"): "e → i · ceñ- + núcleo i · ciñ- + ∅ ante o/eron",
    (24, "ind_preterite"): "tema construy- · superficie: constru- + núcleo i → y ante o/eron",
    (26, "ind_preterite"): "raíz d- · núcleo i",
    (30, "ind_preterite"): "o → u en terceras personas · dorm-/durm- + núcleo i",
    (33, "ind_preterite"): "e → i en terceras personas · ergu-/irgu- + núcleo i",
    (36, "ind_present"): "formas he / ha / hay / hemos / han",
    (38, "ind_present"): "formas supletivas voy / va- / vamos",
    (39, "ind_preterite"): "g → gu ante e (yo jugué) · demás: jug- + núcleo a",
    (40, "ind_preterite"): "tema ley- · superficie: le- + núcleo i → y ante o/eron",
    (43, "ind_preterite"): "mull- + núcleo i · i → ∅ ante o/eron",
    (44, "ind_preterite"): "tema oy- · superficie: o- + núcleo i → y ante o/eron",
    (46, "ind_preterite"): "e → i en terceras personas · ped-/pid- + núcleo i",
    (57, "ind_preterite"): "tema roy- · superficie: ro- + núcleo i → y ante o/eron",
    (60, "ind_preterite"): "e → i en terceras personas · sent-/sint- + núcleo i",
    (61, "ind_present"): "formas supletivas soy / er- / es / som- / son",
    (62, "ind_preterite"): "tema sonri- · superficie: sonre- + núcleo í · sonr- + núcleo i ante o/eron",
    (63, "ind_preterite"): "tañ- + núcleo i · i → ∅ ante o/eron",
    (68, "ind_present"): "forma veo · demás: v- + núcleo e",
    (68, "ind_preterite"): "raíz v- · núcleo i",
    (75, "ind_preterite"): "o → u en terceras personas · mor-/mur- + núcleo i",
    (78, "ind_preterite"): "tema fri- · superficie: fre- + núcleo í · fr- + núcleo i ante o/eron · frio sin tilde",
    (79, "ind_preterite"): "tema provey- · superficie: prove- + núcleo i → y ante o/eron",
    (80, "ind_preterite"): "e → i en terceras personas · eleg-/elig- + núcleo i",
}

PRESERVE_PRESENT_NUCLEUS_ACCENT = {44, 62, 78}


def inferred_base(value: str, key: str, cls: str, index: int) -> str | None:
    """Recover the visible base without pretending the black person material is
    part of it.  This is used only for the compact explanatory line in a header.
    """
    nucleus, _ = surface_nucleus(value, key, cls, index)
    if nucleus:
        position = value.rfind(nucleus)
        if position >= 0:
            return value[:position]

    fallback_suffixes: dict[str, tuple[tuple[str, ...], ...]] = {
        "ind_present": (
            ("oy", "o"), ("as", "es"), ("a", "e"),
            ("amos", "emos", "imos"), ("an", "en"),
        ),
        "ind_preterite": (
            ("é", "í", "e", "i"), ("aste", "iste"), ("ó", "o", "e"),
            ("amos", "imos"), ("ieron", "aron", "eron"),
        ),
        "ind_future": tuple((suffix,) for suffix in ("é", "ás", "á", "emos", "án")),
    }
    rows = fallback_suffixes.get(key)
    if rows:
        for suffix in rows[index]:
            if value.endswith(suffix) and len(value) > len(suffix):
                return value[:-len(suffix)]
    return None


def present_surface_formula(
    candidates: list[tuple[str, int]], key: str, cls: str,
    *, preserve_acute: bool = False,
) -> str:
    """Describe only base+nucleus pairings that actually occur on the page."""
    groups: list[tuple[str, list[str]]] = []
    for candidate, index in candidates:
        nucleus, _ = surface_nucleus(candidate, key, cls, index)
        if not nucleus:
            continue
        position = candidate.rfind(nucleus)
        base = candidate[:position] if position >= 0 else ""
        if not base or not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", base):
            continue
        normalized_nucleus = nucleus if preserve_acute else unaccent(nucleus)
        group = next((item for item in groups if item[0] == normalized_nucleus), None)
        if group is None:
            group = (normalized_nucleus, [])
            groups.append(group)
        if base not in group[1]:
            group[1].append(base)

    if not groups:
        return ""
    if all(group[1] == groups[0][1] for group in groups[1:]):
        bases = "/".join(f"{base}-" for base in groups[0][1])
        nuclei = "/".join(group[0] for group in groups)
        return f"{bases} + núcleo {nuclei}"
    return " · ".join(
        f'{"/".join(f"{base}-" for base in bases)} + núcleo {nucleus}'
        for nucleus, bases in groups
    )


def key_text(
    family: Family, forms: dict[str, object], key: str, *, allow_overrides: bool = True,
) -> str:
    if allow_overrides and (family.number, key) in HEADER_TEXT_OVERRIDES:
        return HEADER_TEXT_OVERRIDES[(family.number, key)]
    cls = verb_class(family.lemma)
    stem = unaccent(family.lemma)[:-2]
    default = {
        "ind_present": f"{stem}- + vocal/persona",
        "ind_preterite": f"{stem}- + {'a' if cls == 'ar' else 'i'}",
        "ind_imperfect": f"{stem}- + {'aba' if cls == 'ar' else 'ía'}",
        "ind_future": f"{unaccent(family.lemma)} +",
        "ind_conditional": f"{unaccent(family.lemma)} + ía",
        "subj_present": f"{stem}- + {'e' if cls == 'ar' else 'a'}",
        "subj_ra": f"{stem}- + {'ara' if cls == 'ar' else 'iera'}",
        "subj_se": f"{stem}- + {'ase' if cls == 'ar' else 'iese'}",
        "subj_future": f"{stem}- + {'are' if cls == 'ar' else 'iere'}",
    }[key]
    nucleus = {
        "ind_present": "a" if cls == "ar" else ("e/i" if cls == "ir" else "e"),
        "ind_preterite": "a" if cls == "ar" else "i",
        "ind_imperfect": "aba" if cls == "ar" else "ía",
        "ind_future": "terminación",
        "ind_conditional": "ía",
        "subj_present": "e" if cls == "ar" else "a",
        "subj_ra": "ara" if cls == "ar" else "iera",
        "subj_se": "ase" if cls == "ar" else "iese",
        "subj_future": "are" if cls == "ar" else "iere",
    }[key]
    sample_value: str | None = None
    sample_nucleus: str | None = None
    values = forms.get(key)
    all_candidates: list[tuple[str, int]] = []
    marked_candidates: list[tuple[str, int]] = []
    if isinstance(values, list):
        for index, value in enumerate(values):
            if is_variants(value):
                candidates = [(item["text"], item.get("kind")) for item in value]
                has_marked_variant = any(kind for _, kind in candidates)
                for candidate, _ in candidates:
                    all_candidates.append((candidate, index))
                    # A variant set is pedagogically meaningful as a whole: show
                    # both the ordinary and changed bases in the header.
                    if has_marked_variant:
                        marked_candidates.append((candidate, index))
            elif isinstance(value, str):
                all_candidates.append((value, index))
                if forms["marks"].get(key, {}).get(str(index)):
                    marked_candidates.append((value, index))

    samples = marked_candidates or all_candidates
    for candidate, index in samples:
        visible_nucleus, _ = surface_nucleus(candidate, key, cls, index)
        if visible_nucleus:
            sample_value, sample_nucleus = candidate, visible_nucleus
            break
    if sample_nucleus and not (key == "ind_present" and cls == "ir"):
        # -ía is the repeated nucleus itself in imperfect and conditional; its
        # acute is therefore colored and belongs in the header.  Other sampled
        # accents are person-specific spellings rather than the shared label.
        preserve_acute = key == "ind_conditional" or (key == "ind_imperfect" and sample_nucleus == "ía")
        nucleus = sample_nucleus if preserve_acute else unaccent(sample_nucleus)
    reasons: list[str] = []
    def add_reason(reason: str | None) -> None:
        if not reason:
            return
        for clause in re.split(r";\s*", reason):
            if clause and clause not in reasons:
                reasons.append(clause)
    for entry in forms["marks"].get(key, {}).values():
        add_reason(entry["reason"])
    if isinstance(values, list):
        for value in values:
            if is_variants(value):
                for item in value:
                    if item.get("kind"):
                        add_reason(item.get("reason"))
    if reasons:
        if key in {"ind_present", "subj_present"}:
            surface_formula = present_surface_formula(
                all_candidates, key, cls,
                preserve_acute=key == "ind_present" and family.number in PRESERVE_PRESENT_NUCLEUS_ACCENT,
            )
            if surface_formula:
                return " · ".join(reasons) + " · " + surface_formula
        base_override = HEADER_BASE_OVERRIDES.get((family.number, key)) if allow_overrides else None
        bases: list[str] = list(base_override) if base_override is not None else []
        reason_already_names_base = any(
            re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+-", reason)
            for reason in reasons
        )
        if base_override is None and not reason_already_names_base:
            for candidate, index in marked_candidates:
                base = inferred_base(candidate, key, cls, index)
                if (
                    base
                    and re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", base)
                    and base not in bases
                ):
                    bases.append(base)
        if not bases and not reason_already_names_base and sample_value and sample_nucleus:
            position = sample_value.rfind(sample_nucleus)
            if position > 0:
                bases.append(sample_value[:position])
        if not bases and not reason_already_names_base and stem:
            bases.append(stem)
        base_text = " · base " + " / ".join(f"{base}-" for base in bases[:4]) if bases else ""
        return " · ".join(reasons) + base_text + f" · núcleo {nucleus}"
    return default


def table_head(label: str, css_class: str, key: str, family: Family, forms: dict[str, object], *, group_start: bool = False) -> str:
    classes = [css_class]
    if group_start:
        classes.append("group-start")
    return f'<th class="{" ".join(classes)}" scope="col">{escape(label)}<span class="stem-key">{escape(key_text(family, forms, key))}</span></th>'


AUX = {
    "perfect": ["he", "has", "ha", "hemos", "han"],
    "pluperfect": ["había", "habías", "había", "habíamos", "habían"],
    "future_perfect": ["habré", "habrás", "habrá", "habremos", "habrán"],
    "conditional_perfect": ["habría", "habrías", "habría", "habríamos", "habrían"],
    "subj_perfect": ["haya", "hayas", "haya", "hayamos", "hayan"],
    "subj_pluperfect_ra": ["hubiera", "hubieras", "hubiera", "hubiéramos", "hubieran"],
    "subj_pluperfect_se": ["hubiese", "hubieses", "hubiese", "hubiésemos", "hubiesen"],
    "anterior": ["hube", "hubiste", "hubo", "hubimos", "hubieron"],
    "subj_future_perfect": ["hubiere", "hubieres", "hubiere", "hubiéremos", "hubieren"],
}


def aux_nucleus(aux_key: str, index: int) -> tuple[str, bool]:
    patterns = {
        "perfect": ["he", "ha", "ha", "he", "ha"],
        "pluperfect": ["había"] * 5,
        "future_perfect": ["habré", "habrá", "habrá", "habre", "habrá"],
        "conditional_perfect": ["habría"] * 5,
        "subj_perfect": ["haya"] * 5,
        "subj_pluperfect_ra": ["hubiera", "hubiera", "hubiera", "hubiéra", "hubiera"],
        "subj_pluperfect_se": ["hubiese", "hubiese", "hubiese", "hubiése", "hubiese"],
        "anterior": ["hube", "hubi", "hubo", "hubi", "hubie"],
        "subj_future_perfect": ["hubiere", "hubiere", "hubiere", "hubiére", "hubiere"],
    }
    return patterns[aux_key][index], index == 3 and aux_key in {"subj_pluperfect_ra", "subj_pluperfect_se", "subj_future_perfect"}


def highlighted_aux(aux_key: str, index: int) -> str:
    aux = AUX[aux_key][index]
    nucleus, black_shift = aux_nucleus(aux_key, index)
    position = aux.find(nucleus)
    if position < 0:
        return escape(aux)
    return escape(aux[:position]) + styled_pattern(nucleus, black_shift) + escape(aux[position + len(nucleus):])


def compound_text(aux: str, participle: str) -> str:
    return f"{aux} {participle}"


def compound_cell(forms: dict[str, object], aux_key: str, index: int, css_class: str, *, group_start: bool = False) -> str:
    if index in forms.get("_compound_unavailable", []):
        classes = [css_class, "unavailable"]
        if group_start:
            classes.append("group-start")
        return f'<td class="{" ".join(classes)}" aria-label="forma no disponible">—</td>'
    participle = forms["participle"]
    part_mark = None if is_variants(participle) else mark_for(forms, "participle")
    classes = [css_class]
    if group_start:
        classes.append("group-start")
    attrs = ""
    prefix = ""
    if part_mark and part_mark["kind"] == "irregular":
        classes.append("is-irregular")
        attrs = f' data-reason="{escape(part_mark["reason"], quote=True)}" title="{escape(part_mark["reason"], quote=True)}"'
        prefix = '<span class="sr-only">forma irregular: </span>'
    aux = AUX[aux_key][index]
    aux_html = highlighted_aux(aux_key, index)
    if is_variants(participle):
        content = render_variants(
            participle, lambda part: aux_html + " " + escape(part),
            styled_kinds={"irregular"},
        )
    else:
        content = aux_html + " " + escape(participle)
    return f'<td class="{" ".join(classes)}"{attrs}>{prefix}{content}</td>'


def nonfinite_cell(forms: dict[str, object], key: str, label: str) -> str:
    value = forms[key]
    mark = None if is_variants(value) else mark_for(forms, key)
    classes = ["nonfinite"]
    attrs = ""
    prefix = ""
    if mark:
        classes.append("is-irregular" if mark["kind"] == "irregular" else "is-orthographic")
        attrs = f' data-reason="{escape(mark["reason"], quote=True)}" title="{escape(mark["reason"], quote=True)}"'
        prefix = f'<span class="sr-only">{"forma irregular" if mark["kind"] == "irregular" else "ajuste ortográfico"}: </span>'
    content = render_variants(value, lambda text: escape(text)) if is_variants(value) else escape(value)
    return f'<tr><th scope="row">{escape(label)}</th><td class="{" ".join(classes)}"{attrs}>{prefix}{content}</td></tr>'


def page_shell(title: str, body: str, css: str, description: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(description, quote=True)}">
  <title>{escape(title)}</title>
  <style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def sources_section() -> str:
    items = "".join(f'<li><a href="{escape(url, quote=True)}">{escape(label)}</a></li>' for label, url in SOURCES)
    return f'<section class="sources"><h2>Fuentes y criterio</h2><ul class="source-links">{items}</ul></section>'


def form_texts(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if is_variants(value):
        return [item["text"] for item in value]
    return []


def selected_signature(family: Family, member: str, forms: dict[str, object]) -> str:
    """Keep the compact signature exact without leaking representative roots."""
    if member == family.lemma:
        return family.signature
    if family.number == 68:
        prefix = member[:-3]
        return f"{prefix}ve- / {prefix}vi- / {plain_value(forms['participle'])}"
    if family.number == 72:
        return f"{member[:-2]}- / {plain_value(forms['participle'])}"
    if family.number == 77:
        present_yo = forms["ind_present"][0]
        present_nos = forms["ind_present"][3]
        boot = present_yo[:-1] if isinstance(present_yo, str) else member[:-2]
        base = present_nos[:-4] if isinstance(present_nos, str) and present_nos.endswith("emos") else member[:-2]
        return f"{boot}- / {base}- / {plain_value(forms['participle'])}"
    if member.endswith(family.lemma):
        prefix = member[:-len(family.lemma)]
        signature = prefixed_reason(family.signature, prefix)
        source = paradigm(family)
        pairs: list[tuple[str, str]] = []
        for source_value, target_value in (
            (source["participle"], forms["participle"]),
            (source["ind_present"][0], forms["ind_present"][0]),
            (source["imperative"][0], forms["imperative"][0]),
        ):
            pairs.extend(zip(form_texts(source_value), form_texts(target_value)))
        for source_text, target_text in sorted(pairs, key=lambda pair: len(pair[0]), reverse=True):
            signature = re.sub(
                rf"(?<![\wáéíóúüñ]){re.escape(source_text)}(?![\wáéíóúüñ])",
                target_text,
                signature,
            )
        return signature
    return f"mismo patrón irregular que {family.lemma}"


def member_key_text(
    family: Family, member: str, forms: dict[str, object], key: str,
) -> str:
    """Member-aware compact header, including exceptional surface spellings."""
    if member == family.lemma:
        return key_text(family, forms, key)
    member_family = replace(family, lemma=member)
    if key != "ind_preterite":
        return key_text(member_family, forms, key, allow_overrides=False)

    n = family.number
    stem = unaccent(member)[:-2]
    spelling = spelling_rule(member)
    if spelling:
        first = forms["ind_preterite"][0]
        return f"yo {first} · demás: {stem}- + núcleo a"
    if n == 19:
        return f"tema {stem}y- · superficie: {stem}- + núcleo i → y ante o/eron"
    if n == 21:
        changed = replace_last(stem, "e", "i")
        return f"e → i · {stem}- + núcleo i · {changed}- + ∅ ante o/eron"
    if n == 24:
        text = f"tema {stem}y- · superficie: {stem}- + núcleo i → y ante o/eron"
        if member in {"fluir", "huir"}:
            text += f" · yo {forms['ind_preterite'][0]} sin tilde"
        return text
    if n == 32 and member in {"criar", "fiar", "guiar", "liar"}:
        return f"formas {forms['ind_preterite'][0]} / {forms['ind_preterite'][2]} sin tilde · demás: {stem}- + núcleo a"
    if n in {40, 44, 57}:
        return f"tema {stem}y- · superficie: {stem}- + núcleo i → y ante o/eron"
    if n in {43, 63}:
        return f"{stem}- + núcleo i · i → ∅ ante o/eron"
    if n in {46, 60, 80}:
        changed = replace_last(stem, "e", "i")
        return f"e → i en terceras personas · {stem}-/{changed}- + núcleo i"
    if n in {62, 78}:
        root = stem[:-1]
        theme = root + "i"
        text = f"tema {theme}- · superficie: {stem}- + núcleo í · {root}- + núcleo i ante o/eron"
        if member == "reír":
            text += " · rio sin tilde"
        return text
    if n == 68:
        base = member[:-2]
        return f"raíz {base}- · núcleo i · tilde en {forms['ind_preterite'][0]} / {forms['ind_preterite'][2]}"
    return key_text(member_family, forms, key, allow_overrides=False)


def render_member_view(family: Family, member: str, forms: dict[str, object]) -> dict[str, object]:
    """Pre-render one exact member view for deterministic local-file swapping."""
    header_keys = (
        "ind_present", "ind_preterite", "ind_imperfect", "ind_future",
        "ind_conditional", "subj_present", "subj_ra", "subj_se", "subj_future",
    )
    headers = {key: member_key_text(family, member, forms, key) for key in header_keys}

    indicator_rows: list[str] = []
    for i, person in enumerate(PERSONS):
        indicator_rows.append(
            f'<tr><th scope="row">{person}</th>'
            + cell(forms, "ind_present", i, "present")
            + cell(forms, "ind_preterite", i, "preterite", group_start=True)
            + cell(forms, "ind_imperfect", i, "imperfect", group_start=True)
            + cell(forms, "ind_future", i, "future", group_start=True)
            + cell(forms, "ind_conditional", i, "conditional", group_start=True)
            + "</tr>"
        )

    subj_rows: list[str] = []
    for i, person in enumerate(PERSONS):
        subj_rows.append(
            f'<tr><th scope="row">{person}</th>'
            + cell(forms, "subj_present", i, "subjunctive")
            + cell(forms, "subj_ra", i, "subjunctive", group_start=True)
            + cell(forms, "subj_se", i, "subjunctive", group_start=True)
            + "</tr>"
        )

    compound_rows: list[str] = []
    for i, person in enumerate(PERSONS):
        compound_rows.append(
            f'<tr><th scope="row">{person}</th>'
            + compound_cell(forms, "perfect", i, "present")
            + compound_cell(forms, "pluperfect", i, "imperfect")
            + compound_cell(forms, "future_perfect", i, "future")
            + compound_cell(forms, "conditional_perfect", i, "conditional")
            + compound_cell(forms, "subj_perfect", i, "compound-sub", group_start=True)
            + compound_cell(forms, "subj_pluperfect_ra", i, "compound-sub")
            + compound_cell(forms, "subj_pluperfect_se", i, "compound-sub")
            + "</tr>"
        )

    command_rows = "".join(
        f'<tr><th scope="row">{person}</th>{cell(forms, "imperative", i, "affirmative")}</tr>'
        for i, person in enumerate(COMMAND_PERSONS)
    )

    participle = forms["participle"]
    part_mark = None if is_variants(participle) else mark_for(forms, "participle")
    compound_nf_class = "nonfinite is-irregular" if part_mark and part_mark["kind"] == "irregular" else "nonfinite"
    compound_nf_reason = f' data-reason="{escape(part_mark["reason"], quote=True)}" title="{escape(part_mark["reason"], quote=True)}"' if part_mark and part_mark["kind"] == "irregular" else ""
    if is_variants(participle):
        infinitive_compound = render_variants(
            participle, lambda part: escape("haber " + part), styled_kinds={"irregular"}
        )
        gerund_compound = render_variants(
            participle, lambda part: escape("habiendo " + part), styled_kinds={"irregular"}
        )
    else:
        infinitive_compound = "haber " + escape(participle)
        gerund_compound = "habiendo " + escape(participle)
    infinitive_key = "infinitive_display" if "infinitive_display" in forms else "infinitive"
    nonfinite_rows = (
        nonfinite_cell(forms, infinitive_key, "Infinitivo")
        + nonfinite_cell(forms, "gerund", "Gerundio")
        + nonfinite_cell(forms, "participle", "Participio")
        + f'<tr><th scope="row">Infinitivo compuesto</th><td class="{compound_nf_class}"{compound_nf_reason}>{infinitive_compound}</td></tr>'
        + f'<tr><th scope="row">Gerundio compuesto</th><td class="{compound_nf_class}"{compound_nf_reason}>{gerund_compound}</td></tr>'
    )

    rare_rows: list[str] = []
    for i, person in enumerate(PERSONS):
        rare_rows.append(
            f'<tr><th scope="row">{person}</th>'
            + compound_cell(forms, "anterior", i, "rare")
            + cell(forms, "subj_future", i, "rare", group_start=True)
            + compound_cell(forms, "subj_future_perfect", i, "rare")
            + "</tr>"
        )

    member_note = ""
    if member == "atañer":
        member_note = "Atañer solo se usa en formas no personales y en tercera persona; los guiones conservan esa defectividad en vez de completar el paradigma por analogía."

    description = (
        "Formas disponibles de atañer, verbo defectivo de la familia de tañer"
        if member == "atañer"
        else f"Conjugación completa de {member} dentro de la familia irregular de {family.lemma}"
    )

    return {
        "lemma": member,
        "title": f"{member} · conjugación irregular",
        "description": description,
        "signature": selected_signature(family, member, forms),
        "indicative_formula": member,
        "compound_formula": "haber + " + plain_value(forms["participle"]),
        "nonfinite_header": member,
        "member_note": member_note,
        "headers": headers,
        "bodies": {
            "indicative": "".join(indicator_rows),
            "subjunctive": "".join(subj_rows),
            "compound": "".join(compound_rows),
            "command": command_rows,
            "nonfinite": nonfinite_rows,
            "rare": "".join(rare_rows),
        },
        "labels": {
            "indicative": f"Conjugación de {member} en indicativo",
            "subjunctive": f"Conjugación de {member} en subjuntivo",
            "compound": f"Tiempos compuestos de {member}",
            "command": f"Imperativo afirmativo de {member}",
            "nonfinite": f"Formas no personales de {member}",
            "rare": f"Formas raras de {member}",
        },
    }


def view_table_head(
    label: str, css_class: str, key: str, view: dict[str, object], *, group_start: bool = False,
) -> str:
    classes = [css_class]
    if group_start:
        classes.append("group-start")
    return (
        f'<th class="{" ".join(classes)}" scope="col">{escape(label)}'
        f'<span class="stem-key" data-header="{key}">{escape(view["headers"][key])}</span></th>'
    )


def render_member_switcher(family: Family, views: dict[str, dict[str, object]]) -> str:
    payload = json.dumps(
        {"initial": family.lemma, "members": views},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    return f"""
  <script type="application/json" id="family-data">{payload}</script>
  <script>
    (() => {{
      const dataNode = document.querySelector('#family-data');
      const buttons = [...document.querySelectorAll('[data-member-id]')];
      if (!dataNode || !buttons.length) return;
      const data = JSON.parse(dataNode.textContent);
      const bySlot = name => document.querySelector(`[data-slot="${{name}}"]`);
      const selectMember = member => {{
        const view = data.members[member];
        if (!view) return;
        bySlot('lemma').textContent = view.lemma;
        bySlot('signature').textContent = view.signature;
        bySlot('indicative-formula').textContent = view.indicative_formula;
        bySlot('compound-formula').textContent = view.compound_formula;
        bySlot('nonfinite-header').textContent = view.nonfinite_header;
        Object.entries(view.headers).forEach(([key, value]) => {{
          document.querySelector(`[data-header="${{key}}"]`).textContent = value;
        }});
        Object.entries(view.bodies).forEach(([key, value]) => {{
          document.querySelector(`[data-body="${{key}}"]`).innerHTML = value;
        }});
        Object.entries(view.labels).forEach(([key, value]) => {{
          document.querySelector(`[data-table="${{key}}"]`).setAttribute('aria-label', value);
        }});
        const memberNote = bySlot('member-note');
        memberNote.textContent = view.member_note;
        memberNote.hidden = !view.member_note;
        document.title = view.title;
        document.querySelector('meta[name="description"]').setAttribute('content', view.description);
        buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.memberId === member)));
        document.querySelector('[data-member-live]').textContent = `Mostrando la conjugación de ${{view.lemma}}`;
      }};
      buttons.forEach(button => button.addEventListener('click', () => selectMember(button.dataset.memberId)));
    }})();
  </script>
"""


def render_family(
    family: Family, member_forms: dict[str, dict[str, object]], css: str,
) -> str:
    views = {
        member: render_member_view(family, member, member_forms[member])
        for member in family.members
    }
    view = views[family.lemma]
    if len(family.members) > 1:
        members = "".join(
            f'<li><button type="button" data-member-id="{escape(member, quote=True)}" aria-pressed="{str(member == family.lemma).lower()}">{escape(member)}</button></li>'
            for member in family.members
        )
        member_class = "member-list is-switcher"
    else:
        members = f"<li>{escape(family.lemma)}</li>"
        member_class = "member-list"
    note = f'<p class="family-note">{escape(family.note)}</p>' if family.note else ""
    switcher = render_member_switcher(family, views) if len(family.members) > 1 else ""

    if family.number <= 69:
        model_label = f"MODELO RAE {family.number}"
    elif family.number <= 74:
        model_label = "FAMILIA DE PARTICIPIO IRREGULAR"
    else:
        model_label = "SUBFAMILIA DE FIRMA COMPLETA"
    body = f"""
  <main>
    <header class="page-head">
      <div class="topline"><a class="back-link" href="index.html">← Índice de familias</a><span class="model-number">{model_label}</span></div>
      <h1 data-slot="lemma">{escape(view["lemma"])}</h1>
      <p class="signature" data-slot="signature">{escape(view["signature"])}</p>
      <p class="scope-note">Familia de conjugación del español estándar contemporáneo. Se muestran las cinco filas del cuadro latinoamericano: yo, tú, tercera persona singular, nosotros/as y tercera persona plural.</p>
      <div class="legend-row"><span><span class="swatch irregular"></span>rojo = irregularidad que se memoriza</span><span><span class="swatch orthographic"></span>ámbar = ajuste predecible de escritura/sonido</span><span><span class="pattern">subrayado</span> = núcleo repetido · color = tiempo</span><span>acento negro = desplazamiento en nosotros/as</span></div>
      <ul class="{member_class}" aria-label="Miembros frecuentes de la familia">{members}</ul>
      <p class="family-note member-status" data-slot="member-note" hidden></p>
      <p class="sr-only" data-member-live aria-live="polite" aria-atomic="true"></p>
      {note}
    </header>

    <section id="indicativo">
      <div class="section-head"><h2>Indicativo · tiempos simples</h2><p class="formula" data-slot="indicative-formula">{escape(view["indicative_formula"])}</p></div>
      <div class="table-wrap"><table class="indicative-table" data-table="indicative" aria-label="{escape(view["labels"]["indicative"], quote=True)}">
        <thead><tr><th class="person" rowspan="2" scope="col">Persona</th><th class="present strong" scope="col">Presente</th><th class="preterite strong group-start" scope="col">Pretérito</th><th class="imperfect strong group-start" scope="col">Imperfecto</th><th class="future strong group-start" scope="col">Futuro</th><th class="conditional strong group-start" scope="col">Condicional</th></tr>
        <tr>{view_table_head("raíz + núcleo", "present", "ind_present", view)}{view_table_head("raíz + núcleo", "preterite", "ind_preterite", view, group_start=True)}{view_table_head("raíz + núcleo", "imperfect", "ind_imperfect", view, group_start=True)}{view_table_head("raíz + núcleo", "future", "ind_future", view, group_start=True)}{view_table_head("raíz + núcleo", "conditional", "ind_conditional", view, group_start=True)}</tr></thead>
        <tbody data-body="indicative">{view["bodies"]["indicative"]}</tbody>
      </table></div>
    </section>

    <section id="subjuntivo">
      <div class="section-head"><h2>Subjuntivo · tiempos simples</h2></div>
      <div class="table-wrap"><table class="subjunctive-table" data-table="subjunctive" aria-label="{escape(view["labels"]["subjunctive"], quote=True)}">
        <thead><tr><th class="person" rowspan="2" scope="col">Persona</th><th class="subjunctive strong" scope="col">Presente</th><th class="subjunctive strong group-start" scope="col">Imperfecto · -ra</th><th class="subjunctive strong group-start" scope="col">Imperfecto · -se</th></tr>
        <tr>{view_table_head("raíz + núcleo", "subjunctive", "subj_present", view)}{view_table_head("raíz + núcleo", "subjunctive", "subj_ra", view, group_start=True)}{view_table_head("raíz + núcleo", "subjunctive", "subj_se", view, group_start=True)}</tr></thead>
        <tbody data-body="subjunctive">{view["bodies"]["subjunctive"]}</tbody>
      </table></div>
    </section>

    <section id="compuestos">
      <div class="section-head"><h2>Tiempos compuestos</h2><p class="formula" data-slot="compound-formula">{escape(view["compound_formula"])}</p></div>
      <div class="table-wrap"><table class="compound-table" data-table="compound" aria-label="{escape(view["labels"]["compound"], quote=True)}">
        <thead><tr><th class="person" rowspan="2" scope="col">Persona</th><th class="compound-ind strong" colspan="4" scope="colgroup">Indicativo</th><th class="compound-sub strong group-start" colspan="3" scope="colgroup">Subjuntivo</th></tr>
        <tr><th class="present" scope="col">Pretérito perfecto<span class="stem-key">he / ha + participio</span></th><th class="imperfect" scope="col">Pluscuamperfecto<span class="stem-key">había + participio</span></th><th class="future" scope="col">Futuro perfecto<span class="stem-key">habré / habrá / habre + participio</span></th><th class="conditional" scope="col">Condicional perfecto<span class="stem-key">habría + participio</span></th><th class="compound-sub group-start" scope="col">Pretérito perfecto<span class="stem-key">haya + participio</span></th><th class="compound-sub" scope="col">Pluscuamperfecto · -ra<span class="stem-key">hubiera + participio</span></th><th class="compound-sub" scope="col">Pluscuamperfecto · -se<span class="stem-key">hubiese + participio</span></th></tr></thead>
        <tbody data-body="compound">{view["bodies"]["compound"]}</tbody>
      </table></div>
    </section>

    <section class="paired-tables" aria-label="Imperativo y formas no personales">
      <div class="table-card" id="imperativo"><h2>Imperativo</h2><div class="table-wrap"><table class="command-table" data-table="command" aria-label="{escape(view["labels"]["command"], quote=True)}"><thead><tr><th class="person" scope="col">Persona</th><th class="affirmative strong" scope="col">Afirmativo<span class="stem-key">forma completa</span></th></tr></thead><tbody data-body="command">{view["bodies"]["command"]}</tbody></table></div><p class="command-rule"><strong>Negativo:</strong> no + <strong>presente de subjuntivo</strong></p></div>
      <div class="table-card" id="no-personales"><h2>Formas no personales</h2><div class="table-wrap"><table class="nonfinite-table" data-table="nonfinite" aria-label="{escape(view["labels"]["nonfinite"], quote=True)}"><thead><tr><th class="person" scope="col">Forma</th><th class="nonfinite strong" scope="col"><span data-slot="nonfinite-header">{escape(view["nonfinite_header"])}</span><span class="stem-key">simple / compuesta</span></th></tr></thead><tbody data-body="nonfinite">{view["bodies"]["nonfinite"]}</tbody></table></div></div>
    </section>

    <section class="rare-section" id="formas-raras">
      <div class="section-head"><h2>Formas raras o históricas</h2><p class="formula">compuestos: haber + participio</p></div>
      <div class="table-wrap"><table class="rare-table" data-table="rare" aria-label="{escape(view["labels"]["rare"], quote=True)}"><thead><tr><th class="person" rowspan="2" scope="col">Persona</th><th class="rare strong" scope="colgroup">Indicativo</th><th class="rare strong group-start" colspan="2" scope="colgroup">Subjuntivo</th></tr><tr><th class="rare" scope="col">Pretérito anterior<span class="stem-key">hube / hubi- / hubo / hubie-</span></th>{view_table_head("Futuro", "rare", "subj_future", view, group_start=True)}<th class="rare" scope="col">Futuro perfecto<span class="stem-key">hubiere + participio</span></th></tr></thead><tbody data-body="rare">{view["bodies"]["rare"]}</tbody></table></div>
    </section>
    {sources_section()}
  </main>
  {switcher}
"""
    return page_shell(view["title"], body, css, view["description"])


def render_index(css: str) -> str:
    grouped: dict[str, list[Family]] = {}
    for family in FAMILIES:
        grouped.setdefault(family.category, []).append(family)

    category_order = [
        "Paradigmas especiales", "Familias mixtas", "Alternancias vocálicas",
        "Presente especial", "Presente y gerundio", "Acentuación vocálica",
        "Pretéritos fuertes", "Variantes de paradigma", "Participios irregulares",
        "Ajustes fonológicos",
    ]
    sections = []
    for category in category_order:
        families = grouped.get(category, [])
        if not families:
            continue
        cards = []
        for family in families:
            search = " ".join((family.lemma, family.title, family.signature, *family.members)).lower()
            member_preview = " · ".join(family.members[:6]) + ("…" if len(family.members) > 6 else "")
            if family.number <= 69:
                model_label = f"RAE #{family.number}"
            elif family.number <= 74:
                model_label = "participio"
            else:
                model_label = "subfamilia"
            cards.append(
                f'<article class="family-card" data-family-card data-search="{escape(search, quote=True)}">'
                f'<h3><a href="{family.filename}">{escape(family.lemma)}</a> <span class="model-number">{model_label}</span></h3>'
                f'<p class="mini-signature">{escape(family.signature)}</p><p>{escape(member_preview)}</p></article>'
            )
        sections.append(f'<section><div class="section-head"><h2>{escape(category)}</h2><p class="formula">{len(families)} familias</p></div><div class="family-grid">{"".join(cards)}</div></section>')

    controls = " · ".join(f"{number} {lemma}" for number, lemma in EXCLUDED_CONTROLS.items())
    body = f"""
  <main class="index-main">
    <header class="page-head index-intro">
      <div>
        <a class="back-link" href="../spanish-conjugation-chart.html">← Terminaciones regulares</a>
        <h1>Familias irregulares del español</h1>
        <p class="signature">modelos académicos · español latinoamericano · tú/usted/ustedes</p>
        <p class="scope-note">Cobertura: todos los modelos no regulares o impredecibles de RAE/ASALE (4–69), las cinco familias cuyo único cambio está en el participio y siete subfamilias separadas porque añaden otro participio o imperativo. Los derivados transparentes se agrupan con su modelo; la lista léxica no se presenta como cerrada porque la prefijación sigue siendo productiva.</p>
      </div>
      <div class="count-box">{len(FAMILIES)} páginas de familia<br>{sum(len(f.members) for f in FAMILIES)} verbos frecuentes indexados<br>5 personas por paradigma</div>
    </header>
    <div class="legend-row"><span><span class="swatch irregular"></span>rojo = irregularidad que se memoriza</span><span><span class="swatch orthographic"></span>ámbar = ajuste predecible</span><span>gris = forma no disponible</span></div>
    <label class="sr-only" for="family-search">Buscar familia o verbo</label><input class="search-box" id="family-search" type="search" placeholder="Buscar: tener, e→ie, participio…" autocomplete="off">
    {''.join(sections)}
    <section><div class="section-head"><h2>Verbos defectivos</h2></div><div class="family-grid"><article class="family-card" data-family-card data-search="defectivos soler balbucir llover nevar acontecer acaecer atañer concernir"><h3><a href="defectivos.html">Formas restringidas</a></h3><p class="mini-signature">— = forma ausente o no usual</p><p>soler · balbucir · meteorológicos · terciopersonales…</p></article></div></section>
    <section><div class="section-head"><h2>Controles regulares no duplicados</h2></div><p class="control-note">Los modelos académicos {escape(controls)} sirven para fijar silabificación, acento o escritura, pero no contienen una irregularidad morfológica que deba ponerse en rojo. Por eso remiten al <a href="../spanish-conjugation-chart.html">cuadro regular</a> y no generan páginas engañosamente “irregulares”.</p></section>
    {sources_section()}
  </main>
  <script>
    const input = document.querySelector('#family-search');
    const cards = [...document.querySelectorAll('[data-family-card]')];
    input.addEventListener('input', () => {{
      const query = input.value.trim().toLocaleLowerCase('es');
      cards.forEach(card => {{ card.hidden = query && !card.dataset.search.includes(query); }});
      document.querySelectorAll('.family-grid').forEach(grid => {{
        const section = grid.closest('section');
        section.hidden = [...grid.children].every(card => card.hidden);
      }});
    }});
  </script>
"""
    return page_shell("Familias irregulares del español", body, css, "Índice de familias de conjugación irregular del español latinoamericano")


def render_defectives(css: str) -> str:
    rows = [
        ("soler", "presente e imperfecto", "Presente de indicativo/subjuntivo e imperfecto; también perfecto compuesto", "Futuro, condicional, pretérito simple e imperativo no son normales en el uso actual"),
        ("balbucir", "paradigma incompleto", "Formas documentadas fuera de los huecos; suele sustituirse por balbucear", "Faltan la 1.ª y la 3.ª personas del singular del presente de indicativo y todo el presente de subjuntivo"),
        ("atañer · concernir · competer", "uso terciopersonal", "Terceras personas, sobre todo en presente e imperfecto", "Las demás personas carecen normalmente de uso por su significado"),
        ("acaecer · acontecer", "uso terciopersonal", "Terceras personas; participios y formas no personales cuando el contexto los admite", "Otras personas son excepcionales"),
        ("llover · nevar · granizar", "meteorológicos", "Tercera persona singular en sentido literal", "Pueden hacerse personales en usos figurados: llovieron críticas"),
        ("arrecir · aterir · descolorir · embaír · manir · preterir", "defectividad morfofonológica", "Solo las formas asentadas en el uso", "No completar por analogía; son raros y varían por verbo"),
        ("garantir", "defectividad regional", "En Argentina y Uruguay se documenta el paradigma completo", "En el uso general suele evitar las formas sin i en la desinencia; garantizar es la alternativa extendida"),
        ("desvaír", "defectividad variable", "Se usa normalmente en las formas cuya desinencia empieza por i; también se documentan otras", "La extensión del paradigma fluctúa en el uso"),
        ("abolir", "ya no defectivo", "Paradigma completo y regular: abolo, aboles, abole…", "No usar *abuelo como forma de abolir"),
    ]
    body_rows = "".join(
        f'<tr><th scope="row">{escape(verb)}</th><td class="present">{escape(kind)}</td><td class="affirmative">{escape(used)}</td><td class="unavailable">{escape(restricted)}</td></tr>'
        for verb, kind, used, restricted in rows
    )
    source = "https://www.rae.es/gramática/morfología/verbos-irregulares-vi-verbos-defectivos"
    body = f"""
  <main>
    <header class="page-head"><div class="topline"><a class="back-link" href="index.html">← Índice de familias</a><span class="model-number">USO RESTRINGIDO</span></div><h1>Verbos defectivos</h1><p class="signature">no se inventan las formas que el uso no sostiene</p><p class="scope-note">La defectividad no es una sustitución de raíz. Por eso esta página conserva los huecos como información y no fuerza estos verbos dentro de una tabla completa.</p></header>
    <section><div class="section-head"><h2>Disponibilidad del paradigma</h2><p class="formula">— = no usual / no disponible</p></div><div class="table-wrap"><table class="defective-table" aria-label="Uso de los principales verbos defectivos"><thead><tr><th class="person" scope="col">Familia</th><th class="present strong" scope="col">Tipo</th><th class="affirmative strong" scope="col">Uso asentado</th><th class="nonfinite strong" scope="col">Restricción</th></tr></thead><tbody>{body_rows}</tbody></table></div></section>
    <section class="sources"><h2>Fuente específica</h2><ul class="source-links"><li><a href="{source}">RAE/ASALE · verbos defectivos</a></li></ul></section>
  </main>
"""
    return page_shell("Verbos defectivos del español", body, css, "Guía de uso y formas restringidas de los verbos defectivos")


def exportable_forms(forms: dict[str, object]) -> dict[str, object]:
    return {
        key: value for key, value in forms.items()
        if key != "marks" and key != "_headers"
    } | {"marks": forms["marks"]}


def main() -> None:
    original_before = sha256(REGULAR_CHART.read_bytes()).hexdigest()
    css = extract_base_css()
    manifest = {
        "scope": "RAE/ASALE models 4–69 with eight regular controls excluded, plus five participle-only and seven full-signature subfamilies",
        "persons": PERSONS,
        "families": [],
        "excluded_regular_controls": EXCLUDED_CONTROLS,
        "sources": [{"label": label, "url": url} for label, url in SOURCES],
    }

    for family in FAMILIES:
        member_forms = {
            member: member_paradigm(family, member)
            for member in family.members
        }
        forms = member_forms[family.lemma]
        html = render_family(family, member_forms, css)
        (ROOT / family.filename).write_text(nfc(html), encoding="utf-8")
        manifest["families"].append({
            "number": family.number,
            "lemma": family.lemma,
            "file": family.filename,
            "category": family.category,
            "signature": family.signature,
            "members": list(family.members),
            "note": family.note,
            "forms": exportable_forms(forms),
            "member_forms": {
                member: exportable_forms(member_forms[member])
                for member in family.members
            },
        })

    (ROOT / "index.html").write_text(nfc(render_index(css)), encoding="utf-8")
    (ROOT / "defectivos.html").write_text(nfc(render_defectives(css)), encoding="utf-8")
    (ROOT / "atlas-data.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    original_after = sha256(REGULAR_CHART.read_bytes()).hexdigest()
    if original_before != original_after:
        raise RuntimeError("The regular chart changed during generation")
    print(f"Generated {len(FAMILIES)} family pages + index + defectives")
    print(f"Regular chart SHA-256 unchanged: {original_after}")


if __name__ == "__main__":
    main()
