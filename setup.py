"""
Setup script for WaybackPress
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read long description from README
readme_file = Path(__file__).parent / 'README.md'
long_description = readme_file.read_text(encoding='utf-8') if readme_file.exists() else ''

setup(
    name='waybackpress',
    version='0.1.0',
    author='Shift8 Web',
    author_email='info@shift8web.ca',
    description='Recover WordPress sites from the Internet Archive Wayback Machine',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/stardothosting/shift8-waybackpress',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Topic :: Internet :: WWW/HTTP :: Site Management',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    python_requires='>=3.8',
    install_requires=[
        'beautifulsoup4>=4.11.0',
        'lxml>=4.9.0',
        'aiohttp>=3.8.0',
        'python-dateutil>=2.8.0',
    ],
    entry_points={
        'console_scripts': [
            'waybackpress=waybackpress.cli:main',
        ],
    },
    keywords='wordpress wayback-machine archive recovery backup migration',
    project_urls={
        'Bug Reports': 'https://github.com/stardothosting/shift8-waybackpress/issues',
        'Source': 'https://github.com/stardothosting/shift8-waybackpress',
    },
)

