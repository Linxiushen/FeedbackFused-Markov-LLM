import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# LLM配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # 备选
DEEPSEEK_MODEL = "deepseek-r1"
OPENAI_MODEL = "gpt-4o"  # 备选

# 马尔可夫模型配置
DEFAULT_ALPHA = 0.1  # 平滑参数
MIN_PROBABILITY = 0.01
MAX_STATES = 100  # 最大状态数
UPDATE_INTERVAL = 3600  # 模型更新间隔（秒），每小时更新一次

# API配置
API_HOST = "127.0.0.1"
API_PORT = 8000

# 反馈系统配置
FEEDBACK_WEIGHT = 0.2  # 新数据权重
UPDATE_THRESHOLD = 10  # 收集多少反馈后更新模型

# 数据库配置
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "markov_llm")
POSTGRES_URI = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Redis配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_DB = os.getenv("REDIS_DB", "0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_URI = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}" if REDIS_PASSWORD else f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# 模型自动更新
ENABLE_AUTO_UPDATE = True

# CI/CD配置
CICD_WEBHOOK_URL = os.getenv("CICD_WEBHOOK_URL", "")
CICD_API_TOKEN = os.getenv("CICD_API_TOKEN", "")
ENABLE_GIT_INTEGRATION = True  # 是否启用Git集成
SIGNIFICANT_CHANGE_THRESHOLD = 0.15  # 显著变化阈值，超过此值触发CI/CD 