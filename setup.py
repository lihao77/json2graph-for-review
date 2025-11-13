"""json2graph包的安装配置文件"""

from setuptools import setup, find_packages
import os

# 读取README文件
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# 读取requirements文件
with open(os.path.join(here, 'requirements.txt'), encoding='utf-8') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="json2graph",
    version="0.1.0",
    author="lihao77",
    author_email="anonymous",
    description="JSON到图数据库的动态转换框架",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/lihao77/json2graph",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Database",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.8",
            "mypy>=0.800",
        ],
        "docs": [
            "sphinx>=4.0",
            "sphinx-rtd-theme>=0.5",
        ],
    },
    entry_points={
        "console_scripts": [
            "json2graph=json2graph.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords="json graph database neo4j knowledge-graph spatio-temporal",
    project_urls={
        "Bug Reports": "https://github.com/lihao77/json2graph/issues",
        "Source": "https://github.com/lihao77/json2graph",
        "Documentation": "https://json2graph.readthedocs.io/",
    },
)