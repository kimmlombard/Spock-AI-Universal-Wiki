"""Null llama-server embeddings must fail with a clear error, not a TypeError."""

from spock_rag_adapter.embedding_utils import (
    embedding_from_response,
    flatten_embedding,
)
from spock_shell.llama_gui_command import command_warnings, parse_llama_gui_command


def test_nested_null_vector_raises_a_clear_error():
    raw = [[None] * 8]
    try:
        flatten_embedding(raw)
    except ValueError as exc:
        assert "null" in str(exc).lower()
    else:
        raise AssertionError("null vector was accepted")


def test_flat_null_vector_raises():
    payload = [{"index": 0, "embedding": [None, None, None]}]
    try:
        embedding_from_response(payload)
    except ValueError as exc:
        assert "null" in str(exc).lower()
    else:
        raise AssertionError("null vector was accepted")


def test_token_rows_average():
    assert flatten_embedding([[1.0, 3.0], [3.0, 5.0]]) == [2.0, 4.0]


def test_mixed_batch_keeps_real_vectors_and_marks_nulls():
    from spock_rag_adapter.embedding_utils import embeddings_from_response

    payload = [
        {"index": 1, "embedding": [None, None]},
        {"index": 0, "embedding": [[1.0, 3.0], [3.0, 5.0]]},
    ]
    vectors, saw_null = embeddings_from_response(payload, 2)
    assert saw_null
    assert vectors[0] == [2.0, 4.0]
    assert vectors[1] is None


def test_embed_command_warns_about_chat_sized_context():
    argv = parse_llama_gui_command(
        "llama-server.exe -c 64000 -fa auto -ngl auto -fit on --port 8080 "
        "--embedding -m C:\\models\\embed.gguf"
    )
    notes = " ".join(command_warnings(argv, "embedding", 8080))
    assert "64000" in notes
    assert "--pooling last" in notes
    assert "-ngl 99" in notes
    assert "Flash attention" not in notes
