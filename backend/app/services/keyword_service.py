"""ATS keyword matching: what the JD asks for, and whether the profile says it.

Applicant tracking systems screen on words. This module answers the only
question that matters before hitting *Apply*: of the things this posting asks
for, which ones does the candidate's own material actually say, and in which
words.

The work is split in two, deliberately:

1. **Extraction is a model call.** Deciding that "own the CI/CD pipeline" is a
   *required* responsibility and that "familiarity with Kafka is a plus" is a
   *preferred* tool is a reading-comprehension task. It runs on Azure GPT-4o
   (:func:`extract_jd_keywords`) at a low temperature, and its result is cached
   on the chat -- the JD does not change, so re-extracting is pure cost.

2. **Matching is deterministic.** Whether the profile contains "PostgreSQL" is
   not a judgement call, and a model asked to decide it would answer slightly
   differently every time. So the match is plain string work over a normalised
   corpus, and it is re-run on *every* request even when the extraction is
   reused. That is the whole point: the user edits their profile, comes back,
   and the numbers move -- with no model call and no way for the score to drift
   on its own.

Normalisation is what makes the deterministic half honest. "CI/CD", "ci-cd" and
"continuous integration" are the same requirement; so are "Postgres" and
"PostgreSQL", "K8s" and "Kubernetes", "API" and "APIs". Case, punctuation,
separators and plurals are flattened, then a small hand-written alias table
(:data:`ALIAS_GROUPS`) plus whatever aliases the model supplied are folded in.
Everything unmatched is reported as missing rather than quietly excused.

Two corpora are searched. The **profile** is the candidate as they exist; the
**generated resume**, when this chat has one, is the document they would
actually send. A keyword can be in the profile but missing from the resume --
that is a tailoring bug worth seeing -- so the two are reported separately and
``in_resume`` is null when there is no resume to check.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.services import llm, profile_service

logger = logging.getLogger(__name__)

# Extraction is close to a parsing task: the same JD should yield the same
# keyword list twice running.
EXTRACTION_TEMPERATURE = 0.1
EXTRACTION_MAX_TOKENS = 2048

# Azure GPT-4o reads a long JD and holds the whole thing in view while it
# decides what is required and what is merely nice to have. Groq is capped and
# is the fallback, not the first choice.
EXTRACTION_PROVIDER = llm.AZURE

# Fewer than this and the match is not a screen, it is a spot check; more and
# the list stops being a checklist a person can read.
MIN_KEYWORDS = 15
MAX_KEYWORDS = 40

CATEGORIES: tuple[str, ...] = (
    "skill",
    "tool",
    "qualification",
    "responsibility",
    "soft_skill",
    "domain",
)
DEFAULT_CATEGORY = "skill"

IMPORTANCE_REQUIRED = "required"
IMPORTANCE_PREFERRED = "preferred"
IMPORTANCES: tuple[str, ...] = (IMPORTANCE_REQUIRED, IMPORTANCE_PREFERRED)
DEFAULT_IMPORTANCE = IMPORTANCE_PREFERRED

# A missing "required" keyword costs the candidate twice what a missing
# "preferred" one does. That ratio is the whole scoring model -- deliberately
# crude, because a percentage nobody can recompute in their head is a number
# nobody trusts.
WEIGHTS: dict[str, int] = {IMPORTANCE_REQUIRED: 2, IMPORTANCE_PREFERRED: 1}

# Evidence is a hint, not a quotation: enough to recognise where the match came
# from, short enough to sit in a table cell.
MAX_EVIDENCE_CHARS = 120

# How much of a keyword's own alias list to trust. The model occasionally
# free-associates; a dozen aliases for one keyword is noise, not recall.
MAX_ALIASES_PER_KEYWORD = 8


class KeywordError(Exception):
    """Raised when the extraction model is unreachable or returns nothing usable."""


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

# Everything that is not a letter, a digit, ``+`` or ``#`` becomes a space, so
# "CI/CD", "ci-cd" and "ci cd" all collapse to the same token pair while "C++"
# and "C#" survive as themselves.
_NOT_WORD_RE = re.compile(r"[^a-z0-9+#]+")

# Endings that are never a plural marker, whatever the word.
_NEVER_PLURAL: tuple[str, ...] = ("ss", "os")

# Endings that are usually a Latin singular ("analysis", "focus") -- but only in
# words long enough for that to be plausible, so "apis" still folds to "api".
_LATIN_SINGULAR: tuple[str, ...] = ("us", "is")
_LATIN_SINGULAR_MIN_LENGTH = 5


def singularise(token: str) -> str:
    """Fold a token onto its singular form, conservatively.

    Applied to both sides of every comparison, so it does not need to be
    linguistically right -- only consistent. "kubernetes" becoming "kubernete"
    is harmless because the profile's "Kubernetes" becomes "kubernete" too.
    Tokens of three characters or fewer are left alone, which is what keeps
    "aws", "js" and "k8s" intact.
    """
    if len(token) <= 3:
        return token
    if token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith(("sses", "shes", "ches", "xes")):
        return token[:-2]
    if token.endswith(_NEVER_PLURAL):
        return token
    if (
        token.endswith(_LATIN_SINGULAR)
        and len(token) >= _LATIN_SINGULAR_MIN_LENGTH
    ):
        return token
    if token.endswith("s"):
        return token[:-1]
    return token


def normalise(text: str) -> str:
    """Reduce a phrase to the canonical form matching is done in.

    Lowercased, punctuation and separators flattened to single spaces, every
    token singularised. ``"CI/CD Pipelines"`` and ``"ci cd pipeline"`` both come
    out as ``"ci cd pipeline"``.
    """
    lowered = (text or "").lower()
    spaced = _NOT_WORD_RE.sub(" ", lowered)
    return " ".join(singularise(token) for token in spaced.split())


# --------------------------------------------------------------------------
# Aliases
# --------------------------------------------------------------------------

# Hand-written equivalences a normaliser cannot derive. Each tuple is one
# group: every member matches every other member, in both directions.
#
# Kept deliberately small and deliberately unambiguous. "go"/"golang" and
# "cv"/"computer vision" are *not* here on purpose -- "go" and "cv" are ordinary
# words in a resume, and a false match is worse than a missed one, because the
# user acts on this list by editing their resume.
ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("postgres", "postgresql", "postgre sql", "psql"),
    ("mysql", "my sql"),
    ("mongo", "mongodb"),
    ("elasticsearch", "elastic search"),
    ("k8s", "kubernetes"),
    ("js", "javascript"),
    ("ts", "typescript"),
    ("ml", "machine learning"),
    ("ai", "artificial intelligence"),
    ("llm", "large language model"),
    ("nlp", "natural language processing"),
    ("gcp", "google cloud", "google cloud platform"),
    ("aws", "amazon web services"),
    ("azure", "microsoft azure"),
    (
        "ci/cd",
        "ci cd",
        "cicd",
        "continuous integration",
        "continuous delivery",
        "continuous deployment",
        "continuous integration and continuous delivery",
    ),
    ("react.js", "react", "reactjs"),
    ("node", "node.js", "nodejs"),
    ("next.js", "nextjs"),
    ("vue.js", "vue", "vuejs"),
    ("angular", "angular.js", "angularjs"),
    (".net", "dotnet", "dot net"),
    ("c#", "c sharp", "csharp"),
    ("c++", "cpp"),
    ("rest", "restful", "rest api", "restful api"),
    ("graphql", "graph ql"),
    ("db", "database"),
    ("nosql", "no sql"),
    ("oop", "object oriented programming"),
    ("iac", "infrastructure as code"),
    ("etl", "extract transform load"),
    ("tdd", "test driven development"),
    ("sre", "site reliability engineering"),
    ("qa", "quality assurance"),
    ("ux", "user experience"),
    ("ui", "user interface"),
    ("saas", "software as a service"),
    ("bi", "business intelligence"),
    ("crm", "customer relationship management"),
    ("github actions", "gh actions"),
    ("frontend", "front end"),
    ("backend", "back end"),
    ("fullstack", "full stack"),
)


def _build_alias_index() -> dict[str, frozenset[str]]:
    """Index every normalised alias to the whole group it belongs to.

    Groups that happen to share a member are merged, so the table stays
    order-independent: adding a group later can widen an existing equivalence
    but can never split one.
    """
    groups: list[set[str]] = []
    for group in ALIAS_GROUPS:
        members = {normalise(member) for member in group}
        members.discard("")
        if not members:
            continue
        overlapping = [g for g in groups if g & members]
        for existing in overlapping:
            members |= existing
            groups.remove(existing)
        groups.append(members)

    index: dict[str, frozenset[str]] = {}
    for group in groups:
        frozen = frozenset(group)
        for member in group:
            index[member] = frozen
    return index


ALIAS_INDEX: dict[str, frozenset[str]] = _build_alias_index()


def variants_for(keyword: str, aliases: list[str] | None = None) -> set[str]:
    """Every normalised phrase that counts as a hit for one keyword.

    The keyword itself, the aliases the model supplied, and -- for each of those
    -- the built-in group it belongs to. One level of expansion is enough:
    :data:`ALIAS_INDEX` already holds each group whole.
    """
    seeds = [keyword] + list(aliases or [])[:MAX_ALIASES_PER_KEYWORD]
    variants: set[str] = set()
    for seed in seeds:
        phrase = normalise(seed)
        if not phrase:
            continue
        variants.add(phrase)
        variants |= ALIAS_INDEX.get(phrase, frozenset())
    return variants


# --------------------------------------------------------------------------
# Corpora
# --------------------------------------------------------------------------


def _flatten(value: Any, into: list[str]) -> None:
    """Collect every human-readable string inside a parsed profile.

    Structure-agnostic on purpose. The profile schema grows -- coursework,
    honours, publications, project links -- and a keyword matcher that had to be
    taught each new field would silently stop seeing the newest half of a user's
    profile. Anything that is a string is corpus.
    """
    if isinstance(value, str):
        text = value.strip()
        if text:
            into.append(text)
        return
    if isinstance(value, dict):
        for item in value.values():
            _flatten(item, into)
        return
    if isinstance(value, (list, tuple)):
        strings = [item.strip() for item in value if isinstance(item, str)]
        if strings and len(strings) == len(value):
            # A flat list of short strings (skills, technologies, highlights)
            # reads better as one line than as one segment each.
            joined = ", ".join(item for item in strings if item)
            if joined:
                into.append(joined)
            return
        for item in value:
            _flatten(item, into)


def profile_corpus(parsed_json: dict[str, Any] | None) -> list[str]:
    """Return the user's whole profile as searchable text segments.

    Prefers ``profile_service.render_profile_text`` when it exists, because that
    is the profile rendered the way the rest of the product reads it. Falls back
    to walking the stored JSON for every string, which cannot miss a field but
    also cannot label one.
    """
    if not parsed_json:
        return []

    render = getattr(profile_service, "render_profile_text", None)
    if callable(render):
        try:
            rendered = render(parsed_json)
        except Exception:
            logger.exception("render_profile_text failed; walking the JSON instead")
        else:
            if isinstance(rendered, str) and rendered.strip():
                return text_corpus(rendered)

    segments: list[str] = []
    _flatten(parsed_json, segments)
    return segments


def text_corpus(text: str | None) -> list[str]:
    """Split a document into non-empty lines, the unit evidence is quoted from."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _prepare(segments: list[str]) -> list[tuple[str, str]]:
    """Pair each raw segment with its normalised form, once per request."""
    prepared = []
    for raw in segments:
        normalised = normalise(raw)
        if normalised:
            prepared.append((raw, normalised))
    return prepared


def _contains(haystack: str, phrase: str) -> bool:
    """Whole-phrase containment over normalised text.

    Padded with spaces on both sides so "java" does not match "javascript" and
    "ai" does not match "email".
    """
    if not phrase:
        return False
    return " {} ".format(phrase) in " {} ".format(haystack)


def find_evidence(
    corpus: list[tuple[str, str]],
    variants: set[str],
) -> str | None:
    """Return the first raw segment containing any variant, trimmed for display.

    None means no segment matched -- which is exactly what "not in the profile"
    means, so the caller needs no second flag.
    """
    for raw, normalised in corpus:
        if any(_contains(normalised, variant) for variant in variants):
            return _trim(raw)
    return None


def _trim(text: str) -> str:
    """Shorten a snippet to :data:`MAX_EVIDENCE_CHARS`, ellipsis included."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= MAX_EVIDENCE_CHARS:
        return collapsed
    return collapsed[: MAX_EVIDENCE_CHARS - 1].rstrip() + "…"


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are an applicant tracking system (ATS) \
reading one job description.

Extract the concrete things this posting screens candidates on. Return a JSON \
object with exactly one key, "keywords", whose value is an array of {min}-{max} \
objects. Each object has:

  "keyword":    the term itself, lowercase, as short as it can be and still be \
specific -- "kubernetes", not "experience with kubernetes"
  "category":   one of "skill", "tool", "qualification", "responsibility", \
"soft_skill", "domain"
  "importance": "required" if the posting states or clearly implies the \
candidate must have it; "preferred" if it is a plus, a bonus, or a nice-to-have
  "aliases":    other spellings a resume might legitimately use for the same \
thing -- abbreviations, expansions, common variants. Empty array if there are \
none. Do not list related-but-different technologies.

Rules:
- Only terms the job description actually contains. Do not add what a role like \
this usually wants.
- One concept per entry, deduplicated. Never list the same thing twice under \
two spellings -- pick one and put the rest in "aliases".
- Prefer the specific over the generic: "postgresql" over "databases", \
"terraform" over "infrastructure".
- Do not invent seniority, years of experience, or salary as keywords.

JSON only. No preamble, no markdown.""".format(min=MIN_KEYWORDS, max=MAX_KEYWORDS)

EXTRACTION_USER_TEMPLATE = """JOB DESCRIPTION:
{jd}

Extract the keywords and return the JSON object."""


def _parse_object(content: str) -> dict[str, Any]:
    """Parse a response that is supposed to be a JSON object.

    Tries the whole response, then the outermost ``{...}`` span, which rescues a
    reply with a stray sentence wrapped around the object.

    Raises:
        KeywordError: If no JSON object can be recovered.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise KeywordError("The keyword extraction model did not return valid JSON.")


def _clean_aliases(value: Any) -> list[str]:
    """Return the model's alias list as trimmed, deduplicated strings."""
    if not isinstance(value, (list, tuple)):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        alias = " ".join(item.split()).lower()
        if alias and alias not in seen:
            seen.add(alias)
            out.append(alias)
        if len(out) >= MAX_ALIASES_PER_KEYWORD:
            break
    return out


def coerce_keywords(raw: Any) -> list[dict[str, Any]]:
    """Normalise whatever the model returned into a usable keyword list.

    A model that answers with a bare array, an unknown category, a missing
    importance, or the same keyword twice should produce a slightly poorer match
    -- never a 500. Entries without a keyword are the only ones dropped
    outright, because there is nothing left to match on.
    """
    items = raw.get("keywords") if isinstance(raw, dict) else raw
    if not isinstance(items, (list, tuple)):
        return []

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            item = {"keyword": item}
        if not isinstance(item, dict):
            continue

        keyword = item.get("keyword")
        if not isinstance(keyword, str):
            continue
        keyword = " ".join(keyword.split()).lower()
        if not keyword:
            continue

        # Dedupe on the *normalised* form, so "APIs" and "api" cannot both
        # occupy a slot and be counted twice in the score.
        fingerprint = normalise(keyword)
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)

        category = item.get("category")
        importance = item.get("importance")
        out.append(
            {
                "keyword": keyword,
                "category": (
                    category if category in CATEGORIES else DEFAULT_CATEGORY
                ),
                "importance": (
                    importance if importance in IMPORTANCES else DEFAULT_IMPORTANCE
                ),
                "aliases": _clean_aliases(item.get("aliases")),
            }
        )
        if len(out) >= MAX_KEYWORDS:
            break

    return out


def extract_jd_keywords(jd_text: str) -> tuple[list[dict[str, Any]], str]:
    """Extract the screening keywords from one job description.

    Args:
        jd_text: The chat's job description.

    Returns:
        ``(keywords, provider)`` -- the coerced keyword list and the name of the
        provider that actually served the call.

    Raises:
        KeywordError: If the JD is empty, both providers fail, or nothing
            usable comes back.
    """
    if not (jd_text or "").strip():
        raise KeywordError("There is no job description to extract keywords from.")

    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": EXTRACTION_USER_TEMPLATE.format(jd=jd_text)},
    ]

    try:
        content = llm.complete_json(
            messages,
            max_tokens=EXTRACTION_MAX_TOKENS,
            temperature=EXTRACTION_TEMPERATURE,
            prefer=EXTRACTION_PROVIDER,
            purpose="ATS keyword extraction",
        )
    except Exception as exc:
        raise KeywordError(
            "Could not reach the model to extract keywords from this job description."
        ) from exc

    keywords = coerce_keywords(_parse_object(content))
    if not keywords:
        raise KeywordError("The model returned no usable keywords for this job.")

    return keywords, llm.provider_of(content, default=EXTRACTION_PROVIDER)


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


def match_percent(
    required_matched: int,
    required_total: int,
    preferred_matched: int,
    preferred_total: int,
) -> int:
    """Weighted percentage of the posting's asks the profile evidences.

    Required keywords count double. An empty keyword list scores 0 rather than
    dividing by zero -- there was nothing to match, which is not a pass.
    """
    earned = (
        WEIGHTS[IMPORTANCE_REQUIRED] * required_matched
        + WEIGHTS[IMPORTANCE_PREFERRED] * preferred_matched
    )
    possible = (
        WEIGHTS[IMPORTANCE_REQUIRED] * required_total
        + WEIGHTS[IMPORTANCE_PREFERRED] * preferred_total
    )
    if possible <= 0:
        return 0
    return round(100 * earned / possible)


def match_keywords(
    keywords: list[dict[str, Any]],
    profile_segments: list[str],
    resume_segments: list[str] | None = None,
    provider: str = "",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Score a keyword list against the profile, and optionally against a resume.

    Pure and deterministic: same inputs, same output, no network. Called on
    every request -- including the ones that reuse a cached extraction -- so an
    edit to the profile is reflected the next time the user looks.

    Args:
        keywords: Coerced keywords, as :func:`coerce_keywords` returns them.
        profile_segments: The profile as searchable lines.
        resume_segments: The latest generated resume as searchable lines, or
            None when this chat has not generated one.
        provider: Which provider extracted the keywords, carried through to the
            stored result.
        generated_at: Timestamp to stamp the result with; defaults to now.

    Returns:
        The full match result, ready to store and return.
    """
    profile = _prepare(profile_segments)
    resume = _prepare(resume_segments) if resume_segments is not None else None

    rows: list[dict[str, Any]] = []
    matched = {IMPORTANCE_REQUIRED: 0, IMPORTANCE_PREFERRED: 0}
    totals = {IMPORTANCE_REQUIRED: 0, IMPORTANCE_PREFERRED: 0}
    missing_required: list[str] = []

    for entry in keywords:
        importance = entry.get("importance", DEFAULT_IMPORTANCE)
        if importance not in WEIGHTS:
            importance = DEFAULT_IMPORTANCE
        totals[importance] += 1

        variants = variants_for(entry["keyword"], entry.get("aliases"))
        evidence = find_evidence(profile, variants)
        in_profile = evidence is not None

        if in_profile:
            matched[importance] += 1
        elif importance == IMPORTANCE_REQUIRED:
            missing_required.append(entry["keyword"])

        in_resume: bool | None = None
        if resume is not None:
            resume_evidence = find_evidence(resume, variants)
            in_resume = resume_evidence is not None
            # The resume is what actually gets screened, so when the profile
            # has nothing to show, the resume's line is better than no line.
            if evidence is None:
                evidence = resume_evidence

        rows.append(
            {
                "keyword": entry["keyword"],
                "category": entry.get("category", DEFAULT_CATEGORY),
                "importance": importance,
                "aliases": list(entry.get("aliases") or []),
                "in_profile": in_profile,
                "in_resume": in_resume,
                "evidence": evidence,
            }
        )

    return {
        "match_percent": match_percent(
            matched[IMPORTANCE_REQUIRED],
            totals[IMPORTANCE_REQUIRED],
            matched[IMPORTANCE_PREFERRED],
            totals[IMPORTANCE_PREFERRED],
        ),
        "required_matched": matched[IMPORTANCE_REQUIRED],
        "required_total": totals[IMPORTANCE_REQUIRED],
        "preferred_matched": matched[IMPORTANCE_PREFERRED],
        "preferred_total": totals[IMPORTANCE_PREFERRED],
        "keywords": rows,
        "missing_required": missing_required,
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
        "provider": provider,
    }


def stored_keywords(keyword_match: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Recover the extracted keyword list from a stored match result.

    The stored rows carry their aliases, which is what makes a re-match without
    a re-extraction possible: the scores and the evidence are thrown away and
    recomputed, the model's reading of the JD is kept.
    """
    if not isinstance(keyword_match, dict):
        return []
    return coerce_keywords(keyword_match.get("keywords"))


def run_keyword_match(
    jd_text: str | None,
    parsed_json: dict[str, Any] | None,
    resume_content: str | None = None,
    existing: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Produce the keyword match for one chat, extracting only when it must.

    Args:
        jd_text: The chat's job description.
        parsed_json: The user's structured profile.
        resume_content: The latest generated resume for this chat, if any.
        existing: The previously stored match, whose keyword list can be reused.
        force: Re-extract from the JD even when a stored list exists.

    Returns:
        The full match result.

    Raises:
        KeywordError: If extraction is needed and fails.
    """
    keywords = [] if force else stored_keywords(existing)
    provider = ""

    if keywords and not force:
        provider = (existing or {}).get("provider") or ""
    else:
        keywords, provider = extract_jd_keywords(jd_text or "")

    return match_keywords(
        keywords,
        profile_corpus(parsed_json),
        text_corpus(resume_content) if resume_content is not None else None,
        provider=provider,
    )
