from __future__ import annotations

import pytest

from app.models.semantic_embedding import SemanticEmbedding
from app.services.embedding_service import content_hash, validate_embedding_dimension


def test_embedding_content_hash_is_stable():
    assert content_hash("客户HHI") == content_hash("客户HHI")
    assert content_hash("客户HHI") != content_hash("现金流质量")


def test_embedding_dimension_validation():
    assert validate_embedding_dimension([0.1] * 512, 512) == 512
    with pytest.raises(ValueError):
        validate_embedding_dimension([0.1] * 10, 512)


def test_semantic_embedding_model_has_unique_tool_model_constraint():
    names = {constraint.name for constraint in SemanticEmbedding.__table__.constraints}
    assert "uq_semantic_embedding_tool_model" in names
