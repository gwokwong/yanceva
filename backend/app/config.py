"""\n配置管理\n统一从项目根目录的 .env 文件加载配置\n"""

import os
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
# 路径: MiroFish/.env (相对于 backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv(override=True)


class Config:
    """Flask配置类"""
    
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    # 端点单次输出 tokens 上限（可选；DeepSeek=8192。设置后 graphiti 的
    # 大 max_tokens 请求会被钳制，避免 400）
    LLM_MAX_OUTPUT_TOKENS = (
        int(os.environ.get('LLM_MAX_OUTPUT_TOKENS', '0') or 0) or None
    )
    
    # 图谱后端配置（Graphiti + Neo4j，取代原 Zep Cloud）
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD')

    # Embedding 配置（Graphiti 向量检索用；缺省回退到 LLM_* 端点）
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY') or os.environ.get('LLM_API_KEY')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL') or os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    EMBEDDING_MODEL_NAME = os.environ.get('EMBEDDING_MODEL_NAME', 'text-embedding-v4')
    EMBEDDING_DIM = int(os.environ.get('EMBEDDING_DIM', '0') or 0) or None
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = 500  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = 50  # 默认重叠大小
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    # ===== 平台订单/支付配置 =====
    # 支付模式：dev（默认，未配置支付渠道时自动标记已支付，仅限本地开发）
    #          stripe（需 STRIPE_API_KEY；Checkout 托管收银台 + webhook 回调）
    PAYMENT_MODE = os.environ.get('PAYMENT_MODE', 'dev')
    # 邮件通知（Resend，免费 100 封/天；未配置则静默跳过）
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
    RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', 'onboarding@resend.dev')
    # 美元→人民币参考汇率（仅用于前端展示；实际扣款由 Creem 按实时汇率结算）
    USD_TO_CNY_RATE = float(os.environ.get('USD_TO_CNY_RATE', '7.25'))  # dev | stripe | creem
    # Creem（MoR，个人可接，支付宝直提人民币）：https://creem.io
    CREEM_API_KEY = os.environ.get('CREEM_API_KEY')
    CREEM_WEBHOOK_SECRET = os.environ.get('CREEM_WEBHOOK_SECRET')
    # 生产环境必须保持 False（否则免费"支付"任意订单）；本地开发设 True
    ALLOW_DEV_PAYMENT = os.environ.get('ALLOW_DEV_PAYMENT', 'false').lower() == 'true'
    # 运维查询全部订单的管理密钥（可选；不配则只能按 user_email 查询）
    ADMIN_KEY = os.environ.get('ADMIN_KEY')
    # CORS 允许来源（逗号分隔；默认 * 保持本地开发兼容，生产建议锁定前端域名）
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
    STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    # 支付成功后的前端跳转地址（Stripe Checkout 用）
    PAYMENT_SUCCESS_URL = os.environ.get(
        'PAYMENT_SUCCESS_URL', 'http://localhost:3000/orders?paid=1')
    # Worker 配置
    WORKER_CONCURRENCY = int(os.environ.get('WORKER_CONCURRENCY', '1'))
    WORKER_POLL_INTERVAL = int(os.environ.get('WORKER_POLL_INTERVAL', '5'))
    
    @classmethod
    def validate(cls) -> list[str]:
        """验证必要配置"""
        errors: list[str] = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        if not cls.NEO4J_PASSWORD:
            errors.append("NEO4J_PASSWORD 未配置")
        if cls.DEBUG:
            import warnings
            warnings.warn("Flask DEBUG mode is enabled. Do not use in production.", RuntimeWarning)
        return errors
