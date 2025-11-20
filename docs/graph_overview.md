# 广西洪涝灾害知识图谱总体说明

本说明文档概述当前知识图谱中的**节点类型、属性字段、关系类型**以及它们在图中的组织方式，便于后续建模扩展与查询设计。

---

## 一、节点类型与核心属性

知识图谱中主要包含以下几类节点（对应 `template.json` 中的“基础实体”和“状态实体”）：

### 1. 基础实体节点

基础实体是相对稳定的“骨架”，描述事件、地点、设施等对象本身，不带具体时段的状态。所有基础实体节点都会使用“`entity`”通用标签，并叠加其中文类型标签（例如 `(:事件:entity)`、`(:地点:entity)`），这一点来自 `skg_store._create_base_entity` 中的 `MERGE (e:{entity_type}:entity {...})` 语句。

#### 1.1 事件节点 (`事件`)
- **示例含义**：台风、强降雨过程、特大洪水等，具有明确时间段和空间范围的灾害事件。
- **Neo4j标签**：`(:事件:entity)`（固定 `entity` 通用标签 + 中文类型标签 `事件`）
- **写入属性（来自 `_create_base_entity`）**：
  - `id`：唯一ID，例如 `E-450000-20231001-TYPHOON`
  - `name`：事件名称，例如 `2023年10月广西台风事件`
  - `geo_description`：事件影响的主要区域文字描述（由 JSON 的“地理描述”映射而来）
  - `source`：文档来源，可为空
  - 其他属性：后续处理器可能追加分析属性（如 `event_locations`）

#### 1.2 地点节点 (`地点`)
- **示例含义**：行政区域（省、市、县、镇、村）、自然地理实体（河流、湖泊、流域等）。
- **Neo4j标签**：`(:地点:entity)`；对于河流等自然实体，仍以 `地点` 作为类型标签
- **写入属性**：
  - `id`：唯一ID
    - 行政区：`L-<行政区划码>[>子区域]`，如 `L-450100`、`L-450103>新竹街道`
    - 河流：`L-RIVER-<名称>[>区段]`，如 `L-RIVER-长江>荆江河段`
  - `name`：标准化名称，如 `南宁市`、`长江>荆江河段`
  - `geo_description`：文本中的地理描述
  - `source`：文档来源
  - `admin_level`：行政层级（`province/city/county/town/village`）
  - `has_spatial_hierarchy`：是否参与行政层级关系（布尔）
  - `parent_location_id`：上级行政单元ID（若有）

#### 1.3 设施节点 (`设施`)
- **示例含义**：具有专有名称的人造结构或场所，如水库、大坝、水文站、道路、学校等。
- **Neo4j标签**：`(:设施:entity)`
- **写入属性**：
  - `id`：`F-<行政区划码>-<设施名称>`，如 `F-420500-三峡大坝`
  - `name`：设施名称
  - `geo_description`：文本中的位置描述
  - `source`：文档来源
  - 处理器追加属性：`admin_location_id`（所属行政区）、`facility_type` 等

> 说明：基础实体节点一般不直接存储“受灾人口”“经济损失”等时变信息，这类信息放在状态实体节点中，以便刻画时间演化过程。

---

### 2. 状态实体节点与属性节点

状态实体是挂接在基础实体上的“快照”，描述在**特定时间范围**内，该实体或实体组合的灾情、影响或响应状态。

在图结构中，状态本身与其属性是拆开的：
- **状态实体节点**（Neo4j标签 `(:State)`）承载时间、类型、关联对象等“元信息”，核心字段包括 `type`、`time`、`start_time`、`end_time`、`entity_ids`、`source`、`geo`（可选）。
- **属性节点**（标签 `Attribute`）只存储一个数值字段 `value`（以及 `id` 作为唯一标识），每个状态属性值对应一个节点，
- `hasAttribute` 关系把状态节点与属性节点连接起来，并在关系属性 `type` 上记录“属性名称”（例如“降雨量”“受灾人口”）。

状态节点按作用对象分为四类：事件状态 (`ES`)，地点状态 (`LS`)，设施状态 (`FS`)，联合状态 (`JS`)。

#### 2.1 事件状态节点 (`ES-*`)
- **示例含义**：某次台风在特定时间段内的演化状态，如登陆、移出等阶段。
- **Neo4j标签**：`(:State)`（所有 ES/LS/FS/JS 共用）
- **ID 规则**：
  - `ES-E-<事件ID>-<开始日期YYYYMMDD>_<结束日期YYYYMMDD>`
  - 例如：`ES-E-450000-20231001-TYPHOON-20231001_20231010`
- **主要属性（存储在状态节点上）**：
  - `状态ID`：如上所示
  - `时间`：`YYYY-MM-DD至YYYY-MM-DD`
  - `类型`：`独立状态`
  - `state_type`：`event`
  - `associated_events` / `event_ids`：关联事件ID
  - 其他元信息：如抽取来源、置信度等（视实现而定）

与之相连的**属性节点**示例：
- 节点标签：`(:Attribute)`
- 节点属性：
  - `id`: `ES-E-450000-20231001-TYPHOON-20231001_20231010-台风`
  - `value`: `"台风"`
- 关系：
  - `(:State {id:"ES-E-450000-20231001-TYPHOON-20231001_20231010"})-[:hasAttribute {type:"事件类型"}]->(:Attribute {id:"...", value:"台风"})`

#### 2.2 地点状态节点 (`LS-*`)
- **示例含义**：某个行政区或自然实体在某时段的降雨、水位、受灾情况等。
- **Neo4j标签**：`(:State)`
- **ID 规则**：
  - `LS-L-<地点ID>-<开始日期>_<结束日期>`
  - 例如：`LS-L-450100-20231001_20231001`（南宁市当日降雨）
- **主要属性（存储在状态节点上）**：
  - `状态ID`，`时间`，`类型`（独立/联合）
  - `state_type`：`location`
  - `associated_locations` / `location_ids`
  - `is_location_state`：布尔
  - `spatial_coverage`：涉及地点数量

与之相连的**属性节点**示例：
- `(:Attribute {id:"LS-L-450100-20231001_20231001-200mm", value:"200mm"})`
- `(:Attribute {id:"LS-L-450326-20231001_20231001-上涨0.5米", value:"上涨0.5米"})`
- `(:Attribute {id:"JS-L-450100-L-450500-20231001_20231010-52.88万人", value:"52.88万人"})`

每个属性值对应一个属性节点，并通过 `hasAttribute` 连接，关系属性 `type` 记录属性名称，例如：
- `(:State {id:"LS-L-450100-20231001_20231001"})-[:hasAttribute {type:"降雨量"}]->(:Attribute {value:"200mm"})`

#### 2.3 设施状态节点 (`FS-*`)
- **示例含义**：水库泄洪、水文站监测值、堤防损毁程度等设施在某时段的状态。
- **Neo4j标签**：`(:State)`
- **ID 规则**：
  - `FS-F-<设施ID>-<开始日期>_<结束日期>`
  - 例如：`FS-F-420500-三峡大坝-20231003_20231003`
- **主要属性（存储在状态节点上）**：
  - `状态ID`，`时间`
  - `state_type`：`facility`
  - `associated_facilities` / `facility_ids`
  - `is_facility_state`：布尔

典型属性节点：
- `(:Attribute {id:"FS-F-420500-三峡大坝-20231003_20231003-泄洪", value:"泄洪"})`
- `(:Attribute {id:"FS-F-420500-三峡大坝-20231003_20231003-5000", value:5000})`
对应关系示例：`(:State {id:"FS-F-420500-三峡大坝-20231003_20231003"})-[:hasAttribute {type:"泄洪流量_m3_s"}]->(:Attribute {value:5000})`

#### 2.4 联合状态节点 (`JS-*`)
- **Neo4j标签**：`(:State)`
- **示例含义**：
  - 多个城市的统计汇总，如“南宁、北海两市总受灾人口52.88万人，直接经济损失3.90亿元”；
  - 多条河流、多个设施等不可拆分的整体描述。
- **ID 规则**：
  - `JS-<关联实体ID1>-<关联实体ID2>-...-<开始日期>_<结束日期>`
  - 例如：`JS-L-450100-L-450500-20231001_20231010`
- **主要属性（存储在状态节点上）**：
  - `类型`：`联合状态`
  - `关联实体ID列表`：如 `["L-450100","L-450500"]`
  - `state_type`：`joint`
  - `is_joint_state`：布尔
  - `spatial_coverage`：参与实体数量

对应的属性节点：
- `(:Attribute {id:"JS-L-450100-L-450500-20231001_20231010-52.88万人", value:"52.88万人"})`
- `(:Attribute {id:"JS-L-450100-L-450500-20231001_20231010-3.90亿元", value:"3.90亿元"})`

> 说明：在抽取阶段，`状态描述` 以扁平字典形式出现在 JSON 中；在入图库阶段，这些键值对被拆分为 `(State)-[:hasAttribute {type:属性名}]->(Attribute {value:属性值})` 的结构，属性名称保留在关系上，属性值保留在节点上，符合 `skg_store.py` 的实际实现。

#### 2.5 状态链关系（`hasState`/`nextState`/`contain`）
- **创建位置**：`skg_store._handle_entity_state_chain`、`_insert_state_in_chain`
- **用途**：保持同一实体的时间序列
  - `(:entity)-[:hasState]->(:State)`：基础实体到其首个状态节点
  - `(:State)-[:nextState]->(:State)`：同一实体在时间轴上的后继状态，关系属性 `entity` 记录覆盖的实体ID数组
  - `(:State)-[:contain]->(:State)`：表示一个状态的时间范围完全包含另一个状态（父→子）
- **说明**：这些链式关系仅服务于状态排序与嵌套分析，不与 `hasRelation`（灾害因果）混淆。

---

## 二、关系类型与含义

图谱中关系大致分为两类：**空间/结构关系**（连接基础实体）与**状态关系**（连接状态实体）。

### 1. 空间与结构类关系

这类关系由空间处理器与DB框架协同生成，刻画“在哪里”和“属于谁”。

#### 1.1 `:locatedIn`
- **创建位置**：`db.py` 的 `_create_location_framework` / `_create_facility_framework`
- **主体 → 客体**：
  - `(:地点)` → 上级 `(:地点)`（行政层级 child→parent）
  - `(:设施)` → 所在 `(:地点)`（由设施ID推算）
- **含义**：空间包含 / 行政隶属，例如：
  - `(:地点 {id:"L-450100"})-[:locatedIn]->(:地点 {id:"L-450000"})`
  - `(:设施 {id:"F-450223-鹿寨水文站"})-[:locatedIn]->(:地点 {id:"L-450223"})`

#### 1.2 `:occurredAt`
- **创建位置**：`db.py` 的 `_create_event_framework`
- **主体 → 客体**：事件节点 `(:事件)` → 地点节点 `(:地点)`
- **含义**：事件发生或影响到的行政区 / 自然区：
  - `(:事件 {id:"E-450000-20231001-TYPHOON"})-[:occurredAt]->(:地点 {id:"L-450500"})`

> 实际图数据库中的关系名具体大小写取决于 `db.py` 中的建模实现，这里统一用语义名表示。

---

### 2. 状态关系（灾害演化因果链）

状态关系由 `skg_store._create_state_relation` 创建，真实的图结构是 `(:State)-[:hasRelation]->(:State)`，关系标签固定为 `hasRelation`，中文关系类型写在关系属性 `type` 上，并附带 `basis`（依据原文）与 `source`（文档来源）。

所有状态关系**只在状态节点之间建立**，不会直接连到基础实体节点。

常见的 `type` 取值：

#### `type = "导致"`
- **主体**：原因状态节点（常为事件状态或上游地点状态）
- **客体**：结果状态节点（常为地点或设施状态）
- **含义**：强因果，A 是 B 的直接必要原因。
- **示例**：
  - `(:State {id:"ES-E-450000-20231001-TYPHOON-20231001_20231010"})`
    `-[:hasRelation {type:"导致", basis:"…"}]->`
    `(:State {id:"JS-L-450100-L-450500-20231001_20231010"})`

#### `type = "间接导致"`
- **主体**：间接影响因素状态，如基础设施状况、长周期背景条件等。
- **客体**：结果状态
- **含义**：对结果状态具有加重、减缓或调制作用，但不是唯一直接原因。

#### `type = "隐含导致"`
- **主体**：隐含为原因的状态
- **客体**：隐含为结果的状态
- **含义**：文本中没有明确“导致/引发”等词，但通过段落结构、临近性可以确定的强因果关系。

#### `type = "触发"`
- **主体**：阈值型条件状态，如水位达到某级别、降雨超过某阈值等。
- **客体**：程序性行动状态，如发布预警、启动应急响应、组织转移等。
- **含义**：A 作为触发条件或信号，启动了 B。

> 除上述 `type` 取值外，如果模板新增其他关系，同样会写在 `hasRelation` 的 `type` 属性中；关系标签保持不变，便于统一索引和遍历。

---

## 三、组织方式与整体结构

从整体上看，知识图谱遵循“**基础实体 → 状态实体 → 状态关系**”的三层结构：

1. **基础实体层（静态骨架）**
   - 事件、地点、设施节点构成图的主干静态结构。
  - 行政区之间通过 `locatedIn` 形成层次树（省-市-县-乡镇-村）。
  - 设施通过 `locatedIn` 挂接到对应的行政区节点。

2. **状态实体层（动态快照）**
   - 各类状态节点通过属性 `关联实体ID列表` 与基础实体逻辑关联。
   - 在图中，每个状态节点会“靠近”其对应的实体：
     - 事件状态与对应事件节点关联
     - 地点状态与地点节点关联
     - 设施状态与设施节点关联
     - 联合状态与多个基础实体关联
   - 这层刻画在**具体时间段**内局部灾情、降雨、水位、损毁等信息。

3. **状态关系层（演化链条）**
   - 所有因果关系、触发关系都在状态节点之间建立边：
     - `导致`：形成灾害演化主干链（如“事件状态 → 河流超警状态 → 区县受灾状态”）。
     - `间接导致`：刻画环境和基础设施对灾情的调制作用。
     - `隐含导致`：补充文本结构中隐含但逻辑清晰的因果链接。
     - `触发`：串联自然灾情与应急行动（预警、转移等）。
   - 这层结构把分散的状态快照串成一条条“时间有向链”，支持对灾害过程的追溯与推演。

---

## 四、典型查询视角（简要示例）

结合上述节点与关系设计，可以方便地支持多种分析视角，例如：

- **按事件看影响**：给定某个台风事件节点，沿着其事件状态节点出发，经 `导致` / `隐含导致` 关系，找到受影响的地点状态、设施状态及其时间序列。
- **按地点看历次灾情**：从某个行政区的地点节点出发，检索关联的所有地点状态节点，按时间聚合降雨、水位、受灾和经济损失情况。
- **按设施评估风险**：从某个关键设施节点出发，查看历史上的设施状态（如泄洪、水毁），并沿状态关系链条追踪其对下游地点状态产生的影响。

---

## 五、Few-shot：自然语言到 Cypher 的范例

> 目标：给 AI 助手提供“意图 → 图结构 → Cypher” 的参考模板，使其在生成查询时严格遵守本图谱的节点标签、关系名称与属性字段。

**通用策略（在所有示例中遵循）**
- 明确入口节点：`(:事件)`、`(:地点)`、`(:设施)` 等都可通过 `hasState` 找到状态链的起点。
- 沿 `[:nextState*0..]` 展开同一实体的全部状态，再按 `state_type`、`time` 等条件过滤。
- 使用 `[:hasRelation {type:"…"}]` 表达因果/触发逻辑；使用 `[:hasAttribute {type:"…"}]` 提取具体指标值。
- 若需上级区域统计，借助 `(:地点)-[:locatedIn*]->(:地点)` 联通行政层级；事件覆盖范围使用 `:occurredAt`。
- 当用户只提供模糊地名/指标时，优先使用 `toLower(name) CONTAINS toLower($keyword)`、`STARTS WITH`、`ANY(id IN ls.entity_ids WHERE ...)`、正则或区划码前缀等方式宽松过滤，保证召回后再在结果端做精排。

### 示例1：事件导致的地点受灾及人口统计
**用户意图**：列出 ID 为 `E-450000-20231001-TYPHOON` 的事件造成的所有地点状态，并读取“总受灾人口”。

**解析要点**
- 入口：事件节点 → `hasState` → 事件状态链。
- 因果：`hasRelation {type:"导致"}` → 地点状态。
- 指标：地点状态的 `hasAttribute {type:"总受灾人口"}`。

**Cypher 示例**
```cypher
MATCH (e:事件 {id: $eventId})-[:hasState]->(es0:State)
OPTIONAL MATCH (es0)-[:nextState*0..]->(es:State)
WITH DISTINCT es
MATCH (es)-[:hasRelation {type: "导致"}]->(ls:State {state_type: "location"})
OPTIONAL MATCH (ls)-[:hasAttribute {type: "总受灾人口"}]->(pop:Attribute)
RETURN ls.id AS location_state_id,
       ls.entity_ids AS affected_locations,
       pop.value AS total_affected_population,
       ls.time AS period
ORDER BY ls.start_time
```

**提示**：若仅需特定城市，可在 `ls.entity_ids` 中查找 `L-xxxxxx` 并结合 `WHERE ANY(...)` 过滤。

### 示例2：查询指定日期的地方状态与全部属性
**用户意图**：获取 “南宁市” 在 `2023-10-01` 的所有地点状态（降雨量、水位等）。

**解析要点**
- 入口：地点节点 → `hasState` + `nextState` 链。
- 过滤：`state_type = "location"` 且 `time` 字符串包含目标日期。
- 属性：遍历所有 `hasAttribute` 关系并返回 `type/value`。

**Cypher 示例**
```cypher
MATCH (city:地点 {name: $cityName})-[:hasState]->(ls0:State)
OPTIONAL MATCH (ls0)-[:nextState*0..]->(ls:State)
WHERE ls.state_type = "location" AND ls.time CONTAINS $targetDate
MATCH (ls)-[ha:hasAttribute]->(attr:Attribute)
RETURN ls.id AS state_id,
       ls.time AS period,
       ha.type AS metric_name,
       attr.value AS metric_value
ORDER BY ls.id, metric_name
```

**提示**：如果需要携带行政层级，可追加 `MATCH (loc:地点) WHERE loc.id IN ls.entity_ids RETURN loc.name` 以展开行政名称。

### 示例3：设施状态对下游地点的影响链
**用户意图**：查询“三峡大坝”在任意时间的泄洪状态及其导致的下游地点水位响应。

**解析要点**
- 入口：设施节点 → `hasState` → 设施状态；限定 `state_type = "facility"`。
- 属性：设施状态读取 `泄洪流量_m3_s`。
- 因果：设施状态通过 `hasRelation {type:"导致"}` 指向地点状态，再取地点状态的属性（如 `水位变化`）。

**Cypher 示例**
```cypher
MATCH (f:设施 {name: $facilityName})-[:hasState]->(fs0:State)
OPTIONAL MATCH (fs0)-[:nextState*0..]->(fs:State)
WHERE fs.state_type = "facility"
OPTIONAL MATCH (fs)-[:hasAttribute {type: "泄洪流量_m3_s"}]->(flow:Attribute)
MATCH (fs)-[:hasRelation {type: "导致"}]->(down:State {state_type: "location"})
MATCH (down)-[ha:hasAttribute]->(attr:Attribute)
RETURN fs.id        AS facility_state_id,
       flow.value   AS discharge_m3s,
       down.id      AS downstream_state_id,
       ha.type      AS downstream_metric,
       attr.value   AS metric_value,
       down.time    AS downstream_period
ORDER BY fs.start_time, down.start_time
```

**提示**：若只关心特定河段，可在 `down.entity_ids` 中筛选 `L-RIVER-*` ID；若要限制时间窗口，可对 `fs.start_time` / `down.start_time` 追加 `WHERE`。

> 建议在生产环境中将 `$eventId`、`$cityName`、`$targetDate`、`$facilityName` 等占位符交由调用层填充，以便重用上述查询模板。

### 示例4：模糊地名 + 指标关键词的宽松检索
**用户意图**：用户只记得“地名里有‘桂’字，并且指标提到‘经济’”，希望召回所有可能的地点状态及其相关属性。

**解析要点**
- 入口：在 `(:地点)` 上做模糊匹配（`name CONTAINS` 或 `id STARTS WITH`），允许同时提供地名关键词与行政区划前缀。
- 状态链：获取匹配地点的全部 `state_type = "location"` 状态。
- 指标过滤：只保留 `hasAttribute` 的 `type` 含“经济”二字的属性；若关键字为空则返回全部属性。

**Cypher 示例**
```cypher
WITH toLower($locKeyword) AS kw, toLower($metricKeyword) AS mk
MATCH (loc:地点)
WHERE (kw IS NULL OR kw = "" OR toLower(loc.name) CONTAINS kw)
  AND ($adminPrefix IS NULL OR loc.id STARTS WITH $adminPrefix)
MATCH (loc)-[:hasState]->(ls0:State)
OPTIONAL MATCH (ls0)-[:nextState*0..]->(ls:State)
WHERE ls.state_type = "location"
  AND ($date IS NULL OR ls.time CONTAINS $date)
OPTIONAL MATCH (ls)-[ha:hasAttribute]->(attr:Attribute)
WHERE mk IS NULL OR mk = "" OR toLower(ha.type) CONTAINS mk
WITH loc, ls,
     collect({metric: ha.type, value: attr.value}) AS metrics
RETURN loc.name        AS location_name,
       loc.id          AS location_id,
       ls.id           AS state_id,
       ls.time         AS period,
       ls.entity_ids   AS entity_scope,
       metrics         AS fuzzy_metrics
ORDER BY loc.name, ls.start_time
```

**提示**：
- 如果希望放宽属性过滤，可把 `WHERE mk …` 改成 `WITH ... WHERE` 并允许 `mk` 为空数组后在结果侧筛选。
- 对超大图可先对地点执行 `USING INDEX loc:地点(name)`（若已建索引）或在调用层限制 `adminPrefix`，以免扫描全部节点。

