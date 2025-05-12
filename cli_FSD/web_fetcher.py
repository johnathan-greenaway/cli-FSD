"""Web content fetching and processing module.

This module provides a fast and efficient way to fetch web content
and convert it to structured JSON format for agent consumption.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional
import time
from urllib.parse import urlparse, urljoin
import json
import logging
from dataclasses import dataclass, field, asdict
import re

# Configure logging
logging.basicConfig(level=logging.WARNING, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class WebContent:
    """Structured representation of web content."""
    url: str
    title: str
    timestamp: float = field(default_factory=time.time)
    content_type: str = "webpage"
    metadata: Dict[str, Any] = field(default_factory=dict)
    text_content: str = ""
    structured_content: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)
    images: List[Dict[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return asdict(self)
    
    def to_basic_dict(self) -> Dict[str, Any]:
        """Return a simplified representation with just text and basic structure."""
        return {
            "url": self.url,
            "title": self.title,
            "timestamp": self.timestamp,
            "text_content": self.text_content,
            "links": [link["url"] for link in self.links[:5]]  # Include only first 5 links
        }
    
    def to_detailed_dict(self) -> Dict[str, Any]:
        """Return a detailed representation with all content."""
        return self.to_dict()
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Return a summary representation."""
        return {
            "url": self.url,
            "title": self.title,
            "timestamp": self.timestamp,
            "summary": self.text_content[:500] + "..." if len(self.text_content) > 500 else self.text_content,
            "main_topics": self._extract_main_topics(),
            "link_count": len(self.links),
            "image_count": len(self.images)
        }
    
    def _extract_main_topics(self) -> List[str]:
        """Extract main topics from the content."""
        # Simple implementation based on headings
        topics = []
        for content in self.structured_content:
            if content.get("type") == "heading":
                topics.append(content.get("text", ""))
        
        # If no headings found, use first few sentences
        if not topics and self.text_content:
            sentences = re.split(r'[.!?]', self.text_content)
            topics = [s.strip() for s in sentences[:3] if len(s.strip()) > 10]
            
        return topics[:5]  # Return at most 5 topics


class WebContentFetcher:
    """Fetches and processes web content."""
    
    def __init__(self):
        """Initialize the web content fetcher."""
        self.default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        self.session = requests.Session()
        self.session.headers.update(self.default_headers)
        
        # Simple in-memory cache
        self.cache = {}
        self.cache_expiry = 900  # 15 minutes in seconds
    
    def fetch_url(self, url: str, use_cache: bool = True) -> Optional[str]:
        """Fetch content from a URL.

        Args:
            url: The URL to fetch
            use_cache: Whether to use cached content if available

        Returns:
            The HTML content as string or None if fetching failed
        """
        # Add http:// if the URL doesn't have a scheme
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            logger.info(f"Added https:// prefix to URL: {url}")

        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                logger.error(f"Invalid URL format: {url}")
                return None
        except Exception as e:
            logger.error(f"Error parsing URL {url}: {e}")
            return None
        
        # Check cache
        current_time = time.time()
        if use_cache and url in self.cache:
            cache_entry = self.cache[url]
            if current_time - cache_entry["timestamp"] < self.cache_expiry:
                logger.info(f"Using cached content for {url}")
                return cache_entry["content"]
            
        # Fetch content
        try:
            logger.info(f"Fetching content from {url}")
            response = self.session.get(url, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            html_content = response.text
            
            # Cache the content
            if use_cache:
                self.cache[url] = {
                    "content": html_content,
                    "timestamp": current_time
                }
                
                # Clean old cache entries
                self._clean_cache(current_time)
                
            return html_content
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    def _clean_cache(self, current_time: float) -> None:
        """Remove expired entries from cache."""
        expired_urls = []
        for url, entry in self.cache.items():
            if current_time - entry["timestamp"] > self.cache_expiry:
                expired_urls.append(url)
                
        for url in expired_urls:
            del self.cache[url]
    
    def process_html(self, html: str, url: str, mode: str = "basic") -> WebContent:
        """Process HTML content and convert to structured format.
        
        Args:
            html: The HTML content to process
            url: The source URL
            mode: Processing mode ('basic', 'detailed', or 'summary')
            
        Returns:
            Processed WebContent object
        """
        if not html:
            return WebContent(
                url=url,
                title="Error: No content",
                text_content="Failed to fetch content"
            )
        
        # Parse HTML
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract title
        title = soup.title.string.strip() if soup.title else 'No title'
        
        # Create WebContent object
        web_content = WebContent(
            url=url,
            title=title
        )
        
        # Remove unwanted elements
        for selector in [
            'script', 'style', 'meta', 'link', 'noscript', 'iframe',
            '.cookie-banner', '.cookie-consent', '.advertisement', '.ads',
            '.popup', '.modal', '#cookie-banner', '#cookie-consent',
            'footer', 'header', 'nav', '.nav', '.navbar', '.menu',
            '.sidebar', '.comments', '.related-articles'
        ]:
            for element in soup.select(selector):
                element.decompose()
        
        # Process based on mode
        if mode == "detailed":
            self._process_detailed(soup, web_content, url)
        elif mode == "summary":
            self._process_summary(soup, web_content)
        else:  # "basic" mode
            self._process_basic(soup, web_content)
        
        return web_content
    
    def _process_basic(self, soup: BeautifulSoup, web_content: WebContent) -> None:
        """Process content in basic mode, extracting text and basic structure."""
        # Extract main text content
        main_content = ""
        
        # Try to find main content container
        main_element = None
        for selector in ['main', 'article', '[role="main"]', '#content', '.content']:
            if main_element := soup.select_one(selector):
                break
        
        # If main content container found, extract from it
        if main_element:
            main_content = main_element.get_text(separator=' ', strip=True)
        else:
            # Fallback: extract text from paragraphs and headings
            paragraphs = []
            for element in soup.find_all(['h1', 'h2', 'h3', 'p']):
                text = element.get_text(strip=True)
                if text and len(text) > 20:  # Skip very short snippets
                    paragraphs.append(text)
            main_content = ' '.join(paragraphs)
        
        web_content.text_content = main_content
        
        # Extract basic structure (headings and paragraphs)
        structured_content = []
        
        # Extract headings
        for heading_tag in ['h1', 'h2', 'h3']:
            for heading in soup.find_all(heading_tag):
                heading_text = heading.get_text(strip=True)
                if heading_text:
                    structured_content.append({
                        "type": "heading",
                        "level": int(heading_tag[1]),
                        "text": heading_text
                    })
        
        # Extract paragraphs
        for p in soup.find_all('p'):
            p_text = p.get_text(strip=True)
            if p_text and len(p_text) > 30:  # Skip very short paragraphs
                structured_content.append({
                    "type": "paragraph",
                    "text": p_text
                })
        
        web_content.structured_content = structured_content
        
        # Extract links (limit to first 10)
        links = []
        for i, a in enumerate(soup.find_all('a', href=True)):
            if i >= 10:
                break
                
            href = a['href']
            if not href.startswith(('http://', 'https://')):
                href = urljoin(web_content.url, href)
                
            link_text = a.get_text(strip=True)
            if link_text and href:
                links.append({
                    "text": link_text,
                    "url": href
                })
        
        web_content.links = links
    
    def _process_detailed(self, soup: BeautifulSoup, web_content: WebContent, url: str) -> None:
        """Process content in detailed mode, extracting text, links, images, and metadata."""
        # First apply basic processing
        self._process_basic(soup, web_content)
        
        # Extract metadata
        metadata = {}
        
        # Extract OpenGraph and Twitter card metadata
        for meta in soup.find_all('meta'):
            prop = meta.get('property', '') or meta.get('name', '')
            content = meta.get('content', '')
            
            if not prop or not content:
                continue
                
            if prop.startswith('og:') or prop.startswith('twitter:'):
                metadata[prop] = content
        
        web_content.metadata = metadata
        
        # Extract images (limit to first 10)
        images = []
        for i, img in enumerate(soup.find_all('img', src=True)):
            if i >= 10:
                break
                
            src = img['src']
            if not src.startswith(('http://', 'https://')):
                src = urljoin(url, src)
                
            alt = img.get('alt', '')
            images.append({
                "src": src,
                "alt": alt
            })
        
        web_content.images = images
        
        # Extract lists
        for list_tag in ['ul', 'ol']:
            for list_element in soup.find_all(list_tag):
                list_items = []
                for li in list_element.find_all('li'):
                    item_text = li.get_text(strip=True)
                    if item_text:
                        list_items.append(item_text)
                
                if list_items:
                    web_content.structured_content.append({
                        "type": "list",
                        "list_type": "ordered" if list_tag == 'ol' else "unordered",
                        "items": list_items
                    })
    
    def _process_summary(self, soup: BeautifulSoup, web_content: WebContent) -> None:
        """Process content in summary mode, extracting and summarizing key information."""
        # First apply basic processing
        self._process_basic(soup, web_content)
        
        # Extract main headings for topics
        main_topics = []
        for heading in soup.find_all(['h1', 'h2']):
            heading_text = heading.get_text(strip=True)
            if heading_text and len(heading_text) > 5:
                main_topics.append(heading_text)
        
        # Extract first paragraph after each heading as summary
        summaries = []
        for heading in soup.find_all(['h1', 'h2']):
            next_p = heading.find_next('p')
            if next_p:
                p_text = next_p.get_text(strip=True)
                if p_text and len(p_text) > 50:
                    summaries.append(p_text)
        
        # If we couldn't find good summary paragraphs, just take the first few
        if not summaries:
            for p in soup.find_all('p'):
                p_text = p.get_text(strip=True)
                if p_text and len(p_text) > 50:
                    summaries.append(p_text)
                    if len(summaries) >= 3:
                        break
        
        # Combine topics and summaries into structured content
        structured_content = []
        
        if main_topics:
            structured_content.append({
                "type": "topics",
                "items": main_topics[:5]  # Only include up to 5 topics
            })
            
        if summaries:
            structured_content.append({
                "type": "summary",
                "text": ' '.join(summaries[:3])  # Only include up to 3 paragraphs
            })
            
        web_content.structured_content = structured_content

    def fetch_and_process(self, url: str, mode: str = "basic", use_cache: bool = True) -> Dict[str, Any]:
        """Fetch and process a URL in one operation.

        Args:
            url: The URL to fetch and process
            mode: Processing mode ('basic', 'detailed', or 'summary')
            use_cache: Whether to use cached content if available

        Returns:
            Processed content as dictionary or simple text
        """
        html = self.fetch_url(url, use_cache)

        if not html:
            return {
                "error": f"Failed to fetch content from {url}",
                "url": url,
                "timestamp": time.time()
            }

        web_content = self.process_html(html, url, mode)

        # Get the appropriate format based on mode
        if mode == "detailed":
            result = web_content.to_detailed_dict()
        elif mode == "summary":
            result = web_content.to_summary_dict()
        else:  # "basic" mode
            result = web_content.to_basic_dict()

        # Add a simpler text representation - this is useful for simpler models
        # Create a markdown-formatted text representation
        markdown_text = f"# {result['title']}\n\nSource: {url}\n\n"

        # Add text content
        if "text_content" in result and result["text_content"]:
            markdown_text += result["text_content"]

        # Add the markdown text to the result
        result["markdown_content"] = markdown_text

        # Return the dictionary result directly - we don't need the JSON repair anymore
        return result


# Create a singleton instance
fetcher = WebContentFetcher()