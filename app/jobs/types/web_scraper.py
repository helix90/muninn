"""
Web scraper job for URL monitoring and content extraction
"""

import requests
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
from app.utils.validators import validate_url
from ..base import BaseJob


class WebScraperJob(BaseJob):
    """Job for scraping web content from URLs."""
    
    job_type = 'web_scraper'
    required_config_fields = ['url', 'selectors']
    optional_config_fields = ['headers', 'timeout', 'user_agent', 'extract_text', 'extract_links']
    
    def _validate_config_values(self):
        """Validate configuration field values."""
        # Validate URL
        url = self.config.get('url')
        if not url or not validate_url(url):
            raise ValueError("Invalid URL provided")

        # Validate selectors
        selectors = self.config.get('selectors')
        if not isinstance(selectors, dict) or not selectors:
            raise ValueError("Selectors must be a non-empty dictionary")

        # Validate timeout
        timeout = self.config.get('timeout', 30)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("Timeout must be a positive number")

        # Validate extract flags
        for flag in ['extract_text', 'extract_links']:
            if flag in self.config and not isinstance(self.config[flag], bool):
                raise ValueError(f"{flag} must be a boolean")
    
    def execute(self, input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the web scraping job.
        
        Args:
            input_data: Optional input data (not used for web scraping)
            
        Returns:
            Dictionary containing scraped content and metadata
        """
        try:
            self.pre_execute(input_data)
            
            # Prepare request
            url = self.config['url']
            headers = self.config.get('headers', {})
            timeout = self.config.get('timeout', 30)
            
            # Set default user agent if not provided
            if 'User-Agent' not in headers:
                headers['User-Agent'] = self.config.get('user_agent', 'Muninn-WebScraper/1.0')
            
            # Make request
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # Parse content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract content based on selectors
            extracted_data = {}
            for key, selector in self.config['selectors'].items():
                elements = soup.select(selector)
                if elements:
                    if self.config.get('extract_text', True):
                        extracted_data[key] = [elem.get_text(strip=True) for elem in elements]
                    else:
                        extracted_data[key] = [str(elem) for elem in elements]
                else:
                    extracted_data[key] = []
            
            # Extract additional data if requested
            if self.config.get('extract_links', False):
                links = soup.find_all('a', href=True)
                extracted_data['links'] = [
                    {
                        'text': link.get_text(strip=True),
                        'href': link['href'],
                        'title': link.get('title', '')
                    }
                    for link in links
                ]
            
            # Prepare result
            result = {
                'url': url,
                'status_code': response.status_code,
                'content_type': response.headers.get('content-type', ''),
                'content_length': len(response.content),
                'extracted_data': extracted_data,
                'timestamp': response.headers.get('date', ''),
                'headers': dict(response.headers)
            }
            
            self.post_execute(result, success=True)
            return result
            
        except requests.RequestException as e:
            error_result = self.handle_error(e)
            self.post_execute(error_result, success=False)
            return error_result
        except Exception as e:
            error_result = self.handle_error(e)
            self.post_execute(error_result, success=False)
            return error_result
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Get the configuration schema for web scraper jobs."""
        schema = super().get_config_schema()
        schema.update({
            'description': 'Scrapes web content from URLs using CSS selectors',
            'example_config': {
                'url': 'https://example.com',
                'selectors': {
                    'title': 'h1',
                    'content': '.content p',
                    'metadata': '.meta'
                },
                'timeout': 30,
                'extract_text': True,
                'extract_links': False
            }
        })
        return schema
