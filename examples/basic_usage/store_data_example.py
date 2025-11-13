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


def load_sample_data() -> Dict[str, Any]:
    """加载示例JSON数据"""
    try:
        # 加载examples/data文件夹中的示例数据
        with open('../data/sample_data.json', 'r', encoding='utf-8') as f:
            test_data = json.load(f)
            logger.info(f"✓ 成功加载示例数据: {len(test_data.get('基础实体', []))}个基础实体")
            return test_data
    except FileNotFoundError:
        logger.error("✗ 未找到../data/sample_data.json文件")
        raise
    except Exception as e:
        logger.error(f"✗ 加载示例数据失败: {e}")
        raise

def database_connection():
    """测试数据库连接"""
    logger.info("=== 测试数据库连接 ===")

    try:
        db = Neo4jConnection(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="admin123456"
        )
        db.connect()
        logger.info("✓ 数据库连接成功")
        return db
    except Exception as e:
        logger.error(f"✗ 数据库连接失败: {e}")
        raise


def test_basic_storage():
    """测试基础存储功能"""
    logger.info("=== 测试基础存储功能 ===")

    db = None
    try:
        # 连接数据库
        db = database_connection()

        # 创建存储实例
        store = SKGStore(db)

        # 加载示例数据
        data = load_sample_data()
        logger.info(f"加载示例数据: {len(data.get('基础实体', []))}个基础实体, "
                   f"{len(data.get('状态实体', []))}个状态实体, "
                   f"{len(data.get('状态关系', []))}个状态关系")

        # 存储知识图谱
        logger.info("存储知识图谱数据...")
        store.store_knowledge_graph(data)
        logger.info("✓ 知识图谱存储成功")

        # 验证数据
        verify_stored_data(db)

    except Exception as e:
        logger.error(f"测试失败: {e}")
        raise
    finally:
        if db:
            db.close()
            logger.info("数据库连接已关闭")


def verify_stored_data(db: Neo4jConnection):
    """验证存储的数据"""
    logger.info("=== 验证存储的数据 ===")

    try:
        with db.get_session() as session:
            # 查询基础实体
            result = session.run("""
                MATCH (n:基础实体)
                RETURN n.name as name, n.type as type, n.id as id
                ORDER BY n.type, n.name
                LIMIT 10
            """)

            logger.info("基础实体:")
            for record in result:
                logger.info(f"  - {record['name']} ({record['type']}) ID: {record['id']}")

            # 查询状态实体
            result = session.run("""
                MATCH (n:状态实体)
                RETURN n.state_id as state_id, n.type as type
                ORDER BY n.type, n.state_id
                LIMIT 10
            """)

            logger.info("状态实体:")
            for record in result:
                logger.info(f"  - {record['state_id']} ({record['type']})")

            # 查询关系
            result = session.run("""
                MATCH (n1)-[r]->(n2)
                WHERE n1:状态实体 AND n2:状态实体
                RETURN n1.state_id as from_state, type(r) as relation, n2.state_id as to_state
                LIMIT 5
            """)

            logger.info("状态关系:")
            for record in result:
                logger.info(f"  - {record['from_state']} --[{record['relation']}]-> {record['to_state']}")

            # 统计信息
            result = session.run("""
                MATCH (n)
                RETURN labels(n) as labels, count(n) as count
                ORDER BY count DESC
            """)

            logger.info("统计信息:")
            for record in result:
                labels = ":".join(record['labels'])
                count = record['count']
                logger.info(f"  - {labels}: {count}个节点")

    except Exception as e:
        logger.error(f"数据验证失败: {e}")
        raise


def test_spatial_processor():
    """测试空间处理器功能"""
    logger.info("=== 测试空间处理器功能 ===")

    db = None
    try:
        # 连接数据库
        db = database_connection()

        # 创建存储实例
        store = SKGStore(db)
        # 配置空间处理器
        spatial_config = {
            "api_key": "msvcwRmOJFaHyzjlieIP0Z1TI1PZIvgl",  # 请替换为实际的API密钥
            "service": "baidu",
            "cache_file": "spatial_geocoding_cache.json",
            "admin_geojson_dir": "data/admin_geojson",
            "river_geojson_dir": "data/river_geojson"
        }
        # 添加空间处理器
        spatial_processor = SpatialProcessor(
            **spatial_config
        )
        store.add_processor(spatial_processor)
        logger.info("✓ 空间处理器已添加")

        # 创建包含空间信息的测试数据
        spatial_data = {
            "基础实体": [
                {
                    "类型": "地点",
                    "名称": "南宁市青秀区",
                    "唯一ID": "L-450103>青秀区",  # 包含子区域，会触发地理编码
                    "地理描述": "南宁市青秀区政府"
                },
                {
                    "类型": "河流",
                    "名称": "邕江",
                    "唯一ID": "L-RIVER-邕江>南宁市河段",  # 河流段描述
                    "地理描述": "南宁市邕江段"
                },
                {
                    "类型": "河流",
                    "名称": "漓江",
                    "唯一ID": "L-RIVER-漓江",  # 无段描述，使用省级数据
                    "地理描述": "桂林市漓江"
                }
            ],
            "状态实体": [],
            "状态关系": []
        }

        logger.info("存储包含空间信息的实体...")
        store.store_knowledge_graph(spatial_data)
        logger.info("✓ 空间数据存储成功")

    except Exception as e:
        logger.error(f"空间处理器测试失败: {e}")
        raise
    finally:
        if db:
            db.close()
            logger.info("数据库连接已关闭")

def main():
    """主函数"""
    logger.info("=== json2graph 使用示例 ===")
    logger.info("本示例演示如何使用json2graph将JSON数据存储到Neo4j数据库")

    # 测试1: 基础存储功能
    logger.info("\n" + "="*50)
    test_basic_storage()

    # 测试2: 空间处理器功能
    logger.info("\n" + "="*50)
    test_spatial_processor()

    logger.info("\n" + "="*50)
    logger.info("=== 所有示例执行完成 ===")
    logger.info("请检查Neo4j数据库中的数据以验证存储结果")


if __name__ == "__main__":
    main()