"""Tests for the FDE classifier."""

from fde_job_atlas.classifier.fde_classifier import (
    LABEL_CUSTOMER,
    LABEL_FDE,
    LABEL_FIELD,
    LABEL_IMPLEMENTATION,
    LABEL_NOT_FDE,
    LABEL_SOLUTIONS,
    FDEClassifier,
    _extract_handcrafted_features,
    _weak_label,
)
from fde_job_atlas.models import JobPosting


def _make_posting(title: str, description: str = "") -> JobPosting:
    return JobPosting(url=f"https://example.com/{title}", title=title, description=description)


# ── Weak label tests ─────────────────────────────────────────────────


def test_weak_label_forward_deployed():
    p = _make_posting("Forward Deployed Engineer")
    label, score = _weak_label(p)
    assert label == LABEL_FDE
    assert score >= 0.9


def test_weak_label_customer_engineer():
    p = _make_posting("Customer Engineer")
    label, score = _weak_label(p)
    assert label == LABEL_CUSTOMER
    assert score >= 0.8


def test_weak_label_solutions_engineer():
    p = _make_posting("Solutions Engineer")
    label, score = _weak_label(p)
    assert label == LABEL_SOLUTIONS
    assert score >= 0.7


def test_weak_label_implementation_engineer():
    p = _make_posting("Implementation Engineer")
    label, score = _weak_label(p)
    assert label == LABEL_IMPLEMENTATION
    assert score >= 0.7


def test_weak_label_field_engineer():
    p = _make_posting("Field Engineer")
    label, score = _weak_label(p)
    assert label == LABEL_FIELD
    assert score >= 0.7


def test_weak_label_negative():
    p = _make_posting("Sales Representative")
    label, score = _weak_label(p)
    assert label == LABEL_NOT_FDE


def test_weak_label_description_signals():
    p = _make_posting(
        "Technical Specialist",
        "Customer-facing role with travel required. Deploy solutions at client sites. "
        "Build proof-of-concept demonstrations. Enterprise customer integration work.",
    )
    label, score = _weak_label(p)
    assert label == LABEL_FDE
    assert score >= 0.4


def test_weak_label_generic_engineer():
    p = _make_posting("Backend Engineer", "Build APIs and microservices.")
    label, score = _weak_label(p)
    assert label == LABEL_NOT_FDE


# ── Handcrafted feature tests ────────────────────────────────────────


def test_handcrafted_features_shape():
    """Feature vector should have consistent shape."""
    features = _extract_handcrafted_features("Forward Deployed Engineer", "Customer-facing role")
    assert features.ndim == 1
    assert len(features) > 20  # At least 20 features


def test_handcrafted_features_fde_positive():
    """FDE postings should have high feature values for relevant features."""
    fde_features = _extract_handcrafted_features(
        "Forward Deployed Engineer",
        "Customer-facing deployment role with travel required and enterprise integration.",
    )
    generic_features = _extract_handcrafted_features(
        "Backend Engineer",
        "Build REST APIs and maintain database infrastructure.",
    )
    # FDE should have higher sum of features (more signals firing)
    assert fde_features.sum() > generic_features.sum()


# ── Classifier fallback tests ────────────────────────────────────────


def test_classify_fallback_fde():
    """Classifier fallback (no trained model) should score FDE titles highly."""
    clf = FDEClassifier(threshold=0.5)
    p = _make_posting(
        "Forward Deployed Engineer",
        "Deploy software at customer sites.",
    )
    result = clf._classify_fallback(p)
    assert result.fde_score >= 0.5
    assert result.fde_label != LABEL_NOT_FDE


def test_classify_fallback_not_fde():
    """Non-FDE titles should score below threshold."""
    clf = FDEClassifier(threshold=0.5)
    p = _make_posting(
        "Marketing Manager",
        "Lead marketing campaigns and brand strategy.",
    )
    result = clf._classify_fallback(p)
    assert result.fde_label == LABEL_NOT_FDE


# ── Training tests ───────────────────────────────────────────────────


def test_train_with_weak_labels():
    """Training with weak labels should succeed and produce metrics."""
    clf = FDEClassifier(threshold=0.5)
    postings = [
        _make_posting("Forward Deployed Engineer", "Customer-facing deployment role."),
        _make_posting("Solutions Engineer", "Build integrations for enterprise clients."),
        _make_posting("Customer Engineer", "Provide technical support during deployment."),
        _make_posting("Backend Engineer", "Build APIs and services."),
        _make_posting("Frontend Engineer", "Build React components."),
        _make_posting("Data Scientist", "Build ML models."),
        _make_posting("Marketing Manager", "Run campaigns."),
        _make_posting("Sales Representative", "Sell products."),
        _make_posting("Recruiter", "Hire people."),
        _make_posting("Implementation Engineer", "Deploy solutions at client sites."),
    ]
    metrics = clf.train(postings)
    assert metrics["n_samples"] == 10
    assert metrics["n_positive"] >= 3
    assert clf._is_trained is True


def test_classify_with_trained_model():
    """After training, classification should use the model."""
    clf = FDEClassifier(threshold=0.5)
    postings = [
        _make_posting("Forward Deployed Engineer", "Customer-facing deployment."),
        _make_posting("Solutions Engineer", "Build integrations for clients."),
        _make_posting("Customer Engineer", "Technical support for deployment."),
        _make_posting("Implementation Engineer", "Deploy at customer sites."),
        _make_posting("Field Engineer", "Field work at client locations."),
        _make_posting("Backend Engineer", "Build APIs."),
        _make_posting("Frontend Engineer", "Build UIs."),
        _make_posting("Data Scientist", "ML models."),
        _make_posting("Marketing Manager", "Campaigns."),
        _make_posting("Recruiter", "Hire people."),
    ]
    clf.train(postings)

    fde_posting = _make_posting("Forward Deployed Engineer", "Deploy at customer sites.")
    result = clf.classify(fde_posting)
    assert result.fde_score > 0.0  # Model should produce a score


# ── Active learning tests ────────────────────────────────────────────


def test_uncertain_samples_without_model():
    """Uncertain samples should be returned even without a trained model."""
    clf = FDEClassifier()
    postings = [
        _make_posting("Forward Deployed Engineer", "Deploy software."),
        _make_posting("Technical Specialist", "Some ambiguous role."),
        _make_posting("Backend Engineer", "Build services."),
    ]
    uncertain = clf.get_uncertain_samples(postings, n=2)
    assert len(uncertain) == 2
    assert all(isinstance(u, tuple) and len(u) == 2 for u in uncertain)
