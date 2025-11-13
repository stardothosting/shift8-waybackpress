"""
Configuration and state management for WaybackPress.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class ProjectConfig:
    """Project configuration and state."""
    
    domain: str
    output_dir: Path
    delay: float = 5.0
    concurrency: int = 2
    skip_media: bool = False
    user_agent: str = "WaybackPress/0.1.0"
    
    # State tracking
    discovered: bool = False
    validated: bool = False
    media_fetched: bool = False
    exported: bool = False
    
    def __post_init__(self):
        """Ensure output_dir is a Path object."""
        if not isinstance(self.output_dir, Path):
            self.output_dir = Path(self.output_dir)
    
    @classmethod
    def load(cls, config_path: Path) -> 'ProjectConfig':
        """Load configuration from JSON file."""
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        # Convert output_dir string to Path
        if 'output_dir' in data:
            data['output_dir'] = Path(data['output_dir'])
        
        return cls(**data)
    
    def save(self, config_path: Path) -> None:
        """Save configuration to JSON file."""
        data = asdict(self)
        # Convert Path to string for JSON serialization
        data['output_dir'] = str(self.output_dir)
        
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_paths(self) -> Dict[str, Path]:
        """Get all project paths."""
        return {
            'root': self.output_dir,
            'html': self.output_dir / 'html',
            'media': self.output_dir / 'media',
            'discovered_urls': self.output_dir / 'discovered_urls.tsv',
            'valid_posts': self.output_dir / 'valid_posts.tsv',
            'validation_report': self.output_dir / 'validation_report.csv',
            'media_report': self.output_dir / 'media_report.csv',
            'wxr_export': self.output_dir / 'wordpress-export.xml',
            'log': self.output_dir / 'waybackpress.log',
        }
    
    def create_directories(self) -> None:
        """Create all necessary project directories."""
        paths = self.get_paths()
        paths['root'].mkdir(parents=True, exist_ok=True)
        paths['html'].mkdir(exist_ok=True)
        if not self.skip_media:
            paths['media'].mkdir(exist_ok=True)


def setup_logging(config: ProjectConfig, verbose: bool = False) -> logging.Logger:
    """Configure logging for the project."""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create logger
    logger = logging.getLogger('waybackpress')
    logger.setLevel(log_level)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Console handler
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console_fmt = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    console.setFormatter(console_fmt)
    logger.addHandler(console)
    
    # File handler
    log_path = config.get_paths()['log']
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)
    
    return logger


def init_project(domain: str, output_dir: Optional[Path] = None, **kwargs) -> ProjectConfig:
    """Initialize a new project with configuration."""
    # Normalize domain: strip protocol and www
    import re
    domain = re.sub(r'^https?://', '', domain)
    domain = re.sub(r'^www\.', '', domain)
    domain = domain.rstrip('/')
    
    if output_dir is None:
        output_dir = Path.cwd() / 'wayback-data' / domain
    
    config = ProjectConfig(
        domain=domain,
        output_dir=Path(output_dir),
        **kwargs
    )
    
    config.create_directories()
    
    # Save initial config
    config_path = config.output_dir / 'config.json'
    config.save(config_path)
    
    return config


def load_project(output_dir: Path) -> ProjectConfig:
    """Load existing project configuration."""
    config_path = output_dir / 'config.json'
    if not config_path.exists():
        raise FileNotFoundError(
            f"No project found in {output_dir}. "
            f"Run 'discover' command first to initialize."
        )
    return ProjectConfig.load(config_path)

