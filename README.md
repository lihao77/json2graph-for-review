# json2graph - 动态JSON到图数据库转换框架

## 项目简介

**json2graph** 是一个支持动态处理器插拔的JSON到图数据库转换框架，专门用于构建时空知识图谱。该框架采用模块化架构设计，支持多层次空间数据处理、智能地理编码和灵活的处理器架构。

## 核心功能

- **动态处理器架构**：支持在数据插入阶段动态插拔处理器
- **多尺度空间数据处理**：集成行政区划和河流的多层级geojson数据
- **智能地理编码**：优先使用本地geojson数据，API调用兜底
- **时空知识图谱构建**：支持基础实体、状态实体和状态关系的存储
- **处理器协作机制**：通过上下文传递实现处理器间数据共享

## 主要特性

### 🏗️ 架构特性
- **IGraphStore接口**：统一的图存储操作规范
- **IProcessor接口**：动态处理器插拔机制
- **Neo4jConnection**：Neo4j数据库连接管理器，支持空间索引
- **SKGStore/STKGStore**：基础和增强版时空知识图谱存储

### 🌍 空间数据处理
- **行政区划匹配**：省、市、县三级geojson数据智能匹配
- **河流数据处理**：省级、市级、县级三级尺度河流段匹配
- **地理编码兜底**：高德地图、百度地图API支持，本地缓存机制
- **WKT空间格式**：支持WKT格式的空间数据存储

### 🔧 处理器功能
- **结构化操作指令**：通过`ProcessorResult`返回图操作指令
- **属性操作**：批量添加节点属性
- **标签操作**：动态添加节点标签
- **自定义查询**：支持Cypher查询执行
- **上下文传递**：处理器间数据共享和协作

## 安装步骤

### 基础安装
```bash
# 克隆项目
git clone https://github.com/yourusername/json2graph.git
cd json2graph

# 安装核心依赖
pip install -r requirements.txt

# 安装包（开发模式）
pip install -e .
```

### 开发环境安装
```bash
# 安装开发依赖
pip install -e .[dev]

# 安装文档依赖（可选）
pip install -e .[docs]
```

### 依赖要求
- **核心依赖**：neo4j>=5.0.0, requests>=2.25.0, numpy>=1.20.0, pandas>=1.3.0
- **可选依赖**：pyyaml>=5.4.0
- **地理编码**：需要高德地图或百度地图API密钥

## 基本使用示例

### 1. 基础使用
```python
from json2graph.db import Neo4jConnection
from json2graph.store_mode import SKGStore
from json2graph.processor import SpatialProcessor

# 连接数据库
db = Neo4jConnection(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="your_password"
)
db.connect()

# 创建存储实例
store = SKGStore(db)

# 添加空间处理器
spatial_processor = SpatialProcessor(
    api_key="your_amap_key",
    service="amap"
)
store.add_processor(spatial_processor)

# 存储知识图谱数据
data = {
    "基础实体": [
        {
            "类型": "地点",
            "名称": "南宁市",
            "唯一ID": "L-450100",
            "地理描述": "广西壮族自治区首府"
        }
    ],
    "状态实体": [],
    "状态关系": []
}

store.store_knowledge_graph(data)
```

### 2. 自定义处理器
```python
from json2graph.interfaces import IProcessor, EntityType, ProcessorResult

class CustomProcessor(IProcessor):
    def get_name(self) -> str:
        return "custom_processor"

    def get_supported_entity_types(self) -> list:
        return [EntityType.BASE_ENTITY]

    def process(self, entity_type, data, context=None):
        result = ProcessorResult()

        # 添加自定义属性
        result.add_property("custom_tag", "processed")
        result.add_label("CustomEntity")

        # 创建关联节点
        result.create_node(
            node_type="Metadata",
            properties={"source": "custom_processor"},
            relationship_type="HAS_METADATA"
        )

        return result

    def validate_config(self, config):
        return True

# 使用自定义处理器
store.add_processor(CustomProcessor())
```

### 3. 处理器协作
```python
class Processor1(IProcessor):
    def process(self, entity_type, data, context=None):
        result = ProcessorResult()
        result.add_property("step1", "completed")

        # 传递上下文给后续处理器
        result.processor_context = {
            "entity_name": data.get("名称"),
            "step1_completed": True
        }
        return result

class Processor2(IProcessor):
    def process(self, entity_type, data, context=None):
        result = ProcessorResult()

        # 使用前面处理器的数据
        if context and context.get("step1_completed"):
            entity_name = context.get("entity_name")
            result.add_property("step2", f"used_{entity_name}")

        return result
```

## 配置说明

### 地理编码配置
```python
geocoding_config = {
    "amap_key": "高德地图API密钥",
    "baidu_key": "百度地图API密钥",
    "cache_file": "spatial_geocoding_cache.json",
    "default_provider": "amap",
    "timeout": 10,
    "retry_times": 3,
    "request_delay": 0.5,
    "batch_size": 100
}
```

### 空间处理器配置
```python
spatial_config = {
    "admin_geojson_dir": "data/admin_geojson",  # 行政区划数据目录
    "river_geojson_dir": "data/river_geojson",  # 河流数据目录
    "cache_file": "spatial_cache.json",       # 空间数据缓存文件
    "enable_admin_matching": True,            # 启用行政区划匹配
    "enable_river_matching": True,            # 启用河流匹配
    "matching_precision": "high"              # 匹配精度：high/medium/low
}
```

### Neo4j连接配置
```python
neo4j_config = {
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "your_password",
    "max_connection_lifetime": 3600,
    "max_connection_pool_size": 50
}
```

## 数据格式要求

### JSON数据结构
```json
{
  "基础实体": [
    {
      "类型": "事件/地点/设施",
      "名称": "标准化名称",
      "唯一ID": "L-<行政区划码>[>子区域]",
      "地理描述": "地理位置描述文本"
    }
  ],
  "状态实体": [
    {
      "类型": "独立状态/联合状态",
      "关联实体ID列表": ["基础实体ID列表"],
      "状态ID": "S-<实体ID>-<时间>",
      "时间": "YYYY-MM-DD至YYYY-MM-DD",
      "状态描述": { /* 状态属性键值对 */ }
    }
  ],
  "状态关系": [
    {
      "主体状态ID": "源头状态ID",
      "关系": "触发/影响/调控/导致",
      "客体状态ID": "结果状态ID",
      "依据": "原文描述片段"
    }
  ]
}
```

### ID格式规范

#### 行政区划ID格式
- **省级**：`L-450000`（广西壮族自治区）
- **市级**：`L-450100`（南宁市）
- **县级**：`L-450123`（横县）
- **含子区域**：`L-450123>某某乡镇`（自动使用地理编码）

#### 河流ID格式
- **无段描述**：`L-RIVER-贺江`（使用省级数据）
- **河流段描述**：`L-RIVER-武思江>浦北县河段`（精确匹配县级）
- **行政区段描述**：`L-RIVER-长江>荆江河段`（匹配市级）

## 开发指南

### 环境设置
```bash
# 安装开发依赖
pip install -e .[dev]

# 代码格式化
black json2graph/

# 类型检查
mypy json2graph/ --ignore-missing-imports

# 代码风格检查
flake8 json2graph/ --max-line-length=88 --extend-ignore=E203,W503
```

### 测试运行
```bash
# 运行所有测试
pytest tests/

# 运行特定测试文件
pytest tests/test_basic.py

# 带覆盖率报告
pytest tests/ --cov=json2graph --cov-report=html

# 运行空间处理器测试
python test_admin_matching.py
python test_river_matching.py
```

### 数据准备
项目包含以下预置数据：
- **行政区划geojson**：广西省、市、县三级数据
- **河流geojson**：83条河流按省、市、县三级尺度分段存储
- **空间数据缓存**：地理编码结果本地缓存

## API参考概览

### 核心接口

#### IGraphStore
- `add_processor(processor)` - 添加数据处理器
- `remove_processor(name)` - 移除处理器
- `store_base_entities(entities)` - 存储基础实体
- `store_state_entities(states)` - 存储状态实体
- `store_state_relations(relations)` - 存储状态关系
- `store_knowledge_graph(data)` - 存储完整知识图谱

#### IProcessor
- `get_name()` - 获取处理器名称
- `get_supported_entity_types()` - 获取支持的实体类型
- `process(entity_type, data, context)` - 处理数据
- `validate_config(config)` - 验证配置

#### ProcessorResult
- `add_property(key, value)` - 添加属性
- `add_properties(properties)` - 批量添加属性
- `add_label(label)` - 添加标签
- `add_labels(labels)` - 批量添加标签
- `create_node(...)` - 创建关联节点
- `create_relationship(...)` - 创建关系
- `execute_cypher(query, params)` - 执行Cypher查询

### 存储模式

#### SKGStore
基础时空知识图谱存储，支持：
- 基础实体存储
- 状态实体链式结构
- 状态关系存储
- 动态处理器插拔

#### STKGStore
增强版存储，集成：
- 自动地理编码
- 空间处理器
- 多尺度空间数据处理

## 空间数据处理核心逻辑

### 行政区划匹配流程
1. **子区域检测**：ID包含">"符号的跳过geojson，直接地理编码
2. **逐级匹配**：县级（6位代码）→ 市级（前4位+00）→ 省级（前2位+0000）
3. **名称兜底**：精确匹配失败后按名称模糊匹配

### 河流匹配流程
1. **策略选择**：
   - 无段描述 → 直接省级匹配（性能最优）
   - 有段描述 → 县级→市级→省级精度优先匹配
2. **关键词提取**：智能识别"县"、"市"、"区"等行政区标识
3. **精确匹配**：提取的行政区划名称与geojson属性精确比较
4. **模糊兜底**：去除后缀后再次匹配，提高成功率

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交Issue和Pull Request来改进项目。

---

**注意**：使用前需要配置Neo4j数据库连接和地理编码API密钥。详细配置请参考项目文档。