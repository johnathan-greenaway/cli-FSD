import os
import json
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

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


class InteractiveOllamaModelBrowser:
    """
    An interactive browser for Ollama models with improved UI and workflow.
    """
    def __init__(self, config=None):
        self.config = config
        self.manager = OllamaModelManager()
        self.local_models = []
        self.available_models = []
        self.page_size = 10  # Number of models shown per page
        
    async def initialize(self):
        """Initialize the browser by fetching initial data"""
        # Fetch local models
        self.local_models = await self.manager.get_local_models()
        
    def _get_color(self, text, color_code, reset_code):
        """Apply color to text if config is available"""
        if self.config and hasattr(self.config, color_code) and hasattr(self.config, reset_code):
            return f"{getattr(self.config, color_code)}{text}{getattr(self.config, reset_code)}"
        return text
        
    def _colored_text(self, text, color):
        """Formats text with terminal colors based on config"""
        if not self.config:
            return text
            
        color_codes = {
            'green': 'GREEN',
            'cyan': 'CYAN',
            'yellow': 'YELLOW',
            'red': 'RED',
            'bold': 'BOLD',
            'reset': 'RESET'
        }
        
        if color in color_codes and hasattr(self.config, color_codes[color]):
            return f"{getattr(self.config, color_codes[color])}{text}{self.config.RESET}"
        return text
    
    def print_header(self, title):
        """Print a styled header"""
        if self.config:
            print(f"\n{self.config.CYAN}{self.config.BOLD}=== {title} ==={self.config.RESET}")
        else:
            print(f"\n=== {title} ===")
    
    def print_divider(self):
        """Print a divider line"""
        print("-" * 80)
    
    def print_menu(self, options, prompt="Select an option"):
        """Print a menu with numbered options"""
        self.print_divider()
        for idx, option in enumerate(options, 1):
            print(f"{idx}. {option}")
        self.print_divider()
        
        if self.config:
            return input(f"{self.config.YELLOW}{prompt}:{self.config.RESET} ").strip()
        else:
            return input(f"{prompt}: ").strip()
    
    async def display_local_models(self, page=0):
        """Display local models with pagination and selection options"""
        if not self.local_models:
            self.local_models = await self.manager.get_local_models()
            
        if not self.local_models:
            print(self._colored_text("No local Ollama models found.", 'yellow'))
            return None
            
        self.print_header("LOCAL OLLAMA MODELS")
        
        # Calculate pagination
        total_pages = (len(self.local_models) + self.page_size - 1) // self.page_size
        start_idx = page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.local_models))
        
        # Display page info
        if total_pages > 1:
            print(self._colored_text(f"Page {page+1}/{total_pages} - Models {start_idx+1}-{end_idx} of {len(self.local_models)}", 'cyan'))
            
        # Print table header
        print(f"{'#':<3} {'Model Name':<25} {'Size':<12} {'Modified':<20}")
        self.print_divider()
        
        # Print models
        for idx in range(start_idx, end_idx):
            model = self.local_models[idx]
            size = self.manager.format_size(model.get("size", 0))
            modified = model.get("modified_at", "Unknown")
            if isinstance(modified, str) and modified:
                # Try to format the date if possible
                try:
                    dt = datetime.fromisoformat(modified.replace('Z', '+00:00'))
                    modified = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass
            
            print(f"{idx-start_idx+1:<3} {model['name']:<25} {size:<12} {modified:<20}")
            
        # Navigation options
        options = []
        if page > 0:
            options.append(f"{self._colored_text('P', 'bold')}revious page")
        if page < total_pages - 1:
            options.append(f"{self._colored_text('N', 'bold')}ext page")
        
        options.extend([
            f"{self._colored_text('S', 'bold')}elect a model",
            f"{self._colored_text('D', 'bold')}elete a model",
            f"{self._colored_text('B', 'bold')}ack to main menu"
        ])
        
        choice = self.print_menu(options)
        
        if choice.lower() == 'p' and page > 0:
            # Previous page
            return await self.display_local_models(page - 1)
        elif choice.lower() == 'n' and page < total_pages - 1:
            # Next page
            return await self.display_local_models(page + 1)
        elif choice.lower() == 's':
            # Select a model
            model_idx = input("Enter the number of the model to select: ").strip()
            try:
                idx = int(model_idx) - 1
                if 0 <= idx < end_idx - start_idx:
                    model_id = self.local_models[start_idx + idx]['name']
                    return self.activate_model(model_id)
                else:
                    print(self._colored_text("Invalid model number.", 'red'))
                    return await self.display_local_models(page)
            except ValueError:
                print(self._colored_text("Invalid input. Please enter a number.", 'red'))
                return await self.display_local_models(page)
        elif choice.lower() == 'd':
            # Delete a model
            model_idx = input("Enter the number of the model to delete: ").strip()
            try:
                idx = int(model_idx) - 1
                if 0 <= idx < end_idx - start_idx:
                    model_id = self.local_models[start_idx + idx]['name']
                    confirm = input(f"Are you sure you want to delete model '{model_id}'? (y/N): ").strip().lower()
                    if confirm == 'y':
                        result = await self.manager.delete_model(model_id)
                        if result.get('success', False):
                            print(self._colored_text(f"Model '{model_id}' deleted successfully!", 'green'))
                            # Refresh the model list
                            self.local_models = await self.manager.get_local_models()
                        else:
                            print(self._colored_text(f"Error deleting model: {result.get('message')}", 'red'))
                    else:
                        print("Deletion cancelled.")
                    return await self.display_local_models(page)
                else:
                    print(self._colored_text("Invalid model number.", 'red'))
                    return await self.display_local_models(page)
            except ValueError:
                print(self._colored_text("Invalid input. Please enter a number.", 'red'))
                return await self.display_local_models(page)
        
        # Default: back to main menu
        return None
    
    async def browse_remote_models(self, query="", page=0):
        """Browse and search for remote models with enhanced UI"""
        if query:
            self.print_header(f"REMOTE OLLAMA MODELS MATCHING '{query}'")
            self.available_models = await self.manager.search_models(query)
        else:
            self.print_header("REMOTE OLLAMA MODELS")
            if not self.available_models:
                self.available_models = await self.manager.get_registry_models()
        
        if not self.available_models:
            print(self._colored_text("No models found.", 'yellow'))
            # Offer to go back
            input(self._colored_text("Press Enter to return to main menu...", 'cyan'))
            return None
        
        # Calculate pagination
        total_pages = (len(self.available_models) + self.page_size - 1) // self.page_size
        start_idx = page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.available_models))
        
        # Display page info
        if total_pages > 1:
            print(self._colored_text(f"Page {page+1}/{total_pages} - Models {start_idx+1}-{end_idx} of {len(self.available_models)}", 'cyan'))
            
        # Print table header
        print(f"{'#':<3} {'Model Name':<20} {'Size':<10} {'Family':<15} {'Description'}")
        self.print_divider()
        
        # Check which models are already installed
        local_model_names = [model["name"] for model in self.local_models]
        
        # Print models
        for idx in range(start_idx, end_idx):
            model = self.available_models[idx]
            name = model.get("name", "Unknown")
            size = model.get("parameter_size", "Unknown")
            family = model.get("model_family", "Unknown")
            description = model.get("description", "")
            # Truncate description if too long
            if len(description) > 40:
                description = description[:37] + "..."
            
            # Mark installed models
            status = ""
            if name in local_model_names:
                status = self._colored_text(" [INSTALLED]", 'green')
            
            print(f"{idx-start_idx+1:<3} {name:<20} {size:<10} {family:<15} {description}{status}")
            
        # Navigation options
        options = []
        if page > 0:
            options.append(f"{self._colored_text('P', 'bold')}revious page")
        if page < total_pages - 1:
            options.append(f"{self._colored_text('N', 'bold')}ext page")
        
        options.extend([
            f"{self._colored_text('D', 'bold')}ownload a model",
            f"{self._colored_text('S', 'bold')}earch for models",
            f"{self._colored_text('I', 'bold')}nfo about a model",
            f"{self._colored_text('B', 'bold')}ack to main menu"
        ])
        
        choice = self.print_menu(options)
        
        if choice.lower() == 'p' and page > 0:
            # Previous page
            return await self.browse_remote_models(query, page - 1)
        elif choice.lower() == 'n' and page < total_pages - 1:
            # Next page
            return await self.browse_remote_models(query, page + 1)
        elif choice.lower() == 'd':
            # Download a model
            model_idx = input("Enter the number of the model to download: ").strip()
            try:
                idx = int(model_idx) - 1
                if 0 <= idx < end_idx - start_idx:
                    model_id = self.available_models[start_idx + idx]['name']
                    # Check if already installed
                    if model_id in local_model_names:
                        use_anyway = input(f"Model '{model_id}' is already installed. Set as active model? (y/N): ").strip().lower()
                        if use_anyway == 'y':
                            return self.activate_model(model_id)
                        return await self.browse_remote_models(query, page)
                        
                    print(self._colored_text(f"Downloading model {model_id}...", 'cyan'))
                    
                    # Define a progress callback to display download progress
                    async def progress_callback(data):
                        if "status" in data:
                            print(f"Status: {data['status']}")
                        if "completed" in data and "total" in data:
                            if data["total"] > 0:
                                progress = (data["completed"] / data["total"]) * 100
                                print(f"Progress: {progress:.1f}% ({data['completed']}/{data['total']})")
                    
                    result = await self.manager.pull_model(model_id, progress_callback)
                    
                    if result.get("success", False):
                        print(self._colored_text(f"Model {model_id} downloaded successfully!", 'green'))
                        use_model = input("Set as active model? (Y/n): ").strip().lower()
                        if use_model != 'n':
                            return self.activate_model(model_id)
                    else:
                        print(self._colored_text(f"Error downloading model: {result.get('message')}", 'red'))
                        
                    # Refresh local models
                    self.local_models = await self.manager.get_local_models()
                    return await self.browse_remote_models(query, page)
                else:
                    print(self._colored_text("Invalid model number.", 'red'))
                    return await self.browse_remote_models(query, page)
            except ValueError:
                print(self._colored_text("Invalid input. Please enter a number.", 'red'))
                return await self.browse_remote_models(query, page)
        elif choice.lower() == 's':
            # Search for models
            new_query = input("Enter search term (or leave empty for all models): ").strip()
            return await self.browse_remote_models(new_query, 0)  # Reset to first page with new query
        elif choice.lower() == 'i':
            # Show model info
            model_idx = input("Enter the number of the model for details: ").strip()
            try:
                idx = int(model_idx) - 1
                if 0 <= idx < end_idx - start_idx:
                    model_id = self.available_models[start_idx + idx]['name']
                    await self.show_model_info(model_id)
                    return await self.browse_remote_models(query, page)
                else:
                    print(self._colored_text("Invalid model number.", 'red'))
                    return await self.browse_remote_models(query, page)
            except ValueError:
                print(self._colored_text("Invalid input. Please enter a number.", 'red'))
                return await self.browse_remote_models(query, page)
        
        # Default: back to main menu
        return None
    
    async def show_model_info(self, model_id):
        """Show detailed information about a model"""
        self.print_header(f"MODEL DETAILS: {model_id}")
        
        # First check if model is local
        is_local = any(model["name"] == model_id for model in self.local_models)
        
        if is_local:
            details = await self.manager.get_model_details(model_id)
            
            if "error" in details and details["error"]:
                print(self._colored_text(f"Error getting model details: {details['error']}", 'red'))
            else:
                # Display model details in a structured way
                if "modelfile" in details:
                    print(self._colored_text("\nModelfile:", 'bold'))
                    print(details["modelfile"])
                
                if "parameters" in details and details["parameters"]:
                    print(self._colored_text("\nParameters:", 'bold'))
                    for param, value in details["parameters"].items():
                        print(f"  {param}: {value}")
                
                size = self.manager.format_size(details.get("size", 0))
                print(f"\n{self._colored_text('Size:', 'bold')} {size}")
                
                if "created_at" in details and details["created_at"]:
                    try:
                        dt = datetime.fromisoformat(details["created_at"].replace('Z', '+00:00'))
                        created = dt.strftime("%Y-%m-%d %H:%M:%S")
                        print(f"{self._colored_text('Created:', 'bold')} {created}")
                    except (ValueError, TypeError):
                        print(f"{self._colored_text('Created:', 'bold')} {details['created_at']}")
                
                if "modified_at" in details and details["modified_at"]:
                    try:
                        dt = datetime.fromisoformat(details["modified_at"].replace('Z', '+00:00'))
                        modified = dt.strftime("%Y-%m-%d %H:%M:%S")
                        print(f"{self._colored_text('Last modified:', 'bold')} {modified}")
                    except (ValueError, TypeError):
                        print(f"{self._colored_text('Last modified:', 'bold')} {details['modified_at']}")
        else:
            # Show information from available models
            model_info = None
            for model in self.available_models:
                if model["name"] == model_id:
                    model_info = model
                    break
            
            if not model_info:
                # Not in our list, get info from registry
                all_models = await self.manager.get_registry_models()
                for model in all_models:
                    if model["name"] == model_id:
                        model_info = model
                        break
            
            if model_info:
                print(f"{self._colored_text('Name:', 'bold')} {model_info.get('name')}")
                print(f"{self._colored_text('Family:', 'bold')} {model_info.get('model_family')}")
                print(f"{self._colored_text('Parameter Size:', 'bold')} {model_info.get('parameter_size')}")
                print(f"{self._colored_text('Description:', 'bold')} {model_info.get('description')}")
                
                if "tags" in model_info and model_info["tags"]:
                    print(f"{self._colored_text('Tags:', 'bold')} {', '.join(model_info['tags'])}")
                
                # Add download option
                download = input(f"\nDownload this model? (y/N): ").strip().lower() == 'y'
                if download:
                    print(self._colored_text(f"Downloading model {model_id}...", 'cyan'))
                    
                    async def progress_callback(data):
                        if "status" in data:
                            print(f"Status: {data['status']}")
                        if "completed" in data and "total" in data:
                            if data["total"] > 0:
                                progress = (data["completed"] / data["total"]) * 100
                                print(f"Progress: {progress:.1f}% ({data['completed']}/{data['total']})")
                    
                    result = await self.manager.pull_model(model_id, progress_callback)
                    
                    if result.get("success", False):
                        print(self._colored_text(f"Model {model_id} downloaded successfully!", 'green'))
                        use_model = input("Set as active model? (Y/n): ").strip().lower()
                        if use_model != 'n':
                            return self.activate_model(model_id)
                    else:
                        print(self._colored_text(f"Error downloading model: {result.get('message')}", 'red'))
                    
                    # Refresh local models
                    self.local_models = await self.manager.get_local_models()
            else:
                print(self._colored_text(f"No information available for model '{model_id}'", 'yellow'))
        
        # Wait for user
        input("\nPress Enter to continue...")
        return None
    
    def activate_model(self, model_id):
        """Set a model as the active Ollama model in the CLI configuration"""
        if not self.config:
            print(self._colored_text("Cannot set active model: configuration not available.", 'red'))
            return None
            
        # Set as the current Ollama model
        self.config.last_ollama_model = model_id
        # If using Ollama, update current_model as well
        if self.config.use_ollama:
            self.config.current_model = model_id
        self.config.save_preferences()
        
        print(self._colored_text(f"Model '{model_id}' is now set as the active Ollama model.", 'green'))
        
        # Ask if user wants to switch to Ollama mode
        if not self.config.use_ollama:
            switch = input("Switch to Ollama mode? (Y/n): ").strip().lower()
            if switch != 'n':
                self.config.session_model = "ollama"
                self.config.use_ollama = True
                self.config.use_claude = False
                self.config.use_groq = False
                self.config.save_preferences()
                print(self._colored_text("Switched to Ollama mode.", 'green'))
                
                # Remind to restart or reinitialize chat models
                print(self._colored_text("Please reinitialize chat models to apply the changes.", 'yellow'))
        
        input("\nPress Enter to continue...")
        return True
    
    async def run(self):
        """Run the interactive Ollama model browser"""
        await self.initialize()
        
        while True:
            self.print_header("OLLAMA MODEL BROWSER")
            
            options = [
                f"{self._colored_text('L', 'bold')}ocal models - View and manage your installed models",
                f"{self._colored_text('R', 'bold')}emote models - Browse and download new models",
                f"{self._colored_text('S', 'bold')}earch models - Find specific models",
                f"{self._colored_text('E', 'bold')}xit - Return to CLI"
            ]
            
            # Show current model if available
            if self.config and self.config.use_ollama:
                print(self._colored_text(f"Current Ollama model: {self.config.last_ollama_model}", 'cyan'))
            
            choice = self.print_menu(options, prompt="Select an option (L/R/S/E)")
            
            if choice.lower() == 'l':
                # View local models
                await self.display_local_models()
            elif choice.lower() == 'r':
                # Browse remote models
                await self.browse_remote_models()
            elif choice.lower() == 's':
                # Search for models
                query = input("Enter search term: ").strip()
                if query:
                    await self.browse_remote_models(query)
            elif choice.lower() == 'e' or not choice:
                # Exit
                break
            else:
                print(self._colored_text("Invalid option. Please try again.", 'yellow'))


async def run_ollama_browser(config=None):
    """Run the interactive Ollama model browser with the given config"""
    browser = InteractiveOllamaModelBrowser(config)
    await browser.run()

def handle_ollama_models_command(config):
    """Entry point for the ollama models command"""
    asyncio.run(run_ollama_browser(config))