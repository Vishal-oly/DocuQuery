from docuquery.embeddings import HashingEmbedder


def test_hashing_vectors_are_normalized_and_repeatable():
    embedder = HashingEmbedder()
    vector_a = embedder.embed(["A scientific paper about neural retrieval."])[0]
    vector_b = embedder.embed(["A scientific paper about neural retrieval."])[0]
    assert len(vector_a) == 384
    assert vector_a == vector_b
    assert abs(sum(value * value for value in vector_a) - 1.0) < 1e-8


def test_hashing_vectors_change_for_different_text():
    embedder = HashingEmbedder()
    vector_a = embedder.embed(["quantum physics and particles"])[0]
    vector_b = embedder.embed(["botanical gardening and flowers"])[0]
    assert vector_a != vector_b
