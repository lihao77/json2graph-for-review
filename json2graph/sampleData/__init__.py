"""
示例数据模块

提供各种时空知识图谱的示例数据，用于测试和演示空间框架功能。
"""

from .flood_data import get_flood_disaster_data

__all__ = [
    'get_flood_disaster_data'
]