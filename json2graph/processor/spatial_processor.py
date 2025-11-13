"""
空间处理器 - 使用地理编码API将地理描述转换为WKT格式

提供以下功能：
1. 优先查找行政区划和河流的geojson数据
2. 使用高德/百度API进行地理编码兜底
3. 将编码结果转换为WKT格式
4. 创建和管理WKT空间图层
5. 将空间信息存储到实体属性
"""

import json
import logging
import requests
import time
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from ..interfaces import IProcessor, EntityType, ProcessorResult
from ..db import Neo4jConnection


class SpatialProcessor(IProcessor):
    """空间处理器，处理实体的WKT数据和空间图层"""
    
    def __init__(self, 
                 api_key: str = "",
                 service: str = "amap",
                 cache_file: str = "spatial_cache.json",
                 admin_geojson_dir: str = None,
                 river_geojson_dir: str = None,
                 timeout: int = 10,
                 retry_times: int = 3,
                 request_delay: float = 0.5):
        """
        初始化空间处理器
        
        Args:
            api_key: 地理编码API密钥
            service: 地理编码服务提供商，支持"amap"(高德地图)和"baidu"(百度地图)
            cache_file: 地理编码缓存文件路径
            admin_geojson_dir: 行政区划geojson文件目录
            river_geojson_dir: 河流geojson文件目录
            timeout: API请求超时时间（秒）
            retry_times: 重试次数
            request_delay: API请求间隔时间（秒）
        """
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key
        self.service = service.lower()
        self.cache_file = cache_file
        self.admin_geojson_dir = admin_geojson_dir or "data/admin_geojson"
        self.river_geojson_dir = river_geojson_dir or "data/river_geojson"
        self.timeout = timeout
        self.retry_times = retry_times
        self.request_delay = request_delay
        self.cache: Dict[str, Dict[str, float]] = {}  # 缓存地理编码结果
        self.spatial_layers: Dict[str, str] = {}
        # 按层级存储行政区划数据
        self.admin_geojson_cache: Dict[str, Dict[str, Any]] = {}
        self.admin_by_level: Dict[str, Dict[str, Dict[str, Any]]] = {
            "province": {},  # 省：省级代码 -> feature
            "city": {},      # 市：市级代码 -> feature
            "county": {}    # 县：县级代码 -> feature
        }
        # 按尺度存储河流数据
        self.river_geojson_cache: Dict[str, Dict[str, Any]] = {}
        self.river_by_scale: Dict[str, Dict[str, Dict[str, Any]]] = {
            "province": {},  # 省级尺度：河流名称 -> feature
            "city": {},      # 市级尺度：河流名称 -> feature
            "county": {}     # 县级尺度：河流名称 -> feature
        }
        
        # 验证服务类型
        if self.service not in ["amap", "baidu"]:
            self.logger.warning(f"不支持的地理编码服务: {self.service}，使用amap作为默认服务")
            self.service = "amap"
        
        # 加载缓存和geojson数据
        self._load_cache()
        self._load_geojson_data()
    
    def _load_geojson_data(self):
        """加载行政区划和河流的geojson数据"""
        # 加载行政区划geojson
        self._load_admin_geojson()
        # 加载河流geojson
        self._load_river_geojson()
    
    def _load_admin_geojson(self):
        """加载行政区划geojson数据"""
        try:
            if not os.path.exists(self.admin_geojson_dir):
                os.makedirs(self.admin_geojson_dir, exist_ok=True)
                self.logger.info(f"创建行政区划geojson目录: {self.admin_geojson_dir}")
                return
            
            for filename in os.listdir(self.admin_geojson_dir):
                if filename.endswith('.json') or filename.endswith('.geojson'):
                    filepath = os.path.join(self.admin_geojson_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            geojson_data = json.load(f)
                            # 缓存行政区划数据
                            if 'features' in geojson_data:
                                for feature in geojson_data['features']:
                                    properties = feature.get('properties', {})
                                    name = self._extract_name_from_feature(feature)
                                    if name:
                                        # 按层级存储
                                        if 'xian_code' in properties:  # 县级
                                            county_code = properties['xian_code']
                                            self.admin_by_level["county"][county_code] = feature
                                        elif 'shi_code' in properties:  # 市级
                                            city_code = properties['shi_code']
                                            self.admin_by_level["city"][city_code] = feature
                                        elif 'sheng_code' in properties:  # 省级
                                            province_code = properties['sheng_code']
                                            self.admin_by_level["province"][province_code] = feature
                                        
                                        # 同时存储到旧缓存中兼容性
                                        self.admin_geojson_cache[name] = feature
                            elif 'name' in geojson_data:
                                self.admin_geojson_cache[geojson_data['name']] = geojson_data
                    except Exception as e:
                        self.logger.warning(f"加载行政区划geojson失败: {filepath} - {e}")
            
            self.logger.info(f"成功加载行政区划geojson: {len(self.admin_geojson_cache)} 条记录")
            self.logger.info(f"行政区划层级统计: 省={len(self.admin_by_level['province'])}, 市={len(self.admin_by_level['city'])}, 县={len(self.admin_by_level['county'])}")
        except Exception as e:
            self.logger.error(f"加载行政区划geojson数据失败: {e}")
    
    def _load_river_geojson(self):
        """加载河流geojson数据"""
        try:
            if not os.path.exists(self.river_geojson_dir):
                os.makedirs(self.river_geojson_dir, exist_ok=True)
                self.logger.info(f"创建河流geojson目录: {self.river_geojson_dir}")
                return
            
            for filename in os.listdir(self.river_geojson_dir):
                if filename.endswith('.json') or filename.endswith('.geojson'):
                    filepath = os.path.join(self.river_geojson_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            geojson_data = json.load(f)
                            # 缓存河流数据
                            if 'features' in geojson_data:
                                for feature in geojson_data['features']:
                                    properties = feature.get('properties', {})
                                    name = self._extract_name_from_feature(feature)
                                    if name:
                                        # 按尺度存储
                                        admin_level = properties.get('admin_level', 'unknown')
                                        scale_key = None
                                        
                                        if admin_level == 'province':
                                            scale_key = 'province'
                                        elif admin_level == 'city':
                                            scale_key = 'city'
                                        elif admin_level == 'county':
                                            scale_key = 'county'
                                        
                                        if scale_key:
                                            # 对于同一尺度下的同一条河流，如果有多个段，保留所有段
                                            if name not in self.river_by_scale[scale_key]:
                                                self.river_by_scale[scale_key][name] = []
                                            self.river_by_scale[scale_key][name].append(feature)
                                        
                                        # 同时存储到旧缓存中兼容性
                                        self.river_geojson_cache[name] = feature
                            elif 'name' in geojson_data:
                                self.river_geojson_cache[geojson_data['name']] = geojson_data
                    except Exception as e:
                        self.logger.warning(f"加载河流geojson失败: {filepath} - {e}")
            
            self.logger.info(f"成功加载河流geojson: {len(self.river_geojson_cache)} 条记录")
            self.logger.info(f"河流尺度统计: 省={len(self.river_by_scale['province'])}种河流, 市={len(self.river_by_scale['city'])}种河流, 县={len(self.river_by_scale['county'])}种河流")
        except Exception as e:
            self.logger.error(f"加载河流geojson数据失败: {e}")
    
    def _extract_name_from_feature(self, feature: Dict[str, Any]) -> Optional[str]:
        """从geojson feature中提取名称"""
        try:
            # 优先从properties中获取name
            properties = feature.get('properties', {})
            name = properties.get('name')
            if name:
                return name
            
            # 尝试其他可能的名称字段
            for key in ['name', 'NAME', 'Name', 'sheng_name', 'shi_name', 'xian_name', '行政区', '河流名称', 'river_name']:
                name = properties.get(key)
                if name:
                    print(name, "@@@@@@@@@@@@@@")
                    return name
            
            return None
        except Exception:
            return None
    
    def get_name(self) -> str:
        """获取处理器名称"""
        return "spatial_processor"
    
    def get_supported_entity_types(self) -> List[EntityType]:
        """支持基础实体和状态实体"""
        return [EntityType.BASE_ENTITY, EntityType.STATE_ENTITY]
    
    def get_spatial_entity_types(self) -> List[str]:
        """返回需要空间索引的实体类型"""
        return ["地点", "设施"]
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """验证处理器配置"""
        required_keys = ["entity_types", "layer_naming_pattern"]
        return all(key in config for key in required_keys)
    
    def get_required_indexes(self) -> List[str]:
        """返回所需的索引列表，包括Neo4j Spatial索引"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (n:entity) ON (n.type)",
            "CREATE INDEX IF NOT EXISTS FOR (n:entity) ON (n.spatial_layer)",
            "CREATE INDEX IF NOT EXISTS FOR (n:State) ON (n.spatial_layer)",
            "CREATE INDEX IF NOT EXISTS FOR (n:entity) ON (n.wkt_hash)",
        ]
        
        # 添加空间图层创建命令，由SKGStore负责执行和检查
        spatial_entity_types = self.get_spatial_entity_types()
        for entity_type in spatial_entity_types:
            # 使用特殊的标记表示这是空间索引，需要Neo4j Spatial支持
            indexes.append(f"SPATIAL_LAYER:{entity_type}")
        
        return indexes
    
    def _load_cache(self):
        """加载地理编码缓存"""
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                self.cache = json.load(f)
                self.logger.info(f"成功加载地理编码缓存: {len(self.cache)} 条记录")
        except (FileNotFoundError, json.JSONDecodeError):
            self.cache = {}
            self.logger.info("地理编码缓存文件不存在，创建新的缓存")
    
    def _save_cache(self):
        """保存地理编码缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
                self.logger.info(f"地理编码缓存已保存: {len(self.cache)} 条记录")
        except Exception as e:
            self.logger.error(f"保存地理编码缓存失败: {e}")
    
    def _geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        使用地理编码API获取坐标
        
        Args:
            address: 地址描述
            
        Returns:
            (经度, 纬度) 或 None
        """
        if not address or not self.api_key:
            return None
        
        # 检查缓存
        if address in self.cache:
            coords = self.cache[address]
            return coords["lng"], coords["lat"]
        
        try:
            time.sleep(self.request_delay)  # 避免请求过快
            
            if self.service == "amap":
                return self._geocode_amap(address)
            elif self.service == "baidu":
                return self._geocode_baidu(address)
            
        except Exception as e:
            self.logger.error(f"地理编码失败: {address} - {e}")
        
        return None
    
    def _geocode_amap(self, address: str) -> Optional[Tuple[float, float]]:
        """使用高德地图API进行地理编码"""
        url = "https://restapi.amap.com/v3/geocode/geo"
        params = {
            "key": self.api_key,
            "address": address,
            "output": "json"
        }
        
        for attempt in range(self.retry_times):
            try:
                response = requests.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == "1" and data.get("geocodes"):
                    location = data["geocodes"][0]["location"]
                    lng, lat = map(float, location.split(","))
                    
                    # 保存到缓存
                    self.cache[address] = {"lng": lng, "lat": lat}
                    self._save_cache()
                    
                    return lng, lat
                    
            except Exception as e:
                if attempt == self.retry_times - 1:
                    self.logger.error(f"高德地理编码失败: {address} - {e}")
                time.sleep(1)
        
        return None
    
    def _geocode_baidu(self, address: str) -> Optional[Tuple[float, float]]:
        """使用百度地图API进行地理编码"""
        url = "https://api.map.baidu.com/geocoding/v3/"
        params = {
            "ak": self.api_key,
            "address": address,
            "output": "json"
        }
        
        for attempt in range(self.retry_times):
            try:
                response = requests.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == 0:
                    result = data.get("result", {})
                    location = result.get("location", {})
                    lng = location.get("lng")
                    lat = location.get("lat")
                    
                    if lng is not None and lat is not None:
                        # 保存到缓存
                        self.cache[address] = {"lng": lng, "lat": lat}
                        self._save_cache()
                        
                        return float(lng), float(lat)
                        
            except Exception as e:
                if attempt == self.retry_times - 1:
                    self.logger.error(f"百度地理编码失败: {address} - {e}")
                time.sleep(1)
        
        return None
    
    def _get_wkt_from_geojson_or_geocoding(self, entity_id: str, description: str, entity_type: str) -> Optional[str]:
        """
        优先从geojson获取WKT数据，如果没有则使用地理编码兜底
        
        Args:
            entity_id: 实体ID
            description: 地理描述文本
            entity_type: 实体类型
            
        Returns:
            WKT格式的空间数据
        """
        if not description:
            return None
        
        # 优先从geojson查找
        wkt_data = self._get_wkt_from_geojson(entity_id, description)
        if wkt_data:
            self.logger.info(f"从geojson获取空间数据: {entity_id} - {description}")
            return wkt_data
        
        # geojson中没有，使用地理编码兜底
        self.logger.info(f"geojson中未找到，使用地理编码: {entity_id} - {description}")
        return self._get_wkt_from_geocoding(description, entity_type)
    
    def _get_wkt_from_geojson(self, entity_id: str, description: str) -> Optional[str]:
        """
        从geojson数据中获取WKT格式
        
        Args:
            entity_id: 实体ID
            description: 地理描述文本
            
        Returns:
            WKT格式的空间数据
        """
        # 根据ID格式判断查找哪个geojson
        if entity_id.startswith("L-") and not entity_id.startswith("L-RIVER-"):
            # 行政区划类型
            return self._get_wkt_from_admin_geojson(entity_id, description)
        elif entity_id.startswith("L-RIVER-"):
            # 河流类型
            return self._get_wkt_from_river_geojson(entity_id, description)
        
        return None
    
    def _get_wkt_from_admin_geojson(self, entity_id: str, description: str) -> Optional[str]:
        """从行政区划geojson获取WKT"""
        try:
            # 从ID中解析行政区划码和子区域
            # 格式: L-<行政区划码>[>乡镇街道等子区域]
            if not entity_id.startswith("L-") or entity_id.startswith("L-RIVER-"):
                return None
            
            # 检查是否包含子区域（包含">"符号）
            if ">" in entity_id:
                self.logger.info(f"检测到子区域信息，跳过geojson查找，将使用地理编码: {entity_id}")
                return None
            
            # 提取行政区划码（6位数字）
            admin_code = entity_id[2:8]  # 跳过"L-"取6位
            
            # 从县级开始逐级向上查找
            # 1. 先查找县级（6位完整代码）
            if len(admin_code) == 6 and admin_code in self.admin_by_level["county"]:
                feature = self.admin_by_level["county"][admin_code]
                self.logger.info(f"从县级geojson匹配成功: {admin_code}")
                return self._convert_geojson_feature_to_wkt(feature)
            
            # 2. 再查找市级（前4位+00）
            if len(admin_code) >= 4:
                city_code = admin_code[:4] + "00"
                if city_code in self.admin_by_level["city"]:
                    feature = self.admin_by_level["city"][city_code]
                    self.logger.info(f"从市级geojson匹配成功: {city_code}")
                    return self._convert_geojson_feature_to_wkt(feature)
            
            # 3. 最后查找省级（前2位+0000）
            province_code = admin_code[:2] + "0000"
            if province_code in self.admin_by_level["province"]:
                feature = self.admin_by_level["province"][province_code]
                self.logger.info(f"从省级geojson匹配成功: {province_code}")
                return self._convert_geojson_feature_to_wkt(feature)
            
            # 4. 如果都没有找到，按名称匹配作为备选
            for cached_name, feature in self.admin_geojson_cache.items():
                properties = feature.get('properties', {})
                for key in ['sheng_name', 'shi_name', 'xian_name']:
                    name = properties.get(key)
                    if name and name in description:
                        self.logger.info(f"从名称匹配成功: {name}")
                        return self._convert_geojson_feature_to_wkt(feature)
            
            self.logger.info(f"未找到对应的行政区划geojson数据: {admin_code}")
            return None
        except Exception as e:
            self.logger.warning(f"从行政区划geojson获取WKT失败: {e}")
            return None
    
    def _get_wkt_from_river_geojson(self, entity_id: str, description: str) -> Optional[str]:
        """从河流geojson获取WKT"""
        try:
            # 从ID中解析河流信息
            # 格式: L-RIVER-<名称>[>区段]
            if not entity_id.startswith("L-RIVER-"):
                return None
            
            # 提取河流名称和段描述
            river_part = entity_id[8:]  # 跳过"L-RIVER-"
            if ">" in river_part:
                river_name, segment_desc = river_part.split(">", 1)
                has_segment = True
                self.logger.info(f"检测到河流区段信息: 河流={river_name}, 段描述={segment_desc}")
            else:
                river_name = river_part
                segment_desc = None
                has_segment = False
            
            # 匹配逻辑：
            # 1. 没有段描述：直接匹配最粗粒度的省级数据
            # 2. 有段描述：尝试匹配县级和市级数据，比较段描述与行政区划名称
            
            if not has_segment:
                # 没有段描述，直接匹配省级尺度（最粗粒度）
                print(f"无段描述，尝试省级尺度匹配: {river_name}", )
                if river_name in self.river_by_scale["province"]:
                    features = self.river_by_scale["province"][river_name]
                    if features:
                        self.logger.info(f"无段描述，使用省级尺度匹配成功: {river_name} ({len(features)}个段)")
                        return self._convert_geojson_feature_to_wkt(features[0])
                else:
                    self.logger.info(f"无段描述但未找到省级数据: {river_name}")
            else:
                # 有段描述，尝试精确匹配县级和市级数据
                # 1. 先尝试县级匹配（最精确）
                county_match = self._match_river_by_county(river_name, segment_desc)
                if county_match:
                    return county_match
                
                # 2. 再尝试市级匹配
                city_match = self._match_river_by_city(river_name, segment_desc)
                if city_match:
                    return city_match
                
                self.logger.info(f"有段描述但未找到匹配的市县级数据: {river_name}>{segment_desc}")
            
            # 3. 兜底：尝试省级尺度或模糊匹配
            if river_name in self.river_by_scale["province"]:
                features = self.river_by_scale["province"][river_name]
                if features:
                    self.logger.info(f"使用省级尺度兜底匹配成功: {river_name} ({len(features)}个段)")
                    return self._convert_geojson_feature_to_wkt(features[0])
            
            # 4. 最后尝试模糊匹配
            for scale_name, scale_data in self.river_by_scale.items():
                for cached_name, features in scale_data.items():
                    if river_name in cached_name or cached_name in river_name:
                        self.logger.info(f"从{scale_name}尺度模糊匹配成功: {river_name} -> {cached_name}")
                        return self._convert_geojson_feature_to_wkt(features[0])
            
            self.logger.info(f"未找到对应的河流geojson数据: {river_name}")
            return None
        except Exception as e:
            self.logger.warning(f"从河流geojson获取WKT失败: {e}")
            return None
    
    def _match_river_by_county(self, river_name: str, segment_desc: str) -> Optional[str]:
        """按县级匹配河流段"""
        try:
            if river_name not in self.river_by_scale["county"]:
                return None
            
            features = self.river_by_scale["county"][river_name]
            if not features:
                return None
            
            # 提取段描述中的关键词
            # 处理不同类型的段描述：
            # 1. 行政区类型：如"浦北县河段"、"荆江河段"
            # 2. 河流段类型：如"上游段"、"中游段"、"下游段"
            
            # 尝试提取县名
            county_keywords = []
            segment_desc_clean = segment_desc.replace("河段", "").replace("段", "")
            
            # 检查是否包含"县"、"区"等行政区标识
            for admin_word in ["县", "区", "市"]:
                if admin_word in segment_desc:
                    # 提取行政区名称，如"浦北县河段" -> "浦北县"
                    start = 0
                    for i, char in enumerate(segment_desc):
                        if char == admin_word:
                            end = i + 1
                            county_name = segment_desc[start:end].strip()
                            county_keywords.append(county_name)
                            break
            
            # 如果没找到行政区标识，尝试直接匹配描述文本
            if not county_keywords:
                county_keywords = [segment_desc_clean, segment_desc]
            
            self.logger.info(f"县级匹配 - 河流: {river_name}, 段描述: {segment_desc}, 提取的关键词: {county_keywords}")
            
            # 遍历所有县级河段，寻找匹配
            for feature in features:
                properties = feature.get('properties', {})
                xian_name = properties.get('xian_name')
                
                if xian_name:
                    # 精确匹配
                    for keyword in county_keywords:
                        if keyword == xian_name or keyword in xian_name or xian_name in keyword:
                            self.logger.info(f"县级精确匹配成功: {river_name} - {segment_desc} -> 县名: {xian_name}")
                            return self._convert_geojson_feature_to_wkt(feature)
                    
                    # 模糊匹配：去除常见后缀后匹配
                    xian_name_clean = xian_name.replace("县", "").replace("区", "").replace("市", "")
                    for keyword in county_keywords:
                        keyword_clean = keyword.replace("县", "").replace("区", "").replace("市", "")
                        if keyword_clean == xian_name_clean or keyword_clean in xian_name_clean or xian_name_clean in keyword_clean:
                            self.logger.info(f"县级模糊匹配成功: {river_name} - {segment_desc} -> 县名: {xian_name}")
                            return self._convert_geojson_feature_to_wkt(feature)
            
            self.logger.info(f"县级匹配失败: {river_name} - {segment_desc}")
            return None
            
        except Exception as e:
            self.logger.warning(f"县级河流匹配失败: {e}")
            return None
    
    def _match_river_by_city(self, river_name: str, segment_desc: str) -> Optional[str]:
        """按市级匹配河流段"""
        try:
            if river_name not in self.river_by_scale["city"]:
                return None
            
            features = self.river_by_scale["city"][river_name]
            if not features:
                return None
            
            # 提取段描述中的关键词
            city_keywords = []
            segment_desc_clean = segment_desc.replace("河段", "").replace("段", "")
            
            # 检查是否包含"市"等行政区标识
            for admin_word in ["市", "地区"]:
                if admin_word in segment_desc:
                    # 提取行政区名称，如"荆州市河段" -> "荆州市"
                    start = 0
                    for i, char in enumerate(segment_desc):
                        if char == admin_word:
                            end = i + 1
                            city_name = segment_desc[start:end].strip()
                            city_keywords.append(city_name)
                            break
            
            # 如果没找到行政区标识，尝试直接匹配描述文本
            if not city_keywords:
                city_keywords = [segment_desc_clean, segment_desc]
            
            self.logger.info(f"市级匹配 - 河流: {river_name}, 段描述: {segment_desc}, 提取的关键词: {city_keywords}")
            
            # 遍历所有市级河段，寻找匹配
            for feature in features:
                properties = feature.get('properties', {})
                shi_name = properties.get('shi_name')
                
                if shi_name:
                    # 精确匹配
                    for keyword in city_keywords:
                        if keyword == shi_name or keyword in shi_name or shi_name in keyword:
                            self.logger.info(f"市级精确匹配成功: {river_name} - {segment_desc} -> 市名: {shi_name}")
                            return self._convert_geojson_feature_to_wkt(feature)
                    
                    # 模糊匹配：去除常见后缀后匹配
                    shi_name_clean = shi_name.replace("市", "").replace("地区", "")
                    for keyword in city_keywords:
                        keyword_clean = keyword.replace("市", "").replace("地区", "")
                        if keyword_clean == shi_name_clean or keyword_clean in shi_name_clean or shi_name_clean in keyword_clean:
                            self.logger.info(f"市级模糊匹配成功: {river_name} - {segment_desc} -> 市名: {shi_name}")
                            return self._convert_geojson_feature_to_wkt(feature)
            
            self.logger.info(f"市级匹配失败: {river_name} - {segment_desc}")
            return None
            
        except Exception as e:
            self.logger.warning(f"市级河流匹配失败: {e}")
            return None
    
    def _convert_geojson_feature_to_wkt(self, feature: Dict[str, Any]) -> Optional[str]:
        """将geojson feature转换为WKT格式"""
        try:
            # 这里简化处理，实际应用中需要完整的geojson到WKT转换
            geometry = feature.get('geometry')
            if not geometry:
                return None
            
            geom_type = geometry.get('type')
            coordinates = geometry.get('coordinates')
            
            if not coordinates:
                return None
            
            if geom_type == 'Point':
                return f"POINT ({coordinates[0]} {coordinates[1]})"
            elif geom_type == 'LineString':
                coords_str = ', '.join([f"{coord[0]} {coord[1]}" for coord in coordinates])
                return f"LINESTRING ({coords_str})"
            elif geom_type == 'Polygon':
                # 简化处理，只取外环
                coords = coordinates[0]
                coords_str = ', '.join([f"{coord[0]} {coord[1]}" for coord in coords])
                return f"POLYGON (({coords_str}))"
            elif geom_type == 'MultiLineString':
                # 简化为LineString
                if coordinates and coordinates[0]:
                    coords_str = ', '.join([f"{coord[0]} {coord[1]}" for coord in coordinates[0]])
                    return f"LINESTRING ({coords_str})"
            elif geom_type == 'MultiPolygon':
                # 简化为Polygon
                if coordinates and coordinates[0] and coordinates[0][0]:
                    coords = coordinates[0][0]
                    coords_str = ', '.join([f"{coord[0]} {coord[1]}" for coord in coords])
                    return f"POLYGON (({coords_str}))"
            
            return None
        except Exception as e:
            self.logger.warning(f"转换geojson到WKT失败: {e}")
            return None
    
    def _get_wkt_from_geocoding(self, description: str, entity_type: str) -> Optional[str]:
        """
        使用地理编码API获取WKT数据（兜底方案）
        
        Args:
            description: 地理描述文本
            entity_type: 实体类型
            
        Returns:
            WKT格式的空间数据
        """
        if not description:
            return None
        
        # 获取地理编码坐标
        coords = self._geocode_address(description)
        if not coords:
            return None
        
        lng, lat = coords
        
        # 根据实体类型决定几何类型
        if entity_type in ["地点", "设施", "城市", "街道"]:
            return f"POINT ({lng} {lat})"
        elif entity_type in ["区域", "省份", "城市区域", "行政区划"]:
            # 为区域生成简化的边界多边形（实际应用中应使用真实边界数据）
            offset = 0.01
            return f"POLYGON (({lng-offset} {lat-offset}, {lng+offset} {lat-offset}, {lng+offset} {lat+offset}, {lng-offset} {lat+offset}, {lng-offset} {lat-offset}))"
        elif entity_type in ["河流", "道路", "铁路", "路线"]:
            # 为路线生成简化的线段（实际应用中应使用真实路径数据）
            return f"LINESTRING ({lng} {lat}, {lng+0.01} {lat+0.01})"
        else:
            return f"POINT ({lng} {lat})"
    
    def process(self, entity_type: EntityType, data: Dict[str, Any], context: Dict[str, Any] = None) -> ProcessorResult:
        """
        处理空间数据 - 优先使用geojson，然后使用地理编码API将地理描述转换为WKT格式
        
        Args:
            entity_type: 实体类型
            data: 实体数据
            context: 上下文信息（可选，用于接收前置处理器的数据）
            
        Returns:
            ProcessorResult对象，包含空间处理结果和传递给后续处理器的context
        """
        result = ProcessorResult()
        
        try:
            # 获取实体ID
            entity_id = data.get("唯一ID", "")
            if not entity_id:
                self.logger.debug("实体没有ID，跳过空间处理")
                return result
            
            # 获取地理描述
            geo_description = data.get("地理描述", "")
            if not geo_description:
                self.logger.debug("实体没有地理描述，跳过空间处理")
                return result
            
            # 获取实体类型
            entity_type_name = data.get("类型", "Unknown")
            
            # 获取WKT数据（优先geojson，然后地理编码）
            wkt_data = self._get_wkt_from_geojson_or_geocoding(entity_id, geo_description, entity_type_name)
            if not wkt_data:
                self.logger.warning(f"无法为实体获取空间数据: {data.get('名称', '未知实体')} - {geo_description}")
                result.processor_context = {"wkt_error": f"无法获取{geo_description}的空间数据"}
                return result
            
            geometry_type = self._get_geometry_type(wkt_data)
            
            # 添加空间属性到节点
            result.add_properties({
                "geometry": wkt_data,
                "spatial_layer": entity_type_name,
                "wkt_hash": hash(wkt_data),
                "spatial_type": geometry_type,
                "spatial_processed": datetime.now().isoformat(),
                "spatial_processor": self.get_name(),
                "original_address": geo_description
            })
            
            # 将关键空间信息传递给后续处理器
            processor_context = {
                "wkt_data": wkt_data,
                "geometry_type": geometry_type,
                "spatial_layer": entity_type_name,
                "entity_id": entity_id,
                "original_address": geo_description
            }
            result.processor_context = processor_context
            
            # 将实体添加到Neo4j Spatial对应的空间图层
            spatial_entity_types = self.get_spatial_entity_types()
            if entity_type_name in spatial_entity_types:
                layer_name = f"spatial_layer_{entity_type_name}"
                
                # 使用Neo4j Spatial的addNode功能将实体添加到图层，先检查是否已存在
                result.execute_cypher(
                    query=f"""
                    MATCH (n {{id: $entity_id}})
                    OPTIONAL MATCH p = (:SpatialLayer {{layer: $layer_name}})
                        -[:RTREE_ROOT]-()
                        -[:RTREE_CHILD*0..]-()
                        -[:RTREE_REFERENCE]-(n)
                    WITH n , p IS NULL AS needAdd
                    WHERE needAdd
                    CALL spatial.addNode($layer_name, n) YIELD node
                    RETURN node
                    """,
                    params={"entity_id": data.get("唯一ID"), "layer_name": layer_name}
                )
                
                self.logger.info(f"已将实体添加到Neo4j Spatial图层: {data.get('名称', '未知实体')} -> {layer_name}")
            
            self.logger.info(f"成功处理空间数据: {data.get('名称', '未知实体')} - {geo_description} -> {geometry_type}")
            
        except Exception as e:
            self.logger.error(f"处理空间数据失败: {e}")
            result.add_property("spatial_error", str(e))
            result.processor_context = {"wkt_error": str(e)}
        
        return result
    
    def _get_geometry_type(self, wkt: str) -> str:
        """从WKT字符串获取几何类型"""
        if wkt.startswith("POINT"):
            return "Point"
        elif wkt.startswith("LINESTRING"):
            return "LineString"
        elif wkt.startswith("POLYGON"):
            return "Polygon"
        elif wkt.startswith("MULTIPOINT"):
            return "MultiPoint"
        elif wkt.startswith("MULTILINESTRING"):
            return "MultiLineString"
        elif wkt.startswith("MULTIPOLYGON"):
            return "MultiPolygon"
        else:
            return "Unknown"
    
    def add_to_spatial_layer(self, entity_type_name: str, entity_id: str, wkt_data: str) -> bool:
        """
        添加实体到空间图层
        
        Args:
            entity_type_name: 实体类型名称
            entity_id: 实体ID
            wkt_data: WKT空间数据
            
        Returns:
            是否成功添加
        """
        try:
            # 更新节点并添加图层
            layer_name = f"spatial_layer_{entity_type_name}"
            cypher_query = f"""
            MATCH (n) WHERE n.id = '{entity_id}'
            SET n.geometry = '{wkt_data}', n.spatial_layer = '{entity_type_name}'
            WITH n
            CALL spatial.addNode('{layer_name}', n) YIELD node
            RETURN node
            """
            
            self.logger.info(f"执行空间图层添加: {entity_type_name} - {entity_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"添加实体到空间图层失败: {e}")
            return False
    
    def get_entities_by_spatial_layer(self, layer_name: str) -> List[Dict[str, Any]]:
        """
        获取指定空间图层中的所有实体
        
        Args:
            layer_name: 图层名称
            
        Returns:
            实体列表
        """
        # 这里会在查询功能模块中实现
        return []