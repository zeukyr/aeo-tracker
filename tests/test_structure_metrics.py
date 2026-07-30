"""
The new geo_features.json 'ratio' detectors: structural metrics computed from
a structure-preserving trafilatura pass (internal linking density, structured
content share, heading hierarchy depth, paragraph length conformance, emphasis
density) plus query_term_coverage.

_metrics_from_xml is tested directly against hand-built trafilatura-shaped XML
fixtures - this exercises exactly the arithmetic this repo owns, independent
of trafilatura's own content-quality/boilerplate heuristics (a third-party
concern, already spot-checked separately against live pages). No DB, network,
or LLM.
"""

from api.queries.page_facts import _metrics_from_xml, query_term_coverage

_URL = "https://example.com/page"


def _doc(inner):
    return f'<doc><main>{inner}</main></doc>'


def test_no_main_or_empty_content_returns_empty_metrics():
    assert _metrics_from_xml("<doc></doc>", _URL) == {
        "internal_linking_density": None,
        "heading_hierarchy_depth": 0,
        "structured_content_ratio": None,
        "paragraph_length_conformance": None,
        "emphasis_density": None,
    }
    assert _metrics_from_xml(_doc(""), _URL)["structured_content_ratio"] is None


def test_heading_hierarchy_depth_counts_distinct_levels():
    xml = _doc(
        '<head rend="h1">Title</head><p>intro text here</p>'
        '<head rend="h2">Section</head><p>more text here</p>'
        '<head rend="h3">Sub section</head><p>even more text</p>'
    )
    assert _metrics_from_xml(xml, _URL)["heading_hierarchy_depth"] == 3


def test_repeated_heading_level_counts_once():
    xml = _doc('<head rend="h2">A</head><p>x</p><head rend="h2">B</head><p>y</p>')
    assert _metrics_from_xml(xml, _URL)["heading_hierarchy_depth"] == 1


def test_internal_vs_external_link_density():
    xml = _doc(
        "<p>ten filler words padding out this paragraph for the word count check yes</p>"
        f'<p>See our <ref target="{_URL}/internal-one">grooming guide</ref> for more.</p>'
        f'<p>Also read <ref target="https://external.com/x">this article</ref> too.</p>'
    )
    metrics = _metrics_from_xml(xml, _URL)
    # 1 internal / 2 total links = 50%
    assert metrics["internal_linking_density"] == 50


def test_all_internal_links_is_100_pct():
    xml = _doc(
        f'<p>One <ref target="{_URL}/a">link</ref> and '
        f'<ref target="{_URL}/b">another</ref> here.</p>'
    )
    assert _metrics_from_xml(xml, _URL)["internal_linking_density"] == 100


def test_no_links_is_unmeasurable_not_zero():
    xml = _doc("<p>Just plain text with no links anywhere in it at all.</p>")
    assert _metrics_from_xml(xml, _URL)["internal_linking_density"] is None


def test_structured_content_ratio_counts_lists_tables_quotes():
    xml = _doc(
        "<p>ten filler words padding this paragraph for word count test</p>"
        "<list rend='ul'><item>one two three four five</item></list>"
        "<table><row><cell>six seven eight nine ten</cell></row></table>"
    )
    metrics = _metrics_from_xml(xml, _URL)
    # 10 structured words (5 list + 5 table) out of 20 total = 50%
    assert metrics["structured_content_ratio"] == 50


def test_emphasis_density_counts_bold_and_italic():
    xml = _doc(
        '<p>eight filler words here to pad this text '
        '<hi rend="#b">bold word</hi></p>'
    )
    metrics = _metrics_from_xml(xml, _URL)
    # 2 emphasized words out of 10 total = 20%
    assert metrics["emphasis_density"] == 20


def test_paragraph_length_conformance_in_and_out_of_range():
    short_para = "<p>" + ("word " * 10) + "</p>"    # below the 150-300 target
    good_para = "<p>" + ("word " * 200) + "</p>"     # inside the 150-300 target
    xml = _doc(short_para + good_para)
    assert _metrics_from_xml(xml, _URL)["paragraph_length_conformance"] == 50


def test_query_term_coverage_counts_significant_terms():
    question = "How much does it cost to become a certified dog groomer?"
    text = "Becoming a certified dog groomer requires hands-on training."
    coverage = query_term_coverage(question, text)
    # significant terms: much, cost, become, certified, dog, groomer (6);
    # present verbatim: certified, dog, groomer (3) - "become" doesn't match
    # "becoming" (word-boundary match, not a substring/stem match), and
    # "much"/"cost" don't appear in the text at all. 3/6 = 50%.
    assert coverage == 50


def test_query_term_coverage_none_when_no_question_or_text():
    assert query_term_coverage(None, "some text") is None
    assert query_term_coverage("a question", "") is None
    assert query_term_coverage("is are the", "anything") is None  # only stopwords
