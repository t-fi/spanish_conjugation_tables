#!/usr/bin/env python3
"""Deterministic structural and linguistic checks for the generated atlas."""

from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import importlib.util
import json
import re
import sys
import unicodedata


ROOT = Path(__file__).resolve().parent
REGULAR = ROOT.parent / "spanish-conjugation-chart.html"
REGULAR_SHA256 = "92b4f72cb23b137ae8af473de28c66824281909a230334973899a3dce773f0e6"
EXCLUDED_CONTROLS = {6, 11, 12, 15, 16, 20, 22, 47}
OFFICIAL_MODELS = set(range(4, 70)) - EXCLUDED_CONTROLS
EXTRA_FAMILIES = set(range(70, 82))
PERSON_KEYS = (
    "ind_present", "ind_preterite", "ind_imperfect", "ind_future",
    "ind_conditional", "subj_present", "subj_ra", "subj_se", "subj_future",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_generator():
    spec = importlib.util.spec_from_file_location("atlas_generator", ROOT / "generate.py")
    require(spec is not None and spec.loader is not None, "cannot load generator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def variant_texts(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    require(isinstance(value, list), f"unexpected form value {value!r}")
    texts = []
    for item in value:
        require(isinstance(item, dict) and isinstance(item.get("text"), str), f"bad variant {item!r}")
        texts.append(item["text"])
    return texts


def acute_final_vowel(value: str) -> str:
    replacements = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}
    require(value[-1] in replacements, f"cannot accent {value!r}")
    return value[:-1] + replacements[value[-1]]


class PageAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.hrefs: list[str] = []
        self.table_rows: dict[str, int] = {}
        self.table_cells: dict[str, list[str]] = {}
        self._table: str | None = None
        self._tbody = False
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if data.get("id"):
            self.ids.append(data["id"])
        if tag == "a" and data.get("href"):
            self.hrefs.append(data["href"])
        if tag == "table":
            classes = (data.get("class") or "").split()
            self._table = next((name for name in classes if name.endswith("-table")), "table")
            self.table_rows.setdefault(self._table, 0)
            self.table_cells.setdefault(self._table, [])
        elif tag == "tbody" and self._table:
            self._tbody = True
        elif tag == "tr" and self._table and self._tbody:
            self.table_rows[self._table] += 1
        elif tag == "td" and self._table:
            self._in_cell = True
            self._cell_parts = []
        elif self._in_cell and tag == "span" and "sr-only" in (data.get("class") or "").split():
            self._skip_depth = 1
        elif self._skip_depth:
            self._skip_depth += 1

    def handle_data(self, data: str) -> None:
        if self._in_cell and not self._skip_depth:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "td" and self._in_cell and self._table:
            text = unicodedata.normalize("NFC", " ".join("".join(self._cell_parts).split()))
            self.table_cells[self._table].append(text)
            self._in_cell = False
            self._cell_parts = []
            return
        if tag == "tbody":
            self._tbody = False
        elif tag == "table":
            self._table = None
            self._tbody = False


def main() -> None:
    generator = load_generator()
    manifest = json.loads((ROOT / "atlas-data.json").read_text(encoding="utf-8"))
    families = manifest["families"]

    require(sha256(REGULAR.read_bytes()).hexdigest() == REGULAR_SHA256, "regular chart changed")
    require(len(families) == 70, f"expected 70 families, found {len(families)}")
    numbers = {family["number"] for family in families}
    require(numbers == OFFICIAL_MODELS | EXTRA_FAMILIES, "family-number coverage mismatch")
    require({int(key) for key in manifest["excluded_regular_controls"]} == EXCLUDED_CONTROLS, "control-model mismatch")
    require(len(manifest["sources"]) >= 3, "fewer than three sources")

    declared_files = {family["file"] for family in families}
    actual_family_files = {path.name for path in ROOT.glob("[0-9][0-9]-*.html")}
    require(declared_files == actual_family_files, "stale or missing family HTML")
    require(len(list(ROOT.glob("*.html"))) == 72, "expected 70 families + index + defectives")

    known = {
        "andar": {"ind_preterite": ["anduve", "anduviste", "anduvo", "anduvimos", "anduvieron"]},
        "decir": {"ind_preterite": ["dije", "dijiste", "dijo", "dijimos", "dijeron"], "participle": "dicho"},
        "ir": {"ind_imperfect": ["iba", "ibas", "iba", "íbamos", "iban"]},
        "ser": {"ind_imperfect": ["era", "eras", "era", "éramos", "eran"]},
        "satisfacer": {"ind_preterite": ["satisfice", "satisficiste", "satisfizo", "satisficimos", "satisficieron"], "participle": "satisfecho"},
        "tañer": {"ind_future": ["tañeré", "tañerás", "tañerá", "tañeremos", "tañerán"]},
        "ceñir": {"ind_future": ["ceñiré", "ceñirás", "ceñirá", "ceñiremos", "ceñirán"]},
    }

    # Goldens concentrate on places where productive prefixing is not enough:
    # spelling before e/a, modern monosyllabic accentuation, strong stems,
    # contracted futures, imperative stress and lexical participles.
    member_goldens = {
        "empezar": {"ind_preterite": {0: "empecé"}, "subj_present": {0: "empiece", 3: "empecemos"}},
        "negar": {"ind_preterite": {0: "negué"}, "subj_present": {0: "niegue", 3: "neguemos"}},
        "enraizar": {"ind_preterite": {0: "enraicé"}, "subj_present": {0: "enraíce", 3: "enraicemos"}},
        "huir": {"ind_preterite": {0: "hui", 2: "huyó"}, "participle": "huido"},
        "fluir": {"ind_preterite": {0: "flui", 2: "fluyó"}, "participle": "fluido"},
        "criar": {"ind_preterite": {0: "crie", 2: "crio"}},
        "guiar": {"ind_preterite": {0: "guie", 2: "guio"}},
        "erguir": {"subj_present": {3: ["yergamos", "irgamos"]}, "imperative": {2: ["yergamos", "irgamos"]}},
        "maldecir": {"ind_preterite": {0: "maldije", 4: "maldijeron"}, "participle": "maldecido"},
        "teñir": {"ind_preterite": {2: "tiñó", 4: "tiñeron"}, "gerund": "tiñendo"},
        "aducir": {"ind_present": {0: "aduzco"}, "ind_preterite": {4: "adujeron"}},
        "cocer": {"ind_present": {0: "cuezo"}, "subj_present": {0: "cueza", 3: "cozamos"}},
        "torcer": {"ind_present": {0: "tuerzo"}, "subj_present": {0: "tuerza", 3: "torzamos"}},
        "conseguir": {"ind_present": {0: "consigo", 1: "consigues"}, "subj_present": {0: "consiga"}},
        "corregir": {"ind_present": {0: "corrijo", 1: "corriges"}, "subj_present": {0: "corrija"}},
        "contradecir": {"ind_future": {0: ["contradeciré", "contradiré"]}, "participle": "contradicho"},
        "podrir": {"ind_present": {0: "pudro", 3: ["podrimos", "pudrimos"]}, "participle": "podrido"},
        "corroer": {"ind_present": {0: ["corroo", "corroigo", "corroyo"]}, "gerund": "corroyendo"},
        "reír": {"ind_preterite": {2: "rio", 4: "rieron"}, "subj_present": {3: "riamos"}, "gerund": "riendo"},
        "desleír": {"ind_preterite": {2: "deslió", 4: "deslieron"}, "gerund": "desliendo"},
        "componer": {"imperative": {0: "compón"}, "participle": "compuesto"},
        "mantener": {"imperative": {0: "mantén"}},
        "prevenir": {"imperative": {0: "prevén"}},
        "prever": {"ind_present": {1: "prevés", 2: "prevé", 4: "prevén"}, "ind_preterite": {0: "preví", 2: "previó"}, "imperative": {0: "prevé"}, "participle": "previsto"},
        "describir": {"participle": ["descrito", "descripto"]},
        "freír": {"ind_preterite": {2: "frio"}},
        "refreír": {"ind_preterite": {2: "refrió"}, "participle": ["refreído", "refrito"]},
        "disolver": {"ind_present": {0: "disuelvo", 3: "disolvemos"}, "participle": "disuelto"},
        "reelegir": {"ind_present": {0: "reelijo", 1: "reeliges"}, "participle": ["reelegido", "reelecto"]},
    }
    member_header_goldens = {
        "empezar": "yo empecé · demás: empez- + núcleo a",
        "negar": "yo negué · demás: neg- + núcleo a",
        "enraizar": "yo enraicé · demás: enraiz- + núcleo a",
        "fluir": "tema fluy- · superficie: flu- + núcleo i → y ante o/eron · yo flui sin tilde",
        "recaer": "tema recay- · superficie: reca- + núcleo i → y ante o/eron",
        "teñir": "e → i · teñ- + núcleo i · tiñ- + ∅ ante o/eron",
        "creer": "tema crey- · superficie: cre- + núcleo i → y ante o/eron",
        "reír": "tema ri- · superficie: re- + núcleo í · r- + núcleo i ante o/eron · rio sin tilde",
        "refreír": "tema refri- · superficie: refre- + núcleo í · refr- + núcleo i ante o/eron",
        "reelegir": "e → i en terceras personas · reeleg-/reelig- + núcleo i",
    }
    signature_goldens = {
        "reabrir": "reabr- / reabierto",
        "absolver": "absuelv- / absolv- / absuelto",
        "refreír": "refrí- / refri- / refre- / refrito",
        "reelegir": "reelij- / reelig- / reeleg- / reelecto",
        "prever": "preve- / previ- / previsto",
    }

    expected_rows = {
        "indicative-table": 5,
        "subjunctive-table": 5,
        "compound-table": 5,
        "command-table": 4,
        "nonfinite-table": 5,
        "rare-table": 5,
    }
    future_suffixes = ("é", "ás", "á", "emos", "án")
    conditional_suffixes = ("ía", "ías", "ía", "íamos", "ían")

    for family in families:
        lemma = family["lemma"]
        forms = family["forms"]
        require(unicodedata.is_normalized("NFC", json.dumps(family, ensure_ascii=False)), f"non-NFC data in {lemma}")
        for key in PERSON_KEYS:
            require(isinstance(forms[key], list) and len(forms[key]) == 5, f"{lemma}: {key} does not have five forms")
        require(isinstance(forms["imperative"], list) and len(forms["imperative"]) == 4, f"{lemma}: imperative size")

        plural = variant_texts(forms["ind_preterite"][4])[0]
        require(plural.endswith("ron"), f"{lemma}: bad preterite plural")
        base = plural[:-3]
        accented = acute_final_vowel(base)
        require(forms["subj_ra"] == [base + "ra", base + "ras", base + "ra", accented + "ramos", base + "ran"], f"{lemma}: -ra derivation")
        require(forms["subj_se"] == [base + "se", base + "ses", base + "se", accented + "semos", base + "sen"], f"{lemma}: -se derivation")
        require(forms["subj_future"] == [base + "re", base + "res", base + "re", accented + "remos", base + "ren"], f"{lemma}: future-subjunctive derivation")

        for index in range(5):
            future_stems = {text[:-len(future_suffixes[index])] for text in variant_texts(forms["ind_future"][index]) if text.endswith(future_suffixes[index])}
            conditional_stems = {text[:-len(conditional_suffixes[index])] for text in variant_texts(forms["ind_conditional"][index]) if text.endswith(conditional_suffixes[index])}
            require(future_stems and future_stems == conditional_stems, f"{lemma}: future/conditional stem mismatch at row {index}")

        for imperative_index, subjunctive_index in ((1, 2), (2, 3), (3, 4)):
            imperative_forms = set(variant_texts(forms["imperative"][imperative_index]))
            subjunctive_forms = set(variant_texts(forms["subj_present"][subjunctive_index]))
            require(subjunctive_forms <= imperative_forms, f"{lemma}: imperative/subjunctive mismatch")

        for key, marks in forms["marks"].items():
            require(key in forms, f"{lemma}: mark for unknown key {key}")
            for index, mark in marks.items():
                require(index == "value" or index.isdigit(), f"{lemma}: malformed mark index")
                require(mark.get("kind") in {"irregular", "orthographic"} and mark.get("reason"), f"{lemma}: incomplete mark")

        for key in ("subj_ra", "subj_se", "subj_future"):
            html = generator.highlight_form(forms[key][3], key, generator.verb_class(lemma), 3)
            require(html.count('class="shift-accent"') == 1, f"{lemma}: missing black nosotros accent in {key}")
        for imperfect_form in variant_texts(forms["ind_imperfect"][3]):
            imperfect_html = generator.highlight_form(imperfect_form, "ind_imperfect", generator.verb_class(lemma), 3)
            if imperfect_form.endswith(("ábamos", "éramos", "íbamos")):
                require(imperfect_html.count('class="shift-accent"') == 1, f"{lemma}: missing imperfect stress shift")
            else:
                require('class="shift-accent"' not in imperfect_html, f"{lemma}: recurring -ía accent made black")

        path = ROOT / family["file"]
        html = path.read_text(encoding="utf-8")
        require(unicodedata.is_normalized("NFC", html), f"{lemma}: non-NFC HTML")
        require(not re.search(r"\bvosotros\b|\bvos\b", html, re.I), f"{lemma}: non-Latin-American person leaked")
        require("jieron" not in html, f"{lemma}: invalid j-stem plural")
        require("cenir" not in html and ">taner<" not in html, f"{lemma}: ñ lost")
        parser = PageAudit()
        parser.feed(html)
        require(len(parser.ids) == len(set(parser.ids)), f"{lemma}: duplicate HTML id")
        require(parser.table_rows == expected_rows, f"{lemma}: table row structure {parser.table_rows}")
        for href in parser.hrefs:
            if re.match(r"^[a-z]+:", href) or href.startswith("#"):
                continue
            require((path.parent / href.split("#", 1)[0]).exists(), f"{lemma}: broken link {href}")

        member_forms = family.get("member_forms")
        require(isinstance(member_forms, dict), f"{lemma}: member paradigms missing")
        require(set(member_forms) == set(family["members"]), f"{lemma}: member paradigm set mismatch")
        require(member_forms[lemma] == forms, f"{lemma}: representative/member data diverged")

        payload_match = re.search(
            r'<script type="application/json" id="family-data">(.*?)</script>',
            html,
            re.S,
        )
        button_count = len(re.findall(r'<button\b[^>]*\bdata-member-id=', html))
        expected_buttons = len(family["members"]) if len(family["members"]) > 1 else 0
        require(button_count == expected_buttons, f"{lemma}: member button count {button_count}")
        pressed_count = len(re.findall(r'<button\b[^>]*\baria-pressed="true"', html))
        require(pressed_count == (1 if expected_buttons else 0), f"{lemma}: pressed-button state")
        payload = None
        if expected_buttons:
            require(payload_match is not None, f"{lemma}: family payload missing")
            payload_text = payload_match.group(1)
            require("<" not in payload_text, f"{lemma}: unsafe literal markup in JSON script")
            payload = json.loads(payload_text)
            require(payload["initial"] == lemma, f"{lemma}: wrong initial payload member")
            require(set(payload["members"]) == set(family["members"]), f"{lemma}: payload member set mismatch")
        else:
            require(payload_match is None, f"{lemma}: singleton carries dead switching payload")
        require(len(re.findall(r'<tbody\b[^>]*\bdata-body=', html)) == 6, f"{lemma}: dynamic table-body slots")
        require(len(re.findall(r'<table\b[^>]*\bdata-table=', html)) == 6, f"{lemma}: dynamic table-label slots")
        require("addEventListener('click'" in html if expected_buttons else True, f"{lemma}: click handler missing")

        family_object = next(item for item in generator.FAMILIES if item.lemma == lemma)
        for member in family["members"]:
            target = member_forms[member]
            require(target["infinitive"] == member, f"{lemma}/{member}: wrong infinitive identity")
            require(unicodedata.is_normalized("NFC", json.dumps(target, ensure_ascii=False)), f"{lemma}/{member}: non-NFC data")
            for key in PERSON_KEYS:
                require(isinstance(target[key], list) and len(target[key]) == 5, f"{lemma}/{member}: {key} size")
            require(isinstance(target["imperative"], list) and len(target["imperative"]) == 4, f"{lemma}/{member}: imperative size")

            # Every ordinary member's past subjunctives come mechanically from
            # its own preterite plural.  Podrir is intentionally asymmetric:
            # its admitted podr- indicative variants do not create *podriera.
            if not (family["number"] == 53 and member == "podrir"):
                member_plural = variant_texts(target["ind_preterite"][4])[0]
                require(member_plural.endswith("ron"), f"{lemma}/{member}: bad preterite plural")
                member_base = member_plural[:-3]
                member_accented = acute_final_vowel(member_base)
                require(target["subj_ra"] == [member_base + "ra", member_base + "ras", member_base + "ra", member_accented + "ramos", member_base + "ran"], f"{lemma}/{member}: -ra derivation")
                require(target["subj_se"] == [member_base + "se", member_base + "ses", member_base + "se", member_accented + "semos", member_base + "sen"], f"{lemma}/{member}: -se derivation")
                require(target["subj_future"] == [member_base + "re", member_base + "res", member_base + "re", member_accented + "remos", member_base + "ren"], f"{lemma}/{member}: future-subjunctive derivation")

            for row in range(5):
                future_stems = {
                    text[:-len(future_suffixes[row])]
                    for text in variant_texts(target["ind_future"][row])
                    if text.endswith(future_suffixes[row])
                }
                conditional_stems = {
                    text[:-len(conditional_suffixes[row])]
                    for text in variant_texts(target["ind_conditional"][row])
                    if text.endswith(conditional_suffixes[row])
                }
                require(future_stems and future_stems == conditional_stems, f"{lemma}/{member}: future/conditional stem mismatch at {row}")

            unavailable = target.get("_unavailable", {})
            for imperative_index, subjunctive_index in ((1, 2), (2, 3), (3, 4)):
                if imperative_index in unavailable.get("imperative", []):
                    continue
                imperative_forms = set(variant_texts(target["imperative"][imperative_index]))
                subjunctive_forms = set(variant_texts(target["subj_present"][subjunctive_index]))
                require(subjunctive_forms <= imperative_forms, f"{lemma}/{member}: imperative/subjunctive mismatch")

            for mark_key, marks in target["marks"].items():
                require(mark_key in target, f"{lemma}/{member}: mark for unknown key {mark_key}")
                for mark_index, mark in marks.items():
                    require(mark_index == "value" or mark_index.isdigit(), f"{lemma}/{member}: malformed mark index")
                    require(mark.get("kind") in {"irregular", "orthographic"} and mark.get("reason"), f"{lemma}/{member}: incomplete mark")

            generated_view = generator.render_member_view(family_object, member, target)
            if payload is not None:
                require(payload["members"][member] == generated_view, f"{lemma}/{member}: payload/render divergence")
            if member in member_header_goldens:
                require(generated_view["headers"]["ind_preterite"] == member_header_goldens[member], f"{member}: member-aware preterite header mismatch")
            if member in signature_goldens:
                require(generated_view["signature"] == signature_goldens[member], f"{member}: selected signature mismatch")
            participles = variant_texts(target["participle"])
            for part in participles:
                require(f"haber {part}" in generated_view["bodies"]["nonfinite"], f"{lemma}/{member}: compound participle mismatch")
            require(member in generated_view["bodies"]["nonfinite"], f"{lemma}/{member}: infinitive missing from view")

            # A nontransparent member must not inherit the representative's
            # literal stem-key text.  Shared grammatical roots are generated
            # afresh, so this specifically catches cosmetic relabeling.
            if member != lemma and not member.endswith(lemma) and family["number"] != 53:
                representative_stem = generator.unaccent(lemma)[:-2] + "-"
                member_headers = " · ".join(generated_view["headers"].values())
                require(representative_stem not in member_headers, f"{lemma}/{member}: representative header leaked")

            for golden_key, golden in member_goldens.get(member, {}).items():
                actual = target[golden_key]
                if isinstance(golden, dict):
                    for golden_index, expected in golden.items():
                        value = actual[golden_index]
                        if isinstance(expected, list):
                            require(variant_texts(value) == expected, f"{member}: golden mismatch in {golden_key}[{golden_index}]")
                        else:
                            require(value == expected, f"{member}: golden mismatch in {golden_key}[{golden_index}]")
                elif isinstance(golden, list):
                    require(variant_texts(actual) == golden, f"{member}: golden mismatch in {golden_key}")
                else:
                    require(actual == golden, f"{member}: golden mismatch in {golden_key}")

            if member == "atañer":
                require(target.get("_unavailable", {}).get("imperative") == [0, 1, 2, 3], "atañer: imperative must remain unavailable")
                require('aria-label="forma no disponible">—' in generated_view["bodies"]["command"], "atañer: unavailable commands not rendered")
            if member in {"refreír", "sofreír", "reelegir"}:
                for item in target["participle"]:
                    if item.get("kind") == "irregular":
                        require(item["text"] in (item.get("reason") or ""), f"{member}: unprefixed participle reason leaked")

        if 70 <= family["number"] <= 74:
            require("FAMILIA DE PARTICIPIO IRREGULAR" in html, f"{lemma}: participle-only family mislabeled")
        if family["number"] == 53:
            require("principalmente en áreas de América" in html, "pudrir/podrir: regional qualification missing")
        if family["number"] == 66:
            require("uso extremadamente raro" in html, "revaler: rarity qualification missing")

        display = lambda value: " / ".join(variant_texts(value))
        expected_indicative = []
        expected_subjunctive = []
        expected_compound = []
        expected_rare = []
        participles = variant_texts(forms["participle"])
        for index in range(5):
            expected_indicative.extend(display(forms[key][index]) for key in ("ind_present", "ind_preterite", "ind_imperfect", "ind_future", "ind_conditional"))
            expected_subjunctive.extend(display(forms[key][index]) for key in ("subj_present", "subj_ra", "subj_se"))
            for aux_key in ("perfect", "pluperfect", "future_perfect", "conditional_perfect", "subj_perfect", "subj_pluperfect_ra", "subj_pluperfect_se"):
                aux = generator.AUX[aux_key][index]
                expected_compound.append(" / ".join(f"{aux} {part}" for part in participles))
            anterior = generator.AUX["anterior"][index]
            future_perfect = generator.AUX["subj_future_perfect"][index]
            expected_rare.extend((
                " / ".join(f"{anterior} {part}" for part in participles),
                display(forms["subj_future"][index]),
                " / ".join(f"{future_perfect} {part}" for part in participles),
            ))
        infinitive_display = forms.get("infinitive_display", forms["infinitive"])
        expected_nonfinite = [
            display(infinitive_display), display(forms["gerund"]), display(forms["participle"]),
            " / ".join(f"haber {part}" for part in participles),
            " / ".join(f"habiendo {part}" for part in participles),
        ]
        require(parser.table_cells["indicative-table"] == expected_indicative, f"{lemma}: indicative render/data mismatch")
        require(parser.table_cells["subjunctive-table"] == expected_subjunctive, f"{lemma}: subjunctive render/data mismatch")
        require(parser.table_cells["compound-table"] == expected_compound, f"{lemma}: compound render/data mismatch")
        require(parser.table_cells["command-table"] == [display(value) for value in forms["imperative"]], f"{lemma}: imperative render/data mismatch")
        require(parser.table_cells["nonfinite-table"] == expected_nonfinite, f"{lemma}: nonfinite render/data mismatch")
        require(parser.table_cells["rare-table"] == expected_rare, f"{lemma}: rare render/data mismatch")

        for key, expected in known.get(lemma, {}).items():
            require(forms[key] == expected, f"{lemma}: golden mismatch in {key}")

        if generator.verb_class(lemma) == "er":
            present_header = generator.key_text(next(item for item in generator.FAMILIES if item.lemma == lemma), forms, "ind_present")
            require("núcleo e/i" not in present_header, f"{lemma}: -er present mislabeled as e/i")

        present_header_goldens = {
            "adquirir": ("adquier- + núcleo e", "adquir- + núcleo i"),
            "asir": ("as- + núcleo e/i",),
            "caber": ("cab- + núcleo e",),
            "ceñir": ("ciñ- + núcleo e", "ceñ- + núcleo i"),
            "construir": ("construy- + núcleo e", "constru- + núcleo i"),
            "discernir": ("disciern- + núcleo e", "discern- + núcleo i"),
            "dormir": ("duerm- + núcleo e", "dorm- + núcleo i"),
            "oír": ("oy- + núcleo e", "o- + núcleo í"),
            "sonreír": ("sonrí- + núcleo e", "sonre- + núcleo í"),
            "freír": ("frí- + núcleo e", "fre- + núcleo í"),
            "elegir": ("elig- + núcleo e", "eleg- + núcleo i"),
        }
        if lemma in present_header_goldens:
            family_object = next(item for item in generator.FAMILIES if item.lemma == lemma)
            header = generator.key_text(family_object, forms, "ind_present")
            require(all(fragment in header for fragment in present_header_goldens[lemma]), f"{lemma}: present surface header mismatch")

        preterite_header_goldens = {
            "dormir": ("dorm-/durm- + núcleo i",),
            "pedir": ("ped-/pid- + núcleo i",),
            "sentir": ("sent-/sint- + núcleo i",),
            "morir": ("mor-/mur- + núcleo i",),
            "freír": ("tema fri-", "superficie: fre- + núcleo í"),
            "proveer": ("tema provey-", "superficie: prove-"),
            "elegir": ("eleg-/elig- + núcleo i",),
        }
        if lemma in preterite_header_goldens:
            family_object = next(item for item in generator.FAMILIES if item.lemma == lemma)
            header = generator.key_text(family_object, forms, "ind_preterite")
            require(all(fragment in header for fragment in preterite_header_goldens[lemma]), f"{lemma}: preterite surface header mismatch")

        if lemma == "erguir":
            require(variant_texts(forms["ind_present"][0]) == ["yergo", "irgo"], "erguir: missing present variant")
            require(variant_texts(forms["subj_present"][0]) == ["yerga", "irga"], "erguir: missing subjunctive variant")
        elif lemma == "errar":
            require(variant_texts(forms["ind_present"][0]) == ["yerro", "erro"], "errar: missing American regular variant")
            require(variant_texts(forms["subj_present"][0]) == ["yerre", "erre"], "errar: missing American subjunctive variant")
        elif lemma == "ir":
            require(variant_texts(forms["imperative"][2]) == ["vayamos", "vamos"], "ir: missing vamos imperative variant")
        elif lemma == "pudrir":
            require(variant_texts(forms["infinitive_display"]) == ["pudrir", "podrir"], "pudrir: missing infinitive variant")
            require(variant_texts(forms["ind_imperfect"][3]) == ["pudríamos", "podríamos"], "pudrir: incomplete imperfect variants")
            require(variant_texts(forms["ind_preterite"][4]) == ["pudrieron", "podrieron"], "pudrir: incomplete preterite variants")
            require(variant_texts(forms["ind_future"][0]) == ["pudriré", "podriré"], "pudrir: incomplete future variants")
        elif lemma in {"freír", "proveer"}:
            require(forms["participle"][0]["kind"] == "orthographic", f"{lemma}: hiatus participle is not amber")
            simple_participle = generator.nonfinite_cell(forms, "participle", "Participio")
            require("is-orthographic" in simple_participle, f"{lemma}: amber participle not rendered")
            compound = generator.compound_cell(forms, "perfect", 0, "present")
            require("is-orthographic" not in compound and "is-irregular" in compound, f"{lemma}: compound participle color propagation mismatch")

        y_preterite_headers = {
            "caer": "superficie: ca-", "construir": "superficie: constru-", "leer": "superficie: le-",
            "oír": "superficie: o-", "roer": "superficie: ro-", "proveer": "superficie: prove-",
        }
        if lemma in y_preterite_headers:
            family_object = next(item for item in generator.FAMILIES if item.lemma == lemma)
            header = generator.key_text(family_object, forms, "ind_preterite")
            require(y_preterite_headers[lemma] in header and "núcleo i → y ante o/eron" in header, f"{lemma}: incoherent i→y preterite header")

        predictable_y = {
            "caer": (("ind_preterite", "2"), ("gerund", "value"), ("subj_ra", "0")),
            "construir": (("ind_present", "0"), ("ind_preterite", "2"), ("gerund", "value")),
            "leer": (("ind_preterite", "2"), ("gerund", "value"), ("subj_ra", "0")),
            "oír": (("ind_present", "1"), ("ind_preterite", "2"), ("gerund", "value")),
            "roer": (("ind_preterite", "2"), ("gerund", "value"), ("subj_ra", "0")),
            "traer": (("gerund", "value"),),
            "proveer": (("ind_preterite", "2"), ("gerund", "value"), ("subj_ra", "0")),
        }
        for mark_key, mark_index in predictable_y.get(lemma, ()):
            require(forms["marks"][mark_key][mark_index]["kind"] == "orthographic", f"{lemma}: predictable i→y is not amber")
        if lemma == "oír":
            require(forms["marks"]["ind_present"]["0"]["kind"] == "irregular", "oír: lexical oig- must stay red")

    for index in range(5):
        require('class="shift-accent"' not in generator.highlighted_aux("future_perfect", index), "future-perfect accent turned black")
        require('class="shift-accent"' not in generator.highlighted_aux("pluperfect", index), "recurring había accent turned black")
        require('class="shift-accent"' not in generator.highlighted_aux("conditional_perfect", index), "recurring habría accent turned black")
    for key in ("subj_pluperfect_ra", "subj_pluperfect_se", "subj_future_perfect"):
        require(generator.highlighted_aux(key, 3).count('class="shift-accent"') == 1, f"{key}: missing black nosotros accent")

    for name in ("index.html", "defectivos.html"):
        path = ROOT / name
        parser = PageAudit()
        parser.feed(path.read_text(encoding="utf-8"))
        require(len(parser.ids) == len(set(parser.ids)), f"{name}: duplicate HTML id")
        for href in parser.hrefs:
            if re.match(r"^[a-z]+:", href) or href.startswith("#"):
                continue
            require((path.parent / href.split("#", 1)[0]).exists(), f"{name}: broken link {href}")

    member_count = sum(len(family["members"]) for family in families)
    print(f"Atlas verification passed: 70 families, {member_count} member paradigms, 72 HTML files, links, payloads, accents, and source chart integrity.")


if __name__ == "__main__":
    main()
