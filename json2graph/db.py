"""数据库连接模块

提供Neo4j数据库连接和基础操作功能。
"""

from neo4j import GraphDatabase
from typing import Optional, Dict, Any
import logging


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
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()