#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的SKGStore测试脚本

仅测试SKGStore的基本功能和空间处理器
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from json2graph.db import Neo4jConnection
from json2graph.store_mode.skg_store import SKGStore
from json2graph.processor.spatial_processor import SpatialProcessor
from json2graph.interfaces import IProcessor, EntityType, ProcessorResult, GraphOperation, GraphOperationType

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)




def create_test_data():
    """创建带空间数据的测试数据"""
    return {
        "基础实体": [
            {
                "类型": "地点",
                "名称": "南宁市",
                "唯一ID": "L-450100",
                "地理描述": "广西南宁市"
            },
            {
                "类型": "事件",
                "名称": "台风预警",
                "唯一ID": "E-450000-20231001",
                "地理描述": "广西南宁台风预警"
            },
            {
                "类型": "设施",
                "名称": "南宁站",
                "唯一ID": "F-450100-火车站",
                "地理描述": "南宁市火车站"
            }
        ],
        "状态实体": [
            {
                "类型": "独立状态",
                "关联实体ID列表": ["L-450100"],
                "状态ID": "S-L-450100-20231001",
                "时间": "2023-10-01至2023-10-10",
                "状态描述": {
                    "总受灾人口": "52.88万人",
                    "直接经济损失": "3.90亿元"
                }
            }
        ],
        "状态关系": [
            {
                "主体状态ID": "S-L-450100-20231001",
                "关系": "影响",
                "客体状态ID": "S-L-450100-20231001",
                "依据": "台风导致广西南宁市总受灾人口达52.88万人"
            }
        ]
    }


def test_database_connection():
    """测试数据库连接"""
    logger.info("=== 测试数据库连接 ===")
    
    try:
        db = Neo4jConnection(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="admin123456"
        )
        db.connect()
        logger.info("数据库连接成功")
        return db
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        raise


def test_skg_store_with_spatial_processor():
    """测试SKGStore与空间处理器"""
    logger.info("=== 测试SKGStore与空间处理器 ===")
    
    db = test_database_connection()
    store = SKGStore(db)
    
    try:
        # 添加空间处理器（使用地理编码API和geojson优先）
        spatial_config = {
            "api_key": "msvcwRmOJFaHyzjlieIP0Z1TI1PZIvgl",  # 请替换为实际的API密钥
            "service": "baidu",
            "cache_file": "spatial_geocoding_cache.json",
            "admin_geojson_dir": "data/admin_geojson",
            "river_geojson_dir": "data/river_geojson"
        }
        spatial_processor = SpatialProcessor(**spatial_config)
        store.add_processor(spatial_processor)
        logger.info("空间处理器添加成功")
        
        # 存储测试数据
        test_data = create_test_data()
        store.store_knowledge_graph(test_data)
        logger.info("知识图谱存储完成")
        
        # 验证存储结果
        with store.db.driver.session() as session:
            # 查询带空间数据的实体
            spatial_entities = session.run(
                "MATCH (n) WHERE n.wkt IS NOT NULL RETURN n.id as id, n.wkt as wkt, labels(n) as labels"
            )
            
            logger.info("带空间数据的实体:")
            for record in spatial_entities:
                logger.info(f"  实体ID: {record['id']}")
                logger.info(f"  WKT: {record['wkt']}")
                logger.info(f"  标签: {record['labels']}")
                logger.info("---")
            
            # 查询WKT图层
            layers = session.run(
                "MATCH (l:WktLayer) RETURN l.name as name, l.type as type, count{(n)-[:BELONGS_TO_WKT_LAYER]->(l)} as entity_count"
            )
            
            logger.info("WKT空间图层:")
            for record in layers:
                logger.info(f"  图层: {record['name']} ({record['type']}) - 实体数量: {record['entity_count']}")
        
        return store
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        raise
    finally:
        store.close()


def main():
    """主测试函数"""
    logger.info("开始SKGStore空间测试")
    
    try:
        store = test_skg_store_with_spatial_processor()
        logger.info("所有测试完成！")
        
    except Exception as e:
        logger.error(f"测试过程中出现错误: {e}")


if __name__ == "__main__":
    main()