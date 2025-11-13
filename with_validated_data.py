#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用validated_data.json的测试脚本

测试新的SpatialProcessor功能，支持优先查找geojson数据
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any

from json2graph.db import Neo4jConnection
from json2graph.store_mode.skg_store import SKGStore
from json2graph.processor.spatial_processor import SpatialProcessor

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


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


def test_with_validated_data():
    """使用validated_data.json测试"""
    logger.info("=== 使用validated_data.json测试 ===")
    
    # 加载测试数据
    with open('validated_data.json', 'r', encoding='utf-8') as f:
        test_data = json.load(f)
    
    logger.info(f"加载测试数据完成，基础实体数量: {len(test_data['基础实体'])}")
    
    db = test_database_connection()
    store = SKGStore(db)
    
    try:
        # 配置空间处理器
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
        
        # 存储知识图谱
        store.store_knowledge_graph(test_data)
        logger.info("知识图谱存储完成")
        
        # 验证存储结果
        with store.db.driver.session() as session:
            # 查询带空间数据的实体
            spatial_entities = session.run(
                "MATCH (n) WHERE n.wkt IS NOT NULL RETURN n.id as id, n.name as name, n.wkt as wkt, labels(n) as labels"
            )
            
            logger.info("带空间数据的实体:")
            for record in spatial_entities:
                logger.info(f"  实体ID: {record['id']}")
                logger.info(f"  名称: {record['name']}")
                logger.info(f"  WKT: {record['wkt']}")
                logger.info(f"  标签: {record['labels']}")
                logger.info("----------------------------------------------")
            
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
    logger.info("开始validated_data.json测试")
    
    try:
        store = test_with_validated_data()
        logger.info("所有测试完成！")
        
    except Exception as e:
        logger.error(f"测试过程中出现错误: {e}")


if __name__ == "__main__":
    main()