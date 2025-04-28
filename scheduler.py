from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import logging
import datetime
from feedback_system import FeedbackSystem
from typing import Callable, Optional
import config

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler")


class MarkovUpdateScheduler:
    def __init__(self, model_path: str = "model_data/markov_model.json"):
        """
        初始化马尔可夫模型更新调度器
        
        参数:
            model_path: 马尔可夫模型保存路径
        """
        self.scheduler = BackgroundScheduler()
        self.feedback_system = FeedbackSystem(model_path=model_path)
        self.is_running = False
    
    def start(self) -> None:
        """启动调度器"""
        if self.is_running:
            logger.warning("调度器已在运行中")
            return
            
        # 添加每小时更新模型的任务
        self.scheduler.add_job(
            self.update_model,
            IntervalTrigger(seconds=config.UPDATE_INTERVAL),
            id="markov_update",
            replace_existing=True,
            next_run_time=datetime.datetime.now() + datetime.timedelta(minutes=1)  # 启动后1分钟开始第一次运行
        )
        
        # 添加每天凌晨保存反馈数据的任务
        self.scheduler.add_job(
            self.save_feedback_buffer,
            CronTrigger(hour=0, minute=0),
            id="save_feedback",
            replace_existing=True
        )
        
        self.scheduler.start()
        self.is_running = True
        logger.info("马尔可夫模型更新调度器已启动")
    
    def stop(self) -> None:
        """停止调度器"""
        if not self.is_running:
            logger.warning("调度器未运行")
            return
            
        self.scheduler.shutdown()
        self.is_running = False
        logger.info("马尔可夫模型更新调度器已停止")
    
    def update_model(self) -> None:
        """更新马尔可夫模型"""
        logger.info("开始更新马尔可夫模型")
        
        try:
            success = self.feedback_system.update_model()
            if success:
                logger.info("马尔可夫模型更新成功")
            else:
                logger.info("无需更新或无足够的反馈数据")
        except Exception as e:
            logger.error(f"更新马尔可夫模型出错: {str(e)}")
    
    def save_feedback_buffer(self) -> None:
        """保存反馈缓冲区"""
        logger.info("开始保存反馈缓冲区")
        
        try:
            success = self.feedback_system.save_feedback_buffer()
            if success:
                logger.info("反馈缓冲区保存成功")
            else:
                logger.warning("保存反馈缓冲区失败")
        except Exception as e:
            logger.error(f"保存反馈缓冲区出错: {str(e)}")
    
    def add_job(self, func: Callable, trigger: str, **kwargs) -> None:
        """
        添加自定义任务
        
        参数:
            func: 任务函数
            trigger: 触发器类型，如'interval'、'cron'等
            **kwargs: 其他参数
        """
        self.scheduler.add_job(func, trigger, **kwargs)
        logger.info(f"已添加自定义任务: {func.__name__}")


# 创建单例实例
scheduler = MarkovUpdateScheduler()