"""json2graph包的核心接口定义

本模块定义了json2graph包中最关键的接口：
- IProcessor: 数据处理器接口，用于在数据插入图数据库的前中后期进行数据处理
- IGraphStore: 图存储接口，负责将JSON数据转换并存储到图数据库
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from enum import Enum


# ProcessStage枚举已移除，所有处理器操作都在节点插入后执行


class EntityType(Enum):
    """实体类型枚举"""
    BASE_ENTITY = "base_entity"      # 基础实体
    STATE_ENTITY = "state_entity"    # 状态实体
    STATE_RELATION = "state_relation"  # 状态关系


class GraphOperationType(Enum):
    """图操作类型枚举"""
    ADD_PROPERTY = "add_property"        # 添加节点属性
    ADD_LABEL = "add_label"              # 添加节点标签
    CREATE_NODE = "create_node"          # 创建新节点
    CREATE_RELATIONSHIP = "create_relationship"  # 创建关系
    EXECUTE_CYPHER = "execute_cypher"    # 执行自定义Cypher查询


class GraphOperation:
    """图操作指令"""
    
    def __init__(self, operation_type: GraphOperationType, **kwargs):
        self.operation_type = operation_type
        self.params = kwargs
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_type": self.operation_type.value,
            "params": self.params
        }


class ProcessorResult:
    """处理器结果"""
    
    def __init__(self, 
                 graph_operations: Optional[List[GraphOperation]] = None,
                 processor_context: Optional[Dict[str, Any]] = None):
        """
        Args:
            graph_operations: 图操作指令列表（用于新的结构化方式）
            processor_context: 处理器间共享的上下文数据
        """
        self.graph_operations = graph_operations or []
        self.processor_context = processor_context or {}
    
    def add_property(self, key: str, value: Any) -> 'ProcessorResult':
        """添加单个属性到节点"""
        self.graph_operations.append(
            GraphOperation(GraphOperationType.ADD_PROPERTY, key=key, value=value)
        )
        return self
    
    def add_properties(self, properties: Dict[str, Any]) -> 'ProcessorResult':
        """批量添加多个属性到节点"""
        self.graph_operations.append(
            GraphOperation(GraphOperationType.ADD_PROPERTY, properties=properties)
        )
        return self
    
    def add_label(self, label: str) -> 'ProcessorResult':
        """添加单个标签到节点"""
        self.graph_operations.append(
            GraphOperation(GraphOperationType.ADD_LABEL, label=label)
        )
        return self
    
    def add_labels(self, labels: List[str]) -> 'ProcessorResult':
        """批量添加多个标签到节点"""
        self.graph_operations.append(
            GraphOperation(GraphOperationType.ADD_LABEL, labels=labels)
        )
        return self
    
    def create_node(self, node_type: str, properties: Dict[str, Any], 
                   relationship_type: str = None, relationship_direction: str = "outgoing") -> 'ProcessorResult':
        """创建新节点并与当前节点建立关系
        
        Args:
            node_type: 新节点的类型/标签
            properties: 新节点的属性
            relationship_type: 关系类型（如果为None则不创建关系）
            relationship_direction: 关系方向 ("outgoing" 或 "incoming")
        """
        self.graph_operations.append(
            GraphOperation(
                GraphOperationType.CREATE_NODE,
                node_type=node_type,
                properties=properties,
                relationship_type=relationship_type,
                relationship_direction=relationship_direction
            )
        )
        return self
    
    def create_relationship(self, target_node_query: str, relationship_type: str, 
                          relationship_properties: Dict[str, Any] = None,
                          direction: str = "outgoing") -> 'ProcessorResult':
        """创建关系到已存在的节点
        
        Args:
            target_node_query: 目标节点的查询条件（Cypher WHERE子句）
            relationship_type: 关系类型
            relationship_properties: 关系属性
            direction: 关系方向 ("outgoing" 或 "incoming")
        """
        self.graph_operations.append(
            GraphOperation(
                GraphOperationType.CREATE_RELATIONSHIP,
                target_node_query=target_node_query,
                relationship_type=relationship_type,
                relationship_properties=relationship_properties or {},
                direction=direction
            )
        )
        return self
    
    def execute_cypher(self, query: str, params: Dict[str, Any] = None) -> 'ProcessorResult':
        """执行自定义Cypher查询
        
        Args:
            query: Cypher查询语句（使用$current_node_id引用当前节点）
            params: 查询参数
        """
        self.graph_operations.append(
            GraphOperation(
                GraphOperationType.EXECUTE_CYPHER,
                query=query,
                params=params or {}
            )
        )
        return self


class IProcessor(ABC):
    """数据处理器接口
    
    处理器可以在数据插入图数据库的不同阶段对数据进行补充和扩展。
    例如：地理编码处理器可以为基础实体添加空间数据，
    多模态处理器可以为状态属性添加多模态数据。
    """
    
    @abstractmethod
    def get_name(self) -> str:
        """获取处理器名称"""
        pass
    
    # get_supported_stages方法已移除，所有处理器都在节点插入后执行
    
    @abstractmethod
    def get_supported_entity_types(self) -> List[EntityType]:
        """获取支持的实体类型"""
        pass
    
    @abstractmethod
    def process(self, 
                entity_type: EntityType, 
                data: Dict[str, Any], 
                context: Optional[Dict[str, Any]] = None) -> ProcessorResult:
        """处理数据（在节点插入后执行）
        
        Args:
            entity_type: 实体类型
            data: 要处理的数据
            context: 处理器间共享的上下文数据，用于处理器间协作
            
        Returns:
            ProcessorResult对象，包含图操作指令和处理器间共享上下文
            
        Note:
            使用ProcessorResult返回结构化的图操作指令和处理器间共享上下文。
            通过context参数实现处理器间的数据传递和协作。
        """
        pass
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """验证处理器配置
        
        Args:
            config: 配置字典
            
        Returns:
            配置是否有效
        """
        pass
    
    def get_required_indexes(self) -> List[str]:
        """获取处理器需要的所有索引
        
        Returns:
            索引查询语句列表
        """
        return []
    
    def get_spatial_entity_types(self) -> Optional[set]:
        """获取需要空间索引的实体类型
        
        Returns:
            需要空间索引的实体类型集合，如果不需要则返回None
        """
        return None


class IGraphStore(ABC):
    """图存储接口
    
    负责将JSON数据转换并存储到图数据库中。
    支持动态插拔处理器，可以在数据插入的不同阶段进行数据处理和扩展。
    """
    
    @abstractmethod
    def add_processor(self, processor: IProcessor) -> None:
        """添加数据处理器
        
        Args:
            processor: 要添加的处理器
        """
        pass
    
    @abstractmethod
    def remove_processor(self, processor_name: str) -> bool:
        """移除数据处理器
        
        Args:
            processor_name: 处理器名称
            
        Returns:
            是否成功移除
        """
        pass
    
    @abstractmethod
    def get_processors(self) -> List[IProcessor]:
        """获取所有处理器"""
        pass
    
    @abstractmethod
    def store_base_entities(self, entities: List[Dict[str, Any]]) -> None:
        """存储基础实体
        
        Args:
            entities: 基础实体列表
        """
        pass
    
    @abstractmethod
    def store_state_entities(self, states: List[Dict[str, Any]]) -> None:
        """存储状态实体
        
        Args:
            states: 状态实体列表
        """
        pass
    
    @abstractmethod
    def store_state_relations(self, relations: List[Dict[str, Any]]) -> None:
        """存储状态关系
        
        Args:
            relations: 状态关系列表
        """
        pass
    
    @abstractmethod
    def store_knowledge_graph(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """存储完整的知识图谱数据
        
        Args:
            data: 包含基础实体、状态实体、状态关系的完整数据
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """关闭存储连接"""
        pass