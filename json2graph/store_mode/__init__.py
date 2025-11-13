"""存储模式模块

包含不同的图存储实现，支持各种时空知识图谱构建模式。
"""

from .skg_store import SKGStore
from .stkg_store import STKGStore

__all__ = [
    'SKGStore',
    'STKGStore',
]