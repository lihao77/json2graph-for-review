"""空间关系处理器

用于创建和维护空间实体之间的关系，包括层级化的空间关系和事件与地点的关联关系。
"""

from typing import Dict, Any, List, Optional
import logging

from ..interfaces import IProcessor, EntityType, ProcessorResult, GraphOperation, GraphOperationType


class SpatialRelationshipProcessor(IProcessor):
    """空间关系处理器

    负责创建和维护空间实体之间的关系，包括：
    - 层级化的空间关系 (locatedIn)
    - 事件与地点的关联关系 (occurredAt)
    - 设施与地点的空间关系 (locatedIn)
    """

    def __init__(self, relationship_config: Optional[Dict[str, Any]] = None):
        """初始化空间关系处理器

        Args:
            relationship_config: 关系配置字典
        """
        self.relationship_config = relationship_config or {}
        self.logger = logging.getLogger(__name__)

        # 空间关系类型
        self.spatial_relationships = {
            'locatedIn': ['地点', '设施'],  # 设施位于地点，地点位于上级地点
            'occurredAt': ['事件', '地点']   # 事件发生在地点
        }

        # 行政区划层级关系
        self.admin_hierarchy = {
            'province': ['city', 'county', 'town', 'village'],
            'city': ['county', 'town', 'village'],
            'county': ['town', 'village'],
            'town': ['village']
        }

    def get_name(self) -> str:
        """获取处理器名称"""
        return "spatial_relationship_processor"

    def get_supported_entity_types(self) -> List[EntityType]:
        """获取支持的实体类型"""
        return [EntityType.BASE_ENTITY, EntityType.STATE_ENTITY]

    def process(self,
                entity_type: EntityType,
                data: Dict[str, Any],
                context: Optional[Dict[str, Any]] = None) -> ProcessorResult:
        """处理空间关系

        Args:
            entity_type: 实体类型
            data: 要处理的数据
            context: 处理器间共享的上下文数据

        Returns:
            ProcessorResult对象，包含图操作指令
        """
        result = ProcessorResult()

        if entity_type == EntityType.BASE_ENTITY:
            # 处理基础实体的空间关系
            self._process_base_entity_relationships(data, result)
        elif entity_type == EntityType.STATE_ENTITY:
            # 处理状态实体的空间关系
            self._process_state_entity_relationships(data, result)

        return result

    def _process_base_entity_relationships(self, data: Dict[str, Any], result: ProcessorResult):
        """处理基础实体的空间关系 - 仅处理简单、直接的关系

        职责说明:
        - 仅创建不需要复杂图分析的关系
        - 避免与db.py框架的批量处理功能重复
        - 专注于提供立即可用的基础空间属性
        """
        entity_id = data.get("唯一ID", "")
        entity_type = data.get("类型", "")

        # 仅为地点实体添加空间属性，不创建层级关系
        # (层级关系由db.py框架统一处理，确保数据一致性)
        
        # 仅处理以"L-"开头的地点实体，避免处理非标准ID
        if entity_type == "地点" and entity_id.startswith("L-"):
            # 添加行政级别属性，供后续查询使用
            admin_level = self._get_admin_level(entity_id)
            if admin_level != "unknown":
                # 使用批量属性添加方式，符合执行器期望的格式
                result.add_properties({
                    "admin_level": admin_level,
                    "has_spatial_hierarchy": True
                })

            # 对于子区域，添加父区域ID属性
            if ">" in entity_id:
                parent_id = self._get_parent_location_id(entity_id)
                if parent_id:
                    result.add_properties({"parent_location_id": parent_id})

        # 为设施实体添加位置属性，不创建关系
        # (设施-地点关系由db.py框架统一处理)
        elif entity_type == "设施":
            location_id = self._get_facility_location_id(entity_id)
            if location_id:
                result.add_properties({
                    "admin_location_id": location_id,
                    "facility_type": "设施"
                })

        # 为河流实体添加空间属性
        elif entity_type == "河流":
            result.add_properties({"water_feature_type": "河流"})
            # 添加河段信息（如果有）
            if ">" in entity_id:
                parts = entity_id.split(">")
                if len(parts) > 1:
                    result.add_properties({"river_segment": parts[1]})

    def _process_state_entity_relationships(self, data: Dict[str, Any], result: ProcessorResult):
        """处理状态实体的空间关系 - 仅添加属性，不创建关系

        职责说明:
        - 为状态实体添加空间属性，供db.py框架后续使用
        - 不直接创建关系，避免与批量处理器冲突
        - 提供空间分析所需的基础数据
        - 支持所有状态类型：LS-(地点状态), FS-(设施状态), ES-(事件状态), JS-(联合状态)
        """
        state_id = data.get("状态ID", "")
        entity_ids = data.get("关联实体ID列表", [])

        # 解析状态类型前缀
        state_type = self._get_state_type(state_id)

        # 根据状态类型查找关联的空间实体
        location_ids = []
        facility_ids = []
        event_ids = []

        for entity_id in entity_ids:
            if entity_id.startswith("L-"):
                location_ids.append(entity_id)
            elif entity_id.startswith("F-"):
                facility_ids.append(entity_id)
            elif entity_id.startswith("E-"):
                event_ids.append(entity_id)

        # 为状态实体添加空间属性（不创建关系）
        properties = {
            "state_type": state_type,
            "associated_locations": location_ids,
            "associated_facilities": facility_ids,
            "associated_events": event_ids,
            "total_associations": len(entity_ids)
        }

        # 根据状态类型添加特定属性
        if location_ids:
            properties["location_coverage"] = len(location_ids)

        if facility_ids:
            properties["facility_coverage"] = len(facility_ids)

        if event_ids:
            properties["event_coverage"] = len(event_ids)

        # 根据状态类型前缀添加特定标识
        if state_id.startswith("LS-"):
            properties["is_location_state"] = True
            properties["spatial_coverage"] = len(location_ids)
            if location_ids:
                properties["location_ids"] = location_ids

        elif state_id.startswith("FS-"):
            properties["is_facility_state"] = True
            properties["spatial_coverage"] = len(facility_ids)
            if facility_ids:
                properties["facility_ids"] = facility_ids

        elif state_id.startswith("ES-"):
            properties["is_event_state"] = True
            properties["spatial_coverage"] = len(event_ids)
            if event_ids:
                properties["event_ids"] = event_ids
                properties["event_locations"] = location_ids  # 兼容原有逻辑

        elif state_id.startswith("JS-"):
            properties["is_joint_state"] = True
            properties["spatial_coverage"] = len(entity_ids)

        result.add_properties(properties)

    def _get_state_type(self, state_id: str) -> str:
        """获取状态实体类型

        Args:
            state_id: 状态实体ID

        Returns:
            状态类型: 'location', 'facility', 'event', 'joint', 'unknown'
        """
        if state_id.startswith("LS-"):
            return "location"
        elif state_id.startswith("FS-"):
            return "facility"
        elif state_id.startswith("ES-"):
            return "event"
        elif state_id.startswith("JS-"):
            return "joint"
        else:
            return "unknown"

    def _get_parent_location_id(self, location_id: str) -> Optional[str]:
        """获取上级地点ID

        Args:
            location_id: 地点ID (格式: L-行政区划码[>子区域])

        Returns:
            上级地点ID，如果没有则返回None
        """
        # 处理子区域的情况
        if ">" in location_id:
            parts = location_id.split(">")
            if len(parts) > 1:
                return parts[0]  # 返回基础行政区划ID
            return None

        # 处理标准行政区划代码
        if location_id.startswith("L-"):
            admin_code = location_id[2:]  # 去掉L-前缀

            if len(admin_code) >= 6:
                # 省级代码 (如: 450000)
                if admin_code.endswith("0000"):
                    return None  # 省级没有上级

                # 市级代码 (如: 450100)
                elif admin_code[4:6] == "00":
                    return f"L-{admin_code[:2]}0000"  # 省级父ID

                # 县级代码 (如: 450123)
                else:
                    return f"L-{admin_code[:4]}00"  # 市级父ID

        return None

    def _get_admin_level(self, location_id: str) -> str:
        """获取行政区划级别

        Args:
            location_id: 地点ID

        Returns:
            行政级别: province, city, county, town, village
        """
        if ">" in location_id:
            parts = location_id.split(">")
            if len(parts) == 2:
                return "town"
            elif len(parts) >= 3:
                return "village"

        if location_id.startswith("L-"):
            admin_code = location_id[2:]

            if len(admin_code) >= 6:
                if admin_code.endswith("0000"):
                    return "province"
                elif admin_code[4:6] == "00":
                    return "city"
                else:
                    return "county"

        return "unknown"

    def _get_facility_location_id(self, facility_id: str) -> Optional[str]:
        """获取设施所属的地点ID

        Args:
            facility_id: 设施ID (格式: F-行政区划码-设施名称)

        Returns:
            地点ID，如果无法解析则返回None
        """
        if facility_id.startswith("F-"):
            parts = facility_id.split("-")
            if len(parts) >= 3:
                admin_code = parts[1]
                return f"L-{admin_code}"

        return None

    def _get_river_admin_relations(self, river_data: Dict[str, Any]) -> List[str]:
        """获取河流与行政区划的关系

        Args:
            river_data: 河流数据

        Returns:
            关联的行政区划ID列表
        """
        location_ids = []

        # 从河流ID中提取信息
        river_id = river_data.get("唯一ID", "")
        river_name = river_data.get("名称", "")
        geo_desc = river_data.get("地理描述", "")

        # 解析河流ID中的行政区划信息
        if river_id.startswith("L-RIVER-"):
            # 检查是否有河段描述
            if ">" in river_id:
                parts = river_id.split(">")
                if len(parts) > 1:
                    segment_desc = parts[1]  # 河段描述

                    # 从河段描述中提取行政区划信息
                    # 例如: "浦北县河段", "荆江河段"等
                    if "县" in segment_desc:
                        county_name = segment_desc.split("县")[0] + "县"
                        # 这里需要结合地理编码或行政区划数据来匹配具体的ID
                        # 暂时返回空列表，实际使用时需要结合地理编码服务
                        pass
                    elif "市" in segment_desc:
                        city_name = segment_desc.split("市")[0] + "市"
                        pass
                    elif "区" in segment_desc:
                        district_name = segment_desc.split("区")[0] + "区"
                        pass

        # 从地理描述中提取行政区划信息
        if geo_desc:
            # 简单的关键词匹配，实际使用时需要更复杂的地理编码
            admin_keywords = ["省", "市", "县", "区"]
            for keyword in admin_keywords:
                if keyword in geo_desc:
                    # 这里需要结合地理编码服务来精确匹配
                    pass

        return location_ids



    def get_required_indexes(self) -> List[str]:
        """获取处理器需要的所有索引

        Returns:
            索引查询语句列表
        """
        return [
            "CREATE INDEX location_id_index IF NOT EXISTS FOR (n:地点) ON (n.id)",
            "CREATE INDEX facility_id_index IF NOT EXISTS FOR (n:设施) ON (n.id)",
            "CREATE INDEX event_id_index IF NOT EXISTS FOR (n:事件) ON (n.id)",
            "CREATE INDEX river_id_index IF NOT EXISTS FOR (n:河流) ON (n.id)",
        ]