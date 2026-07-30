# 环境依赖（Python 3.10）

来自项目文档"环境依赖@胡禹成"章节，新建/复现开发环境时以此为准：

```
pydantic>=2.0
pydantic-settings>=2.0
pyyaml>=6.0
langgraph>=0.2.0
langchain-core>=0.3.0
httpx>=0.27.0

# Web Framework
fastapi>=0.110.0
uvicorn[standard]>=0.29.0

# Document Processing
pymupdf>=1.24.0

# Vector Search & Retrieval
faiss-cpu>=1.7.0
rank-bm25>=0.2.2

# Database
sqlalchemy>=2.0
asyncpg>=0.29.0
redis>=5.0
alembic>=1.13.0

# Data
numpy>=1.26.0
typing-extensions>=4.0
```

若后续新增依赖（例如图表理解模型、XGBoost/LightGBM等），请在此文件同步更新，
保证团队成员和CI环境版本一致，避免"我这里能跑"的问题。
