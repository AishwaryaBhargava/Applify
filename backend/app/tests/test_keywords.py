"""Tests for ATS keyword extraction, the deterministic match, and the route.

The feature is deliberately half model and half arithmetic, and the tests are
split the same way.

The **matcher** is pure, so it is tested directly with hand-written keyword
lists: normalisation, aliases, weighting, evidence, and the two corpora are all
exercised without a route or a session in the way.

The **route** is tested against the ``FakeSession`` with exactly one seam
patched -- ``llm.complete_json`` -- so the prompt assembly, the JSON parsing, the
coercion of a malformed reply, the storage on ``job_chats.keyword_match``, and
the reuse-versus-force decision are all the real code.

``test_live_keyword_extraction`` is the one exception and is opt-in behind
``RUN_LIVE=1``: every offline test here would still pass with a prompt that made
the model return nonsense.
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.routes.chats import NO_JD, NO_PROFILE
from app.models.job_chat import JobChat
from app.services import keyword_service, llm, profile_service
from app.services.keyword_service import KeywordError
from app.tests.conftest import OTHER_USER_ID, FakeSession
from app.tests.test_chat import make_chat, make_profile, make_tracker
from app.tests.test_outputs import make_output

CHAT_ID = "00000000-0000-0000-0000-000000000001"

# A model reply in the shape the extraction prompt asks for.
EXTRACTION_RESPONSE = {
    "keywords": [
        {
            "keyword": "python",
            "category": "skill",
            "importance": "required",
            "aliases": [],
        },
        {
            "keyword": "postgresql",
            "category": "tool",
            "importance": "required",
            "aliases": ["postgres"],
        },
        {
            "keyword": "kubernetes",
            "category": "tool",
            "importance": "required",
            "aliases": ["k8s"],
        },
        {
            "keyword": "stakeholder communication",
            "category": "soft_skill",
            "importance": "preferred",
            "aliases": [],
        },
    ]
}


def keyword(
    name: str,
    importance: str = "required",
    category: str = "skill",
    aliases: list[str] | None = None,
) -> dict:
    """Build one coerced keyword, as the extraction step hands them on."""
    return {
        "keyword": name,
        "category": category,
        "importance": importance,
        "aliases": aliases or [],
    }


@pytest.fixture
def mock_extraction(monkeypatch: pytest.MonkeyPatch):
    """Patch the one network seam. Returns a setter for the response body.

    The returned object also counts calls, which is how the reuse-versus-force
    tests tell "read the JD again" apart from "rescore what we already read".
    """
    state = {"calls": 0, "body": json.dumps(EXTRACTION_RESPONSE)}

    def fake_complete_json(messages, **kwargs):
        state["calls"] += 1
        state["messages"] = messages
        state["kwargs"] = kwargs
        return llm.ProviderText(state["body"], llm.AZURE)

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    return state


def seeded_chat(db: FakeSession, **kwargs) -> JobChat:
    """Seed a chat with its tracker entry and the sample profile."""
    chat = db.seed(make_chat(**kwargs))
    db.seed(make_tracker(chat.id))
    db.seed(make_profile())
    return chat


# ==========================================================================
# Auth guard
# ==========================================================================


def test_keywords_requires_auth(client: TestClient) -> None:
    """POST /chats/{id}/keywords is protected by get_current_user."""
    assert client.post("/chats/{}/keywords".format(CHAT_ID)).status_code == 401


# ==========================================================================
# Normalisation
# ==========================================================================


@pytest.mark.parametrize(
    "text, expected",
    [
        ("CI/CD", "ci cd"),
        ("ci-cd", "ci cd"),
        ("Node.js", "node js"),
        ("REST APIs", "rest api"),
        ("Machine  Learning", "machine learning"),
        ("Responsibilities:", "responsibility"),
        ("AWS", "aws"),
        ("K8s", "k8s"),
        ("C++", "c++"),
        ("", ""),
    ],
)
def test_normalise_flattens_case_punctuation_and_plurals(
    text: str, expected: str
) -> None:
    """One canonical form, applied identically to both sides of a comparison."""
    assert keyword_service.normalise(text) == expected


def test_singularise_leaves_short_tokens_alone() -> None:
    """Stripping the s off "aws" would be worse than not stripping it at all."""
    assert keyword_service.singularise("aws") == "aws"
    assert keyword_service.singularise("apis") == "api"
    assert keyword_service.singularise("business") == "business"


# ==========================================================================
# Aliases
# ==========================================================================


def test_built_in_aliases_match_in_both_directions() -> None:
    """The table is symmetric: the JD's spelling and the resume's both work."""
    forward = keyword_service.match_keywords(
        [keyword("postgresql")], ["Six years of Postgres in production."]
    )
    backward = keyword_service.match_keywords(
        [keyword("postgres")], ["Deep PostgreSQL tuning experience."]
    )

    assert forward["keywords"][0]["in_profile"] is True
    assert backward["keywords"][0]["in_profile"] is True


@pytest.mark.parametrize(
    "jd_term, profile_text",
    [
        ("kubernetes", "Ran K8s clusters for three teams."),
        ("k8s", "Migrated the fleet to Kubernetes."),
        ("javascript", "Wrote the dashboard in JS."),
        ("machine learning", "Shipped an ML ranking model."),
        ("amazon web services", "Everything runs on AWS."),
        ("ci/cd", "Owned continuous integration for the monorepo."),
        ("react", "Built the UI in React.js."),
        ("node.js", "A Node service behind the API."),
        ("google cloud", "Moved billing to GCP."),
        ("infrastructure as code", "All environments defined as IaC."),
    ],
)
def test_the_alias_table_matches_the_spellings_resumes_actually_use(
    jd_term: str, profile_text: str
) -> None:
    """Each built-in group, checked with the wording a real resume would use."""
    result = keyword_service.match_keywords([keyword(jd_term)], [profile_text])

    assert result["keywords"][0]["in_profile"] is True


def test_model_supplied_aliases_are_honoured() -> None:
    """The model knows domain synonyms the built-in table never will."""
    result = keyword_service.match_keywords(
        [keyword("payment reconciliation", aliases=["settlement matching"])],
        ["Owned settlement matching for the card rails."],
    )

    assert result["keywords"][0]["in_profile"] is True


def test_matching_respects_word_boundaries() -> None:
    """"java" must not be found inside "javascript"."""
    result = keyword_service.match_keywords(
        [keyword("java")], ["Frontend work in JavaScript and TypeScript."]
    )

    assert result["keywords"][0]["in_profile"] is False


# ==========================================================================
# Weighting
# ==========================================================================


def test_required_keywords_count_double() -> None:
    """One of two required and one of two preferred is 3/6, not 2/4."""
    result = keyword_service.match_keywords(
        [
            keyword("python", "required"),
            keyword("kubernetes", "required"),
            keyword("terraform", "preferred"),
            keyword("graphql", "preferred"),
        ],
        ["Python and GraphQL every day."],
    )

    assert result["required_matched"] == 1
    assert result["required_total"] == 2
    assert result["preferred_matched"] == 1
    assert result["preferred_total"] == 2
    assert result["match_percent"] == 50


def test_a_perfect_match_is_a_hundred_and_an_empty_one_is_zero() -> None:
    """Both ends of the scale, including the divide-by-zero case."""
    perfect = keyword_service.match_keywords(
        [keyword("python", "required"), keyword("go", "preferred")],
        ["Python and Go."],
    )
    nothing = keyword_service.match_keywords([keyword("rust")], ["Python only."])

    assert perfect["match_percent"] == 100
    assert nothing["match_percent"] == 0
    assert keyword_service.match_keywords([], ["anything"])["match_percent"] == 0


def test_only_missing_required_keywords_are_listed_as_missing() -> None:
    """The actionable half: what the posting demands and the profile lacks."""
    result = keyword_service.match_keywords(
        [
            keyword("python", "required"),
            keyword("kubernetes", "required"),
            keyword("terraform", "preferred"),
        ],
        ["Python, mostly."],
    )

    assert result["missing_required"] == ["kubernetes"]


# ==========================================================================
# Evidence
# ==========================================================================


def test_evidence_is_the_first_matching_line() -> None:
    """The snippet is the user's own words, so they can see why it counted."""
    result = keyword_service.match_keywords(
        [keyword("postgresql")],
        [
            "Skills: Python, Go",
            "Tuned PostgreSQL for a 4TB ledger.",
            "Also PostgreSQL replication.",
        ],
    )

    assert result["keywords"][0]["evidence"] == "Tuned PostgreSQL for a 4TB ledger."


def test_evidence_is_trimmed_to_the_display_limit() -> None:
    """A 400-word highlight becomes a snippet, not a wall of text in a cell."""
    long_line = "Owned PostgreSQL " + "and a great deal more besides " * 20
    result = keyword_service.match_keywords([keyword("postgresql")], [long_line])

    evidence = result["keywords"][0]["evidence"]
    assert len(evidence) <= keyword_service.MAX_EVIDENCE_CHARS
    assert evidence.startswith("Owned PostgreSQL")
    assert evidence.endswith("…")


def test_evidence_is_null_when_nothing_matched() -> None:
    """No evidence and no match are the same fact, reported once each."""
    result = keyword_service.match_keywords([keyword("rust")], ["Python only."])

    assert result["keywords"][0]["evidence"] is None
    assert result["keywords"][0]["in_profile"] is False


# ==========================================================================
# The two corpora
# ==========================================================================


def test_in_resume_is_null_when_there_is_no_resume() -> None:
    """Null is "not checked"; False would be a claim the resume omits it."""
    result = keyword_service.match_keywords([keyword("python")], ["Python."])

    assert result["keywords"][0]["in_resume"] is None


def test_the_resume_is_scored_separately_from_the_profile() -> None:
    """A skill the profile has but the tailored resume dropped is worth seeing."""
    result = keyword_service.match_keywords(
        [keyword("python"), keyword("kubernetes")],
        ["Python and Kubernetes both."],
        ["## Skills", "Python"],
    )

    rows = {row["keyword"]: row for row in result["keywords"]}
    assert rows["python"]["in_profile"] is True
    assert rows["python"]["in_resume"] is True
    assert rows["kubernetes"]["in_profile"] is True
    assert rows["kubernetes"]["in_resume"] is False


def test_the_score_is_the_profile_not_the_resume() -> None:
    """The resume is a second opinion; the profile is the candidate."""
    result = keyword_service.match_keywords(
        [keyword("python", "required")], ["Python."], ["A resume with no skills."]
    )

    assert result["match_percent"] == 100
    assert result["keywords"][0]["in_resume"] is False


def test_the_resume_supplies_evidence_the_profile_lacks() -> None:
    """When only the resume says it, the resume's line is the honest snippet."""
    result = keyword_service.match_keywords(
        [keyword("kubernetes")], ["Python only."], ["Ran Kubernetes in anger."]
    )

    assert result["keywords"][0]["in_profile"] is False
    assert result["keywords"][0]["evidence"] == "Ran Kubernetes in anger."


# ==========================================================================
# Building the profile corpus
# ==========================================================================


def test_profile_corpus_finds_every_string_in_the_stored_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback walk is structure-agnostic, so new profile fields are free."""
    monkeypatch.delattr(profile_service, "render_profile_text", raising=False)

    corpus = keyword_service.profile_corpus(
        {
            "skills": ["Python", "Kubernetes"],
            "publications": [
                {"title": "On Ledger Reconciliation", "year": "2024"}
            ],
            "education": [{"coursework": ["Distributed Systems"]}],
        }
    )
    joined = " ".join(corpus)

    assert "Kubernetes" in joined
    assert "On Ledger Reconciliation" in joined
    assert "Distributed Systems" in joined


def test_profile_corpus_prefers_the_shared_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When profile_service can render the profile, that is the corpus."""
    monkeypatch.setattr(
        profile_service,
        "render_profile_text",
        lambda parsed: "Line one\nLine two",
        raising=False,
    )

    assert keyword_service.profile_corpus({"skills": ["ignored"]}) == [
        "Line one",
        "Line two",
    ]


def test_profile_corpus_falls_back_when_the_renderer_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken helper must not take the whole feature down with it."""

    def boom(parsed):
        raise RuntimeError("nope")

    monkeypatch.setattr(
        profile_service, "render_profile_text", boom, raising=False
    )

    assert keyword_service.profile_corpus({"skills": ["Python"]}) == ["Python"]


def test_profile_corpus_of_no_profile_is_empty() -> None:
    """No profile is not an error here -- the route has already refused."""
    assert keyword_service.profile_corpus(None) == []


# ==========================================================================
# Coercing what the model returned
# ==========================================================================


def test_coerce_keywords_survives_a_malformed_reply() -> None:
    """Unknown categories, missing importance, and bare strings all land."""
    coerced = keyword_service.coerce_keywords(
        {
            "keywords": [
                {"keyword": "Python", "category": "wizardry"},
                {"keyword": "  ", "importance": "required"},
                "kubernetes",
                {"category": "skill"},
                42,
            ]
        }
    )

    assert [item["keyword"] for item in coerced] == ["python", "kubernetes"]
    assert coerced[0]["category"] == keyword_service.DEFAULT_CATEGORY
    assert coerced[0]["importance"] == keyword_service.DEFAULT_IMPORTANCE


def test_coerce_keywords_dedupes_on_the_normalised_form() -> None:
    """"APIs" and "api" are one requirement, and must not be scored twice."""
    coerced = keyword_service.coerce_keywords(
        {"keywords": [{"keyword": "APIs"}, {"keyword": "api"}]}
    )

    assert len(coerced) == 1


def test_coerce_keywords_caps_the_list() -> None:
    """A model that returns two hundred keywords does not get to."""
    coerced = keyword_service.coerce_keywords(
        {"keywords": [{"keyword": "skill-{}".format(n)} for n in range(200)]}
    )

    assert len(coerced) == keyword_service.MAX_KEYWORDS


def test_extraction_asks_azure_at_a_low_temperature(mock_extraction) -> None:
    """Extraction is a reading task, so it goes to GPT-4o and stays cold."""
    keywords, provider = keyword_service.extract_jd_keywords("Python and Postgres.")

    assert provider == llm.AZURE
    assert mock_extraction["kwargs"]["prefer"] == llm.AZURE
    assert mock_extraction["kwargs"]["temperature"] == 0.1
    assert mock_extraction["kwargs"]["max_tokens"] == 2048
    assert [item["keyword"] for item in keywords][:2] == ["python", "postgresql"]
    assert "Python and Postgres." in mock_extraction["messages"][1]["content"]


def test_extraction_rejects_an_empty_job_description() -> None:
    """No JD, no keywords -- and no model call to discover that."""
    with pytest.raises(KeywordError):
        keyword_service.extract_jd_keywords("   ")


def test_extraction_raises_on_unparseable_output(mock_extraction) -> None:
    """Prose where JSON was asked for is a KeywordError, not a crash."""
    mock_extraction["body"] = "I think the main skills are Python and SQL."

    with pytest.raises(KeywordError):
        keyword_service.extract_jd_keywords("Python.")


def test_extraction_raises_when_the_model_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both providers failing surfaces as one error the route can map to 502."""

    def boom(messages, **kwargs):
        raise RuntimeError("azure is down")

    monkeypatch.setattr(llm, "complete_json", boom)

    with pytest.raises(KeywordError):
        keyword_service.extract_jd_keywords("Python.")


# ==========================================================================
# POST /chats/{id}/keywords
# ==========================================================================


def test_keyword_match_returns_and_stores_the_result(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """One call reads the JD, scores the profile, and files the answer."""
    chat = seeded_chat(db)

    response = auth_client.post("/chats/{}/keywords".format(chat.id))

    assert response.status_code == 200
    body = response.json()
    rows = {row["keyword"]: row for row in body["keywords"]}
    assert rows["python"]["in_profile"] is True
    assert rows["postgresql"]["in_profile"] is True
    assert rows["kubernetes"]["in_profile"] is False
    assert body["missing_required"] == ["kubernetes"]
    assert body["provider"] == llm.AZURE
    assert body["generated_at"]
    assert chat.keyword_match["match_percent"] == body["match_percent"]


def test_keyword_match_is_reachable_from_the_chat_detail(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """Reopening a chat redraws the match without re-running anything."""
    chat = seeded_chat(db)
    assert auth_client.get("/chats/{}".format(chat.id)).json()["keyword_match"] is None

    auth_client.post("/chats/{}/keywords".format(chat.id))

    detail = auth_client.get("/chats/{}".format(chat.id)).json()
    assert detail["keyword_match"]["required_total"] == 3
    assert mock_extraction["calls"] == 1


def test_a_second_call_reuses_the_extraction_but_rescores(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """The JD has not changed; the profile has. Only one of those costs money."""
    chat = seeded_chat(db)
    first = auth_client.post("/chats/{}/keywords".format(chat.id)).json()
    assert first["required_matched"] == 2

    profile = profile_service.get_profile(db, str(chat.user_id))
    profile.parsed_json = dict(
        profile.parsed_json, skills=["Python", "PostgreSQL", "Kubernetes"]
    )

    second = auth_client.post("/chats/{}/keywords".format(chat.id)).json()

    assert mock_extraction["calls"] == 1
    assert second["required_matched"] == 3
    assert second["missing_required"] == []
    assert second["match_percent"] > first["match_percent"]


def test_force_re_extracts_from_the_job_description(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """?force=true is the only way to spend a model call on the same JD twice."""
    chat = seeded_chat(db)
    auth_client.post("/chats/{}/keywords".format(chat.id))

    mock_extraction["body"] = json.dumps(
        {"keywords": [{"keyword": "rust", "importance": "required"}]}
    )
    forced = auth_client.post(
        "/chats/{}/keywords?force=true".format(chat.id)
    ).json()

    assert mock_extraction["calls"] == 2
    assert [row["keyword"] for row in forced["keywords"]] == ["rust"]
    assert chat.keyword_match["missing_required"] == ["rust"]


def test_reuse_keeps_the_provider_that_did_the_reading(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """The provider names who extracted the keywords, not who scored them."""
    chat = seeded_chat(db)
    auth_client.post("/chats/{}/keywords".format(chat.id))

    assert (
        auth_client.post("/chats/{}/keywords".format(chat.id)).json()["provider"]
        == llm.AZURE
    )


def test_a_generated_resume_is_matched_as_a_second_corpus(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """With a resume in the chat, every keyword reports both corpora."""
    chat = seeded_chat(db)
    db.seed(
        make_output(
            chat.id,
            output_type="resume",
            content="# Ada\n\n## Skills\nPython, Go\n",
        )
    )

    rows = {
        row["keyword"]: row
        for row in auth_client.post("/chats/{}/keywords".format(chat.id)).json()[
            "keywords"
        ]
    }

    assert rows["python"]["in_resume"] is True
    assert rows["postgresql"]["in_profile"] is True
    assert rows["postgresql"]["in_resume"] is False


def test_in_resume_is_null_until_a_resume_exists(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """A cover letter is not a resume, so it is not the second corpus."""
    chat = seeded_chat(db)
    db.seed(make_output(chat.id, output_type="cover_letter", content="Dear team"))

    rows = auth_client.post("/chats/{}/keywords".format(chat.id)).json()["keywords"]

    assert all(row["in_resume"] is None for row in rows)


def test_keyword_match_409s_without_a_profile(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """There is nothing to match against, and the frontend says so by name."""
    chat = db.seed(make_chat())
    db.seed(make_tracker(chat.id))

    response = auth_client.post("/chats/{}/keywords".format(chat.id))

    assert response.status_code == 409
    assert response.json()["detail"] == NO_PROFILE
    assert mock_extraction["calls"] == 0


def test_keyword_match_422s_without_a_job_description(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """A chat with no JD has nothing to extract keywords from."""
    chat = seeded_chat(db, jd_text=None)

    response = auth_client.post("/chats/{}/keywords".format(chat.id))

    assert response.status_code == 422
    assert response.json()["detail"] == NO_JD


def test_keyword_match_404s_on_another_users_chat(
    auth_client: TestClient, db: FakeSession, mock_extraction
) -> None:
    """Someone else's chat does not exist, and is not scored."""
    chat = db.seed(make_chat(user_id=OTHER_USER_ID))
    db.seed(make_profile())

    response = auth_client.post("/chats/{}/keywords".format(chat.id))

    assert response.status_code == 404
    assert chat.keyword_match is None


def test_keyword_match_404s_on_an_unknown_chat(
    auth_client: TestClient, mock_extraction
) -> None:
    """A chat id that was never issued is a 404, not a 500."""
    response = auth_client.post("/chats/{}/keywords".format(uuid.uuid4()))

    assert response.status_code == 404


def test_keyword_match_502s_when_extraction_fails(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider outage is reported as a bad gateway, and stores nothing."""
    chat = seeded_chat(db)

    def boom(messages, **kwargs):
        raise RuntimeError("azure is down")

    monkeypatch.setattr(llm, "complete_json", boom)

    response = auth_client.post("/chats/{}/keywords".format(chat.id))

    assert response.status_code == 502
    assert chat.keyword_match is None


# ==========================================================================
# Live extraction (opt-in)
# ==========================================================================


@pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1", reason="Set RUN_LIVE=1 to call Azure for real"
)
def test_live_keyword_extraction() -> None:
    """Every offline test here would pass with a prompt that returned nonsense."""
    jd = (
        "Senior Backend Engineer. You will own our Python services on AWS, "
        "design PostgreSQL schemas for high-volume ledgers, and run the CI/CD "
        "pipeline. Kubernetes experience is a plus. Strong written "
        "communication is required. Fintech background preferred."
    )

    keywords, provider = keyword_service.extract_jd_keywords(jd)

    assert provider in llm.PROVIDERS
    assert keyword_service.MIN_KEYWORDS - 5 <= len(keywords) <= 40
    names = {item["keyword"] for item in keywords}
    assert {"python", "postgresql"} & names
    assert all(item["category"] in keyword_service.CATEGORIES for item in keywords)
    assert any(item["importance"] == "required" for item in keywords)
