"""Supported vocabulary languages and their prompt guidance."""

from dataclasses import dataclass
import unicodedata

from fastapi import HTTPException, Query


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    canonical_form: str
    definition_instruction: str
    exclusion_instruction: str
    meanings_instruction: str
    challenge_instruction: str
    check_instruction: str
    hint_instruction: str
    yes_token: str
    no_token: str
    supports_verb_forms: bool


LANGUAGES = {
    "IT": Language(
        code="IT", name="Italian",
        canonical_form="nouns singular, adjectives masculine singular, and verbs infinitive",
        definition_instruction="Provide definitions and examples in Italian. Give translations in English.",
        exclusion_instruction="Do not use any excluded word or its inflected forms.",
        meanings_instruction="Add only clearly distinct meanings of the same lemma. Preserve the word and all existing meanings; do not add derivatives or minor variants.",
        challenge_instruction="Write a short, simple clue in Italian without using the answer or an obvious inflection.",
        check_instruction='Is the guess “{guess}” a plausible answer to the clue “{challenge}”? Reply only SI or NO.',
        hint_instruction='Give a short hint in Italian without using the word “{word}” or an obvious inflection.',
        yes_token="SI", no_token="NO", supports_verb_forms=True,
    ),
    "DE": Language(
        code="DE", name="German",
        canonical_form="Gib Substantive im Nominativ Singular mit Artikel an; Verben im Infinitiv; Adjektive in der Grundform.",
        definition_instruction="Schreibe Definitionen und Beispielsätze auf Deutsch. Gib Übersetzungen ins Englische.",
        exclusion_instruction="Verwende keines der ausgeschlossenen Wörter oder deren gebeugte Formen.",
        meanings_instruction="Ergänze nur klar unterscheidbare Bedeutungen desselben Lemmas. Behalte das Wort und alle vorhandenen Bedeutungen bei; füge keine Ableitungen oder bloßen Varianten hinzu.",
        challenge_instruction="Schreibe einen kurzen, einfachen Hinweis auf Deutsch, ohne die gesuchte Vokabel oder eine offensichtliche gebeugte Form zu nennen.",
        check_instruction='Ist die Vermutung „{guess}“ eine plausible Antwort auf den Hinweis „{challenge}“? Antworte ausschließlich mit JA oder NEIN.',
        hint_instruction='Gib einen kurzen Hinweis auf Deutsch zur gesuchten Vokabel, ohne die Vokabel „{word}“ oder eine offensichtliche gebeugte Form zu nennen.',
        yes_token="JA", no_token="NEIN", supports_verb_forms=False,
    ),
    "EL": Language(
        code="EL", name="Greek",
        canonical_form="Δώσε τα ουσιαστικά στην ονομαστική ενικού μαζί με το γένος τους ή το άρθρο όπου είναι φυσικό, τα ρήματα στον ενεστώτα, α΄ ενικό πρόσωπο, και τα επίθετα στο αρσενικό, ονομαστική ενικού.",
        definition_instruction="Γράψε τους ορισμούς και τα παραδείγματα στα ελληνικά. Δώσε τις μεταφράσεις στα αγγλικά.",
        exclusion_instruction="Μη χρησιμοποιήσεις καμία από τις λέξεις που εξαιρούνται ούτε κλιτές μορφές τους.",
        meanings_instruction="Πρόσθεσε μόνο σαφώς διαφορετικές σημασίες του ίδιου λήμματος. Διατήρησε τη λέξη και όλες τις υπάρχουσες σημασίες· μην προσθέσεις παράγωγα ή απλές παραλλαγές.",
        challenge_instruction="Γράψε μια σύντομη, απλή περιγραφή στα ελληνικά, χωρίς να χρησιμοποιήσεις τη λέξη που αναζητάμε ή προφανή κλιτή μορφή της.",
        check_instruction='Είναι η απάντηση «{guess}» εύλογη για την περιγραφή «{challenge}»; Απάντησε μόνο ΝΑΙ ή ΟΧΙ.',
        hint_instruction='Δώσε μια σύντομη υπόδειξη στα ελληνικά για τη ζητούμενη λέξη, χωρίς να αναφέρεις τη λέξη «{word}» ή προφανή κλιτή μορφή της.',
        yes_token="ΝΑΙ", no_token="ΟΧΙ", supports_verb_forms=False,
    ),
}


def normalize_language(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in LANGUAGES:
        raise ValueError("Language must be one of IT, DE, or EL")
    return normalized


def get_language(code: str) -> Language:
    try:
        return LANGUAGES[normalize_language(code)]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def language_query(language: str = Query("IT")) -> str:
    return get_language(language).code


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip().casefold()
