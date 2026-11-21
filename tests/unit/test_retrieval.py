from packages.shared.schemas import Role
from services.retrieval import HybridRetriever
from services.retrieval.hybrid import chunk_document


def test_chunking_has_overlap():
    chunks = chunk_document(" ".join(str(i) for i in range(20)), max_tokens=10, overlap=2)
    assert len(chunks) == 3
    assert chunks[0].split()[-2:] == chunks[1].split()[:2]


def test_hybrid_retrieval_returns_approved_role_filtered_evidence(database):
    result = HybridRetriever(database).search("forgot password reset", Role.EMPLOYEE, intent="password_reset")
    assert result.citations
    assert result.citations[0].document_id == "kb_password"
    assert 0.3 < result.confidence <= 1


def test_unanswerable_query_has_no_evidence(database):
    result = HybridRetriever(database).search("quantum toaster purple smoke", Role.EMPLOYEE, intent="unknown")
    assert result.citations == []
    assert result.confidence == 0

