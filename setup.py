from setuptools import find_packages, setup

setup(
    name="notion-age-sync",
    version="0.1.0",
    packages=find_packages(),
    package_dir={"": "src"},
    install_requires=[
        "apache-age-python",
        "chromadb",
        "langchain-chroma",
        "langchain-core",
        "langchain-google-genai",
        "langchain-groq",
        "langchain-ollama",
        "psycopg2-binary",
        "python-dotenv",
        "requests",
        "tiktoken",
    ],
    entry_points={
        "console_scripts": [
            "notion-sync=main:main",
        ],
    },
)
