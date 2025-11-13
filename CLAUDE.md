# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**json2graph** - 支持动态处理器插拔的JSON到图数据库转换框架，专门用于构建时空知识图谱。核心特性包括多层次空间数据处理、智能地理编码和灵活的处理器架构。

## 架构设计

### 核心接口与组件

- **IGraphStore**: 图存储接口，定义存储操作规范和索引管理
- **IProcessor**: 处理器接口，支持数据插入阶段的动态处理，返回结构化的图操作指令
- **Neo4jConnection**: Neo4j数据库连接管理器，支持空间索引和图层管理
- **SKGStore**: 基础时空知识图谱存储实现
- **STKGStore**: 增强版存储，集成自动地理编码和空间处理器

### 处理器架构

处理器通过`ProcessorResult`返回结构化的图操作指令，支持：
- 属性操作：`ADD_PROPERTY` - 批量添加节点属性
- 标签操作：`ADD_LABEL` - 添加节点标签
- 自定义查询：`EXECUTE_CYPHER` - 执行Cypher查询
- 处理器间通信：通过`processor_context`传递上下文数据

### 空间数据处理架构

#### SpatialProcessor（空间处理器）
空间处理器是系统的核心组件，实现了复杂的空间数据匹配逻辑：

##### 行政区划处理
- **层级存储**：按省、市、县三级分别存储geojson数据
- **智能匹配**：从县级开始逐级向上匹配，确保精度优先
- **子区域检测**：包含子区域（">"符号）的ID自动使用地理编码API

##### 河流数据处理
- **多尺度存储**：省级（83条）、市级（123段）、县级（252段）三级尺度
- **智能匹配策略**：
  - 无段描述：直接使用省级数据（性能最优）
  - 有段描述：优先县级精确匹配，其次市级，最后省级兜底
- **段描述解析**：智能识别"浦北县河段"、"荆江河段"等不同格式，提取行政区划关键词进行精确匹配

##### 地理编码兜底
- **缓存机制**：地理编码结果本地缓存，避免重复API调用
- **多服务商支持**：高德地图、百度地图API支持
- **错误重试**：可配置的重试次数和超时设置

## 关键文件结构

```
json2graph/
├── __init__.py          # 主导出和版本信息
├── interfaces.py        # 核心接口定义（IProcessor, IGraphStore, ProcessorResult）
├── db.py               # Neo4j连接管理和空间索引操作
├── exception.py        # 自定义异常类
├── store_mode/
│   ├── __init__.py     # 存储模式导出
│   ├── skg_store.py    # 基础SKG实现
│   └── stkg_store.py   # 增强STKG实现
├── processor/
│   ├── __init__.py     # 处理器导出
│   └── spatial_processor.py  # 空间处理器（核心复杂逻辑）
└── data/
    ├── admin_geojson/   # 行政区划geojson数据（省、市、县三级）
    └── river_geojson/  # 河流geojson数据（省、市、县三级尺度）
```

## 开发命令

### 环境设置
```bash
# 安装核心依赖
pip install -r requirements.txt

# 安装包（开发模式）
pip install -e .

# 安装开发依赖（测试、代码质量工具）
pip install -e .[dev]
```

### 测试运行
```bash
# 运行所有测试
pytest tests/

# 运行特定测试文件
pytest tests/test_basic.py

# 带覆盖率报告
pytest tests/ --cov=json2graph --cov-report=html

# 运行单个测试类
pytest tests/test_basic.py::TestSKGStore
```

### 代码质量与格式化
```bash
# 代码格式化（遵循PEP8）
black json2graph/

# 类型检查
mypy json2graph/ --ignore-missing-imports

# 代码风格检查
flake8 json2graph/ --max-line-length=88 --extend-ignore=E203,W503
```

### 空间处理器测试
```bash
# 测试行政区划匹配逻辑
python test_admin_matching.py

# 测试河流段匹配逻辑
python test_river_matching.py

# 测试河流段精确匹配
python test_river_segment_matching.py
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

### 多尺度数据利用
- **行政区划**：1个省级feature + 14个市级features + 111个县级features
- **河流数据**：83条河流，分别按省（83段）、市（123段）、县（252段）存储
- **智能回退**：细粒度失败时自动使用粗粒度数据

### 空间框架功能

#### 架构设计
空间框架采用**协调式架构**，明确分离职责：

1. **SpatialRelationshipProcessor**: 实时处理器，负责添加基础空间属性
2. **db.py空间框架**: 批量处理器，负责复杂关系构建和验证

#### SpatialRelationshipProcessor职责
- **添加空间属性**: 为实体添加`admin_level`、`parent_location_id`等属性
- **实时处理**: 在实体插入时立即处理，无需等待批量操作
- **基础分析**: 进行简单的ID解析和属性提取
- **不创建关系**: 避免与批量处理器冲突
- **支持所有状态类型**: 完整支持LS-(地点状态)、FS-(设施状态)、ES-(事件状态)、JS-(联合状态)

#### db.py空间框架职责
- **批量关系创建**: 统一创建所有空间关系（locatedIn、occurredAt）
- **复杂图分析**: 处理需要全局图信息的关系
- **数据验证**: 验证处理器添加的属性与实际关系的一致性
- **完整性保证**: 确保所有空间关系的完整性和一致性

#### 空间框架构建
```python
# 构建空间框架（自动协调处理器和批量处理）
spatial_info = store.build_spatial_framework()
# 返回: {
#   "location_hierarchies": 12,
#   "event_locations": 5,
#   "validation_results": {...}
# }
```

#### 使用方式
```python
# 1. 添加空间处理器（添加基础属性）
spatial_processor = SpatialRelationshipProcessor()
store.add_processor(spatial_processor)

# 2. 存储数据（处理器自动添加空间属性）
store.store_knowledge_graph(data)

# 3. 构建空间框架（批量创建关系和验证）
spatial_info = store.build_spatial_framework()
```

#### ID格式支持
- **行政区划**：`L-450000`（省）、`L-450100`（市）、`L-450103`（县）
- **子区域**：`L-450123>某某镇>某某村`（支持多级）
- **设施**：`F-450103-南宁吴圩国际机场`
- **事件**：`E-450300-20240615-FLOOD`
- **河流**：`L-RIVER-漓江`、`L-RIVER-武思江>浦北县河段`
- **状态实体**：
  - `LS-L-450300-20240615`（地点状态）
  - `FS-F-450103-20240615`（设施状态）
  - `ES-E-450300-20240615`（事件状态）
  - `JS-MULTI-20240615`（联合状态）



## 回答请使用中文