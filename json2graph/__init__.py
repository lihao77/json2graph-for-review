"""json2graph - JSON到图数据库的动态转换框架

一个支持动态处理器插拔的Python包，用于将JSON数据转换为图数据库存储。
支持基础实体、状态实体和状态关系的存储，以及多种图存储模式。
"""

__version__ = "0.1.0"
__author__ = "json2graph Team"
__description__ = "JSON到图数据库的动态转换框架"

# 核心接口
from .interfaces import IProcessor, IGraphStore, EntityType

# 数据库连接
from .db import Neo4jConnection

# 存储模式
from .store_mode import SKGStore, STKGStore

# 处理器
from .processor import SpatialProcessor, SpatialRelationshipProcessor

# 异常类
from .exception import (
    Json2GraphError,
    DatabaseConnectionError,
    ProcessorError,
    ProcessorNotFoundError,
    DataValidationError,
    EntityNotFoundError,
    StateChainError,
    GeoCodingError,
    SpatialIndexError
)

__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    "__description__",
    
    # 核心接口
    "IProcessor",
    "IGraphStore",
    "ProcessStage",
    "EntityType",
    
    # 数据库连接
    "Neo4jConnection",
    
    # 存储模式
    "SKGStore",
    "STKGStore",
    
    # 处理器
    "SpatialProcessor",
    "SpatialRelationshipProcessor",
    
    # 异常类
    "Json2GraphError",
    "DatabaseConnectionError",
    "ProcessorError",
    "ProcessorNotFoundError",
    "DataValidationError",
    "EntityNotFoundError",
    "StateChainError",
    "GeoCodingError",
    "SpatialIndexError"
]