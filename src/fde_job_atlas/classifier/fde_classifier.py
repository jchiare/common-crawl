"""FDE relevance classification with a proper ML pipeline.

Architecture:
  1. Feature extraction layer:
     - TF-IDF on title + description text
     - Sentence-transformer embeddings (semantic features)
     - Hand-crafted keyword / pattern features
  2. Classifier layer:
     - Logistic regression (interpretable baseline)
     - Gradient-boosted trees (higher accuracy)
     - Ensemble of both
  3. Active learning loop:
     - Identify uncertain predictions for human review
     - Retrain with new labels
  4. Weak-label bootstrapping:
     - Keyword rules generate noisy labels for initial training
"""

from __future__ import annotations

import logging
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, VotingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline as SKPipeline
from sklearn.preprocessing import StandardScaler

from fde_job_atlas.models import JobPosting

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

LABEL_FDE = "forward_deployed"
LABEL_SOLUTIONS = "solutions_engineer"
LABEL_CUSTOMER = "customer_engineer"
LABEL_IMPLEMENTATION = "implementation_engineer"
LABEL_FIELD = "field_engineer"
LABEL_NOT_FDE = "not_fde"

_POSITIVE_LABELS = {LABEL_FDE, LABEL_SOLUTIONS, LABEL_CUSTOMER, LABEL_IMPLEMENTATION, LABEL_FIELD}

# ── Keyword rule patterns ────────────────────────────────────────────

_STRONG_TITLE_RULES: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\bforward[\s\-]deployed\b", re.I), LABEL_FDE, 0.95),
    (re.compile(r"\bcustomer[\s\-]engineer", re.I), LABEL_CUSTOMER, 0.85),
    (re.compile(r"\bsolutions?[\s\-]engineer", re.I), LABEL_SOLUTIONS, 0.80),
    (re.compile(r"\bimplementation[\s\-]engineer", re.I), LABEL_IMPLEMENTATION, 0.80),
    (re.compile(r"\bfield[\s\-]engineer", re.I), LABEL_FIELD, 0.80),
    (re.compile(r"\bdeployment[\s\-]engineer", re.I), LABEL_FDE, 0.75),
    (re.compile(r"\bapplied[\s\-]engineer", re.I), LABEL_FDE, 0.70),
    (re.compile(r"\btechnical[\s\-]account[\s\-]manager", re.I), LABEL_FDE, 0.70),
    (re.compile(r"\bpartner[\s\-]engineer", re.I), LABEL_FDE, 0.70),
    (re.compile(r"\bprofessional[\s\-]services[\s\-]engineer", re.I), LABEL_FDE, 0.75),
    (re.compile(r"\bsolution[\s\-]architect", re.I), LABEL_SOLUTIONS, 0.65),
]

_POSITIVE_DESC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bcustomer[\s\-]facing\b", re.I),
    re.compile(r"\bclient[\s\-]facing\b", re.I),
    re.compile(r"\bon[\s\-]?site.{0,20}(customer|client)", re.I),
    re.compile(r"\btravel.{0,30}(percent|%|required)", re.I),
    re.compile(r"\bdeployment\b", re.I),
    re.compile(r"\bintegration.{0,20}(partner|customer|client)", re.I),
    re.compile(r"\btechnical.{0,10}relationship", re.I),
    re.compile(r"\bpre[\s\-]?sales?\b", re.I),
    re.compile(r"\bpost[\s\-]?sales?\b", re.I),
    re.compile(r"\bpoc\b|\bproof[\s\-]of[\s\-]concept\b", re.I),
    re.compile(r"\bcustomer[\s\-]success\b", re.I),
    re.compile(r"\bfield.{0,10}(work|role|position|team)\b", re.I),
    re.compile(r"\bwhite[\s\-]glove\b", re.I),
    re.compile(r"\bhands[\s\-]on.{0,20}(deployment|implementation|integration)", re.I),
    re.compile(r"\benterprise.{0,15}(customer|client|account)", re.I),
]

_NEGATIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsales[\s\-]representative\b", re.I),
    re.compile(r"\baccount[\s\-]executive\b", re.I),
    re.compile(r"\bmarketing\b", re.I),
    re.compile(r"\bbusiness[\s\-]development[\s\-]representative\b", re.I),
    re.compile(r"\brecruiter\b", re.I),
    re.compile(r"\bdata[\s\-]scientist\b", re.I),
    re.compile(r"\bmachine[\s\-]learning[\s\-]engineer\b", re.I),
    re.compile(r"\bbackend[\s\-]engineer\b", re.I),
    re.compile(r"\bfrontend[\s\-]engineer\b", re.I),
]


# ── Hand-crafted feature extraction ─────────────────────────────────


def _extract_handcrafted_features(title: str, description: str) -> np.ndarray:
    """Extract 20+ hand-engineered features from a posting.

    These capture domain-specific signals that TF-IDF / embeddings might miss.
    """
    text = f"{title} {description}".lower()
    title_lower = title.lower()
    features = []

    # Title keyword features (binary)
    for pat, _, _ in _STRONG_TITLE_RULES:
        features.append(1.0 if pat.search(title) else 0.0)

    # Positive description pattern hit count
    pos_hits = sum(1 for pat in _POSITIVE_DESC_PATTERNS if pat.search(text))
    features.append(float(pos_hits))
    features.append(float(min(pos_hits, 5)) / 5.0)  # normalized

    # Negative pattern hit count
    neg_hits = sum(1 for pat in _NEGATIVE_PATTERNS if pat.search(text))
    features.append(float(neg_hits))

    # Text length features
    features.append(float(len(description)) / 5000.0)  # normalized length
    features.append(float(len(title.split())))  # title word count

    # Travel mention
    features.append(1.0 if re.search(r"\btravel\b", text) else 0.0)

    # Customer / client mention density
    customer_mentions = len(re.findall(r"\b(customer|client)\b", text))
    features.append(float(min(customer_mentions, 10)) / 10.0)

    # "Deploy" family mention count
    deploy_mentions = len(re.findall(r"\b(deploy|deployment|deployed)\b", text))
    features.append(float(min(deploy_mentions, 5)) / 5.0)

    # Integration mention
    features.append(1.0 if "integration" in text else 0.0)

    # On-site / field mention
    features.append(1.0 if re.search(r"\b(on[\s\-]?site|field)\b", text) else 0.0)

    # Enterprise mention
    features.append(1.0 if "enterprise" in text else 0.0)

    # Title contains "engineer"
    features.append(1.0 if "engineer" in title_lower else 0.0)

    return np.array(features, dtype=np.float32)


def _weak_label(posting: JobPosting) -> tuple[str, float]:
    """Generate a weak label using keyword rules.

    Returns (label, confidence).
    """
    # Title-based rules (highest confidence)
    for pat, label, conf in _STRONG_TITLE_RULES:
        if pat.search(posting.title):
            return label, conf

    # Check negative signals
    for pat in _NEGATIVE_PATTERNS:
        if pat.search(posting.title):
            return LABEL_NOT_FDE, 0.8

    # Description-based scoring
    text = f"{posting.title} {posting.description}"
    pos_hits = sum(1 for pat in _POSITIVE_DESC_PATTERNS if pat.search(text))
    neg_hits = sum(1 for pat in _NEGATIVE_PATTERNS if pat.search(text))

    if pos_hits >= 4 and neg_hits == 0:
        return LABEL_FDE, 0.6
    if pos_hits >= 2 and neg_hits == 0:
        return LABEL_FDE, 0.4

    return LABEL_NOT_FDE, 0.3


# ── FDE archetype descriptions for embedding similarity ──────────────

_FDE_ARCHETYPES = [
    "Forward deployed engineer who works directly with customers to integrate and deploy software solutions on-site, requiring significant travel and client relationship management",
    "Field engineer responsible for customer-facing technical implementation, deployment, and integration of enterprise software at client locations",
    "Solutions engineer building custom integrations, proof-of-concepts, and technical demos for enterprise prospects and customers during the sales cycle",
    "Customer engineer providing hands-on technical guidance, production support, and deployment assistance during and after the enterprise sales process",
    "Implementation engineer deploying and configuring software at customer sites, managing technical project delivery with cross-functional coordination",
    "Technical account manager who combines deep engineering expertise with customer relationship management to ensure successful product adoption",
    "Professional services engineer delivering custom integrations, migrations, and technical solutions for enterprise clients post-sale",
]


@dataclass
class FDEClassifier:
    """Multi-signal FDE classifier with sklearn + embeddings.

    Training pipeline:
      1. Generate weak labels from keyword rules
      2. Extract features: TF-IDF + embeddings + hand-crafted
      3. Train ensemble classifier (logistic regression + gradient boosting)
      4. Support active learning for iterative refinement

    Inference pipeline:
      1. Extract all feature types
      2. Run through trained classifier (or fall back to keyword + embedding scoring)
      3. Set fde_score and fde_label on posting
    """

    model_name: str = "all-MiniLM-L6-v2"
    threshold: float = 0.5
    _embedding_model: Optional[object] = field(default=None, repr=False)
    _tfidf: Optional[TfidfVectorizer] = field(default=None, repr=False)
    _classifier: Optional[VotingClassifier] = field(default=None, repr=False)
    _scaler: Optional[StandardScaler] = field(default=None, repr=False)
    _archetype_embeddings: Optional[np.ndarray] = field(default=None, repr=False)
    _is_trained: bool = False

    def _load_embedding_model(self) -> None:
        """Lazy-load the sentence-transformers model."""
        if self._embedding_model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer(self.model_name)
            logger.info("Loaded embedding model: %s", self.model_name)
        except ImportError:
            logger.warning(
                "sentence-transformers not available; using keyword-only features"
            )

    def embed_text(self, text: str) -> np.ndarray | None:
        """Embed a single text. Returns None if model unavailable."""
        self._load_embedding_model()
        if self._embedding_model is None:
            return None
        return self._embedding_model.encode(text, normalize_embeddings=True)  # type: ignore[union-attr]

    def embed_batch(self, texts: list[str]) -> np.ndarray | None:
        """Embed a batch of texts."""
        self._load_embedding_model()
        if self._embedding_model is None:
            return None
        return self._embedding_model.encode(  # type: ignore[union-attr]
            texts, normalize_embeddings=True, show_progress_bar=False
        )

    def _get_archetype_embeddings(self) -> np.ndarray | None:
        """Compute and cache archetype embeddings."""
        if self._archetype_embeddings is not None:
            return self._archetype_embeddings
        embs = self.embed_batch(_FDE_ARCHETYPES)
        if embs is not None:
            self._archetype_embeddings = embs
        return embs

    def _embedding_similarity_features(self, text: str) -> np.ndarray:
        """Compute cosine similarity features against FDE archetypes.

        Returns a vector of [max_sim, mean_sim, min_sim, std_sim, per-archetype sims].
        """
        query_emb = self.embed_text(text)
        archetype_embs = self._get_archetype_embeddings()

        if query_emb is None or archetype_embs is None:
            return np.zeros(4 + len(_FDE_ARCHETYPES), dtype=np.float32)

        sims = archetype_embs @ query_emb  # cosine similarity (normalized vecs)
        agg_features = np.array(
            [float(np.max(sims)), float(np.mean(sims)), float(np.min(sims)), float(np.std(sims))],
            dtype=np.float32,
        )
        return np.concatenate([agg_features, sims.astype(np.float32)])

    def _build_feature_vector(self, posting: JobPosting) -> np.ndarray:
        """Build a complete feature vector for a posting.

        Concatenates:
          - Hand-crafted features (~25 dims)
          - Embedding similarity features (~11 dims)
          - TF-IDF features (if TF-IDF is fitted)
        """
        text = f"{posting.title}. {posting.description[:1000]}"

        # Hand-crafted
        hc = _extract_handcrafted_features(posting.title, posting.description[:2000])

        # Embedding similarity to archetypes
        emb_sim = self._embedding_similarity_features(text)

        parts = [hc, emb_sim]

        # TF-IDF (only if fitted during training)
        if self._tfidf is not None:
            tfidf_vec = self._tfidf.transform([text]).toarray()[0]
            parts.append(tfidf_vec.astype(np.float32))

        return np.concatenate(parts)

    # ── Training ─────────────────────────────────────────────────────

    def train(
        self,
        postings: list[JobPosting],
        labels: list[str] | None = None,
    ) -> dict:
        """Train the classifier on postings.

        If labels is None, uses weak (keyword-based) labeling.
        Returns a dict with training metrics.
        """
        logger.info("Training FDE classifier on %d postings", len(postings))

        # Generate labels if not provided
        if labels is None:
            labels = []
            for p in postings:
                label, _ = _weak_label(p)
                is_pos = label in _POSITIVE_LABELS
                labels.append("fde" if is_pos else "not_fde")
        else:
            # Normalize to binary
            labels = [
                "fde" if l in _POSITIVE_LABELS else "not_fde" for l in labels
            ]

        # Fit TF-IDF on training text
        texts = [
            f"{p.title}. {p.description[:1000]}" for p in postings
        ]
        self._tfidf = TfidfVectorizer(
            max_features=500,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            sublinear_tf=True,
        )
        self._tfidf.fit(texts)

        # Build feature matrix
        X = np.array([self._build_feature_vector(p) for p in postings])

        # Scale features
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)

        y = np.array(labels)

        # Build ensemble classifier
        lr = LogisticRegression(
            C=1.0, max_iter=1000, class_weight="balanced", random_state=42
        )
        gb = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42,
        )
        self._classifier = VotingClassifier(
            estimators=[("lr", lr), ("gb", gb)],
            voting="soft",
        )

        # Cross-validation
        if len(postings) >= 10:
            cv_folds = min(5, len(postings) // 2)
            cv_scores = cross_val_score(
                self._classifier, X_scaled, y, cv=cv_folds, scoring="f1_macro"
            )
            logger.info(
                "Cross-val F1 (macro): %.3f ± %.3f", cv_scores.mean(), cv_scores.std()
            )
        else:
            cv_scores = np.array([0.0])

        # Fit on full data
        self._classifier.fit(X_scaled, y)
        self._is_trained = True

        # Training metrics
        y_pred = self._classifier.predict(X_scaled)
        report = classification_report(y, y_pred, output_dict=True)
        logger.info("Training classification report:\n%s", classification_report(y, y_pred))

        return {
            "n_samples": len(postings),
            "n_positive": int(sum(1 for l in labels if l == "fde")),
            "n_negative": int(sum(1 for l in labels if l == "not_fde")),
            "cv_f1_mean": float(cv_scores.mean()),
            "cv_f1_std": float(cv_scores.std()),
            "train_report": report,
        }

    # ── Inference ────────────────────────────────────────────────────

    def classify(self, posting: JobPosting) -> JobPosting:
        """Classify a single posting.

        Uses the trained classifier if available, otherwise falls back
        to keyword rules + embedding similarity scoring.
        """
        if self._is_trained and self._classifier is not None:
            return self._classify_with_model(posting)
        return self._classify_fallback(posting)

    def _classify_with_model(self, posting: JobPosting) -> JobPosting:
        """Classify using the trained sklearn model."""
        X = self._build_feature_vector(posting).reshape(1, -1)
        if self._scaler is not None:
            X = self._scaler.transform(X)

        proba = self._classifier.predict_proba(X)[0]  # type: ignore[union-attr]
        classes = self._classifier.classes_  # type: ignore[union-attr]

        # Find probability for "fde" class
        fde_idx = list(classes).index("fde") if "fde" in classes else -1
        if fde_idx >= 0:
            fde_prob = float(proba[fde_idx])
        else:
            fde_prob = 0.0

        # Get weak label for finer-grained category
        weak_label, _ = _weak_label(posting)

        posting.fde_score = round(fde_prob, 4)
        if fde_prob >= self.threshold:
            posting.fde_label = weak_label if weak_label in _POSITIVE_LABELS else LABEL_FDE
        else:
            posting.fde_label = LABEL_NOT_FDE

        # Store embedding for vector search
        text = f"{posting.title}. {posting.description[:500]}"
        emb = self.embed_text(text)
        if emb is not None:
            posting.embedding = emb.tolist()

        return posting

    def _classify_fallback(self, posting: JobPosting) -> JobPosting:
        """Fallback classification using keyword rules + embedding similarity.

        Used when no trained model is available.
        """
        # Keyword-based score
        kw_label, kw_score = _weak_label(posting)

        # Embedding similarity score
        text = f"{posting.title}. {posting.description[:500]}"
        emb_features = self._embedding_similarity_features(text)
        emb_max_sim = float(emb_features[0]) if len(emb_features) > 0 else 0.0

        # Combine keyword and embedding signals
        if kw_score >= 0.8:
            combined = kw_score
            label = kw_label
        elif emb_max_sim > 0:
            combined = 0.35 * kw_score + 0.65 * emb_max_sim
            label = kw_label if kw_score > 0.3 else LABEL_FDE
        else:
            combined = kw_score
            label = kw_label

        posting.fde_score = round(combined, 4)
        posting.fde_label = label if combined >= self.threshold else LABEL_NOT_FDE

        # Store embedding
        emb = self.embed_text(text)
        if emb is not None:
            posting.embedding = emb.tolist()

        return posting

    def classify_batch(self, postings: list[JobPosting]) -> list[JobPosting]:
        """Classify a batch of postings.

        If not yet trained, auto-trains on the batch using weak labels first.
        """
        if not self._is_trained and len(postings) >= 5:
            logger.info("Auto-training classifier on %d postings with weak labels", len(postings))
            self.train(postings)

        return [self.classify(p) for p in postings]

    # ── Active learning ──────────────────────────────────────────────

    def get_uncertain_samples(
        self,
        postings: list[JobPosting],
        n: int = 20,
    ) -> list[tuple[JobPosting, float]]:
        """Identify the most uncertain postings for human review.

        Returns postings sorted by uncertainty (closest to decision boundary).
        This is the core of the active learning loop.
        """
        if not self._is_trained or self._classifier is None:
            # Fall back: return postings with mid-range keyword scores
            scored = []
            for p in postings:
                _, score = _weak_label(p)
                uncertainty = 1.0 - abs(score - 0.5) * 2  # max at 0.5
                scored.append((p, uncertainty))
            scored.sort(key=lambda x: -x[1])
            return scored[:n]

        uncertainties: list[tuple[JobPosting, float]] = []
        for p in postings:
            X = self._build_feature_vector(p).reshape(1, -1)
            if self._scaler is not None:
                X = self._scaler.transform(X)
            proba = self._classifier.predict_proba(X)[0]
            # Uncertainty = how close max probability is to 0.5
            uncertainty = 1.0 - abs(max(proba) - 0.5) * 2
            uncertainties.append((p, uncertainty))

        uncertainties.sort(key=lambda x: -x[1])
        return uncertainties[:n]

    def retrain_with_labels(
        self,
        postings: list[JobPosting],
        labels: list[str],
    ) -> dict:
        """Retrain the model with human-provided labels.

        This is called after human review of uncertain samples.
        """
        logger.info("Retraining with %d human-labeled samples", len(postings))
        return self.train(postings, labels)

    # ── Persistence ──────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Save the full classifier state to disk."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "tfidf": self._tfidf,
            "classifier": self._classifier,
            "scaler": self._scaler,
            "is_trained": self._is_trained,
            "model_name": self.model_name,
            "threshold": self.threshold,
        }
        with open(p, "wb") as f:
            pickle.dump(state, f)
        logger.info("Saved classifier to %s", p)

    def load(self, path: str | Path) -> None:
        """Load a previously saved classifier."""
        p = Path(path)
        if not p.exists():
            logger.warning("Classifier file not found: %s", p)
            return

        with open(p, "rb") as f:
            state = pickle.load(f)  # noqa: S301

        self._tfidf = state.get("tfidf")
        self._classifier = state.get("classifier")
        self._scaler = state.get("scaler")
        self._is_trained = state.get("is_trained", False)
        self.model_name = state.get("model_name", self.model_name)
        self.threshold = state.get("threshold", self.threshold)
        logger.info("Loaded classifier from %s (trained=%s)", p, self._is_trained)
