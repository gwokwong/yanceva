"""
API路由模块
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
campaign_bp = Blueprint('campaign', __name__)
order_bp = Blueprint('order', __name__)

from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
from . import campaign  # noqa: E402, F401
from . import order  # noqa: E402, F401

