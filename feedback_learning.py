import os
import json
import logging
import datetime
import subprocess
import shutil
from typing import Dict, List, Any, Optional, Union, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
import git
from apscheduler.triggers.cron import CronTrigger

import config
from models import Feedback, Message, User
from feedback_system import FeedbackSystem
from scheduler import scheduler, logger

# 扩展日志
feedback_logger = logging.getLogger("feedback_learning")
handler = logging.FileHandler("logs/feedback_learning.log")
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
feedback_logger.addHandler(handler)
feedback_logger.setLevel(logging.INFO)


class FeedbackLearningSystem:
    """自动化反馈学习系统"""
    
    def __init__(self, feedback_system: FeedbackSystem, model_path: str = "model_data/markov_model.json"):
        """
        初始化反馈学习系统
        
        参数:
            feedback_system: 反馈系统实例
            model_path: 马尔可夫模型路径
        """
        self.feedback_system = feedback_system
        self.model_path = model_path
        self.model_backup_dir = "model_data/backups"
        self.significant_change_threshold = 0.15  # 显著变化阈值
        
        # 确保备份目录存在
        os.makedirs(self.model_backup_dir, exist_ok=True)
        
        # 反馈权重配置
        self.feedback_weights = {
            5: 2.0,    # 强烈喜欢 (5星)
            4: 1.5,    # 喜欢 (4星)
            3: 1.0,    # 中性 (3星)
            2: 0.5,    # 不喜欢 (2星)
            1: 0.2,    # 强烈不喜欢 (1星)
            "like": 1.8,      # 点赞
            "dislike": 0.3,   # 点踩
            "save": 1.6,      # 保存/收藏
            "share": 1.7,     # 分享
            "copy": 1.4,      # 复制
            "reuse": 1.5      # 再次使用
        }
        
        # 跟踪学习状态
        self.last_weekly_update = None
        self.processed_feedback_ids = set()
        
        # 初始化Git仓库（如果存在）
        self.repo = self._init_git_repo()
    
    def _init_git_repo(self) -> Optional[git.Repo]:
        """初始化Git仓库"""
        try:
            # 假设当前目录是Git仓库
            return git.Repo(".")
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            feedback_logger.warning("当前目录不是Git仓库，CI/CD集成将不可用")
            return None
    
    def process_star_rating(self, message_id: int, rating: int, db: Session) -> bool:
        """
        处理星级评分反馈
        
        参数:
            message_id: 消息ID
            rating: 评分 (1-5)
            db: 数据库会话
            
        返回:
            是否成功处理
        """
        if rating < 1 or rating > 5:
            feedback_logger.warning(f"评分值 {rating} 无效，应为1-5")
            return False
        
        try:
            # 获取消息和相关用户输入
            message = db.query(Message).filter(Message.id == message_id).first()
            if not message:
                feedback_logger.warning(f"消息ID {message_id} 不存在")
                return False
            
            # 获取对应的用户输入
            user_message = db.query(Message).filter(
                and_(
                    Message.conversation_id == message.conversation_id,
                    Message.role == "user",
                    Message.created_at < message.created_at
                )
            ).order_by(desc(Message.created_at)).first()
            
            if not user_message:
                feedback_logger.warning(f"找不到消息 {message_id} 对应的用户输入")
                return False
            
            # 获取权重
            weight = self.feedback_weights.get(rating, 1.0)
            
            # 添加到反馈系统
            self.feedback_system.add_feedback(
                user_input=user_message.content,
                system_response=message.content,
                user_feedback={"rating": rating, "weight": weight},
                db=db
            )
            
            # 记录已处理的反馈ID
            feedback = db.query(Feedback).filter(Feedback.message_id == message_id).first()
            if feedback:
                self.processed_feedback_ids.add(feedback.id)
            
            feedback_logger.info(f"成功处理消息 {message_id} 的星级评分 {rating}，权重 {weight}")
            return True
            
        except Exception as e:
            feedback_logger.error(f"处理星级评分时出错: {str(e)}")
            return False
    
    def process_reaction(self, message_id: int, reaction_type: str, db: Session) -> bool:
        """
        处理反应类型反馈 (点赞、点踩等)
        
        参数:
            message_id: 消息ID
            reaction_type: 反应类型 ('like', 'dislike', 'save', 'share', 'copy', 'reuse')
            db: 数据库会话
            
        返回:
            是否成功处理
        """
        valid_reactions = ["like", "dislike", "save", "share", "copy", "reuse"]
        if reaction_type not in valid_reactions:
            feedback_logger.warning(f"反应类型 {reaction_type} 无效")
            return False
        
        try:
            # 获取消息和相关用户输入
            message = db.query(Message).filter(Message.id == message_id).first()
            if not message:
                feedback_logger.warning(f"消息ID {message_id} 不存在")
                return False
            
            # 获取对应的用户输入
            user_message = db.query(Message).filter(
                and_(
                    Message.conversation_id == message.conversation_id,
                    Message.role == "user",
                    Message.created_at < message.created_at
                )
            ).order_by(desc(Message.created_at)).first()
            
            if not user_message:
                feedback_logger.warning(f"找不到消息 {message_id} 对应的用户输入")
                return False
            
            # 获取权重
            weight = self.feedback_weights.get(reaction_type, 1.0)
            
            # 点踩类型使用较低的反馈评分
            rating = 2 if reaction_type == "dislike" else 4
            
            # 添加到反馈系统
            self.feedback_system.add_feedback(
                user_input=user_message.content,
                system_response=message.content,
                user_feedback={"rating": rating, "reaction": reaction_type, "weight": weight},
                db=db
            )
            
            feedback_logger.info(f"成功处理消息 {message_id} 的反应 {reaction_type}，权重 {weight}")
            return True
            
        except Exception as e:
            feedback_logger.error(f"处理反应反馈时出错: {str(e)}")
            return False
    
    def collect_unprocessed_feedback(self, db: Session) -> int:
        """
        收集未处理的反馈
        
        参数:
            db: 数据库会话
            
        返回:
            处理的反馈数量
        """
        try:
            # 查询所有未处理的反馈
            feedbacks = db.query(Feedback).filter(
                Feedback.id.notin_(self.processed_feedback_ids) if self.processed_feedback_ids else True
            ).all()
            
            count = 0
            for feedback in feedbacks:
                # 获取消息和对应的用户输入
                message = db.query(Message).filter(Message.id == feedback.message_id).first()
                if not message:
                    continue
                
                user_message = db.query(Message).filter(
                    and_(
                        Message.conversation_id == message.conversation_id,
                        Message.role == "user",
                        Message.created_at < message.created_at
                    )
                ).order_by(desc(Message.created_at)).first()
                
                if not user_message:
                    continue
                
                # 根据评分获取权重
                weight = self.feedback_weights.get(feedback.rating, 1.0)
                
                # 添加到反馈系统
                self.feedback_system.add_feedback(
                    user_input=user_message.content,
                    system_response=message.content,
                    user_feedback={"rating": feedback.rating, "comment": feedback.comment, "weight": weight},
                    db=db
                )
                
                # 记录已处理ID
                self.processed_feedback_ids.add(feedback.id)
                count += 1
            
            if count > 0:
                feedback_logger.info(f"收集了 {count} 条未处理的反馈")
            
            return count
            
        except Exception as e:
            feedback_logger.error(f"收集未处理反馈时出错: {str(e)}")
            return 0
    
    def perform_weekly_update(self, db: Session) -> Tuple[bool, Optional[str]]:
        """
        执行每周模型更新
        
        参数:
            db: 数据库会话
            
        返回:
            (是否成功, 更新摘要)
        """
        feedback_logger.info("开始执行每周模型更新")
        
        try:
            # 先备份当前模型
            backup_path = self._backup_model()
            
            # 收集未处理的反馈
            self.collect_unprocessed_feedback(db)
            
            # 更新马尔可夫模型
            update_success = self.feedback_system.update_model()
            if not update_success:
                feedback_logger.info("没有足够数据进行更新")
                return False, "没有足够数据进行更新"
            
            # 计算变更程度
            change_degree, change_summary = self._calculate_model_changes(backup_path)
            
            # 更新时间
            self.last_weekly_update = datetime.datetime.now()
            
            # 记录更新结果
            result = f"模型更新成功，变更程度: {change_degree:.2f}, {change_summary}"
            feedback_logger.info(result)
            
            # 如果变更显著，提交到Git并触发CI/CD
            if change_degree > self.significant_change_threshold:
                self._handle_significant_change(change_summary, change_degree)
            
            return True, result
            
        except Exception as e:
            error_msg = f"执行每周更新时出错: {str(e)}"
            feedback_logger.error(error_msg)
            return False, error_msg
    
    def _backup_model(self) -> str:
        """
        备份当前模型
        
        返回:
            备份文件路径
        """
        # 生成备份文件名，包含时间戳
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"markov_model_{timestamp}.json"
        backup_path = os.path.join(self.model_backup_dir, backup_filename)
        
        # 复制当前模型文件
        if os.path.exists(self.model_path):
            shutil.copy2(self.model_path, backup_path)
            feedback_logger.info(f"模型已备份到 {backup_path}")
        else:
            feedback_logger.warning(f"模型文件 {self.model_path} 不存在，无法备份")
        
        return backup_path
    
    def _calculate_model_changes(self, backup_path: str) -> Tuple[float, str]:
        """
        计算模型变更程度
        
        参数:
            backup_path: 备份文件路径
            
        返回:
            (变更程度, 变更摘要)
        """
        if not os.path.exists(backup_path) or not os.path.exists(self.model_path):
            return 0.0, "无法比较变更"
        
        try:
            # 加载备份和当前模型
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_model = json.load(f)
            
            with open(self.model_path, 'r', encoding='utf-8') as f:
                current_model = json.load(f)
            
            # 比较状态数量
            old_states = len(backup_model.get('states', []))
            new_states = len(current_model.get('states', []))
            states_change = abs(new_states - old_states) / max(1, old_states)
            
            # 比较转移矩阵
            old_matrix = backup_model.get('transition_matrix', [])
            new_matrix = current_model.get('transition_matrix', [])
            
            if not isinstance(old_matrix, list) or not isinstance(new_matrix, list):
                matrix_change = 0.0
            else:
                # 简化版本：比较矩阵大小变化
                matrix_size_change = abs(len(new_matrix) - len(old_matrix)) / max(1, len(old_matrix))
                
                # 更复杂的比较：取样比较一些转移概率
                prob_changes = []
                for i in range(min(10, len(old_matrix), len(new_matrix))):
                    old_row = old_matrix[i] if i < len(old_matrix) else []
                    new_row = new_matrix[i] if i < len(new_matrix) else []
                    
                    for j in range(min(10, len(old_row), len(new_row))):
                        if isinstance(old_row[j], (int, float)) and isinstance(new_row[j], (int, float)):
                            prob_changes.append(abs(new_row[j] - old_row[j]))
                
                avg_prob_change = sum(prob_changes) / len(prob_changes) if prob_changes else 0.0
                matrix_change = (matrix_size_change + avg_prob_change) / 2
            
            # 综合变更程度
            overall_change = (states_change + matrix_change) / 2
            
            # 生成变更摘要
            summary = f"状态数: {old_states} → {new_states} (变化: {states_change:.2f}), "
            summary += f"矩阵变化: {matrix_change:.2f}"
            
            return overall_change, summary
            
        except Exception as e:
            feedback_logger.error(f"计算模型变更时出错: {str(e)}")
            return 0.0, f"计算变更出错: {str(e)}"
    
    def _handle_significant_change(self, change_summary: str, change_degree: float) -> bool:
        """
        处理显著变更
        
        参数:
            change_summary: 变更摘要
            change_degree: 变更程度
            
        返回:
            是否成功处理
        """
        if not self.repo:
            feedback_logger.warning("Git仓库未初始化，无法处理显著变更")
            return False
        
        try:
            # 生成提交消息
            commit_message = f"[自动] 马尔可夫模型显著更新 (变更度: {change_degree:.2f})\n\n{change_summary}"
            
            # 添加模型文件到Git
            self.repo.git.add(self.model_path)
            
            # 提交变更
            self.repo.git.commit('-m', commit_message)
            
            # 如果配置了远程仓库，推送变更
            if "origin" in [remote.name for remote in self.repo.remotes]:
                self.repo.git.push("origin")
                feedback_logger.info("已将变更推送到远程仓库")
            
            # 触发CI/CD webhook
            self._trigger_cicd_webhook(change_summary, change_degree)
            
            feedback_logger.info(f"已处理显著变更: {commit_message}")
            return True
            
        except Exception as e:
            feedback_logger.error(f"处理显著变更时出错: {str(e)}")
            return False
    
    def _trigger_cicd_webhook(self, change_summary: str, change_degree: float) -> bool:
        """
        触发CI/CD webhook
        
        参数:
            change_summary: 变更摘要
            change_degree: 变更程度
            
        返回:
            是否成功触发
        """
        # 获取webhook URL（应从配置中读取）
        webhook_url = os.environ.get("CICD_WEBHOOK_URL", "")
        if not webhook_url:
            feedback_logger.warning("未配置CI/CD webhook URL，跳过触发")
            return False
        
        try:
            # 准备webhook数据
            payload = {
                "event_type": "markov_model_update",
                "client_payload": {
                    "change_degree": change_degree,
                    "change_summary": change_summary,
                    "timestamp": datetime.datetime.now().isoformat()
                }
            }
            
            # 使用curl发送webhook请求
            curl_cmd = [
                "curl", "-X", "POST",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(payload),
                webhook_url
            ]
            
            result = subprocess.run(curl_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                feedback_logger.info(f"成功触发CI/CD webhook: {result.stdout}")
                return True
            else:
                feedback_logger.error(f"触发CI/CD webhook失败: {result.stderr}")
                return False
                
        except Exception as e:
            feedback_logger.error(f"触发CI/CD webhook时出错: {str(e)}")
            return False


# 创建部署Git钩子的函数
def install_git_hooks():
    """安装Git钩子"""
    if not os.path.exists(".git/hooks"):
        logger.warning("Git钩子目录不存在")
        return False
    
    # post-commit钩子
    post_commit_hook = """#!/bin/bash
# 检查是否是马尔可夫模型更新
if git log -1 | grep -q '\\[自动\\] 马尔可夫模型显著更新'; then
    echo "检测到马尔可夫模型显著更新，触发CI/CD..."
    
    # 如果配置了CI/CD的API令牌和URL
    if [ ! -z "$CICD_API_TOKEN" ] && [ ! -z "$CICD_API_URL" ]; then
        # 提取变更度
        CHANGE_DEGREE=$(git log -1 --pretty=%B | grep -oP '变更度: \\K[0-9.]+')
        
        # 触发CI/CD
        curl -X POST \\
          -H "Authorization: token $CICD_API_TOKEN" \\
          -H "Content-Type: application/json" \\
          -d "{\\"event_type\\":\\"markov_model_update\\",\\"client_payload\\":{\\"change_degree\\":\\"$CHANGE_DEGREE\\"}}" \\
          $CICD_API_URL
        
        echo "CI/CD触发完成"
    else
        echo "未配置CI/CD令牌或URL，跳过触发"
    fi
fi
"""
    
    # 写入post-commit钩子
    with open(".git/hooks/post-commit", "w") as f:
        f.write(post_commit_hook)
    
    # 添加执行权限
    os.chmod(".git/hooks/post-commit", 0o755)
    
    logger.info("Git钩子安装成功")
    return True


# 注册定时任务
def register_feedback_learning_tasks(feedback_learning_system):
    """注册自动化反馈学习任务"""
    # 每周一凌晨2点执行模型微调
    scheduler.add_job(
        lambda: feedback_learning_system.perform_weekly_update(next(get_db())),
        CronTrigger(day_of_week=0, hour=2, minute=0),  # 每周日凌晨2点
        id="weekly_model_update",
        replace_existing=True
    )
    
    # 每天收集未处理的反馈
    scheduler.add_job(
        lambda: feedback_learning_system.collect_unprocessed_feedback(next(get_db())),
        CronTrigger(hour=1, minute=0),  # 每天凌晨1点
        id="daily_feedback_collection",
        replace_existing=True
    )
    
    logger.info("自动化反馈学习任务已注册")


# 初始化
def init_feedback_learning():
    """初始化反馈学习系统"""
    # 创建反馈学习系统实例
    from feedback_system import FeedbackSystem
    from models import get_db
    
    feedback_system = FeedbackSystem()
    feedback_learning_system = FeedbackLearningSystem(feedback_system)
    
    # 注册定时任务
    register_feedback_learning_tasks(feedback_learning_system)
    
    # 安装Git钩子
    install_git_hooks()
    
    return feedback_learning_system 