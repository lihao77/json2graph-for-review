"""数据库连接模块

提供Neo4j数据库连接和基础操作功能。
"""

from neo4j import GraphDatabase
from typing import Optional, Dict, Any, List
import logging
from itertools import chain

logger = logging.getLogger(__name__)


class Neo4jConnection:
    """Neo4j数据库连接管理器"""
    
    def __init__(self, uri: str, user: str, password: str, database: Optional[str] = None):
        """初始化Neo4j连接
        
        Args:
            uri: Neo4j数据库URI
            user: 用户名
            password: 密码
            database: 数据库名称（可选）
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver = None
        self.logger = logging.getLogger(__name__)
        
    def connect(self) -> None:
        """建立数据库连接"""
        try:
            self.driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password)
            )
            # 测试连接
            with self.driver.session(database=self.database) as session:
                session.run("RETURN 1")
            self.logger.info(f"成功连接到Neo4j数据库: {self.uri}")
        except Exception as e:
            self.logger.error(f"连接Neo4j数据库失败: {e}")
            raise
    
    def close(self) -> None:
        """关闭数据库连接"""
        if self.driver:
            self.driver.close()
            self.logger.info("Neo4j数据库连接已关闭")
    
    def get_session(self):
        """获取数据库会话"""
        if not self.driver:
            raise RuntimeError("数据库未连接，请先调用connect()方法")
        return self.driver.session(database=self.database)
    
    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None):
        """执行查询
        
        Args:
            query: Cypher查询语句
            parameters: 查询参数
            
        Returns:
            查询结果
        """
        with self.get_session() as session:
            return session.run(query, parameters or {})
    
    def execute_write_transaction(self, transaction_function, *args, **kwargs):
        """执行写事务
        
        Args:
            transaction_function: 事务函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            事务执行结果
        """
        with self.get_session() as session:
            return session.execute_write(transaction_function, *args, **kwargs)
    
    def execute_read_transaction(self, transaction_function, *args, **kwargs):
        """执行读事务
        
        Args:
            transaction_function: 事务函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            事务执行结果
        """
        with self.get_session() as session:
            return session.execute_read(transaction_function, *args, **kwargs)
    
    def create_index(self, index_query: str) -> bool:
        """创建单个索引
        
        Args:
            index_query: 索引创建的Cypher语句
            
        Returns:
            bool: 索引创建是否成功
        """
        with self.get_session() as session:
            try:
                session.run(index_query)
                self.logger.info(f"索引创建成功: {index_query}")
                return True
            except Exception as e:
                self.logger.warning(f"索引创建失败: {index_query}, 错误: {e}")
                return False
    
    def create_indexes(self, index_queries: list) -> Dict[str, bool]:
        """批量创建索引
        
        Args:
            index_queries: 索引创建语句列表
            
        Returns:
            Dict[str, bool]: 每个索引的创建结果
        """
        results = {}
        for index_query in index_queries:
            results[index_query] = self.create_index(index_query)
        return results
    
    def check_spatial_support(self) -> bool:
        """检查是否支持Neo4j-Spatial插件功能
        
        Returns:
            bool: 是否支持Neo4j-Spatial插件功能
        """
        with self.get_session() as session:
            try:
                # 检查Neo4j-Spatial插件的核心过程是否可用
                result = session.run(
                    "SHOW PROCEDURES YIELD name WHERE name IN ['spatial.addWKTLayer'] RETURN count(*) AS spatial_count"
                ).single()
                
                spatial_count = result.get("spatial_count", 0) if result else 0
                
                # # 如果Neo4j-Spatial插件不可用，检查原生空间索引支持
                # if spatial_count < 1:
                #     self.logger.info("Neo4j-Spatial插件不可用，检查原生空间索引支持")
                #     # 检查是否支持原生POINT INDEX
                #     point_result = session.run(
                #         "SHOW PROCEDURES YIELD name WHERE name = 'db.index.fulltext.createNodeIndex' RETURN count(*) > 0 AS native_spatial"
                #     ).single()
                #     return point_result and point_result.get("native_spatial", False)
                
                return spatial_count >= 1
                
            except Exception as e:
                self.logger.warning(f"检查空间功能时出错: {e}")
                # 如果检查失败，尝试简单的空间功能测试
                try:
                    session.run("RETURN point({longitude: 0, latitude: 0}) AS test_point")
                    return True
                except:
                    return False
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def build_spatial_framework(self):
        """构建层级化的空间框架 - 协调式架构

        职责说明:
        - 协调SpatialRelationshipProcessor创建的基础空间属性
        - 处理需要全局图分析的复杂空间关系
        - 验证和补充处理器创建的关系
        - 确保数据一致性和完整性

        Returns:
            Dict: 空间框架信息，包含位置层级数量和事件位置数量
        """
        logger.info("开始构建层级化的空间框架...")

        with self.get_session() as session:
            # 第一步：创建和验证基础空间层级关系
            # (基于SpatialRelationshipProcessor添加的属性)
            location_count = session.execute_write(self._create_location_framework)

            # 第二步：创建设施与地点的空间关系
            facility_count = session.execute_write(self._create_facility_framework)

            # 第三步：创建事件与地点的复杂空间关系
            # (需要全局图分析，这是SpatialRelationshipProcessor无法处理的)
            event_count = session.execute_write(self._create_event_framework)

            # 第四步：验证和清理空间关系
            validation_results = session.execute_write(self._validate_spatial_relationships)

            # 第五步：获取空间框架统计信息
            info = session.execute_write(self._get_spatial_info)

            logger.info(f"空间框架构建完成: {info}")
            logger.info(f"验证结果: {validation_results}")

            return info

    def _get_spatial_info(self, tx):
        """获取空间框架统计信息"""
        # 返回创建的层级关系数量
        count_query = """
            MATCH ()-[r:locatedIn]->()
            RETURN COUNT(r) AS location_hierarchies
        """
        location_hierarchies = tx.run(count_query).single()["location_hierarchies"]

        count_event_query = """
            MATCH ()-[r:occurredAt]->()
            RETURN COUNT(r) AS event_locations
        """
        event_locations = tx.run(count_event_query).single()["event_locations"]

        return {
            "location_hierarchies": location_hierarchies,
            "event_locations": event_locations,
        }

    def _create_location_framework(self, tx):
        """创建层级化的空间框架结构 - 主要负责复杂的空间关系分析

        职责说明:
        - 处理需要全局图分析的空间关系
        - 验证和补充SpatialRelationshipProcessor创建的关系
        - 处理复杂的多跳层级关系
        - 确保数据一致性和完整性
        """
        logger.info("开始创建层级化的空间框架结构...")

        # 第一步：识别所有地点实体并获取处理器添加的属性
        query_locations = """
            MATCH (l:地点)
            WHERE l.id STARTS WITH 'L-'
            RETURN l.id AS id, l.name AS name, l.admin_level AS admin_level,
                   l.parent_location_id AS processor_parent_id
        """
        locations = tx.run(query_locations).data()
        logger.info(f"找到 {len(locations)} 个地点实体")

        # 第二步：解析地理层级关系并验证处理器提供的信息
        location_hierarchy = {}
        relationships_created = 0

        for location in locations:
            loc_id = location["id"]
            loc_name = location["name"]

            # 优先使用处理器提供的行政级别信息
            admin_level = location.get("admin_level")
            processor_parent = location.get("processor_parent_id")

            # 解析地理ID以确定层级关系
            parts = loc_id.split(">")
            base_id = parts[0]  # 基础行政区划ID
            admin_code = base_id[2:] if base_id.startswith("L-") else base_id

            # 确定行政级别和父ID
            level = None
            parent_id = None

            # 处理更细粒度的地理实体（镇、乡、村等）
            if len(parts) > 1:
                level = "town" if len(parts) == 2 else "village"
                parent_id = base_id
            else:
                if len(admin_code) >= 6:  # 完整的行政区划代码
                    if admin_code.endswith("0000"):  # 省级
                        level = "province"
                    elif admin_code[4:6] == "00":  # 地级市
                        level = "city"
                        parent_id = f"L-{admin_code[:2]}0000"  # 省级父ID
                    else:  # 区县级
                        level = "county"
                        parent_id = f"L-{admin_code[:4]}00"  # 市级父ID

            # 验证处理器提供的信息是否与解析结果一致
            if admin_level and admin_level != level:
                logger.warning(f"地点 {loc_id} 的行政级别不一致: 处理器={admin_level}, 解析={level}")

            if processor_parent and processor_parent != parent_id:
                logger.warning(f"地点 {loc_id} 的父ID不一致: 处理器={processor_parent}, 解析={parent_id}")

            # 存储层级关系信息
            location_hierarchy[loc_id] = {
                "id": loc_id,
                "name": loc_name,
                "level": level,
                "parent_id": parent_id,
                "validated": True  # 标记为已验证
            }

        # 第三步：创建经过验证的层级关系
        logger.info("创建层级关系...")
        for loc_id, loc_info in location_hierarchy.items():
            if loc_info["parent_id"]:
                # 检查父节点是否存在
                parent_exists_query = """
                    MATCH (parent)
                    WHERE parent.id = $parent_id
                    RETURN count(parent) > 0 AS exists
                """
                parent_result = tx.run(parent_exists_query, parent_id=loc_info["parent_id"]).single()

                if parent_result and parent_result["exists"]:
                    query = """
                        MATCH (child) WHERE child.id = $child_id
                        MATCH (parent) WHERE parent.id = $parent_id
                        MERGE (child)-[r:locatedIn]->(parent)
                        ON CREATE SET r.created_by = 'spatial_framework', r.level = $level
                        ON MATCH SET r.validated = true, r.level = $level
                        RETURN r
                    """
                    result = tx.run(query, child_id=loc_id, parent_id=loc_info["parent_id"], level=loc_info["level"])
                    if result.single():
                        relationships_created += 1
                else:
                    logger.warning(f"父节点 {loc_info['parent_id']} 不存在，跳过关系创建")

        logger.info(f"层级关系创建完成，共创建 {relationships_created} 个关系")
        return relationships_created

    def _create_event_framework(self, tx):
        """创建事件与地点的空间关系框架 - 增强版（支持所有状态类型）

        职责:
        - 优先使用SpatialRelationshipProcessor添加的各种状态属性
        - 支持LS-(地点状态), FS-(设施状态), ES-(事件状态), JS-(联合状态)
        - 回退到传统的关系分析方法
        - 处理复杂的事件-地点关联关系
        """
        logger.info("开始创建事件与地点的空间关系框架...")

        # 识别所有事件实体
        query_events = """
            MATCH (e:事件)
            WHERE e.id STARTS WITH 'E-'
            RETURN e.id AS id, e.name AS name
        """
        events = tx.run(query_events).data()
        logger.info(f"找到 {len(events)} 个事件实体")

        relationships_created = 0

        # 对于每个事件，查找相关的地理位置
        for event in events:
            event_id = event["id"]
            event_name = event["name"]
            event_locations = set()

            # 第一步：优先检查SpatialRelationshipProcessor添加的属性
            event_query = """
                MATCH (e:事件)
                WHERE e.id = $event_id
                RETURN e.event_locations AS processor_locations,
                       e.is_event_state AS is_event_state
            """
            event_result = tx.run(event_query, event_id=event_id).single()

            if event_result and event_result["processor_locations"]:
                # 使用处理器添加的event_locations属性
                processor_locations = event_result["processor_locations"]
                if isinstance(processor_locations, list):
                    event_locations.update(processor_locations)
                    logger.debug(f"事件 {event_id} 使用处理器添加的地点: {processor_locations}")

            # 第二步：通过状态实体分析补充地理位置
            states = self._get_all_entity_states(tx, event_id)
            for state in states:
                # 检查状态节点的处理器属性（支持所有状态类型）
                state_attrs_query = """
                    MATCH (s:State)
                    WHERE s.id = $state_id
                    RETURN s.associated_locations AS state_locations,
                           s.associated_events AS state_events,
                           s.state_type AS state_type,
                           s.is_event_state AS state_is_event,
                           s.is_location_state AS state_is_location,
                           s.is_facility_state AS state_is_facility,
                           s.is_joint_state AS state_is_joint
                """
                state_attrs = tx.run(state_attrs_query, state_id=state).single()

                if state_attrs:
                    # 根据状态类型处理空间信息
                    state_type = state_attrs.get("state_type")

                    if state_type == "event" or state_attrs.get("state_is_event"):
                        # ES-状态：直接关联事件，需要找其关联的地点
                        state_locations = state_attrs.get("associated_locations", [])
                        if isinstance(state_locations, list):
                            event_locations.update(state_locations)
                            logger.debug(f"ES状态 {state} 添加地点: {state_locations}")

                    elif state_type == "location" or state_attrs.get("state_is_location"):
                        # LS-状态：直接关联地点
                        state_locations = state_attrs.get("state_locations", [])
                        if isinstance(state_locations, list):
                            event_locations.update(state_locations)
                            logger.debug(f"LS状态 {state} 添加地点: {state_locations}")

                    elif state_type == "joint" or state_attrs.get("state_is_joint"):
                        # JS-状态：联合状态，可能关联多种实体
                        state_locations = state_attrs.get("associated_locations", [])
                        if isinstance(state_locations, list):
                            event_locations.update(state_locations)
                            logger.debug(f"JS状态 {state} 添加地点: {state_locations}")

                if not state_attrs or not any([
                    state_attrs.get("associated_locations"),
                    state_attrs.get("state_locations"),
                    state_attrs.get("associated_events")
                ]):
                    # 回退到传统的关系分析方法
                    logger.debug(f"状态 {state} 使用回退分析方法")
                    query_entity_ids = """
                        MATCH (s1:State)-[:hasRelation]->(s2:State)
                        WHERE s1.id = $state_id
                        RETURN s2.entity_ids AS entity_ids
                    """
                    entity_ids_list = []
                    result = tx.run(query_entity_ids, state_id=state).data()
                    for entity_ids in result:
                        if entity_ids["entity_ids"]:
                            entity_ids_list.append(entity_ids["entity_ids"])

                    flattened_list = list(chain.from_iterable(entity_ids_list))
                    unique_entity_ids = list(set(flattened_list))
                    # 只保留"L-"开头的实体ID
                    unique_entity_ids = [
                        id for id in unique_entity_ids if id.startswith("L-")
                    ]
                    event_locations.update(unique_entity_ids)

            # 为事件创建与地理位置的关联
            if event_locations:
                logger.info(f"事件 {event_name} ({event_id}) 关联到 {len(event_locations)} 个地点")
                for location_id in event_locations:
                    query = """
                        MATCH (e) WHERE e.id = $event_id
                        MATCH (l) WHERE l.id = $location_id
                        MERGE (e)-[r:occurredAt]->(l)
                        ON CREATE SET r.created_by = 'spatial_framework'
                        RETURN r
                    """
                    result = tx.run(query, event_id=event_id, location_id=location_id)
                    if result.single():
                        relationships_created += 1
            else:
                logger.warning(f"事件 {event_name} ({event_id}) 没有找到关联的地点")

        logger.info(f"事件空间关系创建完成，共创建 {relationships_created} 个关系")
        return relationships_created

    def _create_facility_framework(self, tx):
        """创建设施与地点的空间关系框架"""
        # 识别所有设施实体
        query_facilities = """
            MATCH (f:设施)
            WHERE f.id STARTS WITH 'F-'
            RETURN f.id AS id, f.name AS name
        """
        facilities = tx.run(query_facilities).data()

        facilities_hierarchy = {}
        for facility in facilities:
            fac_id = facility["id"]
            fac_name = facility["name"]

            # 解析设施ID以确定所属地点
            # 设施 ID: `F-<行政区划码>-<设施名称>` (e.g., `F-420500-三峡大坝`)
            parts = fac_id.split("-")
            if len(parts) >= 3:
                admin_code = parts[1]
                location_id = f"L-{admin_code}"
                facilities_hierarchy[fac_id] = {
                    "id": fac_id,
                    "name": fac_name,
                    "location_id": location_id,
                }
                # 创建设施与地点的关联
                query = """
                    MATCH (f) WHERE f.id = $facility_id
                    MATCH (l) WHERE l.id = $location_id
                    MERGE (f)-[r:locatedIn]->(l)
                    RETURN r
                """
                tx.run(query, facility_id=fac_id, location_id=location_id)
        return len(facilities_hierarchy)

    def _get_all_entity_states(self, tx, entity_id: str) -> List[str]:
        """获取实体的所有状态节点"""
        query = """
            MATCH (s:State)
            WHERE $entity_id IN s.entity_ids
            RETURN s.id AS state_id
        """
        result = tx.run(query, entity_id=entity_id)
        return [record["state_id"] for record in result]

    def _validate_spatial_relationships(self, tx):
        """验证和清理空间关系

        职责:
        - 验证空间关系的完整性
        - 清理无效的关系（指向不存在的节点）
        - 补充缺失的关系
        - 确保数据一致性
        """
        logger.info("开始验证空间关系...")

        validation_results = {
            "invalid_relationships_removed": 0,
            "missing_relationships_added": 0,
            "inconsistent_attributes_fixed": 0
        }

        # 1. 清理指向不存在节点的关系
        cleanup_query = """
            MATCH (start)-[r:locatedIn|occurredAt]-(end)
            WHERE NOT EXISTS {
                MATCH (end)
                WHERE end.id IS NOT NULL
            }
            DELETE r
            RETURN count(r) as removed_count
        """
        cleanup_result = tx.run(cleanup_query).single()
        if cleanup_result:
            validation_results["invalid_relationships_removed"] = cleanup_result["removed_count"]

        # 2. 验证行政层级关系的一致性
        consistency_check = """
            MATCH (child:地点)-[r:locatedIn]->(parent:地点)
            WHERE child.id STARTS WITH 'L-' AND parent.id STARTS WITH 'L-'
            WITH child, parent, r,
                 CASE
                     WHEN child.id ENDS WITH '0000' THEN 'province'
                     WHEN substring(child.id, 4, 2) = '00' THEN 'city'
                     ELSE 'county'
                 END as child_level,
                 CASE
                     WHEN parent.id ENDS WITH '0000' THEN 'province'
                     WHEN substring(parent.id, 4, 2) = '00' THEN 'city'
                     ELSE 'county'
                 END as parent_level
            WHERE (
                (child_level = 'city' AND parent_level <> 'province') OR
                (child_level = 'county' AND parent_level <> 'city')
            )
            RETURN count(r) as inconsistent_count
        """
        consistency_result = tx.run(consistency_check).single()
        if consistency_result:
            validation_results["inconsistent_attributes_fixed"] = consistency_result["inconsistent_count"]

        # 3. 补充缺失的反向关系（可选，根据业务需求）
        # 这里可以添加更多的验证逻辑

        logger.info(f"空间关系验证完成: {validation_results}")
        return validation_results

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()