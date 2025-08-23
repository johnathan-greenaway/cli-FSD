"""Model Manager for detecting and managing all available LLM models.

This module provides dynamic model discovery for all supported providers:
OpenAI, Anthropic (Claude), Ollama, and Groq.
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class ModelInfo:
    """Information about a model."""
    def __init__(self, provider: str, model_id: str, display_name: str = None, 
                 capabilities: List[str] = None, context_window: int = None,
                 is_available: bool = True, error: str = None):
        self.provider = provider
        self.model_id = model_id
        self.display_name = display_name or model_id
        self.capabilities = capabilities or []
        self.context_window = context_window
        self.is_available = is_available
        self.error = error
        self.last_checked = datetime.now()
    
    def to_dict(self) -> Dict:
        return {
            'provider': self.provider,
            'model_id': self.model_id,
            'display_name': self.display_name,
            'capabilities': self.capabilities,
            'context_window': self.context_window,
            'is_available': self.is_available,
            'error': self.error
        }


class ModelManager:
    """Manages model detection and selection for all providers."""
    
    # Cache duration for model lists
    CACHE_DURATION = timedelta(hours=1)
    
    def __init__(self):
        self.models_cache = {}
        self.last_refresh = {}
        self.available_providers = []
        
        # Default model lists (fallback if API detection fails)
        self.default_models = {
            'openai': [
                ModelInfo('openai', 'gpt-4-turbo-preview', 'GPT-4 Turbo', ['chat', 'code', 'vision'], 128000),
                ModelInfo('openai', 'gpt-4', 'GPT-4', ['chat', 'code'], 8192),
                ModelInfo('openai', 'gpt-4-32k', 'GPT-4 32K', ['chat', 'code'], 32768),
                ModelInfo('openai', 'gpt-3.5-turbo', 'GPT-3.5 Turbo', ['chat', 'code'], 16385),
                ModelInfo('openai', 'gpt-3.5-turbo-16k', 'GPT-3.5 Turbo 16K', ['chat', 'code'], 16385),
            ],
            'anthropic': [
                ModelInfo('anthropic', 'claude-3-opus-20240229', 'Claude 3 Opus', ['chat', 'code', 'vision'], 200000),
                ModelInfo('anthropic', 'claude-3-sonnet-20240229', 'Claude 3 Sonnet', ['chat', 'code', 'vision'], 200000),
                ModelInfo('anthropic', 'claude-3-haiku-20240307', 'Claude 3 Haiku', ['chat', 'code', 'vision'], 200000),
                ModelInfo('anthropic', 'claude-2.1', 'Claude 2.1', ['chat', 'code'], 200000),
                ModelInfo('anthropic', 'claude-2.0', 'Claude 2.0', ['chat', 'code'], 100000),
                ModelInfo('anthropic', 'claude-instant-1.2', 'Claude Instant', ['chat', 'code'], 100000),
            ],
            'groq': [
                ModelInfo('groq', 'mixtral-8x7b-32768', 'Mixtral 8x7B', ['chat', 'code'], 32768),
                ModelInfo('groq', 'llama2-70b-4096', 'LLaMA2 70B', ['chat', 'code'], 4096),
                ModelInfo('groq', 'gemma-7b-it', 'Gemma 7B', ['chat', 'code'], 8192),
            ],
            'ollama': []  # Will be populated dynamically
        }
    
    def detect_available_providers(self) -> List[str]:
        """Detect which providers are available based on API keys and services."""
        available = []
        
        # Check OpenAI
        if os.getenv('OPENAI_API_KEY'):
            available.append('openai')
            logger.info("OpenAI provider detected (API key found)")
        
        # Check Anthropic/Claude
        if os.getenv('ANTHROPIC_API_KEY'):
            available.append('anthropic')
            logger.info("Anthropic provider detected (API key found)")
        
        # Check Groq
        if os.getenv('GROQ_API_KEY'):
            available.append('groq')
            logger.info("Groq provider detected (API key found)")
        
        # Check Ollama (local service)
        if self._check_ollama_service():
            available.append('ollama')
            logger.info("Ollama provider detected (service running)")
        
        self.available_providers = available
        return available
    
    def _check_ollama_service(self) -> bool:
        """Check if Ollama service is running locally."""
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def get_openai_models(self, force_refresh: bool = False) -> List[ModelInfo]:
        """Get available OpenAI models."""
        if not force_refresh and 'openai' in self.models_cache:
            if datetime.now() - self.last_refresh.get('openai', datetime.min) < self.CACHE_DURATION:
                return self.models_cache['openai']
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return []
        
        try:
            headers = {'Authorization': f'Bearer {api_key}'}
            response = requests.get('https://api.openai.com/v1/models', headers=headers, timeout=5)
            
            if response.status_code == 200:
                models_data = response.json()
                models = []
                
                # Filter for chat models only
                chat_model_ids = [
                    'gpt-4-turbo-preview', 'gpt-4-0125-preview', 'gpt-4-1106-preview',
                    'gpt-4', 'gpt-4-0613', 'gpt-4-32k', 'gpt-4-32k-0613',
                    'gpt-3.5-turbo', 'gpt-3.5-turbo-0125', 'gpt-3.5-turbo-1106',
                    'gpt-3.5-turbo-16k', 'gpt-3.5-turbo-0613', 'gpt-3.5-turbo-16k-0613'
                ]
                
                for model in models_data.get('data', []):
                    model_id = model.get('id', '')
                    if any(chat_id in model_id for chat_id in chat_model_ids):
                        # Determine context window
                        context_window = 4096  # Default
                        if '32k' in model_id:
                            context_window = 32768
                        elif '16k' in model_id:
                            context_window = 16385
                        elif 'turbo-preview' in model_id or '1106' in model_id:
                            context_window = 128000
                        elif 'gpt-4' in model_id:
                            context_window = 8192
                        
                        models.append(ModelInfo(
                            provider='openai',
                            model_id=model_id,
                            display_name=self._format_model_name(model_id),
                            capabilities=['chat', 'code'],
                            context_window=context_window
                        ))
                
                if models:
                    self.models_cache['openai'] = models
                    self.last_refresh['openai'] = datetime.now()
                    logger.info(f"Detected {len(models)} OpenAI models")
                    return models
                    
        except Exception as e:
            logger.warning(f"Failed to fetch OpenAI models: {e}")
        
        # Return default models if API fails
        return self.default_models['openai']
    
    def get_anthropic_models(self, force_refresh: bool = False) -> List[ModelInfo]:
        """Get available Anthropic/Claude models."""
        if not force_refresh and 'anthropic' in self.models_cache:
            if datetime.now() - self.last_refresh.get('anthropic', datetime.min) < self.CACHE_DURATION:
                return self.models_cache['anthropic']
        
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            return []
        
        # Anthropic doesn't have a models endpoint, so we use the default list
        # but verify the API key works
        try:
            headers = {
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json'
            }
            
            # Test with a minimal request
            test_data = {
                'model': 'claude-2.1',
                'max_tokens': 1,
                'messages': [{'role': 'user', 'content': 'test'}]
            }
            
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers=headers,
                json=test_data,
                timeout=5
            )
            
            if response.status_code in [200, 400, 429]:  # API is working
                models = self.default_models['anthropic']
                self.models_cache['anthropic'] = models
                self.last_refresh['anthropic'] = datetime.now()
                logger.info(f"Anthropic API verified, {len(models)} models available")
                return models
                
        except Exception as e:
            logger.warning(f"Failed to verify Anthropic API: {e}")
        
        return []
    
    def get_ollama_models(self, force_refresh: bool = False) -> List[ModelInfo]:
        """Get available Ollama models."""
        if not force_refresh and 'ollama' in self.models_cache:
            if datetime.now() - self.last_refresh.get('ollama', datetime.min) < self.CACHE_DURATION:
                return self.models_cache['ollama']
        
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=5)
            
            if response.status_code == 200:
                models_data = response.json()
                models = []
                
                for model in models_data.get('models', []):
                    model_name = model.get('name', '')
                    size = model.get('size', 0)
                    
                    # Estimate context window based on model name
                    context_window = 2048  # Default
                    if '32k' in model_name:
                        context_window = 32768
                    elif '16k' in model_name:
                        context_window = 16384
                    elif '8k' in model_name:
                        context_window = 8192
                    elif '4k' in model_name or '4096' in model_name:
                        context_window = 4096
                    
                    models.append(ModelInfo(
                        provider='ollama',
                        model_id=model_name,
                        display_name=f"{model_name} ({self._format_size(size)})",
                        capabilities=['chat', 'code'],
                        context_window=context_window
                    ))
                
                if models:
                    self.models_cache['ollama'] = models
                    self.last_refresh['ollama'] = datetime.now()
                    logger.info(f"Detected {len(models)} Ollama models")
                    return models
                    
        except Exception as e:
            logger.warning(f"Failed to fetch Ollama models: {e}")
        
        return []
    
    def get_groq_models(self, force_refresh: bool = False) -> List[ModelInfo]:
        """Get available Groq models."""
        if not force_refresh and 'groq' in self.models_cache:
            if datetime.now() - self.last_refresh.get('groq', datetime.min) < self.CACHE_DURATION:
                return self.models_cache['groq']
        
        api_key = os.getenv('GROQ_API_KEY')
        if not api_key:
            return []
        
        try:
            headers = {'Authorization': f'Bearer {api_key}'}
            response = requests.get('https://api.groq.com/openai/v1/models', headers=headers, timeout=5)
            
            if response.status_code == 200:
                models_data = response.json()
                models = []
                
                for model in models_data.get('data', []):
                    model_id = model.get('id', '')
                    
                    # Parse context window from model data if available
                    context_window = model.get('context_window', 4096)
                    
                    models.append(ModelInfo(
                        provider='groq',
                        model_id=model_id,
                        display_name=self._format_model_name(model_id),
                        capabilities=['chat', 'code'],
                        context_window=context_window
                    ))
                
                if models:
                    self.models_cache['groq'] = models
                    self.last_refresh['groq'] = datetime.now()
                    logger.info(f"Detected {len(models)} Groq models")
                    return models
                    
        except Exception as e:
            logger.warning(f"Failed to fetch Groq models: {e}")
        
        # Return default models if API fails
        return self.default_models['groq']
    
    def get_all_models(self, force_refresh: bool = False) -> Dict[str, List[ModelInfo]]:
        """Get all available models from all providers."""
        all_models = {}
        
        # Detect available providers first
        if not self.available_providers or force_refresh:
            self.detect_available_providers()
        
        # Get models from each available provider
        for provider in self.available_providers:
            if provider == 'openai':
                models = self.get_openai_models(force_refresh)
            elif provider == 'anthropic':
                models = self.get_anthropic_models(force_refresh)
            elif provider == 'ollama':
                models = self.get_ollama_models(force_refresh)
            elif provider == 'groq':
                models = self.get_groq_models(force_refresh)
            else:
                continue
            
            if models:
                all_models[provider] = models
        
        return all_models
    
    def search_models(self, query: str) -> List[ModelInfo]:
        """Search for models matching a query string."""
        all_models = self.get_all_models()
        results = []
        query_lower = query.lower()
        
        for provider, models in all_models.items():
            for model in models:
                if (query_lower in model.model_id.lower() or 
                    query_lower in model.display_name.lower() or
                    query_lower in provider.lower()):
                    results.append(model)
        
        return results
    
    def get_model_by_id(self, model_id: str, provider: str = None) -> Optional[ModelInfo]:
        """Get a specific model by ID."""
        if provider:
            # Search in specific provider
            models = []
            if provider == 'openai':
                models = self.get_openai_models()
            elif provider == 'anthropic':
                models = self.get_anthropic_models()
            elif provider == 'ollama':
                models = self.get_ollama_models()
            elif provider == 'groq':
                models = self.get_groq_models()
            
            for model in models:
                if model.model_id == model_id:
                    return model
        else:
            # Search all providers
            all_models = self.get_all_models()
            for provider, models in all_models.items():
                for model in models:
                    if model.model_id == model_id:
                        return model
        
        return None
    
    def _format_model_name(self, model_id: str) -> str:
        """Format model ID into a readable display name."""
        # Remove common prefixes and suffixes
        name = model_id.replace('-preview', '').replace('-0125', '').replace('-0613', '')
        name = name.replace('-1106', '').replace('-0314', '').replace('-32768', ' 32K')
        name = name.replace('-4096', ' 4K').replace('-16k', ' 16K').replace('-32k', ' 32K')
        
        # Capitalize appropriately
        parts = name.split('-')
        formatted_parts = []
        for part in parts:
            if part.lower() in ['gpt', 'llama', 'claude']:
                formatted_parts.append(part.upper())
            elif part[0].isdigit():
                formatted_parts.append(part)
            else:
                formatted_parts.append(part.capitalize())
        
        return ' '.join(formatted_parts)
    
    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"
    
    def format_models_table(self, models: List[ModelInfo]) -> str:
        """Format models as a nice table for display."""
        if not models:
            return "No models available"
        
        lines = []
        lines.append("╭" + "─" * 78 + "╮")
        lines.append("│ " + "Available Models".center(76) + " │")
        lines.append("├" + "─" * 78 + "┤")
        lines.append("│ Provider │ Model ID" + " " * 25 + "│ Context │ Status │")
        lines.append("├" + "─" * 78 + "┤")
        
        for model in models:
            provider = model.provider[:8].ljust(8)
            model_id = model.model_id[:32].ljust(32)
            context = str(model.context_window).rjust(7) if model.context_window else "Unknown"
            status = "✓" if model.is_available else "✗"
            
            lines.append(f"│ {provider} │ {model_id} │ {context} │   {status}    │")
        
        lines.append("╰" + "─" * 78 + "╯")
        return "\n".join(lines)


# Global instance
_model_manager = None


def get_model_manager() -> ModelManager:
    """Get or create the global model manager instance."""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager