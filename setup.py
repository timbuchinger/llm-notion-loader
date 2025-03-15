from setuptools import find_packages, setup

setup(
    name="llm-notion-loader",
    version="0.1.0",
    description="A tool for synchronizing Notion pages to vector databases with LLM-powered features",
    author="",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "pinecone-client",
        "python-dotenv",
        "requests",
        "pyyaml",
        "tiktoken",
        "langchain-core",
        "langchain-google-genai",
        "langchain-groq",
        "langchain-ollama",
    ],
    entry_points={
        "console_scripts": [
            "notion-sync=src.main:main",
        ],
    },
    python_requires=">=3.8",
)
