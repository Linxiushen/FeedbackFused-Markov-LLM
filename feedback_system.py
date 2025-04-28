from typing import Dict, List, Tuple, Optional, Any
import json
import os
import time
from markov_model import MarkovModel
from sqlalchemy.orm import Session
from redis_client import redis_client
import models
import config


class FeedbackSystem:
    def __init__(self, model_path: str = "model_data/markov_model.json"):
        """
        初始化反馈系统
        
        参数:
            model_path: 马尔可夫模型保存路径
        """
        self.model_path = model_path
        self.feedback_buffer: List[Dict[str, Any]] = []
        self.buffer_size = config.UPDATE_THRESHOLD
        self.model: Optional[MarkovModel] = None
        
        # 确保模型目录存在
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        
        # 尝试加载已有模型
        self._load_or_create_model()
    
    def _load_or_create_model(self) -> None:
        """加载或创建新的马尔可夫模型"""
        try:
            if os.path.exists(self.model_path):
                self.model = MarkovModel.load_model(self.model_path)
                print(f"成功从{self.model_path}加载模型")
            else:
                self.model = MarkovModel()
                print("创建了新的马尔可夫模型")
        except Exception as e:
            print(f"加载模型时出错: {str(e)}，创建新模型")
            self.model = MarkovModel()
    
    def add_feedback(self, 
                     user_input: str, 
                     system_response: str, 
                     user_feedback: Dict[str, Any],
                     context: Optional[Dict[str, Any]] = None,
                     db: Optional[Session] = None) -> None:
        """
        添加用户反馈
        
        参数:
            user_input: 用户输入
            system_response: 系统回复
            user_feedback: 用户反馈，包含评分等信息
            context: 上下文信息
            db: 数据库会话
        """
        feedback_entry = {
            "timestamp": time.time(),
            "user_input": user_input,
            "system_response": system_response,
            "user_feedback": user_feedback,
            "context": context or {}
        }
        
        self.feedback_buffer.append(feedback_entry)
        
        # 如果提供了数据库会话，保存到数据库
        if db:
            try:
                # 创建消息记录
                message = models.Message(
                    role="user",
                    content=user_input
                )
                db.add(message)
                db.flush()  # 获取ID
                
                # 添加回复
                response_message = models.Message(
                    role="assistant",
                    content=system_response
                )
                db.add(response_message)
                db.flush()
                
                # 添加反馈
                feedback = models.Feedback(
                    message_id=response_message.id,
                    rating=user_feedback.get("rating", 3),
                    comment=user_feedback.get("comment")
                )
                db.add(feedback)
                
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"保存反馈到数据库时出错: {str(e)}")
        
        # 如果缓冲区满了，更新模型
        if len(self.feedback_buffer) >= self.buffer_size:
            self.update_model()
    
    def update_model(self) -> bool:
        """
        根据反馈更新马尔可夫模型
        
        返回:
            是否成功更新
        """
        if not self.model:
            self._load_or_create_model()
            
        if not self.feedback_buffer:
            return False
            
        try:
            # 准备转移数据
            transitions = []
            weights = []
            
            for entry in self.feedback_buffer:
                # 提取用户输入和系统响应
                user_input = entry["user_input"]
                system_response = entry["system_response"]
                
                # 获取用户反馈分数（假设0-5分制）
                feedback_score = entry["user_feedback"].get("rating", 3)
                normalized_score = feedback_score / 5.0  # 归一化为0-1
                
                # 添加从用户输入到系统响应的转移
                transitions.append((user_input, system_response))
                weights.append(normalized_score)
                
                # 如果有上下文，也可以添加上下文到用户输入的转移
                if entry["context"]:
                    for context_name, context_value in entry["context"].items():
                        if isinstance(context_value, str):
                            transitions.append((context_value, user_input))
                            weights.append(normalized_score * 0.8)  # 降低权重
            
            # 更新模型
            if transitions:
                self.model.update_transition_probabilities(transitions, weights)
                
                # 保存模型
                self.model.save_model(self.model_path)
                
                # 清空反馈缓冲区
                self.feedback_buffer = []
                
                # 清除Redis缓存
                redis_client.clear_cache("suggestions:")
                redis_client.clear_cache("distribution:")
                
                return True
                
        except Exception as e:
            print(f"更新模型时出错: {str(e)}")
            return False
            
        return False
    
    def get_suggestions(self, current_state: str, max_suggestions: int = 3) -> List[str]:
        """
        基于当前状态获取建议回复
        
        参数:
            current_state: 当前状态/用户输入
            max_suggestions: 最大建议数量
            
        返回:
            建议回复列表
        """
        if not self.model:
            self._load_or_create_model()
        
        # 尝试从Redis缓存获取建议
        cached_suggestions = redis_client.get_cached_suggestions(current_state)
        if cached_suggestions:
            return cached_suggestions[:max_suggestions]
            
        if current_state not in self.model.states:
            return []
            
        try:
            # 获取下一状态分布
            distribution = self.model.get_next_state_distribution(current_state)
            
            # 按概率排序
            sorted_states = sorted(distribution.items(), key=lambda x: x[1], reverse=True)
            
            # 获取前N个建议
            suggestions = [state for state, _ in sorted_states[:max_suggestions]]
            
            # 缓存建议到Redis
            redis_client.cache_markov_suggestion(current_state, suggestions)
            
            return suggestions
            
        except Exception as e:
            print(f"获取建议时出错: {str(e)}")
            return []
    
    def save_feedback_buffer(self, filepath: str = "model_data/feedback_buffer.json") -> bool:
        """
        将当前反馈缓冲区保存到文件
        
        参数:
            filepath: 保存路径
            
        返回:
            是否成功保存
        """
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.feedback_buffer, f, ensure_ascii=False, indent=2)
                
            return True
            
        except Exception as e:
            print(f"保存反馈缓冲区时出错: {str(e)}")
            return False
    
    def load_feedback_buffer(self, filepath: str = "model_data/feedback_buffer.json") -> bool:
        """
        从文件加载反馈缓冲区
        
        参数:
            filepath: 加载路径
            
        返回:
            是否成功加载
        """
        try:
            if not os.path.exists(filepath):
                return False
                
            with open(filepath, 'r', encoding='utf-8') as f:
                self.feedback_buffer = json.load(f)
                
            return True
            
        except Exception as e:
            print(f"加载反馈缓冲区时出错: {str(e)}")
            return False
    
    def get_model_statistics(self) -> Dict[str, Any]:
        """
        获取模型统计信息
        
        返回:
            统计信息字典
        """
        stats = {
            "states_count": 0,
            "feedback_count": len(self.feedback_buffer),
            "last_update": None
        }
        
        if self.model:
            stats["states_count"] = len(self.model.states)
            
            # 获取模型文件的最后修改时间
            if os.path.exists(self.model_path):
                stats["last_update"] = os.path.getmtime(self.model_path)
        
        return stats 