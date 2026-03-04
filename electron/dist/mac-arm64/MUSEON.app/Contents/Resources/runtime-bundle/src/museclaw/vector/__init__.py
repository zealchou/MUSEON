"""VectorBridge — 語義搜尋統一門面.

提供 Qdrant 後端 + fastembed 嵌入的統一搜尋介面，
graceful degradation 到 TF-IDF（ChromosomeIndex）。
"""
