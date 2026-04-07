"""
Meridian — Retriever helpers.
Wraps each VectorStoreIndex as a QueryEngine with similarity_top_k=5.
Used by orchestrator.py to build the QueryEngineTools for the agent.
"""

# TODO: Implement the following using LlamaIndex:
#
#   get_query_engine(index: VectorStoreIndex, top_k: int = 5) -> RetrieverQueryEngine
#     - Returns a query engine with similarity_top_k=top_k
#     - Used by orchestrator.py to create each QueryEngineTool

from __future__ import annotations


def get_query_engine(index, top_k: int = 5):
    # TODO: implement
    raise NotImplementedError
