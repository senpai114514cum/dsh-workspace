"""MinerU 批量转换器 —— 图形化界面。

模块划分（便于后续扩展）：
    config.py   设置项、路径自动探测、持久化
    checker.py  输出体检与清理（消幻觉）
    runner.py   任务队列与执行流水线（纯逻辑，不依赖 UI）
    ui.py       tkinter 界面
"""

__version__ = '1.0.0'
APP_NAME = 'MinerU 批量转换器'
