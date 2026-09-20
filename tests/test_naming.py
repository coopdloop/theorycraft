import json

import pytest

from theorycraft import naming
from theorycraft.graph.nodes.github_publish import _product_name
from theorycraft.integrations.github import _is_name_collision


class TestSlugifyWords:
    def test_short_text_is_untouched(self):
        assert naming.slugify_words("Paerhaps") == "paerhaps"

    def test_drops_trailing_words_instead_of_cutting_one(self):
        slug = naming.slugify_words("an llm cli chat where you talk with and i spec", max_length=40)
        assert slug == "an-llm-cli-chat-where-you-talk-with-and"

    def test_single_word_longer_than_budget_is_hard_cut(self):
        assert naming.slugify_words("supercalifragilisticexpialidocious", max_length=10) == "supercalif"

    def test_empty_text(self):
        assert naming.slugify_words("!!!") == ""


class TestIdeaSlug:
    def test_strips_leading_prompt_filler(self):
        assert naming.idea_slug("I want to build a link shortener") == "link-shortener"

    def test_drops_filler_stranded_by_truncation(self):
        assert naming.idea_slug("An LLM CLI chat where you talk with and", max_length=32) == "llm-cli-chat-where-you-talk"

    def test_respects_max_length(self):
        assert len(naming.idea_slug(" ".join(["widget"] * 40), max_length=30)) <= 30


class TestRepoName:
    def test_uses_the_product_name_not_the_idea_prompt(self):
        idea = "An LLM CLI chat where you talk with and I spec"
        assert naming.repo_name("Paerhaps", naming.idea_slug(idea)) == "paerhaps-spec"

    def test_falls_back_to_the_session_slug(self):
        assert naming.repo_name("", "llm-cli-chat-where-you-talk") == "llm-cli-chat-where-you-talk-spec"

    def test_cuts_a_long_product_name_without_losing_the_suffix(self):
        repo = naming.repo_name("Word " * 60, "")
        assert len(repo) <= naming.GITHUB_REPO_MAX_LENGTH
        assert repo.endswith("-spec")

    def test_does_not_double_the_suffix(self):
        assert naming.repo_name("Paerhaps Spec", "") == "paerhaps-spec"

    def test_never_returns_a_blank_name(self):
        assert naming.repo_name("", "") == "theorycraft-spec"

    def test_sanitizes_non_ascii(self):
        assert naming.repo_name("Café Qué?!", "") == "cafe-que-spec"

    def test_deduped_names_stay_under_the_limit(self):
        deduped = naming.repo_name("x" * 300, "", suffix="-spec-2")
        assert len(deduped) <= naming.GITHUB_REPO_MAX_LENGTH
        assert deduped.endswith("-spec-2")


class TestPackageScope:
    def test_nameless_product_still_gets_a_scope(self):
        assert naming.package_scope("") == "myproduct"

    def test_product_name_becomes_the_sdk_scope(self):
        assert naming.package_scope("Paerhaps Console") == "paerhaps-console"


class TestTitleFromConcept:
    def test_strips_markdown_and_label(self):
        assert naming.title_from_concept("## **Product name:** Paerhaps") == "Paerhaps"

    def test_truncates_on_a_word_boundary(self):
        title = naming.title_from_concept("word " * 40, max_length=30)
        assert len(title) <= 30 and not title.endswith(" ")

    def test_empty_concept(self):
        assert naming.title_from_concept("") == "Untitled product"


class TestProductNameFromConcept:
    CONCEPTS = {
        "# Paerhaps\n\n**Product name:** Paerhaps\nA claude-tag style CLI for group chat.\n": "Paerhaps",
        "## Product Name: **FocusGuard**\n\nTagline: never lose a tab\n": "FocusGuard",
        "**Product name**: Marble Jar\n": "Marble Jar",
        "": "Untitled product",
    }

    def test_extracts_whatever_shape_the_model_used(self):
        for concept, expected in self.CONCEPTS.items():
            assert naming.product_name_from_concept(concept) == expected

    def test_tagline_is_not_mistaken_for_the_name(self):
        concept = "# Paerhaps\n**Product name:** Paerhaps — a CLI for group chat\n"
        assert naming.product_name_from_concept(concept) == "Paerhaps"

    def test_long_name_is_clipped_on_a_word_boundary(self):
        concept = "**Product name:** " + " ".join(["widget"] * 20)
        name = naming.product_name_from_concept(concept)
        assert len(name) <= 40 and not name.endswith("wid")


class TestPublishWiring:
    def test_product_name_comes_from_the_compiled_spec(self):
        assert _product_name(json.dumps({"vision": {"name": "Paerhaps"}})) == "Paerhaps"

    def test_malformed_spec_falls_back_to_no_name(self):
        assert _product_name("{not json") == ""
        assert _product_name(json.dumps({"vision": None})) == ""
        assert _product_name(json.dumps({})) == ""

    def test_regression_theorycraft_idea_publishes_as_the_product_name(self):
        """The bug: a long prompt became a truncated sentence as the repo name."""
        idea = "An LLM CLI chat where you talk with and I spec"
        session = naming.idea_slug(idea)
        concept = "# Paerhaps\n\n**Product name:** Paerhaps\n\nTagline: group chat in your terminal\n"
        product = naming.product_name_from_concept(concept)

        assert session == "llm-cli-chat-where-you-talk-with-and-i-spec"
        assert naming.repo_name(product, session) == "paerhaps-spec"
        # Even with no product name at all, the fallback must not cut mid-word.
        assert naming.repo_name("", session).endswith("-spec")
        assert "- i-spec" not in naming.repo_name("", session)

    def test_github_publish_prefers_the_state_product_name(self, monkeypatch, tmp_path):
        from types import SimpleNamespace

        from theorycraft.graph.nodes.github_publish import github_publish as publish_node

        spec = tmp_path / "product.json"
        spec.write_text(json.dumps({"vision": {"name": "Paerhaps"}}))

        seen = {}

        class FakeClient:
            def __init__(self, _cfg):
                pass

            def create_repo(self, session_name, content, *, org=None, product_name=""):
                seen["session_name"] = session_name
                seen["product_name"] = product_name
                return "https://github.com/coopdloop/paerhaps-spec"

        monkeypatch.setattr("theorycraft.integrations.github.GitHubClient", FakeClient)
        monkeypatch.setattr(
            "theorycraft.config.get_settings",
            lambda: SimpleNamespace(github_enabled=True, github_org=None),
        )

        result = publish_node(
            {"session_name": "llm-cli-chat", "output_path": str(spec), "github_publish_mode": "repo"}
        )

        assert result["github_output_url"].endswith("paerhaps-spec")
        assert seen == {"session_name": "llm-cli-chat", "product_name": "Paerhaps"}


class TestCollisionDetection:
    def test_recognizes_githubs_name_taken_error(self):
        assert _is_name_collision(Exception('422 {"message": "name already exists on this account"}'))

    def test_does_not_swallow_unrelated_failures(self):
        assert not _is_name_collision(Exception("401 Bad credentials"))


class _FakeContents:
    sha = "deadbeef"


class _FakeRepo:
    html_url = "https://github.com/coopdloop/paerhaps-spec"

    def __init__(self, name):
        self.name = name
        self.files: list[str] = []

    def get_contents(self, path, ref=None):
        return _FakeContents()

    def update_file(self, path, *args, **kwargs):
        self.files.append(path)

    def create_file(self, path, *args, **kwargs):
        self.files.append(path)


class _FakeOwner:
    def __init__(self, taken=()):
        self.taken = set(taken)
        self.created: list[str] = []

    def create_repo(self, name, **kwargs):
        if name in self.taken:
            raise Exception(f'422 {{"message": "name already exists on this account"}} for {name}')
        self.created.append(name)
        return _FakeRepo(name)


def _client():
    """A GitHubClient with auth and the post-create sleep bypassed."""
    from types import SimpleNamespace

    from theorycraft.integrations.github import GitHubClient

    client = GitHubClient.__new__(GitHubClient)
    client._cfg = SimpleNamespace(github_org=None)
    return client


class TestCreateRepoNaming:
    def test_repo_is_named_after_the_product_not_the_idea(self, monkeypatch):
        monkeypatch.setattr("theorycraft.integrations.github.time.sleep", lambda _s: None)
        client = _client()
        owner = _FakeOwner()
        monkeypatch.setattr(client, "_get_org_or_user", lambda org=None: owner)

        client.create_repo(
            "a-llm-cli-chat-where-you-talk-with-and-i",
            "{}",
            product_name="Paerhaps",
        )

        assert owner.created == ["paerhaps-spec"]

    def test_retries_with_a_suffix_when_the_name_is_taken(self, monkeypatch):
        monkeypatch.setattr("theorycraft.integrations.github.time.sleep", lambda _s: None)
        client = _client()
        owner = _FakeOwner(taken=["paerhaps-spec"])
        monkeypatch.setattr(client, "_get_org_or_user", lambda org=None: owner)

        client.create_repo("paerhaps", "{}", product_name="Paerhaps")

        assert owner.created == ["paerhaps-spec-2"]

    def test_non_collision_errors_are_not_retried(self, monkeypatch):
        client = _client()
        owner = _FakeOwner()

        def boom(name, **kwargs):
            raise Exception("401 Bad credentials")

        owner.create_repo = boom
        monkeypatch.setattr(client, "_get_org_or_user", lambda org=None: owner)

        with pytest.raises(Exception, match="Bad credentials"):
            client.create_repo("paerhaps", "{}", product_name="Paerhaps")
