# 空间框架功能文档

## 概述

json2graph的空间框架功能采用**协调式架构**，通过两个互补的组件提供完整的空间关系管理能力：

1. **SpatialRelationshipProcessor**: 实时处理器，在数据插入阶段添加基础空间属性
2. **db.py空间框架**: 批量处理器，负责复杂关系构建、验证和完整性保证

这种架构设计避免了功能重复，同时确保了数据一致性和处理效率。该功能基于Neo4j图数据库，利用Cypher查询语言创建和维护复杂的空间关系网络。

## 核心功能

### 1. 层级化的空间关系 (locatedIn)

自动识别和构建行政区划的层级关系：
- **省级** → **市级** → **区县级** → **乡镇级** → **村级**
- 支持标准行政区划代码（如：450000广西，450100南宁，450103青秀区）
- 支持子区域描述（如：L-450123>某某镇>某某村）

### 2. 事件与地点的关联 (occurredAt)

自动建立事件与相关地理位置的关联：
- 事件实体（E-开头）与地点实体（L-开头）的关联
- 基于状态实体中关联的实体ID自动识别相关地点
- 支持多地点关联（一个事件可能影响多个地点）

### 3. 设施与地点的关联 (locatedIn)

自动创建设施与所属地点的空间关系：
- 设施实体（F-开头）与地点实体的关联
- 基于设施ID中的行政区划代码自动匹配
- 格式：F-<行政区划码>-<设施名称>

## 架构设计

### 协调式架构

空间框架采用**分层协调架构**，明确分离职责：

```
┌─────────────────────────────────────────────────────────────┐
│                    用户接口层                                │
│                build_spatial_framework()                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────┴───────────────────────────────────┐
│                  协调控制层                                │
│  1. 获取处理器添加的空间属性                                │
│  2. 批量创建复杂空间关系                                    │
│  3. 验证关系一致性                                         │
│  4. 清理无效关系                                          │
└─────┬───────────────────────────────┬───────────────────────┘
      │                               │
┌─────┴──────────────────┐  ┌─────────┴────────────────────┐
│  SpatialRelationshipProcessor │  │  db.py空间框架方法            │
│  (实时处理器)              │  │  (批量处理器)                │
├────────────────────────┤  ├──────────────────────────────┤
│ 职责:                    │  │ 职责:                        │
│ • 添加空间属性           │  │ • 批量创建关系               │
│ • 实时处理               │  │ • 复杂图分析                 │
│ • 基础ID解析             │  │ • 数据验证                   │
│ • 不创建关系             │  │ • 完整性保证                 │
└────────────────────────┘  └──────────────────────────────┘
```

### 核心组件职责

#### 1. SpatialRelationshipProcessor - 实时属性处理器

**职责范围**：
- ✅ **添加空间属性**：为实体添加`admin_level`、`parent_location_id`等属性
- ✅ **实时处理**：在实体插入时立即处理，无需等待批量操作
- ✅ **基础分析**：进行简单的ID解析和属性提取
- ❌ **不创建关系**：避免与批量处理器冲突

**代码位置**：`json2graph/processor/spatial_relationship_processor.py`

**处理逻辑**：
```python
def _process_base_entity_relationships(self, data, result):
    # 仅为地点实体添加空间属性，不创建层级关系
    if entity_type == "地点":
        result.add_property("admin_level", admin_level)
        result.add_property("has_spatial_hierarchy", True)
        # 不创建locatedIn关系 - 由db.py框架统一处理
```

#### 2. db.py空间框架 - 批量关系构建器

**职责范围**：
- ✅ **批量关系创建**：统一创建所有空间关系（locatedIn、occurredAt）
- ✅ **复杂图分析**：处理需要全局图信息的关系
- ✅ **数据验证**：验证处理器添加的属性与实际关系的一致性
- ✅ **完整性保证**：确保所有空间关系的完整性和一致性

**代码位置**：`json2graph/db.py`

**协调逻辑**：
```python
def build_spatial_framework(self):
    # 1. 基于处理器添加的属性创建关系
    location_count = session.execute_write(self._create_location_framework)
    # 2. 验证处理器属性与解析结果的一致性
    # 3. 处理需要全局分析的复杂关系
    # 4. 清理无效关系
```

#### 3. SKGStore集成层

**代码位置**：`json2graph/store_mode/skg_store.py`

**作用**：提供统一的用户接口，协调两个处理器的工作

### 核心组件

#### 1. Neo4jConnection扩展

在`json2graph/db.py`中扩展了`Neo4jConnection`类，添加了空间框架构建方法：

- `build_spatial_framework()`: 主入口方法
- `_create_location_framework()`: 创建地点层级关系
- `_create_facility_framework()`: 创建设施空间关系
- `_create_event_framework()`: 创建事件空间关系
- `_get_spatial_info()`: 获取空间框架统计信息

#### 2. SKGStore集成

在`json2graph/store_mode/skg_store.py`中添加了`build_spatial_framework()`方法，提供存储层面的空间框架构建接口。

#### 3. 空间关系处理器

创建了`SpatialRelationshipProcessor`类，用于在数据插入阶段处理空间关系：

- 支持基础实体和状态实体的空间关系处理
- 自动识别实体类型并创建相应的空间关系
- 提供灵活的配置选项

## 使用方法

### 基本使用

```python
from json2graph import Neo4jConnection, SKGStore

# 创建数据库连接
db = Neo4jConnection(uri="bolt://localhost:7687", user="neo4j", password="password")
db.connect()

# 创建存储实例
store = SKGStore(db)

# 存储数据
store.store_knowledge_graph(data)

# 构建空间框架
spatial_info = store.build_spatial_framework()
print(f"空间框架信息: {spatial_info}")
```

### 使用空间关系处理器

```python
from json2graph import SpatialRelationshipProcessor

# 创建空间关系处理器
spatial_processor = SpatialRelationshipProcessor()

# 添加到存储
store.add_processor(spatial_processor)

# 存储数据时会自动处理空间关系
store.store_knowledge_graph(data)
```

### 自定义配置

```python
# 自定义空间关系配置
relationship_config = {
    "spatial_relationships": {
        "locatedIn": ["地点", "设施", "河流"],
        "occurredAt": ["事件"]
    },
    "admin_hierarchy": {
        "province": ["city", "county"],
        "city": ["county", "town"],
        "county": ["town", "village"]
    }
}

spatial_processor = SpatialRelationshipProcessor(relationship_config)
```

## 数据格式要求

### 行政区划ID格式

支持以下行政区划ID格式：

```
L-450000        # 省级（广西壮族自治区）
L-450100        # 市级（南宁市）
L-450103        # 区县级（青秀区）
L-450123>某某镇  # 乡镇级（包含子区域）
L-450123>某某镇>某某村  # 村级（多级子区域）
```

### 设施ID格式

设施ID格式：

```
F-450103-南宁吴圩国际机场  # F-<行政区划码>-<设施名称>
F-450300-桂林两江国际机场
```

### 河流ID格式

河流ID格式：

```
L-RIVER-漓江                    # 无段描述，使用省级数据
L-RIVER-洛清江>中下游          # 有段描述，精确匹配
L-RIVER-武思江>浦北县河段      # 县级河段
L-RIVER-长江>荆江河段          # 市级河段
```

### 事件ID格式

事件ID格式：

```
E-450300-20240615-FLOOD        # E-<行政区划码>-<时间>-<事件类型>
E-450100-20240720-RAIN         # 暴雨事件
E-450000-20240810-TYPHOON      # 台风事件
```

## 空间关系类型

### locatedIn关系

表示实体位于某个地点内：

- **行政区划层级**: 子区域 → 父区域
- **设施与地点**: 设施 → 所属地点
- **河流与行政区划**: 河流 → 流经的行政区划

### occurredAt关系

表示事件发生在某个地点：

- **事件与地点**: 事件 → 发生地点
- 支持多地点关联
- 通过状态实体自动识别相关地点

## 查询示例

### 查询行政区划层级

```cypher
MATCH (child:地点)-[r:locatedIn]->(parent:地点)
WHERE child.id STARTS WITH 'L-' AND parent.id STARTS WITH 'L-'
RETURN child.name, parent.name, child.id, parent.id
```

### 查询事件相关地点

```cypher
MATCH (event)-[r:occurredAt]->(location)
WHERE event.id STARTS WITH 'E-'
RETURN event.name, location.name, event.id, location.id
```

### 查询设施分布

```cypher
MATCH (facility)-[r:locatedIn]->(location)
WHERE facility.id STARTS WITH 'F-'
RETURN facility.name, location.name, facility.id, location.id
```

### 查询空间影响范围

```cypher
MATCH (event)-[:occurredAt]->(location1)
MATCH (location1)-[:locatedIn*]->(location2)
WHERE event.id = 'E-450300-20240615-FLOOD'
RETURN event.name, location1.name, location2.name
```

## 性能优化

### 索引建议

空间框架功能会自动创建以下索引：

```cypher
CREATE INDEX location_id_index FOR (n:地点) ON (n.id)
CREATE INDEX facility_id_index FOR (n:设施) ON (n.id)
CREATE INDEX event_id_index FOR (n:事件) ON (n.id)
CREATE INDEX river_id_index FOR (n:河流) ON (n.id)
```

### 批量处理

空间框架构建采用批量处理方式：

1. 一次性查询所有相关实体
2. 在内存中解析层级关系
3. 批量创建关系，减少数据库交互

### 缓存机制

对于复杂的地理编码和空间匹配，建议使用缓存机制避免重复计算。

## 错误处理

### 常见错误

1. **ID格式错误**: 如果实体ID格式不符合规范，空间关系可能无法正确创建
2. **实体不存在**: 如果关联的实体不存在，关系创建会失败
3. **循环引用**: 避免出现A-locatedIn-B且B-locatedIn-A的循环引用

### 调试建议

1. 启用详细日志记录
2. 分批测试数据，逐步验证空间关系
3. 使用Neo4j Browser可视化验证关系

## 扩展功能

### 自定义关系类型

可以通过扩展`SpatialRelationshipProcessor`来支持自定义关系类型：

```python
class CustomSpatialProcessor(SpatialRelationshipProcessor):
    def __init__(self, config):
        super().__init__(config)
        self.spatial_relationships['affects'] = ['事件', '设施']
```

### 空间索引集成

可以与Neo4j Spatial插件集成，支持地理空间查询：

```python
# 检查空间支持
if db_connection.check_spatial_support():
    # 创建空间索引
    db_connection.create_spatial_layer("admin_boundaries")
    db_connection.create_spatial_layer("rivers")
```

### 多模态空间数据

支持处理包含空间坐标的实体：

```json
{
    "类型": "地点",
    "名称": "测试地点",
    "唯一ID": "L-TEST-001",
    "地理描述": "测试描述",
    "空间坐标": {
        "经度": 108.3,
        "纬度": 22.8,
        "坐标系": "WGS84"
    }
}
```

## 最佳实践

### 1. 数据预处理

在存储数据前，确保：
- 实体ID格式正确
- 行政区划代码有效
- 空间描述信息完整

### 2. 分批处理

对于大量数据，建议分批处理：
- 先存储基础实体
- 构建空间框架
- 验证关系正确性
- 再处理后续批次

### 3. 验证和测试

定期验证空间关系的完整性：
- 检查孤立节点
- 验证层级关系的一致性
- 测试空间查询的性能

### 4. 监控和日志

启用详细的日志记录：
- 监控空间框架构建过程
- 记录关系创建的成功率和失败原因
- 跟踪性能指标

## 总结

json2graph的空间框架功能提供了强大而灵活的空间关系管理能力，支持：

1. **自动化的空间关系构建**: 基于实体ID和类型自动创建空间关系
2. **层级化的行政区划管理**: 支持多级行政区划的层级关系
3. **事件与地点的时空关联**: 自动建立事件与相关地点的关联
4. **灵活的扩展机制**: 支持自定义关系类型和处理逻辑
5. **高性能的批量处理**: 优化的算法和索引策略

这些功能使得json2graph特别适合构建时空知识图谱，为地理空间分析、事件追踪和设施管理提供了强大的基础支撑。