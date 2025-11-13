"""基础SKG（Spatio-temporal Knowledge Graph）存储实现

基于原始的chain_based_neo4j_entity_store.py实现，提供基础的时空知识图谱存储功能。
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from itertools import chain
import logging

import neo4j.time

from ..interfaces import IGraphStore, IProcessor, EntityType, ProcessorResult, GraphOperation, GraphOperationType
from ..db import Neo4jConnection
from ..exception import (
    DatabaseConnectionError, 
    ProcessorNotFoundError, 
    DataValidationError,
    StateChainError
)


class SKGStore(IGraphStore):
    """基础SKG存储实现
    
    提供基础的时空知识图谱存储功能，支持：
    - 基础实体存储
    - 状态实体存储（链式结构）
    - 状态关系存储
    - 动态处理器插拔
    """
    
    # 定义确定的基础索引
    BASIC_INDEXES = [
        "CREATE INDEX entity_id_index IF NOT EXISTS FOR (n:entity) ON (n.id)",
        "CREATE INDEX entity_name_index IF NOT EXISTS FOR (n:entity) ON (n.name)",
        "CREATE INDEX state_id_index IF NOT EXISTS FOR (n:State) ON (n.id)",
        "CREATE INDEX state_name_index IF NOT EXISTS FOR (n:State) ON (n.name)",
        "CREATE INDEX attribute_id_index IF NOT EXISTS FOR (n:Attribute) ON (n.id)",
        "CREATE INDEX attribute_name_index IF NOT EXISTS FOR (n:Attribute) ON (n.name)",
        "CREATE INDEX state_start_index IF NOT EXISTS FOR (n:State) ON (n.start_time)",
        "CREATE INDEX state_end_index IF NOT EXISTS FOR (n:State) ON (n.end_time)",
    ]
    
    def __init__(self, db_connection: Neo4jConnection):
        """初始化SKG存储
        
        Args:
            db_connection: Neo4j数据库连接
        """
        self.db = db_connection
        self.processors: Dict[str, IProcessor] = {}
        self.logger = logging.getLogger(__name__)
        
        # 确保数据库连接
        if not self.db.driver:
            self.db.connect()
        
        # 用于跟踪已创建的索引
        self._created_indexes = set()
        
        # 一次性创建所有基础索引
        self._create_basic_indexes()
    
    def add_processor(self, processor: IProcessor) -> None:
        """添加数据处理器"""
        processor_name = processor.get_name()
        self.processors[processor_name] = processor
        
        # 为处理器创建所需的索引
        self._create_processor_indexes(processor)
        
        self.logger.info(f"已添加处理器: {processor_name}")
    
    def _create_processor_indexes(self, processor: IProcessor) -> None:
        """为处理器创建所需的索引
        
        Args:
            processor: 处理器实例
        """
        # 获取处理器需要的所有索引
        required_indexes = processor.get_required_indexes()
        if required_indexes:
            # 分离常规索引和空间索引
            regular_indexes = []
            spatial_indexes = []
            
            for index_query in required_indexes:
                if index_query.startswith("SPATIAL_LAYER:"):
                    # 这是空间图层索引
                    layer_name = index_query.replace("SPATIAL_LAYER:", "")
                    spatial_indexes.append(layer_name)
                else:
                    # 这是常规索引
                    regular_indexes.append(index_query)
            
            # 创建常规索引
            if regular_indexes:
                results = self.db.create_indexes(regular_indexes)
                for index_query, success in results.items():
                    if success:
                        self._created_indexes.add(index_query)
                        self.logger.info(f"为处理器 {processor.get_name()} 创建索引: {index_query}")
            
            # 创建空间图层
            if spatial_indexes:
                self._create_spatial_indexes_for_processor(processor, spatial_indexes)
    
    def remove_processor(self, processor_name: str) -> bool:
        """移除数据处理器"""
        if processor_name in self.processors:
            del self.processors[processor_name]
            self.logger.info(f"已移除处理器: {processor_name}")
            return True
        return False
    
    def get_processors(self) -> List[IProcessor]:
        """获取所有处理器"""
        return list(self.processors.values())
    
    def _apply_processors(self, 
                         entity_type: EntityType, 
                         data: Dict[str, Any],
                         context: Optional[Dict[str, Any]] = None) -> List[GraphOperation]:
        """应用处理器（在节点插入后执行）
        
        支持处理器间的数据传递，通过context参数实现处理器间协作。
        只使用ProcessorResult返回图操作指令和共享上下文。
        
        Returns:
            List[GraphOperation]: 图操作指令列表
        """
        all_graph_operations = []
        
        # 初始化处理器间共享的上下文
        processor_context = {}
        if context:
            processor_context.update(context)
        
        for processor in self.processors.values():
            if entity_type in processor.get_supported_entity_types():
                try:
                    # 传递处理器间共享的上下文
                    result = processor.process(entity_type, data, processor_context)
                    
                    # 收集图操作指令
                    if result.graph_operations:
                        all_graph_operations.extend(result.graph_operations)
                    
                    # 更新处理器间共享的上下文
                    if result.processor_context:
                        processor_context.update(result.processor_context)
                    self.logger.debug(f"处理器 {processor.get_name()} 处理完成")
                except Exception as e:
                    self.logger.error(f"处理器 {processor.get_name()} 处理失败: {e}")
                    raise
        
        return all_graph_operations

    def store_base_entities(self, entities: List[Dict[str, Any]]) -> None:
        """存储基础实体"""
        if not entities:
            return
        
        for entity_data in entities:
            # 先创建基础实体
            entity_node = self.db.execute_write_transaction(
                self._create_base_entity, 
                entity_data
            )
            
            # 应用处理器并执行图操作
            operations = self._apply_processors(
                EntityType.BASE_ENTITY, 
                entity_data,
                {"entity_node": entity_node, "entity_type": "base_entity"}
            )
            
            # 执行图操作
            if operations:
                self.db.execute_write_transaction(
                    self._execute_graph_operations_with_node,
                    entity_node,
                    operations
                )
            
            self.logger.info(
                f"已创建基础实体: {entity_data['类型']} - {entity_data['名称']} (ID: {entity_data['唯一ID']})"
            )
    
    def store_state_entities(self, states: List[Dict[str, Any]]) -> None:
        """存储状态实体"""
        if not states:
            return
        
        # 按时间排序状态实体
        sorted_states = sorted(
            states,
            key=lambda x: self._parse_time_range(x.get("时间", ""))[0] or datetime.max,
        )
        
        for state_data in sorted_states:
            # 先创建状态实体
            state_node = self.db.execute_write_transaction(
                self._create_state_entity, 
                state_data
            )
            
            # 应用处理器并执行图操作
            operations = self._apply_processors(
                EntityType.STATE_ENTITY, 
                state_data,
                {"state_node": state_node, "entity_type": "state_entity"}
            )
            
            # 执行图操作
            if operations:
                self.db.execute_write_transaction(
                    self._execute_graph_operations_with_node,
                    state_node,
                    operations
                )
            
            self.logger.info(
                f"已创建状态实体: {state_data['状态ID']} (关联实体: {state_data['关联实体ID列表']})"
            )
    
    def store_state_relations(self, relations: List[Dict[str, Any]]) -> None:
        """存储状态关系"""
        if not relations:
            return
        
        for relation_data in relations:
            # 先创建状态关系
            relation_result = self.db.execute_write_transaction(
                self._create_state_relation, 
                relation_data
            )
            
            # 应用处理器并执行图操作
            operations = self._apply_processors(
                EntityType.STATE_RELATION, 
                relation_data,
                {"relation_result": relation_result, "entity_type": "state_relation"}
            )
            
            # 执行图操作（对于关系，我们可能需要特殊处理）
            if operations:
                # 对于关系，我们可以使用源节点或目标节点来执行操作
                # 这里选择使用源节点
                source_node_query = f"MATCH (n) WHERE n.id = '{relation_data['主体状态ID']}' RETURN n"
                source_node = self.db.execute_read_transaction(
                    lambda tx: tx.run(source_node_query).single()
                )
                if source_node:
                    self.db.execute_write_transaction(
                        self._execute_graph_operations_with_node,
                        source_node[0],
                        operations
                    )
            
            self.logger.info(
                f"已创建状态关系: {relation_data['主体状态ID']} -{relation_data['关系']}-> {relation_data['客体状态ID']}"
            )
    
    def store_knowledge_graph(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """存储完整的知识图谱数据"""

        self.logger.info("开始存储数据...")
        
        # 1. 存储基础实体
        if "基础实体" in data:
            self.store_base_entities(data["基础实体"])
        
        # 2. 存储状态实体
        if "状态实体" in data:
            self.store_state_entities(data["状态实体"])
        
        # 3. 存储状态关系
        if "状态关系" in data:
            self.store_state_relations(data["状态关系"])
        
        self.logger.info("数据存储完成")
    
    def close(self) -> None:
        """关闭存储连接"""
        self.db.close()
    
    def _create_basic_indexes(self) -> None:
        """创建确定的基础索引"""
        self.logger.info("创建基础索引...")
        
        results = self.db.create_indexes(self.BASIC_INDEXES)
        for index_query, success in results.items():
            if success:
                self._created_indexes.add(index_query)
                self.logger.debug(f"基础索引创建成功: {index_query}")
            else:
                self.logger.warning(f"基础索引创建失败: {index_query}")
        
        self.logger.info(f"基础索引创建完成，共创建 {len([s for s in results.values() if s])} 个索引")
    
    def _create_spatial_indexes_for_processor(self, processor, spatial_entity_types: List[str]) -> None:
        """为处理器创建空间索引
        
        Args:
            processor: 处理器实例

            spatial_entity_types: 需要空间索引的实体类型列表
        """
        self.logger.info(f"为处理器 {processor.get_name()} 创建空间索引，实体类型: {spatial_entity_types}")
        
        # 检查是否支持Neo4j-Spatial插件
        if not self.db.check_spatial_support():
            self.logger.error(f"数据库不支持Neo4j-Spatial插件，无法为处理器 {processor.get_name()} 创建空间索引")
            raise RuntimeError("数据库不支持Neo4j-Spatial插件，无法创建空间索引")
        
        with self.db.driver.session() as session:
            for entity_type in spatial_entity_types:
                try:
                    # 使用Neo4j-Spatial创建空间图层
                    self._create_spatial_layer_for_entity_type(session, entity_type)
                        
                except Exception as e:
                    self.logger.error(f"为实体类型 {entity_type} 创建空间索引失败: {e}")
    
    def _create_spatial_layer_for_entity_type(self, session, entity_type: str) -> None:
        """为特定实体类型创建Neo4j-Spatial图层"""
        layer_name = f"spatial_layer_{entity_type}"
        
        if layer_name not in self._created_indexes:
            def create_layer(tx):
                # 创建空间图层 - 使用正确的参数顺序和YIELD
                create_layer_query = """
                CALL spatial.addLayer($layer_name, 'wkt', 'geometry') YIELD node
                RETURN $layer_name AS layer_name
                """
                
                result = tx.run(create_layer_query, layer_name=layer_name)
                return result.single()
            
            try:
                result = session.execute_write(create_layer)
                if result:
                    self.logger.info(f"成功为实体类型 {entity_type} 创建空间图层: {layer_name}")
                    self._created_indexes.add(layer_name)
                    
            except Exception as e:
                # 如果图层已存在，则忽略错误
                if "already exists" in str(e).lower():
                    self.logger.info(f"空间图层 {layer_name} 已存在")
                    self._created_indexes.add(layer_name)
                else:
                    self.logger.error(f"创建空间图层 {layer_name} 失败: {e}")
                    # 不抛出异常，继续处理
    
    def _parse_time_range(self, time_str: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """解析时间范围，返回开始和结束时间"""
        if not time_str:
            return None, None
        
        # 处理如"2016-06-30至2016-07-06"格式的时间字符串
        match = re.match(r"(\d{4}-\d{2}-\d{2})至(\d{4}-\d{2}-\d{2})", time_str)
        if match:
            start_date = datetime.strptime(match.group(1), "%Y-%m-%d")
            end_date = datetime.strptime(match.group(2), "%Y-%m-%d")
            return start_date, end_date
        return None, None
    
    def _create_base_entity(self, tx, entity_data: Dict[str, Any]):
        """创建基础实体节点"""
        entity_type = entity_data["类型"]
        entity_name = entity_data["名称"]
        entity_id = entity_data["唯一ID"]
        source = entity_data.get("文档来源", "")
        geo_description = entity_data.get("地理描述", "")
        
        # 基本查询 - 同时添加具体类型标签和通用entity标签
        query = f"MERGE (e:{entity_type}:entity {{id: $entity_id}}) "
        query += f"SET e.name = COALESCE(e.name, $entity_name), "
        query += f"e.source = COALESCE(e.source, $source) "
        query += f"SET e.geo_description = COALESCE(e.geo_description, $geo_description) "
        query += f"RETURN e"
        
        params = {"entity_id": entity_id, "entity_name": entity_name, "source": source, "geo_description": geo_description}
        
        entity_node = tx.run(query, **params).single()[0]
        
        return entity_node
    
    def _execute_graph_operations_with_node(self, tx, node, operations: List[GraphOperation]) -> None:
        """在指定节点上执行图操作指令
        
        Args:
            tx: Neo4j事务
            node: 目标节点
            operations: 图操作指令列表
        """
        node_id = node.get('id') or node.id
        
        for operation in operations:
            try:
                if operation.operation_type == GraphOperationType.ADD_PROPERTY:
                    # 批量添加属性
                    properties = operation.params.get('properties', {})
                    if properties:
                        set_clauses = []
                        params = {'node_id': node_id}
                        for key, value in properties.items():
                            set_clauses.append(f"n.{key} = ${key}")
                            params[key] = value
                        
                        query = f"MATCH (n) WHERE n.id = $node_id SET {', '.join(set_clauses)}"
                        tx.run(query, **params)
                        self.logger.debug(f"为节点 {node_id} 批量添加属性: {list(properties.keys())}")
                
                elif operation.operation_type == GraphOperationType.ADD_LABEL:
                    # 批量添加标签
                    labels = operation.params.get('labels', [])
                    if labels:
                        label_str = ':'.join(labels)
                        query = f"MATCH (n) WHERE n.id = $node_id SET n:{label_str}"
                        tx.run(query, node_id=node_id)
                        self.logger.debug(f"为节点 {node_id} 批量添加标签: {labels}")
                
                elif operation.operation_type == GraphOperationType.CREATE_NODE:
                    # 创建新节点并建立关系
                    node_type = operation.params.get('node_type')
                    properties = operation.params.get('properties', {})
                    relationship_type = operation.params.get('relationship_type')
                    relationship_direction = operation.params.get('relationship_direction', 'outgoing')
                    
                    if node_type and properties:
                        # 生成新节点ID
                        new_node_id = f"{node_id}_{node_type}_{len(properties)}"
                        
                        # 创建新节点
                        props_str = ', '.join([f"n.{k} = ${k}" for k in properties.keys()])
                        create_query = f"CREATE (n:{node_type} {{id: $new_node_id}}) SET {props_str} RETURN n"
                        params = {'new_node_id': new_node_id, **properties}
                        new_node = tx.run(create_query, **params).single()[0]
                        
                        # 创建关系（如果指定）
                        if relationship_type:
                            if relationship_direction == 'outgoing':
                                rel_query = f"MATCH (a) WHERE a.id = $node_id MATCH (b) WHERE b.id = $new_node_id CREATE (a)-[:{relationship_type}]->(b)"
                            else:
                                rel_query = f"MATCH (a) WHERE a.id = $node_id MATCH (b) WHERE b.id = $new_node_id CREATE (b)-[:{relationship_type}]->(a)"
                            tx.run(rel_query, node_id=node_id, new_node_id=new_node_id)
                        
                        self.logger.debug(f"为节点 {node_id} 创建关联节点: {new_node_id} ({node_type})")
                
                elif operation.operation_type == GraphOperationType.CREATE_RELATIONSHIP:
                    # 创建关系到已存在的节点
                    target_node_query = operation.params.get('target_node_query')
                    relationship_type = operation.params.get('relationship_type')
                    relationship_properties = operation.params.get('relationship_properties', {})
                    direction = operation.params.get('direction', 'outgoing')
                    
                    if target_node_query and relationship_type:
                        if direction == 'outgoing':
                            rel_query = f"MATCH (a) WHERE a.id = $node_id MATCH (b) WHERE {target_node_query} CREATE (a)-[r:{relationship_type}]->(b)"
                        else:
                            rel_query = f"MATCH (a) WHERE a.id = $node_id MATCH (b) WHERE {target_node_query} CREATE (b)-[r:{relationship_type}]->(a)"
                        
                        # 添加关系属性
                        if relationship_properties:
                            props_str = ', '.join([f"r.{k} = ${k}" for k in relationship_properties.keys()])
                            rel_query += f" SET {props_str}"
                        
                        params = {'node_id': node_id, **relationship_properties}
                        tx.run(rel_query, **params)
                        self.logger.debug(f"为节点 {node_id} 创建关系: {relationship_type}")
                
                elif operation.operation_type == GraphOperationType.EXECUTE_CYPHER:
                    # 执行自定义Cypher查询
                    query = operation.params.get('query')
                    params = operation.params.get('params', {})
                    
                    if query:
                        # 将current_node_id作为参数传递，而不是直接替换
                        params['current_node_id'] = node_id
                        tx.run(query, **params)
                        self.logger.debug(f"为节点 {node_id} 执行自定义查询")
                
            except Exception as e:
                self.logger.error(f"执行图操作失败 {operation.operation_type}: {e}")
                # 继续执行其他操作，不中断整个流程
      
    def _create_state_entity(self, tx, state_data: Dict[str, Any]):
        """创建状态实体节点及其关系，处理时间序列关系，使用链式结构"""
        state_type = state_data["类型"]
        entity_ids = state_data["关联实体ID列表"]
        state_id = state_data["状态ID"]
        time_info = state_data.get("时间", "")
        geo_info = state_data.get("地理描述", "")
        source = state_data.get("文档来源", "")

        start_time, end_time = self._parse_time_range(time_info)

        # 检查状态节点是否存在
        check_existence_query = "MATCH (s:State {id: $state_id}) RETURN s"
        existing_state = tx.run(check_existence_query, state_id=state_id).single()
        
        # 创建状态节点
        state_query_parts = [
            f"MERGE (s:State {{id: $state_id}})",
            f"SET s.type = $state_type,",
            f"s.time = $time_info,",
            f"s.start_time = date($start_time),",
            f"s.end_time = date($end_time),",
            f"s.entity_ids = $entity_ids,",
            f"s.source = $source,"
        ]
        
        # 只在地理描述有值时才设置
        params = {
            "state_id": state_id,
            "state_type": state_type,
            "time_info": time_info,
            "start_time": start_time,
            "end_time": end_time,
            "entity_ids": entity_ids,
            "source": source
        }
        
        if geo_info and geo_info.strip():
            state_query_parts.insert(-1, "s.geo = $geo_info,")
            params["geo_info"] = geo_info

        # # 处理状态描述 - 作为属性添加到状态实体中
        # state_desc = state_data.get("状态描述", {})
        # for attr_key, attr_value in state_desc.items():
        #     state_query_parts.insert(-1, f"s.{attr_key} = {attr_value},")

        # 移除最后一个逗号并添加RETURN
        state_query_parts[-1] = state_query_parts[-1].rstrip(",")
        state_query_parts.append("RETURN s")
        
        state_query = " ".join(state_query_parts)
        
        state_node = tx.run(state_query, **params).single()[0]
        
        # 仅当状态不存在时处理实体关系
        if not existing_state:
            self.logger.debug(f"处理实体关系: State({state_id})")
            
            # 处理与基础实体的关系，使用链式结构
            for entity_id in entity_ids:
                self._handle_entity_state_chain(tx, entity_id, state_id, time_info)
        else:
            self.logger.debug(f"State {state_id} 已存在，跳过实体关系处理")
        
        # 处理状态描述 - 将每个key作为关系，value作为属性节点
        state_desc = state_data.get("状态描述", {})
        for attr_key, attr_value in state_desc.items():
            attr_id = f"{state_id}-{attr_value}"

            # 创建属性值节点
            attr_query = (
                f"MERGE (a:Attribute {{id: $attr_id}}) "
                f"SET a.value = $attr_value "
                f"RETURN a"
            )
            tx.run(attr_query, attr_value=attr_value, attr_id=attr_id)

            # 创建关系
            relation_query = (
                f"MATCH (s:State {{id: $state_id}}) "
                f"MATCH (a:Attribute {{id: $attr_id}}) "
                f"MERGE (s)-[r:hasAttribute]->(a) "
                f"SET r.type = $attr_key "
                f"RETURN r"
            )
            tx.run(relation_query, state_id=state_id, attr_id=attr_id, attr_key=attr_key)
        
        return state_node
    
    def _handle_entity_state_chain(self, tx, entity_id: str, state_id: str, time_info: str):
        """处理实体状态链"""
        # 查询该实体的状态链
        state_chain = self._get_entity_state_chain(tx, entity_id)
        
        if not state_chain:
            # 如果是第一个状态，直接创建hasState关系
            entity_state_query = (
                f"MATCH (e) WHERE e.id = $entity_id "
                f"MATCH (s:State {{id: $state_id}}) "
                f"MERGE (e)-[r:hasState]->(s) "
                f"SET r.entity = $entity_id "
                f"RETURN r"
            )
            tx.run(entity_state_query, entity_id=entity_id, state_id=state_id)
            self.logger.debug(f"创建基础关系: Entity({entity_id}) -[hasState]-> State({state_id})")
        else:
            # 按照时间顺序确定新状态的位置
            self._insert_state_in_chain(tx, entity_id, state_id, time_info, state_chain)
    
    def _get_entity_state_chain(self, tx, entity_id: str) -> List[Dict]:
        """获取实体的完整状态链，按时间顺序排列"""
        # 查询实体是否存在
        entity_query = "MATCH (e) WHERE e.id = $entity_id RETURN e"
        entity_result = tx.run(entity_query, entity_id=entity_id).single()
        
        if not entity_result:
            # 创建新实体
            self.logger.debug(f"实体 {entity_id} 不存在，创建新实体")
            self._create_base_entity(tx, {"唯一ID": entity_id, "类型": "未知", "名称": entity_id})
            return []
        
        # 查询与实体相关的所有状态节点
        query = """
        MATCH (e)-[:hasState]->(first_state:State)
        WHERE e.id = $entity_id
        WITH first_state
        OPTIONAL MATCH path = (first_state)-[:nextState*]->(subsequent_state)
        WHERE ALL(r IN RELATIONSHIPS(path) WHERE $entity_id IN r.entity)
        WITH first_state, path, subsequent_state
        RETURN 
            CASE WHEN path IS NULL THEN first_state.id ELSE first_state.id END AS state_id,
            CASE WHEN path IS NULL THEN first_state.time ELSE first_state.time END AS time,
            0 AS depth
        UNION
        MATCH (e)-[:hasState]->(first_state:State)-[r:nextState*]->(state:State)
        WHERE e.id = $entity_id AND ALL(rel IN r WHERE $entity_id IN rel.entity)
        RETURN state.id AS state_id, state.time AS time, SIZE(r) AS depth
        ORDER BY depth
        """
        
        result = tx.run(query, entity_id=entity_id).data()
        
        # 按时间排序结果
        sorted_result = sorted(
            result,
            key=lambda x: (self._parse_time_range(x.get("time", ""))[0] or datetime.max),
        )
        
        return sorted_result
    
    def _insert_state_in_chain(self, tx, entity_id: str, state_id: str, time_info: str, state_chain: List[Dict]):
        """在状态链中插入新状态"""
        # 解析新状态的时间
        new_start_time, new_end_time = self._parse_time_range(time_info)
        
        if not new_start_time:
            # 如果无法解析时间，添加到链的末尾
            latest_state_id = self._get_entity_latest_state(tx, entity_id)
            if latest_state_id:
                next_state_query = """
                MATCH (s1:State {id: $latest_state_id})
                MATCH (s2:State {id: $state_id})
                MERGE (s1)-[r:nextState]->(s2)
                SET r.entity = 
                  CASE
                    WHEN r.entity IS NULL THEN [ $entity_id ]
                    ELSE r.entity + $entity_id
                  END
                RETURN r
                """
                tx.run(
                    next_state_query,
                    latest_state_id=latest_state_id,
                    state_id=state_id,
                    entity_id=entity_id,
                )
                self.logger.debug(f"时间未知，添加到链尾: State({latest_state_id}) -[nextState]-> State({state_id})")
            return
        
        # 实现复杂的时间序列插入逻辑
        # 查询该实体的第一个状态
        first_state_query = """
        MATCH (e)-[r:hasState]->(s:State)
        WHERE e.id = $entity_id
        RETURN s.id AS state_id, s.time AS time
        """
        first_state_result = tx.run(first_state_query, entity_id=entity_id).single()
        
        if not first_state_result:
            self.logger.debug(f"实体 {entity_id} 没有状态，跳过链式处理")
            return
        
        first_state_id = first_state_result["state_id"]
        current_state_id = first_state_id
        prev_state_id = None
        inserted = False
        
        # 遍历状态链，找到合适的插入位置
        while current_state_id and not inserted:
            # 获取当前状态的时间和下一个状态
            current_state_query = """
            MATCH (s:State {id: $current_id})
            OPTIONAL MATCH (s)-[r:nextState]->(next:State)
            WHERE $entity_id IN r.entity
            OPTIONAL MATCH (s)-[cr:contain]->(child:State)
            WHERE $entity_id IN cr.entity
            RETURN s.time AS current_time, next.id AS next_id, child.id AS child_id
            """
            current_result = tx.run(
                current_state_query,
                current_id=current_state_id,
                entity_id=entity_id,
            ).single()
            
            if not current_result:
                break
            
            current_time = current_result["current_time"]
            next_state_id = current_result["next_id"]
            child_state_id = current_result["child_id"]
            
            # 解析当前状态的时间范围
            current_start_time, current_end_time = self._parse_time_range(current_time or "")
            
            # 情况1: 新状态被当前状态包含 - 新状态成为当前状态的子节点
            if (
                current_start_time
                and current_end_time
                and new_start_time
                and new_end_time
                and current_start_time <= new_start_time
                and current_end_time >= new_end_time
            ):
                # 查找子状态链的末尾
                prev_state_id = current_state_id
                current_state_id = child_state_id
                
                # 如果没有子状态，创建contain关系
                if not current_state_id:
                    contain_query = """
                    MATCH (s1:State {id: $prev_id})
                    MATCH (s2:State {id: $state_id})
                    MERGE (s1)-[r:contain]->(s2)
                    SET r.entity = 
                        CASE
                          WHEN r.entity IS NULL THEN [ $entity_id ]
                          ELSE r.entity + $entity_id
                        END
                    """
                    tx.run(
                        contain_query,
                        prev_id=prev_state_id,
                        state_id=state_id,
                        entity_id=entity_id,
                    )
                    self.logger.debug(
                        f"contain分支尽头，添加到链尾: State({prev_state_id}) -[contain]-> State({state_id})"
                    )
                    inserted = True
                    break
                # 如果有子状态，继续向下查询
                else:
                    continue
            
            # 情况2: 新状态在当前状态之后 - 继续向下查询
            elif (
                current_start_time
                and current_end_time
                and new_start_time
                and current_start_time < new_start_time
            ):
                prev_state_id = current_state_id
                current_state_id = next_state_id
                
                # 如果没有下一个状态，在末尾添加
                if not current_state_id:
                    next_state_query = """
                    MATCH (s1:State {id: $prev_id})
                    MATCH (s2:State {id: $state_id})
                    MERGE (s1)-[r:nextState]->(s2)
                    SET r.entity = 
                        CASE
                          WHEN r.entity IS NULL THEN [ $entity_id ]
                          ELSE r.entity + $entity_id
                        END
                    """
                    tx.run(
                        next_state_query,
                        prev_id=prev_state_id,
                        state_id=state_id,
                        entity_id=entity_id,
                    )
                    self.logger.debug(
                        f"nextState分支尽头，添加到链尾: State({prev_state_id}) -[nextState]-> State({state_id})"
                    )
                    inserted = True
                    break
                # 如果有下一个状态，继续向下查询
                else:
                    continue
            
            # 情况3: 新状态包含当前状态 - 新状态成为当前状态的父节点
            elif (
                current_start_time
                and current_end_time
                and new_start_time
                and new_end_time
                and new_start_time <= current_start_time
                and new_end_time >= current_end_time
            ):
                # 如果当前状态是首节点，需要调整hasState关系
                if current_state_id == first_state_id:
                    # 删除原有hasState关系
                    remove_has_state_query = """
                    MATCH (e)-[r:hasState]->(s:State {id: $current_id})
                    WHERE e.id = $entity_id
                    DELETE r
                    """
                    tx.run(
                        remove_has_state_query,
                        current_id=current_state_id,
                        entity_id=entity_id,
                    )
                    
                    # 创建新的hasState关系到新状态
                    new_has_state_query = """
                    MATCH (e) WHERE e.id = $entity_id
                    MATCH (s:State {id: $state_id})
                    MERGE (e)-[r:hasState]->(s)
                    SET r.entity = $entity_id
                    """
                    tx.run(
                        new_has_state_query,
                        state_id=state_id,
                        entity_id=entity_id,
                    )
                else:
                    # 删除原有contain关系
                    remove_contain_query = """
                    MATCH (s1:State {id: $prev_id})-[r:contain]->(s2:State {id: $current_id})
                    SET r.entity = [x IN r.entity WHERE x <> $entity_id]
                    WITH r
                    WHERE SIZE(r.entity) = 0
                    DELETE r
                    """
                    tx.run(
                        remove_contain_query,
                        prev_id=prev_state_id,
                        current_id=current_state_id,
                        entity_id=entity_id,
                    )
                    
                    # 创建新的contain关系到新状态
                    new_contain_query = """
                    MATCH (s1:State {id: $prev_id})
                    MATCH (s2:State {id: $state_id})
                    MERGE (s1)-[r:contain]->(s2)
                    SET r.entity = [ $entity_id ]
                    """
                    tx.run(
                        new_contain_query,
                        prev_id=prev_state_id,
                        state_id=state_id,
                        entity_id=entity_id,
                    )
                
                # 创建从新状态到当前状态的contain关系
                new_contain_query = """
                MATCH (s1:State {id: $state_id})
                MATCH (s2:State {id: $current_id})
                MERGE (s1)-[r:contain]->(s2)
                SET r.entity = 
                  CASE
                    WHEN r.entity IS NULL THEN [ $entity_id ]
                    ELSE r.entity + $entity_id
                  END
                RETURN r
                """
                tx.run(
                    new_contain_query,
                    state_id=state_id,
                    current_id=current_state_id,
                    entity_id=entity_id,
                )
                
                # 从当前状态沿着nextState关系查找状态，直到找到一个状态不被新状态包含
                prev_state_id = current_state_id
                current_state_id = next_state_id
                while current_state_id:
                    # 获取当前状态的nextState关系
                    next_state_query = """
                    MATCH (s1:State {id: $current_id})-[r:nextState]->(s2:State)
                    WHERE $entity_id IN r.entity
                    RETURN s2.id AS next_id, s2.time AS time
                    """
                    current_result = tx.run(
                        next_state_query,
                        current_id=current_state_id,
                        entity_id=entity_id,
                    ).single()
                    current_time = (
                        current_result["time"] if current_result else ""
                    )
                    # 解析当前状态的时间范围
                    current_start_time, current_end_time = (
                        self._parse_time_range(current_time)
                    )
                    # 如果当前状态被新状态包含，更新current_state_id
                    if (
                        current_start_time
                        and current_end_time
                        and new_start_time
                        and new_end_time
                        and new_start_time <= current_start_time
                        and new_end_time >= current_end_time
                    ):
                        current_state_id = current_result["next_id"]
                    # 如果当前状态不被新状态包含，创建新的nextState关系
                    else:
                        # 删除原有nextState关系
                        remove_next_state_query = """
                        MATCH (s1:State {id: $prev_id})-[r:nextState]->(s2:State {id: $current_id})
                        SET r.entity = [x IN r.entity WHERE x <> $entity_id]
                        WITH r
                        WHERE SIZE(r.entity) = 0
                        DELETE r
                        """
                        tx.run(
                            remove_next_state_query,
                            prev_id=prev_state_id,
                            current_id=current_state_id,
                            entity_id=entity_id,
                        )
                        # 创建新的nextState关系
                        new_next_state_query = """
                        MATCH (s1:State {id: $state_id})
                        MATCH (s2:State {id: $current_id})
                        MERGE (s1)-[r:nextState]->(s2)
                        SET r.entity = 
                          CASE
                            WHEN r.entity IS NULL THEN [ $entity_id ]
                            ELSE r.entity + $entity_id
                          END
                        RETURN r
                        """
                        tx.run(
                            new_next_state_query,
                            state_id=state_id,
                            current_id=current_state_id,
                            entity_id=entity_id,
                        )
                        break
                inserted = True
                self.logger.debug(
                    f"新状态包含当前状态: State({state_id}) -[nextState]-> State({current_state_id})"
                )
            
            # 情况4: 新状态在当前状态之前 - 新状态成为当前状态的前驱
            elif (
                current_start_time
                and new_start_time
                and new_end_time
                and new_start_time < current_start_time
            ):
                # 如果当前状态是首节点，需要调整hasState关系
                if current_state_id == first_state_id:
                    # 删除原有hasState关系
                    remove_has_state_query = """
                    MATCH (e)-[r:hasState]->(s:State {id: $current_id})
                    WHERE e.id = $entity_id
                    DELETE r
                    """
                    tx.run(
                        remove_has_state_query,
                        current_id=current_state_id,
                        entity_id=entity_id,
                    )
                    
                    # 创建新的hasState关系到新状态
                    new_has_state_query = """
                    MATCH (e) WHERE e.id = $entity_id
                    MATCH (s:State {id: $state_id})
                    MERGE (e)-[r:hasState]->(s)
                    SET r.entity = $entity_id
                    """
                    tx.run(
                        new_has_state_query,
                        state_id=state_id,
                        entity_id=entity_id,
                    )
                else:
                    # 如果不是首节点，调整前一个节点的nextState关系
                    # 删除原有nextState关系
                    remove_next_state_query = """
                    MATCH (s1:State {id: $prev_id})-[r:nextState]->(s2:State {id: $current_id})
                    SET r.entity = [x IN r.entity WHERE x <> $entity_id]
                    WITH r
                    WHERE SIZE(r.entity) = 0
                    DELETE r
                    """
                    tx.run(
                        remove_next_state_query,
                        prev_id=prev_state_id,
                        current_id=current_state_id,
                        entity_id=entity_id,
                    )
                    
                    # 创建从前一个节点到新状态的nextState关系
                    new_prev_next_query = """
                    MATCH (s1:State {id: $prev_id})
                    MATCH (s2:State {id: $state_id})
                    MERGE (s1)-[r:nextState]->(s2)
                    SET r.entity =
                      CASE
                        WHEN r.entity IS NULL THEN [ $entity_id ]
                        ELSE r.entity + $entity_id
                      END
                    """
                    tx.run(
                        new_prev_next_query,
                        prev_id=prev_state_id,
                        state_id=state_id,
                        entity_id=entity_id,
                    )
                
                # 创建从新状态到当前状态的nextState关系
                new_next_state_query = """
                MATCH (s1:State {id: $state_id})
                MATCH (s2:State {id: $current_id})
                MERGE (s1)-[r:nextState]->(s2)
                SET r.entity =
                  CASE
                    WHEN r.entity IS NULL THEN [ $entity_id ]
                    ELSE r.entity + $entity_id
                  END
                RETURN r
                """
                tx.run(
                    new_next_state_query,
                    state_id=state_id,
                    current_id=current_state_id,
                    entity_id=entity_id,
                )
                
                inserted = True
                self.logger.debug(
                    f"新状态在当前状态之前: State({state_id}) -[nextState]-> State({current_state_id})"
                )
                self.logger.debug(
                    f"调整前驱: State({prev_state_id}) -[nextState]-> State({state_id})"
                )
        
        # 如果遍历完整个链还没有插入，则添加到链的末尾
        if not inserted:
            self.logger.debug("所有情况都不满足，跳过当前状态的处理")
    
    def _get_entity_latest_state(self, tx, entity_id: str) -> Optional[str]:
        """获取实体的最新状态节点ID"""
        query = """
        MATCH (e)-[:hasState]->(first:State)
        WHERE e.id = $entity_id
        WITH first
        OPTIONAL MATCH path = (first)-[rels:nextState*]->(last)
        WHERE ALL(r IN rels WHERE $entity_id IN r.entity)
        WITH first, last, path, length(path) AS pathLength
        ORDER BY pathLength DESC
        LIMIT 1
        WITH first, CASE WHEN path IS NOT NULL THEN last ELSE first END AS targetNode
        RETURN targetNode.id AS state_id, targetNode.time AS time
        """
        
        result = tx.run(query, entity_id=entity_id).data()
        
        if not result:
            return None
        
        # 返回时间最晚的状态
        latest_state = max(
            result,
            key=lambda x: (self._parse_time_range(x["time"])[1] if x["time"] else datetime.min),
        )
        
        return latest_state["state_id"]
    
    def _create_state_relation(self, tx, relation_data: Dict[str, Any]):
        """创建状态之间的关系"""
        subject_id = relation_data["主体状态ID"]
        relation_type = relation_data["关系"]
        object_id = relation_data["客体状态ID"]
        basis = relation_data.get("依据")
        source = relation_data.get("文档来源", "")
        
        # 优化查询以避免笛卡尔积 - 先匹配主体状态，再匹配客体状态
        relation_query = (
            f"MATCH (s1:State {{id: $subject_id}}) "
            f"MATCH (s2:State {{id: $object_id}}) "
            f"MERGE (s1)-[r:hasRelation {{type: $relation_type, basis: $basis, source: $source}}]->(s2) "
            f"RETURN r"
        )
        
        return tx.run(
            relation_query,
            subject_id=subject_id,
            object_id=object_id,
            relation_type=relation_type,
            basis=basis,
            source=source,
        ).single()