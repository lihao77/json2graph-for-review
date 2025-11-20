# json2graph - 洪涝灾害时空知识图谱构建框架

## 项目简介

**json2graph** 是一个专门用于构建洪涝灾害时空知识图谱的Python框架。该框架基于Neo4j图数据库，支持将结构化JSON数据转换为知识图谱，通过动态处理器架构实现灵活的数据处理和空间关系建模。

## 核心功能

- **时空知识图谱构建**：支持基础实体（事件、地点、设施）、状态实体和状态关系的存储
- **动态处理器架构**：支持在节点插入后动态插拔处理器进行数据增强
- **空间关系处理**：自动构建行政区划层级关系、地点-设施关联关系
- **处理器协作机制**：通过上下文传递实现处理器间数据共享

## 主要特性

### 🏗️ 架构特性
- **IGraphStore接口**：统一的图存储操作规范
- **IProcessor接口**：动态处理器插拔机制，所有处理器在节点插入后执行
- **Neo4jConnection**：Neo4j数据库连接管理器
- **SKGStore**：基础时空知识图谱存储实现
- **STKGStore**：增强版存储（集成空间和关系处理器）

### 🌍 空间数据处理
- **SpatialProcessor**：处理地点实体的空间属性和地理编码
- **SpatialRelationshipProcessor**：构建地点间的层级关系和地点-设施的关联关系
- **支持多种ID格式**：行政区划码、河流标识、自定义子区域

### 🔧 处理器功能
- **结构化操作指令**：通过`ProcessorResult`返回图操作指令
- **属性操作**：批量添加节点属性
- **标签操作**：动态添加节点标签
- **节点创建**：创建新节点并建立关系
- **关系创建**：在已有节点间创建关系
- **自定义查询**：支持执行Cypher查询
- **上下文传递**：处理器间数据共享和协作

## 安装步骤

### 基础安装
```bash
# 克隆项目
git clone https://github.com/lihao77/json2graph.git
cd json2graph

# 安装核心依赖
pip install -r requirements.txt

# 安装包（开发模式）
pip install -e .
```

### 依赖要求
- **核心依赖**：
  - neo4j>=5.0.0
  - requests>=2.25.0
  - numpy>=1.20.0
  - pandas>=1.3.0
  - pyyaml>=5.4.0
- **Python版本**：>=3.8

## 基本使用示例

### 1. 基础使用（SKGStore）
```python
from json2graph import Neo4jConnection, SKGStore

# 连接数据库
db = Neo4jConnection(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="your_password"
)
db.connect()

# 创建存储实例（不带任何处理器）
store = SKGStore(db)

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

### 2. 使用增强版存储（STKGStore）
```python
from json2graph import Neo4jConnection, STKGStore

# 连接数据库
db = Neo4jConnection(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="your_password"
)
db.connect()

# 创建增强版存储实例（自动集成空间和关系处理器）
store = STKGStore(db)

# 存储数据，自动处理空间关系
store.store_knowledge_graph(data)
```

### 3. 自定义处理器
```python
from json2graph import IProcessor, EntityType, ProcessorResult, SKGStore

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

# 使用自定义处理器
store = SKGStore(db)
store.add_processor(CustomProcessor())
```

### 4. 处理器协作示例
```python
class Processor1(IProcessor):
    def get_name(self) -> str:
        return "processor_1"
    
    def get_supported_entity_types(self) -> list:
        return [EntityType.BASE_ENTITY]
    
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
    def get_name(self) -> str:
        return "processor_2"
    
    def get_supported_entity_types(self) -> list:
        return [EntityType.BASE_ENTITY]
    
    def process(self, entity_type, data, context=None):
        result = ProcessorResult()

        # 使用前面处理器的数据
        if context and context.get("step1_completed"):
            entity_name = context.get("entity_name")
            result.add_property("step2", f"used_{entity_name}")

        return result
```

## 配置说明

### Neo4j连接配置
```python
from json2graph import Neo4jConnection

db = Neo4jConnection(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="your_password"
)
db.connect()
```

### 使用不同存储模式

**SKGStore** - 基础存储，只存储JSON数据到图数据库：
```python
from json2graph import SKGStore
store = SKGStore(db)
```

**STKGStore** - 增强版存储，自动集成SpatialProcessor和SpatialRelationshipProcessor：
```python
from json2graph import STKGStore
store = STKGStore(db)
# 自动处理空间关系和层级结构
```

## 数据格式要求

详细的数据格式定义请参考 [jsonDefinition.md](jsonDefinition.md)。

### JSON数据结构
```json
{
  "基础实体": [
    {
      "类型": "事件/地点/设施",
      "名称": "标准化名称",
      "唯一ID": "生成的唯一ID",
      "地理描述": "文本中关于地理位置的描述"
    }
  ],
  "状态实体": [
    {
      "类型": "独立状态/联合状态",
      "关联实体ID列表": ["一个或多个基础实体ID"],
      "状态ID": "唯一状态标识符",
      "时间": "YYYY-MM-DD至YYYY-MM-DD",
      "状态描述": {
        "扁平化属性1": "值1",
        "扁平化属性2": "值2"
      }
    }
  ],
  "状态关系": [
    {
      "主体状态ID": "原因状态的ID",
      "关系": "导致/间接导致/触发",
      "客体状态ID": "结果状态的ID",
      "依据": "原文中支持该关系的关键句"
    }
  ]
}
```

### ID格式规范

#### 事件ID格式
- 格式：`E-<行政区划码>-<日期YYYYMMDD>-<事件类型>`
- 示例：`E-450000-20231001-TYPHOON`

#### 地点ID格式
- **行政区划**：`L-<行政区划码>[>子区域]`
  - 示例：`L-450100`（南宁市）、`L-450103>新竹街道`
- **自然实体（河流等）**：`L-<实体类型>-<名称>[>区段/支流]`
  - 示例：`L-RIVER-长江>荆江段`、`L-RIVER-桂江>良丰河`

#### 设施ID格式
- 格式：`F-<行政区划码>-<设施名称>`
- 示例：`F-450223-鹿寨水文站`

#### 状态ID格式
- 格式：`(ES|LS|FS|JS)-<关联实体ID(s)>-<开始日期YYYYMMDD>_<结束日期YYYYMMDD>`
- 示例：`FS-F-450223-鹿寨水文站-20231001_20231003`
- 类型说明：
  - ES: 事件状态
  - LS: 地点状态
  - FS: 设施状态
  - JS: 联合状态

## 项目结构

```
json2graph/
├── json2graph/              # 主包目录
│   ├── __init__.py         # 包初始化，导出主要接口
│   ├── interfaces.py       # 核心接口定义（IProcessor, IGraphStore等）
│   ├── db.py              # Neo4j数据库连接管理
│   ├── exception.py       # 自定义异常类
│   ├── store_mode/        # 存储模式实现
│   │   ├── skg_store.py   # 基础存储实现
│   │   └── stkg_store.py  # 增强版存储实现
│   ├── processor/         # 处理器实现
│   │   ├── spatial_processor.py              # 空间数据处理器
│   │   └── spatial_relationship_processor.py # 空间关系处理器
│   └── sampleData/        # 示例数据
│       └── flood_data.py  # 洪涝灾害示例数据
├── docs/                  # 文档目录
│   ├── graph_overview.md  # 知识图谱总体说明
│   └── spatial_framework.md  # 空间处理框架说明
├── jsonDefinition.md      # JSON数据格式定义
├── requirements.txt       # 依赖列表
├── setup.py              # 安装配置
└── README.md             # 项目说明
```

## API参考

### 核心接口

#### IGraphStore
图存储接口，主要方法：
- `add_processor(processor)` - 添加数据处理器
- `remove_processor(name)` - 移除处理器
- `store_knowledge_graph(data)` - 存储完整知识图谱（包括基础实体、状态实体、状态关系）

#### IProcessor
处理器接口，必须实现的方法：
- `get_name()` - 返回处理器名称
- `get_supported_entity_types()` - 返回支持的实体类型列表
- `process(entity_type, data, context)` - 处理数据并返回ProcessorResult

可选实现的方法：
- `get_required_indexes()` - 返回处理器需要的索引列表
- `get_spatial_entity_types()` - 返回需要空间索引的实体类型

#### ProcessorResult
处理器结果类，支持的操作：
- `add_property(key, value)` - 添加单个属性
- `add_properties(properties)` - 批量添加属性
- `add_label(label)` - 添加单个标签
- `add_labels(labels)` - 批量添加标签
- `create_node(node_type, properties, relationship_type, relationship_direction)` - 创建新节点并建立关系
- `create_relationship(target_node_id, relationship_type, properties)` - 创建与指定节点的关系
- `execute_cypher(query, params)` - 执行自定义Cypher查询

#### EntityType枚举
- `BASE_ENTITY` - 基础实体（事件、地点、设施）
- `STATE_ENTITY` - 状态实体
- `STATE_RELATION` - 状态关系

### 存储模式

#### SKGStore
基础时空知识图谱存储实现：
- 支持基础实体、状态实体、状态关系的存储
- 状态实体采用链式结构存储
- 支持动态添加和移除处理器
- 所有处理器在节点插入后执行

#### STKGStore  
增强版存储实现，继承自SKGStore：
- 自动集成SpatialProcessor（处理空间属性）
- 自动集成SpatialRelationshipProcessor（构建空间关系）
- 适用于需要空间关系建模的场景

### 内置处理器

#### SpatialProcessor
处理地点实体的空间属性：
- 解析地点ID（行政区划码、河流等）
- 提取行政层级信息
- 识别父级地点关系

#### SpatialRelationshipProcessor  
构建地点间的空间关系：
- 构建行政区划层级关系（PARENT_OF）
- 构建地点-设施关联关系（LOCATED_IN）

## 文档

- [jsonDefinition.md](jsonDefinition.md) - JSON数据格式详细定义
- [docs/graph_overview.md](docs/graph_overview.md) - 知识图谱结构总体说明
- [docs/spatial_framework.md](docs/spatial_framework.md) - 空间处理框架说明

## 示例数据

项目包含洪涝灾害示例数据，位于 `json2graph/sampleData/flood_data.py`，可用于测试和学习。

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交Issue和Pull Request来改进项目。

## 作者

lihao77

---

**注意**：使用前需要安装并配置Neo4j数据库。