import os
import json
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncGenerator

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaModelManager:
    """
    A class to manage Ollama models - listing, downloading, and deleting models.
    """
    def __init__(self, base_url="http://localhost:11434"):
        self.base_url = base_url.rstrip('/')
        logger.info(f"Initializing Ollama model manager with base URL: {self.base_url}")
        
        # Path to the cached models file in the user's config directory
        config_dir = os.path.expanduser("~/.config/cli-FSD")
        os.makedirs(config_dir, exist_ok=True)
        self.models_cache_path = Path(os.path.join(config_dir, "ollama-models.json"))
        
    async def get_local_models(self) -> List[Dict[str, Any]]:
        """Get list of locally available Ollama models"""
        logger.info("Fetching locally available Ollama models...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=5,
                    headers={"Accept": "application/json"}
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    if "models" not in data:
                        raise Exception("Invalid response format: missing 'models' key")
                    
                    models = []
                    for model in data["models"]:
                        if "name" not in model:
                            continue  # Skip invalid models
                        models.append({
                            "id": model["name"],
                            "name": model["name"],
                            "size": model.get("size", 0),
                            "modified_at": model.get("modified_at", ""),
                            "digest": model.get("digest", "")
                        })
                    
                    logger.info(f"Found {len(models)} local Ollama models")
                    return models
        except Exception as e:
            logger.error(f"Error getting local models: {str(e)}")
            return []
            
    async def get_model_details(self, model_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific Ollama model"""
        logger.info(f"Getting details for model: {model_id}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/show",
                    json={"name": model_id},
                    timeout=5
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data
        except Exception as e:
            logger.error(f"Error getting model details: {str(e)}")
            return {
                "error": str(e),
                "modelfile": None,
                "parameters": None,
                "size": 0,
                "created_at": None,
                "modified_at": None
            }
    
    async def get_registry_models(self) -> List[Dict[str, Any]]:
        """Get available models from Ollama registry with cache support"""
        # Check if we need to update the cache
        need_cache_update = True
        models_from_cache = []
        
        try:
            # Try to read from cache first
            if self.models_cache_path.exists():
                with open(self.models_cache_path, 'r') as f:
                    cache_data = json.load(f)
                
                # Check if cache is still valid (less than 24 hours old)
                if cache_data.get("last_updated"):
                    last_updated = datetime.fromisoformat(cache_data["last_updated"])
                    # Cache valid if less than 24 hours old
                    if datetime.now() - last_updated < timedelta(hours=24):
                        need_cache_update = False
                        models_from_cache = cache_data.get("models", [])
                        logger.info(f"Using cached models list with {len(models_from_cache)} models")
        except Exception as e:
            logger.warning(f"Error reading models cache: {str(e)}, will refresh")
        
        # If we need to update the cache, do it now
        if need_cache_update:
            models_from_cache = await self._fetch_and_cache_models()
            
        return models_from_cache
    
    async def _fetch_and_cache_models(self) -> List[Dict[str, Any]]:
        """Fetch models from Ollama registry and cache them"""
        logger.info("Fetching models from Ollama registry...")
        try:
            # In a real implementation, we would query the Ollama registry API
            # For now, we'll use a curated list of popular models
            models = await self._get_curated_model_list()
            
            # Cache the models
            cache_data = {
                "last_updated": datetime.now().isoformat(),
                "models": models
            }
            
            with open(self.models_cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
                
            logger.info(f"Cached {len(models)} models to {self.models_cache_path}")
            return models
        except Exception as e:
            logger.error(f"Error during model fetch and cache: {str(e)}")
            return []
            
    async def _get_curated_model_list(self) -> List[Dict[str, Any]]:
        """Get a curated list of popular Ollama models"""
        # This is a simplified version - in practice, we'd query Ollama's API
        models = [
            {
                "name": "llama3",
                "description": "Meta's Llama 3 8B model",
                "model_family": "Llama",
                "parameter_size": "8B",
                "tags": ["llama", "meta"]
            },
            {
                "name": "llama3:70b",
                "description": "Meta's Llama 3 70B parameter model",
                "model_family": "Llama",
                "parameter_size": "70B",
                "tags": ["llama", "meta"]
            },
            {
                "name": "gemma:7b",
                "description": "Google's Gemma 7B parameter model",
                "model_family": "Gemma",
                "parameter_size": "7B",
                "tags": ["gemma", "google"]
            },
            {
                "name": "llama2",
                "description": "Meta's Llama 2 model",
                "model_family": "Llama",
                "parameter_size": "7B",
                "tags": ["llama", "meta"]
            },
            {
                "name": "mistral",
                "description": "Mistral 7B model - balanced performance",
                "model_family": "Mistral",
                "parameter_size": "7B",
                "tags": ["mistral"]
            },
            {
                "name": "mistral:latest",
                "description": "Latest version of Mistral 7B",
                "model_family": "Mistral",
                "parameter_size": "7B",
                "tags": ["mistral"]
            },
            {
                "name": "codellama",
                "description": "Meta's Code Llama - specialized for code generation",
                "model_family": "Llama",
                "parameter_size": "7B",
                "tags": ["llama", "code", "meta"]
            },
            {
                "name": "codellama:13b",
                "description": "Meta's Code Llama 13B - specialized for code generation",
                "model_family": "Llama",
                "parameter_size": "13B",
                "tags": ["llama", "code", "meta"]
            },
            {
                "name": "codellama:34b",
                "description": "Meta's Code Llama 34B - specialized for code generation",
                "model_family": "Llama",
                "parameter_size": "34B",
                "tags": ["llama", "code", "meta"]
            },
            {
                "name": "phi",
                "description": "Microsoft's Phi model",
                "model_family": "Phi",
                "parameter_size": "3B",
                "tags": ["phi", "microsoft"]
            },
            {
                "name": "phi2",
                "description": "Microsoft's Phi-2 model - efficient small model",
                "model_family": "Phi",
                "parameter_size": "2.7B",
                "tags": ["phi", "microsoft"]
            },
            {
                "name": "phi3",
                "description": "Microsoft's Phi-3 model",
                "model_family": "Phi",
                "parameter_size": "3.8B",
                "tags": ["phi", "microsoft"]
            },
            {
                "name": "phi3:medium",
                "description": "Microsoft's Phi-3 Medium model",
                "model_family": "Phi",
                "parameter_size": "14B",
                "tags": ["phi", "microsoft"]
            },
            {
                "name": "neural-chat",
                "description": "Intel's Neural Chat model",
                "model_family": "Neural Chat",
                "parameter_size": "7B",
                "tags": ["intel", "neural-chat"]
            },
            {
                "name": "mixtral",
                "description": "Mixtral 8x7B mixture of experts model",
                "model_family": "Mixtral",
                "parameter_size": "8x7B",
                "tags": ["mixtral"]
            },
            {
                "name": "qwen",
                "description": "Alibaba's Qwen model",
                "model_family": "Qwen",
                "parameter_size": "7B",
                "tags": ["qwen", "alibaba"]
            },
            {
                "name": "qwen:14b",
                "description": "Alibaba's Qwen 14B model",
                "model_family": "Qwen",
                "parameter_size": "14B",
                "tags": ["qwen", "alibaba"]
            }
        ]
        
        return models
    
    async def search_models(self, query: str = "") -> List[Dict[str, Any]]:
        """Search available models based on a query string"""
        models = await self.get_registry_models()
        
        # If no query, return all models
        if not query:
            return models
            
        # Filter models based on query
        query = query.lower()
        filtered_models = []
        
        for model in models:
            if (query in model["name"].lower() or 
                query in model.get("description", "").lower() or
                query in model.get("model_family", "").lower()):
                filtered_models.append(model)
                
            # Also check tags if available
            if "tags" in model:
                for tag in model["tags"]:
                    if query in tag.lower():
                        if model not in filtered_models:
                            filtered_models.append(model)
                        break
                        
        return filtered_models
            
    async def pull_model(self, model_id: str, progress_callback=None):
        """Pull a model from Ollama registry with progress updates"""
        logger.info(f"Pulling model: {model_id}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model_id},
                    timeout=3600  # 1 hour timeout for large models
                ) as response:
                    response.raise_for_status()
                    async for line in response.content:
                        if line:
                            try:
                                data = json.loads(line)
                                if progress_callback:
                                    await progress_callback(data)
                                else:
                                    if "status" in data:
                                        logger.info(f"Pull status: {data['status']}")
                                    if "completed" in data and "total" in data:
                                        progress = (data["completed"] / data["total"]) * 100 if data["total"] > 0 else 0
                                        logger.info(f"Download progress: {progress:.1f}%")
                            except json.JSONDecodeError:
                                continue
            return {"success": True, "message": f"Model {model_id} pulled successfully"}
        except Exception as e:
            logger.error(f"Error pulling model: {str(e)}")
            return {"success": False, "message": f"Failed to pull model: {str(e)}"}
            
    async def delete_model(self, model_id: str) -> Dict[str, Any]:
        """Delete a model from Ollama"""
        logger.info(f"Deleting model: {model_id}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.base_url}/api/delete",
                    json={"name": model_id},
                    timeout=30
                ) as response:
                    response.raise_for_status()
                    logger.info(f"Model {model_id} deleted successfully")
                    return {"success": True, "message": f"Model {model_id} deleted successfully"}
        except Exception as e:
            logger.error(f"Error deleting model: {str(e)}")
            return {"success": False, "message": f"Failed to delete model: {str(e)}"}

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format size in bytes to human-readable format"""
        if size_bytes == 0:
            return "Unknown"
        
        suffixes = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(suffixes) - 1:
            size_bytes /= 1024
            i += 1
        
        return f"{size_bytes:.2f} {suffixes[i]}"


# Helper functions for CLI interface

async def list_local_models_cli():
    """CLI function to list local Ollama models"""
    manager = OllamaModelManager()
    models = await manager.get_local_models()
    
    if not models:
        print("No local Ollama models found.")
        return
    
    print("\n=== Local Ollama Models ===")
    print(f"{'Model Name':<30} {'Size':<15} {'Modified':<20}")
    print("-" * 65)
    
    for model in models:
        size = OllamaModelManager.format_size(model.get("size", 0))
        modified = model.get("modified_at", "Unknown")
        if isinstance(modified, str) and modified:
            # Try to format the date if possible
            try:
                dt = datetime.fromisoformat(modified.replace('Z', '+00:00'))
                modified = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pass
        
        print(f"{model['name']:<30} {size:<15} {modified:<20}")
    print()

async def search_models_cli(query=""):
    """CLI function to search for available Ollama models"""
    manager = OllamaModelManager()
    models = await manager.search_models(query)
    
    if not models:
        print(f"No models found matching '{query}'." if query else "No models available.")
        return
    
    header = f"\n=== Available Ollama Models"
    if query:
        header += f" matching '{query}'"
    header += " ==="
    print(header)
    print(f"{'Model Name':<25} {'Parameter Size':<15} {'Family':<15} {'Description':<40}")
    print("-" * 95)
    
    for model in models:
        name = model.get("name", "Unknown")
        size = model.get("parameter_size", "Unknown")
        family = model.get("model_family", "Unknown")
        description = model.get("description", "")
        # Truncate description if too long
        if len(description) > 40:
            description = description[:37] + "..."
        
        print(f"{name:<25} {size:<15} {family:<15} {description:<40}")
    print()

async def pull_model_cli(model_id):
    """CLI function to pull an Ollama model"""
    if not model_id:
        print("Error: Model name is required.")
        return
    
    manager = OllamaModelManager()
    
    # Define a progress callback for the CLI
    async def progress_callback(data):
        if "status" in data:
            print(f"Status: {data['status']}")
        if "completed" in data and "total" in data:
            if data["total"] > 0:
                progress = (data["completed"] / data["total"]) * 100
                print(f"Progress: {progress:.1f}% ({data['completed']}/{data['total']})")
    
    print(f"Pulling model: {model_id}...")
    print("This may take a while depending on the model size and your internet connection.")
    result = await manager.pull_model(model_id, progress_callback)
    
    if result.get("success", False):
        print(f"Success: {result.get('message')}")
    else:
        print(f"Error: {result.get('message')}")

async def delete_model_cli(model_id):
    """CLI function to delete an Ollama model"""
    if not model_id:
        print("Error: Model name is required.")
        return
    
    manager = OllamaModelManager()
    
    # First check if the model exists
    models = await manager.get_local_models()
    model_exists = any(model["name"] == model_id for model in models)
    
    if not model_exists:
        print(f"Error: Model '{model_id}' not found locally.")
        return
    
    # Confirm deletion
    confirm = input(f"Are you sure you want to delete the model '{model_id}'? (y/N): ")
    if confirm.lower() != 'y':
        print("Operation cancelled.")
        return
    
    print(f"Deleting model: {model_id}...")
    result = await manager.delete_model(model_id)
    
    if result.get("success", False):
        print(f"Success: {result.get('message')}")
    else:
        print(f"Error: {result.get('message')}")

async def show_model_details_cli(model_id):
    """CLI function to show details of a specific Ollama model"""
    if not model_id:
        print("Error: Model name is required.")
        return
    
    manager = OllamaModelManager()
    details = await manager.get_model_details(model_id)
    
    if "error" in details and details["error"]:
        print(f"Error getting model details: {details['error']}")
        return
    
    print(f"\n=== Details for model: {model_id} ===")
    
    # Format and display model details
    if "modelfile" in details:
        print("\nModelfile:")
        print(details["modelfile"])
    
    if "parameters" in details and details["parameters"]:
        print("\nParameters:")
        for param, value in details["parameters"].items():
            print(f"  {param}: {value}")
    
    size = OllamaModelManager.format_size(details.get("size", 0))
    print(f"\nSize: {size}")
    
    if "created_at" in details and details["created_at"]:
        try:
            dt = datetime.fromisoformat(details["created_at"].replace('Z', '+00:00'))
            created = dt.strftime("%Y-%m-%d %H:%M:%S")
            print(f"Created: {created}")
        except (ValueError, TypeError):
            print(f"Created: {details['created_at']}")
    
    if "modified_at" in details and details["modified_at"]:
        try:
            dt = datetime.fromisoformat(details["modified_at"].replace('Z', '+00:00'))
            modified = dt.strftime("%Y-%m-%d %H:%M:%S")
            print(f"Last modified: {modified}")
        except (ValueError, TypeError):
            print(f"Last modified: {details['modified_at']}")
    print()

# Test function
async def test():
    """Test the Ollama model manager functionality"""
    manager = OllamaModelManager()
    
    print("Testing Ollama Model Manager...")
    
    # List local models
    print("\nListing local models:")
    local_models = await manager.get_local_models()
    for model in local_models:
        print(f"- {model['name']}")
    
    # Search for models
    query = "llama"
    print(f"\nSearching for models with query '{query}':")
    search_results = await manager.search_models(query)
    for model in search_results:
        print(f"- {model['name']}: {model.get('description', '')}")
    
    # Use the CLI functions
    print("\nTesting CLI functions:")
    await list_local_models_cli()
    await search_models_cli("llama")

if __name__ == "__main__":
    # Run the test
    asyncio.run(test())