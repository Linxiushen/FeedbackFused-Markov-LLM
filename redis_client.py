import json
import redis
from typing import Dict, List, Any, Optional, Union
import config


class RedisClient:
    def __init__(self, redis_uri: Optional[str] = None):
        """
        初始化Redis客户端
        
        参数:
            redis_uri: Redis连接URI，默认从配置获取
        """
        self.redis_uri = redis_uri or config.REDIS_URI
        self.client = redis.from_url(self.redis_uri)
        self.prefix = "markov_llm:"  # 键前缀，避免与其他应用冲突
    
    def _format_key(self, key: str) -> str:
        """格式化键名，添加前缀"""
        return f"{self.prefix}{key}"
    
    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """
        设置键值
        
        参数:
            key: 键名
            value: 值（会被JSON序列化）
            ex: 过期时间（秒）
            
        返回:
            是否成功
        """
        formatted_key = self._format_key(key)
        
        try:
            # 将值JSON序列化
            serialized_value = json.dumps(value, ensure_ascii=False)
            self.client.set(formatted_key, serialized_value, ex=ex)
            return True
        except Exception as e:
            print(f"Redis设置键值失败: {str(e)}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取键值
        
        参数:
            key: 键名
            default: 默认值
            
        返回:
            值（已反序列化）或默认值
        """
        formatted_key = self._format_key(key)
        
        try:
            value = self.client.get(formatted_key)
            
            if value is None:
                return default
                
            # 反序列化JSON
            return json.loads(value)
        except Exception as e:
            print(f"Redis获取键值失败: {str(e)}")
            return default
    
    def delete(self, key: str) -> bool:
        """
        删除键
        
        参数:
            key: 键名
            
        返回:
            是否成功
        """
        formatted_key = self._format_key(key)
        
        try:
            self.client.delete(formatted_key)
            return True
        except Exception as e:
            print(f"Redis删除键失败: {str(e)}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        检查键是否存在
        
        参数:
            key: 键名
            
        返回:
            是否存在
        """
        formatted_key = self._format_key(key)
        
        try:
            return bool(self.client.exists(formatted_key))
        except Exception as e:
            print(f"Redis检查键是否存在失败: {str(e)}")
            return False
    
    def expire(self, key: str, seconds: int) -> bool:
        """
        设置键过期时间
        
        参数:
            key: 键名
            seconds: 过期秒数
            
        返回:
            是否成功
        """
        formatted_key = self._format_key(key)
        
        try:
            return bool(self.client.expire(formatted_key, seconds))
        except Exception as e:
            print(f"Redis设置过期时间失败: {str(e)}")
            return False
    
    def cache_markov_suggestion(self, input_text: str, suggestions: List[str], ttl: int = 3600) -> bool:
        """
        缓存马尔可夫模型建议
        
        参数:
            input_text: 输入文本
            suggestions: 建议列表
            ttl: 缓存有效期（秒）
            
        返回:
            是否成功
        """
        cache_key = f"suggestions:{input_text}"
        return self.set(cache_key, suggestions, ex=ttl)
    
    def get_cached_suggestions(self, input_text: str) -> Optional[List[str]]:
        """
        获取缓存的马尔可夫模型建议
        
        参数:
            input_text: 输入文本
            
        返回:
            建议列表，如果没有缓存则返回None
        """
        cache_key = f"suggestions:{input_text}"
        return self.get(cache_key)
    
    def cache_state_distribution(self, state: str, distribution: Dict[str, float], ttl: int = 3600) -> bool:
        """
        缓存状态转移分布
        
        参数:
            state: 当前状态
            distribution: 转移概率分布
            ttl: 缓存有效期（秒）
            
        返回:
            是否成功
        """
        cache_key = f"distribution:{state}"
        return self.set(cache_key, distribution, ex=ttl)
    
    def get_cached_distribution(self, state: str) -> Optional[Dict[str, float]]:
        """
        获取缓存的状态转移分布
        
        参数:
            state: 当前状态
            
        返回:
            转移概率分布，如果没有缓存则返回None
        """
        cache_key = f"distribution:{state}"
        return self.get(cache_key)
    
    def store_user_session(self, user_id: str, session_data: Dict[str, Any], ttl: int = 86400) -> bool:
        """
        存储用户会话数据
        
        参数:
            user_id: 用户ID
            session_data: 会话数据
            ttl: 会话有效期（秒），默认一天
            
        返回:
            是否成功
        """
        session_key = f"session:{user_id}"
        return self.set(session_key, session_data, ex=ttl)
    
    def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户会话数据
        
        参数:
            user_id: 用户ID
            
        返回:
            会话数据，如果不存在则返回None
        """
        session_key = f"session:{user_id}"
        return self.get(session_key)
    
    def clear_cache(self, prefix: str = "") -> bool:
        """
        清除缓存
        
        参数:
            prefix: 键前缀，为空则清除所有缓存
            
        返回:
            是否成功
        """
        pattern = f"{self.prefix}{prefix}*"
        
        try:
            # 获取匹配模式的所有键
            keys = self.client.keys(pattern)
            
            if not keys:
                return True
                
            # 批量删除
            self.client.delete(*keys)
            return True
        except Exception as e:
            print(f"Redis清除缓存失败: {str(e)}")
            return False


# 创建单例实例
redis_client = RedisClient() 