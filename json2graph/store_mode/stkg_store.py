"""STKG（Spatio-temporal Knowledge Graph）存储实现

继承自SKG存储，添加地理编码处理器，实现地理数据的编码。
"""

from typing import Dict, Any, List, Optional
import logging

from .skg_store import SKGStore
from ..processor.spatial_processor import SpatialProcessor
from ..db import Neo4jConnection
from ..interfaces import EntityType


class STKGStore(SKGStore):
    """STKG存储实现
    
    继承自SKG存储，自动添加地理编码处理器，提供：
    - 基础SKG功能
    - 自动地理编码
    - 空间数据处理
    """
    
    def __init__(self, 
                 db_connection: Neo4jConnection,
                 geocoding_config: Optional[Dict[str, Any]] = None):
        """初始化STKG存储
        
        Args:
            db_connection: Neo4j数据库连接
            geocoding_config: 地理编码配置，包含API密钥等信息
        """
        super().__init__(db_connection)
        
        # 添加地理编码处理器
        if geocoding_config is None:
            geocoding_config = {}
        
        geocoding_processor = SpatialProcessor(geocoding_config)
        self.add_processor(geocoding_processor)
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("STKG存储已初始化，包含地理编码处理器")
    
    def store_base_entities(self, entities: List[Dict[str, Any]]) -> None:
        """存储基础实体（带地理编码）
        
        重写父类方法，确保地点和设施类型的实体进行地理编码
        """
        # 过滤需要地理编码的实体
        geo_entities = []
        non_geo_entities = []
        
        for entity in entities:
            entity_type = entity.get("类型", "")
            if entity_type in ["地点", "设施"] and entity.get("地理描述"):
                geo_entities.append(entity)
            else:
                non_geo_entities.append(entity)
        
        # 先处理需要地理编码的实体
        if geo_entities:
            self.logger.info(f"开始处理 {len(geo_entities)} 个需要地理编码的实体")
            super().store_base_entities(geo_entities)
        
        # 再处理不需要地理编码的实体
        if non_geo_entities:
            self.logger.info(f"开始处理 {len(non_geo_entities)} 个不需要地理编码的实体")
            super().store_base_entities(non_geo_entities)
    
    def get_geocoding_stats(self) -> Dict[str, Any]:
        """获取地理编码统计信息"""
        geocoding_processor = None
        for processor in self.processors.values():
            if isinstance(processor, SpatialProcessor):
                geocoding_processor = processor
                break
        
        if geocoding_processor:
            return geocoding_processor.get_cache_stats()
        else:
            return {"error": "未找到地理编码处理器"}
    
    def export_geocoding_cache(self, file_path: str) -> bool:
        """导出地理编码缓存"""
        geocoding_processor = None
        for processor in self.processors.values():
            if isinstance(processor, SpatialProcessor):
                geocoding_processor = processor
                break
        
        if geocoding_processor:
            return geocoding_processor.export_cache(file_path)
        else:
            self.logger.error("未找到地理编码处理器")
            return False
    
    def import_geocoding_cache(self, file_path: str) -> bool:
        """导入地理编码缓存"""
        geocoding_processor = None
        for processor in self.processors.values():
            if isinstance(processor, SpatialProcessor):
                geocoding_processor = processor
                break
        
        if geocoding_processor:
            return geocoding_processor.import_cache(file_path)
        else:
            self.logger.error("未找到地理编码处理器")
            return False
    
    def clear_geocoding_cache(self) -> bool:
        """清空地理编码缓存"""
        geocoding_processor = None
        for processor in self.processors.values():
            if isinstance(processor, SpatialProcessor):
                geocoding_processor = processor
                break
        
        if geocoding_processor:
            geocoding_processor.clear_cache()
            self.logger.info("地理编码缓存已清空")
            return True
        else:
            self.logger.error("未找到地理编码处理器")
            return False
    
    def update_geocoding_config(self, config: Dict[str, Any]) -> bool:
        """更新地理编码配置"""
        geocoding_processor = None
        for processor in self.processors.values():
            if isinstance(processor, SpatialProcessor):
                geocoding_processor = processor
                break
        
        if geocoding_processor:
            try:
                geocoding_processor.update_config(config)
                self.logger.info("地理编码配置已更新")
                return True
            except Exception as e:
                self.logger.error(f"更新地理编码配置失败: {e}")
                return False
        else:
            self.logger.error("未找到地理编码处理器")
            return False
    
    def get_entities_with_geometry(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取包含几何信息的实体
        
        Args:
            entity_type: 实体类型过滤，如"地点"或"设施"
            
        Returns:
            包含几何信息的实体列表
        """
        query = """
        MATCH (e)
        WHERE e.geometry IS NOT NULL
        """
        
        params = {}
        if entity_type:
            query += " AND $entity_type IN labels(e)"
            params["entity_type"] = entity_type
        
        query += """
        RETURN e.id AS id, e.name AS name, labels(e) AS types,
               e.longitude AS longitude, e.latitude AS latitude,
               e.geometry AS geometry
        ORDER BY e.name
        """
        
        result = self.db.execute_read_transaction(
            lambda tx: tx.run(query, **params).data()
        )
        
        return result
    
    def get_entities_by_location(self, 
                               location_name: Optional[str] = None,
                               longitude: Optional[float] = None,
                               latitude: Optional[float] = None,
                               radius_km: float = 10.0) -> List[Dict[str, Any]]:
        """根据位置查询实体
        
        Args:
            location_name: 地点名称
            longitude: 经度
            latitude: 纬度
            radius_km: 搜索半径（公里）
            
        Returns:
            匹配的实体列表
        """
        if location_name:
            # 按名称搜索
            query = """
            MATCH (e)
            WHERE e.name CONTAINS $location_name
            RETURN e.id AS id, e.name AS name, labels(e) AS types,
                   e.longitude AS longitude, e.latitude AS latitude
            ORDER BY e.name
            """
            params = {"location_name": location_name}
        
        elif longitude is not None and latitude is not None:
            # 按坐标和半径搜索
            query = """
            MATCH (e)
            WHERE e.geometry IS NOT NULL
            WITH e, distance(e.geometry, point({longitude: $longitude, latitude: $latitude})) AS dist
            WHERE dist <= $radius_meters
            RETURN e.id AS id, e.name AS name, labels(e) AS types,
                   e.longitude AS longitude, e.latitude AS latitude,
                   dist AS distance_meters
            ORDER BY dist
            """
            params = {
                "longitude": longitude,
                "latitude": latitude,
                "radius_meters": radius_km * 1000
            }
        
        else:
            raise ValueError("必须提供location_name或者longitude+latitude参数")
        
        result = self.db.execute_read_transaction(
            lambda tx: tx.run(query, **params).data()
        )
        
        return result