"""Enhanced web tool plugin with improved content extraction and retry logic."""

import requests
from bs4 import BeautifulSoup
import time
from typing import Dict, Any
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from plugin_system import WebTool, ToolMetadata


class EnhancedWebTool(WebTool):
    """Enhanced web content tool with better extraction and retry logic."""
    
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="enhanced_web",
            version="1.0.0",
            description="Enhanced web content fetching with smart extraction and retry logic",
            author="CLI-FSD Enhancement",
            category="web",
            priority=95,  # Higher than standard MCP tool
            dependencies=["requests", "bs4"],
            supports_autopilot=True,
            requires_confirmation=False
        )
    
    def can_handle(self, operation: str, **kwargs) -> bool:
        """Check if this tool can handle the operation."""
        return operation == "fetch_content"
    
    def fetch_content(self, url: str, **kwargs) -> Dict[str, Any]:
        """Fetch and intelligently extract content from a URL."""
        try:
            # Multiple attempts with different strategies
            strategies = [
                self._fetch_with_headers,
                self._fetch_with_session,
                self._fetch_basic
            ]
            
            for i, strategy in enumerate(strategies):
                try:
                    response = strategy(url)
                    if response:
                        content = self._extract_content(response, url)
                        return {
                            'success': True,
                            'content': content,
                            'strategy_used': i + 1,
                            'url': url
                        }
                except Exception as e:
                    if i == len(strategies) - 1:  # Last strategy
                        raise e
                    time.sleep(1)  # Brief delay between strategies
                    
            return {'success': False, 'error': 'All fetch strategies failed'}
            
        except Exception as e:
            return {'success': False, 'error': f"Enhanced web fetch failed: {str(e)}"}
    
    def _fetch_with_headers(self, url: str) -> requests.Response:
        """Fetch with comprehensive headers."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response
    
    def _fetch_with_session(self, url: str) -> requests.Response:
        """Fetch using a session with cookies."""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
        response = session.get(url, timeout=12)
        response.raise_for_status()
        return response
    
    def _fetch_basic(self, url: str) -> requests.Response:
        """Basic fetch as fallback."""
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response
    
    def _extract_content(self, response: requests.Response, url: str) -> str:
        """Intelligently extract content based on the website."""
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "aside"]):
            script.decompose()
        
        # Site-specific extraction
        if 'news.ycombinator.com' in url:
            return self._extract_hackernews(soup)
        elif 'reddit.com' in url:
            return self._extract_reddit(soup)
        elif 'github.com' in url:
            return self._extract_github(soup)
        else:
            return self._extract_generic(soup)
    
    def _extract_hackernews(self, soup: BeautifulSoup) -> str:
        """Extract Hacker News content."""
        stories = []
        story_elements = soup.select('tr.athing')
        
        for i, story in enumerate(story_elements[:15]):
            title_element = story.select_one('td.title > span.titleline > a')
            if title_element:
                title = title_element.get_text(strip=True)
                link = title_element.get('href', '')
                
                # Get additional info from next row
                score_row = story.find_next_sibling('tr')
                score_text = "Unknown score"
                comments_text = "0 comments"
                
                if score_row:
                    score_element = score_row.select_one('span.score')
                    if score_element:
                        score_text = score_element.get_text(strip=True)
                    
                    comment_links = score_row.select('a')
                    for a in comment_links:
                        if 'comment' in a.get_text():
                            comments_text = a.get_text(strip=True)
                            break
                
                stories.append(f"{i+1}. {title}")
                stories.append(f"   {score_text} | {comments_text}")
                if link:
                    stories.append(f"   Link: {link}")
                stories.append("")
        
        return "# Hacker News Top Stories\n\n" + "\n".join(stories)
    
    def _extract_reddit(self, soup: BeautifulSoup) -> str:
        """Extract Reddit content."""
        posts = []
        
        # Try different selectors for reddit posts
        post_selectors = [
            'div[data-testid="post-container"]',
            '.Post',
            'div.thing'
        ]
        
        for selector in post_selectors:
            post_elements = soup.select(selector)
            if post_elements:
                break
        
        for i, post in enumerate(post_elements[:10]):
            title_element = post.select_one('h3, .title a, [data-testid="post-content"] h3')
            if title_element:
                title = title_element.get_text(strip=True)
                posts.append(f"{i+1}. {title}")
                posts.append("")
        
        return "# Reddit Posts\n\n" + "\n".join(posts) if posts else self._extract_generic(soup)
    
    def _extract_github(self, soup: BeautifulSoup) -> str:
        """Extract GitHub content."""
        content = []
        
        # Repository name
        repo_name = soup.select_one('strong[itemprop="name"] a, h1 strong a')
        if repo_name:
            content.append(f"# {repo_name.get_text(strip=True)}")
            content.append("")
        
        # Description
        description = soup.select_one('p[itemprop="about"], .repository-content .f4')
        if description:
            content.append(description.get_text(strip=True))
            content.append("")
        
        # README content
        readme = soup.select_one('#readme article, .markdown-body')
        if readme:
            content.append("## README")
            content.append(readme.get_text(separator='\n', strip=True)[:2000])
        
        return "\n".join(content) if content else self._extract_generic(soup)
    
    def _extract_generic(self, soup: BeautifulSoup) -> str:
        """Generic content extraction."""
        # Try to find main content areas
        content_selectors = [
            'main',
            'article',
            '.content',
            '.main-content',
            '#content',
            '.post-content',
            '.entry-content'
        ]
        
        main_content = None
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                main_content = element
                break
        
        if not main_content:
            main_content = soup.find('body') or soup
        
        # Extract text with some structure preservation
        text = main_content.get_text(separator='\n', strip=True)
        
        # Clean up excessive whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Limit size
        content = '\n'.join(lines)
        if len(content) > 5000:
            content = content[:5000] + "\n\n[Content truncated...]"
        
        return content