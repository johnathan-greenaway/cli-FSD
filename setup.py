from setuptools import setup, find_packages

setup(
    name='cli-FSD',
    version='1.2.98',
    author='JG',
    author_email='wazacraftRFID@gmail.com',
    description='LLM-enabled companion utility for your terminal.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/wazacraft/cli-FSD',
    packages=find_packages(),
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
        'groq'
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
  
