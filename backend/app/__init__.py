"""
MiroFish Backend - Flask应用工厂
"""

import os
import warnings

# 抑制 multiprocessing resource_tracker 的警告（来自第三方库如 transformers）
# 需要在所有其他导入之前设置
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 设置JSON编码：确保中文直接显示（而不是 \uXXXX 格式）
    # Flask >= 2.3 使用 app.json.ensure_ascii，旧版本使用 JSON_AS_ASCII 配置
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # 设置日志
    logger = setup_logger('mirofish')
    
    # 只在 reloader 子进程中打印启动信息（避免 debug 模式下打印两次）
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend 启动中...")
        logger.info("=" * 50)
    
    # 启用CORS
    cors_origins = [o.strip() for o in Config.CORS_ORIGINS.split(',') if o.strip()] or '*'
    CORS(app, resources={r"/api/*": {"origins": cors_origins}})

    if Config.PAYMENT_MODE == 'dev':
        logger.warning(
            "=" * 60)
        logger.warning(
            "⚠️  PAYMENT_MODE=dev：免费支付通道的状态取决于 ALLOW_DEV_PAYMENT。"
        )
        logger.warning(
            "   生产部署请设置 PAYMENT_MODE=stripe 并配置 STRIPE_API_KEY！"
        )
        logger.warning(
            "=" * 60)
    
    # 注册模拟进程清理函数（确保服务器关闭时终止所有模拟进程）
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("已注册模拟进程清理函数")
    
    # 请求日志中间件
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"请求: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"请求体: {request.get_json(silent=True)}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"响应: {response.status_code}")
        return response
    
    # 注册蓝图
    from .api import graph_bp, simulation_bp, report_bp, campaign_bp, order_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(campaign_bp, url_prefix='/api/campaign')
    app.register_blueprint(order_bp, url_prefix='/api/orders')
    
    # 健康检查
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}

    # 生产部署：直接服务前端构建产物（frontend/dist），SPA fallback
    frontend_dist = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '../../frontend/dist'))
    if os.path.isdir(frontend_dist):
        from flask import send_from_directory

        @app.route('/')
        @app.route('/<path:spa_path>')
        def spa_frontend(spa_path: str = 'index.html'):
            full = os.path.normpath(os.path.join(frontend_dist, spa_path))
            if full.startswith(frontend_dist) and os.path.isfile(full):
                return send_from_directory(frontend_dist, spa_path)
            # SPA 路由（/orders 等）回退到 index.html
            return send_from_directory(frontend_dist, 'index.html')

        if should_log_startup:
            logger.info(f"前端静态资源已挂载: {frontend_dist}")
    
    if should_log_startup:
        logger.info("MiroFish Backend 启动完成")
    
    return app

