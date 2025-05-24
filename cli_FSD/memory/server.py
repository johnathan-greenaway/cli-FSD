"""Memory MCP Server Implementation for cli-FSD.

This server provides a persistent memory system using a knowledge graph structure
to store entities, relationships, and observations across CLI sessions.
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@dataclass
class Observation:
    """A fact or piece of information about an entity."""
    id: str
    content: str
    timestamp: datetime
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert observation to dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence
        }

@dataclass
class Relation:
    """A relationship between two entities."""
    id: str
    from_entity: str
    to_entity: str
    relation_type: str
    properties: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.properties is None:
            self.properties = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert relation to dictionary."""
        return {
            "id": self.id,
            "from": self.from_entity,
            "to": self.to_entity,
            "type": self.relation_type,
            "properties": self.properties,
            "timestamp": self.timestamp.isoformat()
        }

@dataclass
class Entity:
    """An entity in the knowledge graph."""
    name: str
    entity_type: str
    observations: List[Observation] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.observations is None:
            self.observations = []
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def add_observation(self, observation: Observation) -> None:
        """Add an observation to this entity."""
        self.observations.append(observation)
    
    def remove_observation(self, observation_id: str) -> bool:
        """Remove an observation by ID."""
        original_length = len(self.observations)
        self.observations = [o for o in self.observations if o.id != observation_id]
        return len(self.observations) < original_length
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary."""
        return {
            "name": self.name,
            "type": self.entity_type,
            "observations": [o.to_dict() for o in self.observations],
            "created_at": self.created_at.isoformat()
        }

class MemoryGraph:
    """Knowledge graph for storing memories."""
    
    def __init__(self, memory_file: Optional[Path] = None):
        self.memory_file = memory_file or Path.home() / ".cli_fsd" / "memory.json"
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.entities: Dict[str, Entity] = {}
        self.relations: List[Relation] = []
        self._next_id = 1
        
        # Load existing memory if available
        self.load()
    
    def generate_id(self) -> str:
        """Generate a unique ID."""
        id_str = f"mem_{self._next_id}"
        self._next_id += 1
        return id_str
    
    def create_entity(self, name: str, entity_type: str) -> Entity:
        """Create a new entity."""
        entity = Entity(name=name, entity_type=entity_type)
        self.entities[name] = entity
        self.save()
        return entity
    
    def create_entities(self, entities: List[Dict[str, str]]) -> List[Entity]:
        """Create multiple entities."""
        created = []
        for entity_data in entities:
            entity = self.create_entity(
                name=entity_data["name"],
                entity_type=entity_data.get("type", "general")
            )
            created.append(entity)
        return created
    
    def get_entity(self, name: str) -> Optional[Entity]:
        """Get an entity by name."""
        return self.entities.get(name)
    
    def delete_entity(self, name: str) -> bool:
        """Delete an entity and all its relations."""
        if name not in self.entities:
            return False
        
        # Remove all relations involving this entity
        self.relations = [
            r for r in self.relations 
            if r.from_entity != name and r.to_entity != name
        ]
        
        # Remove the entity
        del self.entities[name]
        self.save()
        return True
    
    def create_relation(self, from_entity: str, to_entity: str, 
                       relation_type: str, properties: Optional[Dict[str, Any]] = None) -> Optional[Relation]:
        """Create a relation between two entities."""
        if from_entity not in self.entities or to_entity not in self.entities:
            return None
        
        relation = Relation(
            id=self.generate_id(),
            from_entity=from_entity,
            to_entity=to_entity,
            relation_type=relation_type,
            properties=properties or {}
        )
        self.relations.append(relation)
        self.save()
        return relation
    
    def delete_relation(self, relation_id: str) -> bool:
        """Delete a relation by ID."""
        original_length = len(self.relations)
        self.relations = [r for r in self.relations if r.id != relation_id]
        if len(self.relations) < original_length:
            self.save()
            return True
        return False
    
    def add_observation(self, entity_name: str, content: str, confidence: float = 1.0) -> Optional[Observation]:
        """Add an observation to an entity."""
        entity = self.get_entity(entity_name)
        if not entity:
            return None
        
        observation = Observation(
            id=self.generate_id(),
            content=content,
            timestamp=datetime.now(),
            confidence=confidence
        )
        entity.add_observation(observation)
        self.save()
        return observation
    
    def delete_observation(self, entity_name: str, observation_id: str) -> bool:
        """Delete an observation from an entity."""
        entity = self.get_entity(entity_name)
        if not entity:
            return False
        
        if entity.remove_observation(observation_id):
            self.save()
            return True
        return False
    
    def search_nodes(self, query: str) -> List[Entity]:
        """Search for entities matching a query."""
        query_lower = query.lower()
        results = []
        
        for entity in self.entities.values():
            # Check entity name
            if query_lower in entity.name.lower():
                results.append(entity)
                continue
            
            # Check entity type
            if query_lower in entity.entity_type.lower():
                results.append(entity)
                continue
            
            # Check observations
            for obs in entity.observations:
                if query_lower in obs.content.lower():
                    results.append(entity)
                    break
        
        return results
    
    def get_connected_entities(self, entity_name: str) -> Set[str]:
        """Get all entities connected to a given entity."""
        connected = set()
        for relation in self.relations:
            if relation.from_entity == entity_name:
                connected.add(relation.to_entity)
            elif relation.to_entity == entity_name:
                connected.add(relation.from_entity)
        return connected
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the entire graph to a dictionary."""
        return {
            "entities": {name: entity.to_dict() for name, entity in self.entities.items()},
            "relations": [r.to_dict() for r in self.relations],
            "metadata": {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "entity_count": len(self.entities),
                "relation_count": len(self.relations)
            }
        }
    
    def save(self) -> None:
        """Save the memory graph to disk."""
        data = {
            "entities": {name: entity.to_dict() for name, entity in self.entities.items()},
            "relations": [r.to_dict() for r in self.relations],
            "_next_id": self._next_id
        }
        
        with open(self.memory_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def load(self) -> None:
        """Load the memory graph from disk."""
        if not self.memory_file.exists():
            return
        
        try:
            with open(self.memory_file, 'r') as f:
                data = json.load(f)
            
            # Load entities
            self.entities = {}
            for name, entity_data in data.get("entities", {}).items():
                entity = Entity(
                    name=name,
                    entity_type=entity_data["type"],
                    created_at=datetime.fromisoformat(entity_data["created_at"])
                )
                
                # Load observations
                for obs_data in entity_data.get("observations", []):
                    observation = Observation(
                        id=obs_data["id"],
                        content=obs_data["content"],
                        timestamp=datetime.fromisoformat(obs_data["timestamp"]),
                        confidence=obs_data.get("confidence", 1.0)
                    )
                    entity.observations.append(observation)
                
                self.entities[name] = entity
            
            # Load relations
            self.relations = []
            for rel_data in data.get("relations", []):
                relation = Relation(
                    id=rel_data["id"],
                    from_entity=rel_data["from"],
                    to_entity=rel_data["to"],
                    relation_type=rel_data["type"],
                    properties=rel_data.get("properties", {}),
                    timestamp=datetime.fromisoformat(rel_data["timestamp"])
                )
                self.relations.append(relation)
            
            self._next_id = data.get("_next_id", 1)
            
        except Exception as e:
            print(f"Error loading memory: {e}", file=sys.stderr)


class MemoryMCPServer:
    """MCP Server implementation for Memory functionality."""
    
    def __init__(self, memory_file: Optional[Path] = None):
        self.graph = MemoryGraph(memory_file)
        self.running = False
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP requests."""
        method = request.get("method", "")
        params = request.get("params", {})
        
        # Map method names to handlers
        handlers = {
            "tools/list": self._handle_list_tools,
            "tools/call": self._handle_tool_call,
        }
        
        handler = handlers.get(method)
        if handler:
            return await handler(params)
        
        return {
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }
    
    async def _handle_list_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available tools."""
        return {
            "tools": [
                {
                    "name": "create_entities",
                    "description": "Create one or more entities in the memory graph",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "entities": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "type": {"type": "string"}
                                    },
                                    "required": ["name"]
                                }
                            }
                        },
                        "required": ["entities"]
                    }
                },
                {
                    "name": "create_relations",
                    "description": "Create relationships between entities",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "relations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "from": {"type": "string"},
                                        "to": {"type": "string"},
                                        "type": {"type": "string"},
                                        "properties": {"type": "object"}
                                    },
                                    "required": ["from", "to", "type"]
                                }
                            }
                        },
                        "required": ["relations"]
                    }
                },
                {
                    "name": "add_observations",
                    "description": "Add observations (facts) to entities",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "observations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "entity": {"type": "string"},
                                        "content": {"type": "string"},
                                        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                                    },
                                    "required": ["entity", "content"]
                                }
                            }
                        },
                        "required": ["observations"]
                    }
                },
                {
                    "name": "read_graph",
                    "description": "Read the entire memory graph",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                },
                {
                    "name": "search_nodes",
                    "description": "Search for entities matching a query",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "open_nodes",
                    "description": "Get specific entities by name",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "names": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["names"]
                    }
                },
                {
                    "name": "delete_entities",
                    "description": "Delete entities from the memory graph",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "names": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["names"]
                    }
                },
                {
                    "name": "delete_observations",
                    "description": "Delete specific observations from entities",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "deletions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "entity": {"type": "string"},
                                        "observation_id": {"type": "string"}
                                    },
                                    "required": ["entity", "observation_id"]
                                }
                            }
                        },
                        "required": ["deletions"]
                    }
                },
                {
                    "name": "delete_relations",
                    "description": "Delete specific relations",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "relation_ids": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["relation_ids"]
                    }
                }
            ]
        }
    
    async def _handle_tool_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool calls."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        try:
            if tool_name == "create_entities":
                entities = arguments.get("entities", [])
                created = self.graph.create_entities(entities)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Created {len(created)} entities: {', '.join(e.name for e in created)}"
                        }
                    ]
                }
            
            elif tool_name == "create_relations":
                relations = arguments.get("relations", [])
                created = []
                for rel_data in relations:
                    relation = self.graph.create_relation(
                        from_entity=rel_data["from"],
                        to_entity=rel_data["to"],
                        relation_type=rel_data["type"],
                        properties=rel_data.get("properties")
                    )
                    if relation:
                        created.append(relation)
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Created {len(created)} relations"
                        }
                    ]
                }
            
            elif tool_name == "add_observations":
                observations = arguments.get("observations", [])
                added = []
                for obs_data in observations:
                    observation = self.graph.add_observation(
                        entity_name=obs_data["entity"],
                        content=obs_data["content"],
                        confidence=obs_data.get("confidence", 1.0)
                    )
                    if observation:
                        added.append(observation)
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Added {len(added)} observations"
                        }
                    ]
                }
            
            elif tool_name == "read_graph":
                graph_data = self.graph.to_dict()
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(graph_data, indent=2)
                        }
                    ]
                }
            
            elif tool_name == "search_nodes":
                query = arguments.get("query", "")
                results = self.graph.search_nodes(query)
                
                if not results:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"No entities found matching '{query}'"
                            }
                        ]
                    }
                
                response_text = f"Found {len(results)} entities:\n\n"
                for entity in results:
                    response_text += f"**{entity.name}** ({entity.entity_type})\n"
                    if entity.observations:
                        response_text += "  Observations:\n"
                        for obs in entity.observations[:3]:  # Show first 3
                            response_text += f"  - {obs.content}\n"
                        if len(entity.observations) > 3:
                            response_text += f"  ... and {len(entity.observations) - 3} more\n"
                    response_text += "\n"
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": response_text
                        }
                    ]
                }
            
            elif tool_name == "open_nodes":
                names = arguments.get("names", [])
                response_text = ""
                
                for name in names:
                    entity = self.graph.get_entity(name)
                    if entity:
                        response_text += f"**{entity.name}** ({entity.entity_type})\n"
                        response_text += f"Created: {entity.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                        
                        if entity.observations:
                            response_text += "Observations:\n"
                            for obs in entity.observations:
                                response_text += f"  - {obs.content} (confidence: {obs.confidence})\n"
                        
                        # Show connections
                        connected = self.graph.get_connected_entities(name)
                        if connected:
                            response_text += f"Connected to: {', '.join(connected)}\n"
                        
                        response_text += "\n"
                    else:
                        response_text += f"Entity '{name}' not found\n\n"
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": response_text
                        }
                    ]
                }
            
            elif tool_name == "delete_entities":
                names = arguments.get("names", [])
                deleted = []
                for name in names:
                    if self.graph.delete_entity(name):
                        deleted.append(name)
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Deleted {len(deleted)} entities: {', '.join(deleted)}"
                        }
                    ]
                }
            
            elif tool_name == "delete_observations":
                deletions = arguments.get("deletions", [])
                deleted_count = 0
                for deletion in deletions:
                    if self.graph.delete_observation(deletion["entity"], deletion["observation_id"]):
                        deleted_count += 1
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Deleted {deleted_count} observations"
                        }
                    ]
                }
            
            elif tool_name == "delete_relations":
                relation_ids = arguments.get("relation_ids", [])
                deleted_count = 0
                for rel_id in relation_ids:
                    if self.graph.delete_relation(rel_id):
                        deleted_count += 1
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Deleted {deleted_count} relations"
                        }
                    ]
                }
            
            else:
                return {
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}"
                    }
                }
        
        except Exception as e:
            return {
                "error": {
                    "code": -32603,
                    "message": f"Tool execution error: {str(e)}"
                }
            }
    
    async def run_stdio(self):
        """Run the server using stdio transport."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        
        self.running = True
        while self.running:
            try:
                # Read a line from stdin
                line = await reader.readline()
                if not line:
                    break
                
                # Parse the JSON request
                request = json.loads(line.decode())
                
                # Handle the request
                response = await self.handle_request(request)
                
                # Write the response
                response_json = json.dumps(response) + '\n'
                sys.stdout.write(response_json)
                sys.stdout.flush()
                
            except Exception as e:
                error_response = {
                    "error": {
                        "code": -32700,
                        "message": f"Parse error: {str(e)}"
                    }
                }
                error_json = json.dumps(error_response) + '\n'
                sys.stdout.write(error_json)
                sys.stdout.flush()
    
    def stop(self):
        """Stop the server."""
        self.running = False


async def main():
    """Main entry point for the memory MCP server."""
    # Get memory file path from environment or use default
    memory_file_path = os.environ.get("MEMORY_FILE")
    memory_file = Path(memory_file_path) if memory_file_path else None
    
    # Create and run the server
    server = MemoryMCPServer(memory_file)
    
    # Print initialization message to stderr (not stdout which is used for MCP)
    print(f"Memory MCP Server started. Memory file: {server.graph.memory_file}", file=sys.stderr)
    
    try:
        await server.run_stdio()
    except KeyboardInterrupt:
        print("Server stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    asyncio.run(main())