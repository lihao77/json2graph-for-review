"""json2graph包的异常类定义

定义了json2graph包中使用的各种异常类。
"""


class Json2GraphError(Exception):
    """json2graph包的基础异常类"""
    pass


class DatabaseConnectionError(Json2GraphError):
    """数据库连接异常"""
    pass


class ProcessorError(Json2GraphError):
    """处理器异常"""
    pass


class ProcessorNotFoundError(ProcessorError):
    """处理器未找到异常"""
    pass


class ProcessorConfigError(ProcessorError):
    """处理器配置异常"""
    pass


class DataValidationError(Json2GraphError):
    """数据验证异常"""
    pass


class EntityNotFoundError(Json2GraphError):
    """实体未找到异常"""
    pass


class StateChainError(Json2GraphError):
    """状态链异常"""
    pass


class GeoCodingError(ProcessorError):
    """地理编码异常"""
    pass


class SpatialIndexError(Json2GraphError):
    """空间索引异常"""
    pass