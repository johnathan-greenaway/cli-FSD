from setuptools import setup, find_packages
import os
import re

# Get version from version.py
with open(os.path.join('cli_FSD', 'version.py'), 'r') as f:
    version_file = f.read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        version = version_match.group(1)
    else:
        raise RuntimeError("Unable to find version string in version.py")

setup(
    name='cli-FSD',
    version=version,
    author='JG',
    author_email='wazacraftRFID@gmail.com',
    description='LLM-enabled companion utility for your terminal.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/wazacraft/cli-FSD',
    packages=find_packages(),
    package_data={
        'cli_FSD': [
            'config_files/*.json',
            'small_context/server.py',
            'small_context/cache.py',
            'small_context/test_server.py'
        ]
    },
    entry_points={
        'console_scripts': [
            '@=cli_FSD.main:main', 
        ],
    },
    install_requires=[
        'Flask',
        'flask-cors',
        'python-dotenv',
        'requests',
        'ollama',
        'groq',
        'beautifulsoup4',
        'aiohttp',
        'redis',
        'pylint',
        'beautifulsoup4',
        'flake8',
        'rich',
        'aiohttp'
    ],
    include_package_data=True,
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
