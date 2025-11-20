# json2graph - Flood Disaster Spatio-Temporal Knowledge Graph Construction Framework

## Project Overview

**json2graph** is a Python framework specifically designed for building spatio-temporal knowledge graphs for flood disasters. Based on Neo4j graph database, it supports converting structured JSON data into knowledge graphs with flexible data processing and spatial relationship modeling through a dynamic processor architecture.

## Core Features

- **Spatio-Temporal Knowledge Graph Construction**: Supports storage of base entities (events, locations, facilities), state entities, and state relationships
- **Dynamic Processor Architecture**: Supports dynamically attaching/detaching processors for data enhancement after node insertion
- **Spatial Relationship Processing**: Automatically builds administrative hierarchy relationships and location-facility associations
- **Processor Collaboration Mechanism**: Enables data sharing between processors through context passing

## Key Features

### 🏗️ Architecture Features
- **IGraphStore Interface**: Unified graph storage operation specification
- **IProcessor Interface**: Dynamic processor plug-in mechanism, all processors execute after node insertion
- **Neo4jConnection**: Neo4j database connection manager
- **SKGStore**: Basic spatio-temporal knowledge graph storage implementation
- **STKGStore**: Enhanced storage (integrates spatial and relationship processors)

### 🌍 Spatial Data Processing
- **SpatialProcessor**: Processes spatial attributes and geocoding for location entities
- **SpatialRelationshipProcessor**: Builds hierarchical relationships between locations and location-facility associations
- **Multiple ID Format Support**: Administrative codes, river identifiers, custom sub-regions

### 🔧 Processor Features
- **Structured Operation Instructions**: Returns graph operation instructions via `ProcessorResult`
- **Property Operations**: Batch addition of node properties
- **Label Operations**: Dynamic addition of node labels
- **Node Creation**: Creates new nodes and establishes relationships
- **Relationship Creation**: Creates relationships between existing nodes
- **Custom Queries**: Supports Cypher query execution
- **Context Passing**: Data sharing and collaboration between processors

## Installation

### Basic Installation
```bash
# Clone the repository
git clone https://github.com/lihao77/json2graph.git
cd json2graph

# Install core dependencies
pip install -r requirements.txt

# Install package (development mode)
pip install -e .
```

### Dependencies
- **Core Dependencies**:
  - neo4j>=5.0.0
  - requests>=2.25.0
  - numpy>=1.20.0
  - pandas>=1.3.0
  - pyyaml>=5.4.0
- **Python Version**: >=3.8

## Basic Usage Examples

### 1. Basic Usage (SKGStore)
```python
from json2graph import Neo4jConnection, SKGStore

# Connect to database
db = Neo4jConnection(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="your_password"
)
db.connect()

# Create store instance (without any processors)
store = SKGStore(db)

# Store knowledge graph data
data = {
    "基础实体": [
        {
            "类型": "地点",
            "名称": "南宁市",
            "唯一ID": "L-450100",
            "地理描述": "Capital of Guangxi Zhuang Autonomous Region"
        }
    ],
    "状态实体": [],
    "状态关系": []
}

store.store_knowledge_graph(data)
```

### 2. Using Enhanced Storage (STKGStore)
```python
from json2graph import Neo4jConnection, STKGStore

# Connect to database
db = Neo4jConnection(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="your_password"
)
db.connect()

# Create enhanced store instance (automatically integrates spatial and relationship processors)
store = STKGStore(db)

# Store data with automatic spatial relationship processing
store.store_knowledge_graph(data)
```

### 3. Custom Processor
```python
from json2graph import IProcessor, EntityType, ProcessorResult, SKGStore

class CustomProcessor(IProcessor):
    def get_name(self) -> str:
        return "custom_processor"

    def get_supported_entity_types(self) -> list:
        return [EntityType.BASE_ENTITY]

    def process(self, entity_type, data, context=None):
        result = ProcessorResult()

        # Add custom property
        result.add_property("custom_tag", "processed")
        result.add_label("CustomEntity")

        # Create associated node
        result.create_node(
            node_type="Metadata",
            properties={"source": "custom_processor"},
            relationship_type="HAS_METADATA"
        )

        return result

# Use custom processor
store = SKGStore(db)
store.add_processor(CustomProcessor())
```

### 4. Processor Collaboration Example
```python
class Processor1(IProcessor):
    def get_name(self) -> str:
        return "processor_1"
    
    def get_supported_entity_types(self) -> list:
        return [EntityType.BASE_ENTITY]
    
    def process(self, entity_type, data, context=None):
        result = ProcessorResult()
        result.add_property("step1", "completed")

        # Pass context to subsequent processors
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

        # Use data from previous processor
        if context and context.get("step1_completed"):
            entity_name = context.get("entity_name")
            result.add_property("step2", f"used_{entity_name}")

        return result
```

## Configuration

### Neo4j Connection Configuration
```python
from json2graph import Neo4jConnection

db = Neo4jConnection(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="your_password"
)
db.connect()
```

### Using Different Storage Modes

**SKGStore** - Basic storage, only stores JSON data to graph database:
```python
from json2graph import SKGStore
store = SKGStore(db)
```

**STKGStore** - Enhanced storage, automatically integrates SpatialProcessor and SpatialRelationshipProcessor:
```python
from json2graph import STKGStore
store = STKGStore(db)
# Automatically handles spatial relationships and hierarchical structure
```

## Data Format Requirements

For detailed data format definitions, please refer to [jsonDefinition.md](jsonDefinition.md).

### JSON Data Structure
```json
{
  "基础实体": [
    {
      "类型": "事件/地点/设施",
      "名称": "Standardized name",
      "唯一ID": "Generated unique ID",
      "地理描述": "Geographic description from text"
    }
  ],
  "状态实体": [
    {
      "类型": "独立状态/联合状态",
      "关联实体ID列表": ["One or more base entity IDs"],
      "状态ID": "Unique state identifier",
      "时间": "YYYY-MM-DD to YYYY-MM-DD",
      "状态描述": {
        "flattened_property1": "value1",
        "flattened_property2": "value2"
      }
    }
  ],
  "状态关系": [
    {
      "主体状态ID": "ID of causal state",
      "关系": "导致/间接导致/触发",
      "客体状态ID": "ID of result state",
      "依据": "Key sentence from original text supporting the relationship"
    }
  ]
}
```

### ID Format Specification

#### Event ID Format
- Format: `E-<administrative_code>-<date_YYYYMMDD>-<event_type>`
- Example: `E-450000-20231001-TYPHOON`

#### Location ID Format
- **Administrative Divisions**: `L-<administrative_code>[>sub_area]`
  - Example: `L-450100` (Nanning City), `L-450103>Xinzhu Street`
- **Natural Entities (Rivers, etc.)**: `L-<entity_type>-<name>[>section/tributary]`
  - Example: `L-RIVER-Yangtze>Jingjiang Section`, `L-RIVER-Guijiang>Liangfeng River`

#### Facility ID Format
- Format: `F-<administrative_code>-<facility_name>`
- Example: `F-450223-Luzhai Hydrological Station`

#### State ID Format
- Format: `(ES|LS|FS|JS)-<associated_entity_ID(s)>-<start_date_YYYYMMDD>_<end_date_YYYYMMDD>`
- Example: `FS-F-450223-Luzhai Hydrological Station-20231001_20231003`
- Type Descriptions:
  - ES: Event State
  - LS: Location State
  - FS: Facility State
  - JS: Joint State

## Project Structure

```
json2graph/
├── json2graph/              # Main package directory
│   ├── __init__.py         # Package initialization, exports main interfaces
│   ├── interfaces.py       # Core interface definitions (IProcessor, IGraphStore, etc.)
│   ├── db.py              # Neo4j database connection management
│   ├── exception.py       # Custom exception classes
│   ├── store_mode/        # Storage mode implementations
│   │   ├── skg_store.py   # Basic storage implementation
│   │   └── stkg_store.py  # Enhanced storage implementation
│   ├── processor/         # Processor implementations
│   │   ├── spatial_processor.py              # Spatial data processor
│   │   └── spatial_relationship_processor.py # Spatial relationship processor
│   └── sampleData/        # Sample data
│       └── flood_data.py  # Flood disaster sample data
├── docs/                  # Documentation directory
│   ├── graph_overview.md  # Knowledge graph overview
│   └── spatial_framework.md  # Spatial processing framework documentation
├── jsonDefinition.md      # JSON data format definition
├── requirements.txt       # Dependency list
├── setup.py              # Installation configuration
└── README.md             # Project documentation
```

## API Reference

### Core Interfaces

#### IGraphStore
Graph storage interface, main methods:
- `add_processor(processor)` - Add data processor
- `remove_processor(name)` - Remove processor
- `store_knowledge_graph(data)` - Store complete knowledge graph (including base entities, state entities, state relationships)

#### IProcessor
Processor interface, required methods:
- `get_name()` - Return processor name
- `get_supported_entity_types()` - Return list of supported entity types
- `process(entity_type, data, context)` - Process data and return ProcessorResult

Optional methods:
- `get_required_indexes()` - Return list of required indexes
- `get_spatial_entity_types()` - Return entity types that need spatial indexing

#### ProcessorResult
Processor result class, supported operations:
- `add_property(key, value)` - Add single property
- `add_properties(properties)` - Batch add properties
- `add_label(label)` - Add single label
- `add_labels(labels)` - Batch add labels
- `create_node(node_type, properties, relationship_type, relationship_direction)` - Create new node and establish relationship
- `create_relationship(target_node_id, relationship_type, properties)` - Create relationship with specified node
- `execute_cypher(query, params)` - Execute custom Cypher query

#### EntityType Enumeration
- `BASE_ENTITY` - Base entities (events, locations, facilities)
- `STATE_ENTITY` - State entities
- `STATE_RELATION` - State relationships

### Storage Modes

#### SKGStore
Basic spatio-temporal knowledge graph storage implementation:
- Supports storage of base entities, state entities, and state relationships
- State entities stored in chain structure
- Supports dynamic addition and removal of processors
- All processors execute after node insertion

#### STKGStore  
Enhanced storage implementation, inherits from SKGStore:
- Automatically integrates SpatialProcessor (handles spatial attributes)
- Automatically integrates SpatialRelationshipProcessor (builds spatial relationships)
- Suitable for scenarios requiring spatial relationship modeling

### Built-in Processors

#### SpatialProcessor
Processes spatial attributes of location entities:
- Parses location IDs (administrative codes, rivers, etc.)
- Extracts administrative hierarchy information
- Identifies parent location relationships

#### SpatialRelationshipProcessor  
Builds spatial relationships between locations:
- Builds administrative hierarchy relationships (PARENT_OF)
- Builds location-facility association relationships (LOCATED_IN)

## Documentation

- [jsonDefinition.md](jsonDefinition.md) - Detailed JSON data format definition
- [docs/graph_overview.md](docs/graph_overview.md) - Knowledge graph structure overview
- [docs/spatial_framework.md](docs/spatial_framework.md) - Spatial processing framework documentation

## Sample Data

The project includes flood disaster sample data located in `json2graph/sampleData/flood_data.py`, which can be used for testing and learning.

## License

MIT License - see [LICENSE](LICENSE) file for details

## Contributing

Issues and Pull Requests are welcome to improve the project.

## Author

lihao77

---

**Note**: Neo4j database installation and configuration required before use.

[中文文档](README_zh.md)
