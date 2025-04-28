import openai
import httpx
from typing import Dict, List, Any, Optional
import json
import config
import time


class LLMIntegration:
    def __init__(self, 
                 deepseek_api_key: Optional[str] = None, 
                 openai_api_key: Optional[str] = None,
                 deepseek_model: Optional[str] = None,
                 openai_model: Optional[str] = None):
        """
        初始化LLM集成
        
        参数:
            deepseek_api_key: DeepSeek API密钥，默认从配置读取
            openai_api_key: OpenAI API密钥，默认从配置读取
            deepseek_model: 使用的DeepSeek模型名称，默认从配置读取
            openai_model: 使用的OpenAI模型名称，默认从配置读取
        """
        self.deepseek_api_key = deepseek_api_key or config.DEEPSEEK_API_KEY
        self.openai_api_key = openai_api_key or config.OPENAI_API_KEY
        
        if not self.deepseek_api_key and not self.openai_api_key:
            raise ValueError("未提供API密钥，请在.env文件中设置DEEPSEEK_API_KEY或OPENAI_API_KEY")
            
        self.deepseek_model = deepseek_model or config.DEEPSEEK_MODEL
        self.openai_model = openai_model or config.OPENAI_MODEL
        
        # 设置默认API客户端
        if self.deepseek_api_key:
            self.default_client = "deepseek"
            self.client = httpx.Client(timeout=60.0)
        else:
            self.default_client = "openai"
            openai.api_key = self.openai_api_key
        
        # 对话历史
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history_length = 10  # 保留的最大历史消息数
    
    def add_to_history(self, role: str, content: str) -> None:
        """添加消息到对话历史"""
        self.conversation_history.append({"role": role, "content": content})
        
        # 如果历史记录过长，删除最早的消息
        if len(self.conversation_history) > self.max_history_length:
            self.conversation_history = self.conversation_history[-self.max_history_length:]
    
    def clear_history(self) -> None:
        """清除对话历史"""
        self.conversation_history = []
    
    def _call_deepseek(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 500) -> str:
        """调用DeepSeek API"""
        headers = {
            "Authorization": f"Bearer {self.deepseek_api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.deepseek_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        response = self.client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=data
        )
        
        if response.status_code != 200:
            raise Exception(f"DeepSeek API 请求失败: {response.text}")
            
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    def _call_openai(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 500) -> str:
        """调用OpenAI API"""
        response = openai.ChatCompletion.create(
            model=self.openai_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content.strip()
    
    def generate_response(self, 
                          user_input: str, 
                          context: Optional[Dict[str, Any]] = None,
                          markov_suggestions: Optional[List[str]] = None,
                          client: Optional[str] = None) -> str:
        """
        生成对用户输入的响应
        
        参数:
            user_input: 用户输入文本
            context: 附加上下文信息
            markov_suggestions: 马尔可夫模型的建议回复
            client: 指定使用的客户端，"deepseek"或"openai"
        
        返回:
            生成的响应文本
        """
        # 使用指定的客户端或默认客户端
        client = client or self.default_client
        
        # 构建系统提示
        system_message = {
            "role": "system",
            "content": "你是一个由马尔可夫模型增强的智能助手，提供上下文相关的回复。"
        }
        
        # 添加马尔可夫模型建议（如果有）
        if markov_suggestions and len(markov_suggestions) > 0:
            suggestion_text = "以下是基于历史数据的可能回复建议：\n"
            for i, suggestion in enumerate(markov_suggestions, 1):
                suggestion_text += f"{i}. {suggestion}\n"
            
            system_message["content"] += f"\n\n{suggestion_text}\n你可以参考这些建议，但不必完全采纳。"
        
        # 添加上下文信息（如果有）
        if context:
            context_text = "\n\n当前上下文信息：\n"
            for key, value in context.items():
                context_text += f"- {key}: {value}\n"
            
            system_message["content"] += context_text
        
        # 构建消息列表
        messages = [system_message] + self.conversation_history + [{"role": "user", "content": user_input}]
        
        # 调用API
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if client == "deepseek" and self.deepseek_api_key:
                    response_text = self._call_deepseek(messages)
                else:
                    if not self.openai_api_key:
                        raise ValueError("未提供OpenAI API密钥，无法使用备选模型")
                    response_text = self._call_openai(messages)
                
                # 将用户输入和响应添加到历史记录
                self.add_to_history("user", user_input)
                self.add_to_history("assistant", response_text)
                
                return response_text
                
            except Exception as e:
                if attempt < max_retries - 1:
                    # 指数退避重试
                    time.sleep(2 ** attempt)
                    # 如果当前客户端是deepseek并且失败，尝试切换到openai
                    if client == "deepseek" and self.openai_api_key:
                        client = "openai"
                    continue
                else:
                    return f"抱歉，生成回复时出现错误: {str(e)}"
    
    def extract_keywords(self, text: str, max_keywords: int = 5) -> List[str]:
        """
        从文本中提取关键词
        
        参数:
            text: 输入文本
            max_keywords: 最大关键词数量
            
        返回:
            关键词列表
        """
        prompt = f"""
        请从以下文本中提取最多{max_keywords}个关键词，只返回关键词列表，用逗号分隔，不要有其他内容：

        {text}
        """
        
        try:
            if self.default_client == "deepseek" and self.deepseek_api_key:
                keywords_text = self._call_deepseek(
                    [{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=100
                )
            else:
                keywords_text = self._call_openai(
                    [{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=100
                )
            
            keywords = [k.strip() for k in keywords_text.split(",")]
            return keywords[:max_keywords]
            
        except Exception as e:
            print(f"提取关键词时出错: {str(e)}")
            return []
    
    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """
        分析文本情感
        
        参数:
            text: 输入文本
            
        返回:
            情感分析结果字典，包含积极、消极和中性的概率
        """
        prompt = f"""
        请分析以下文本的情感，返回格式为JSON，包含positive、negative和neutral三个值，值为0到1之间的概率，总和为1：

        {text}
        """
        
        try:
            if self.default_client == "deepseek" and self.deepseek_api_key:
                result_text = self._call_deepseek(
                    [{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=100
                )
            else:
                result_text = self._call_openai(
                    [{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=100
                )
            
            # 提取JSON
            try:
                # 尝试直接解析
                sentiment = json.loads(result_text)
            except json.JSONDecodeError:
                # 如果直接解析失败，尝试从文本中提取JSON部分
                import re
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if json_match:
                    try:
                        sentiment = json.loads(json_match.group(0))
                    except:
                        # 如果仍然失败，返回默认值
                        return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}
                else:
                    return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}
            
            # 确保包含所有必要的键
            required_keys = ["positive", "negative", "neutral"]
            for key in required_keys:
                if key not in sentiment:
                    sentiment[key] = 0.33
                    
            # 确保概率总和为1
            total = sum(sentiment.values())
            if total > 0:
                for key in sentiment:
                    sentiment[key] = sentiment[key] / total
                    
            return sentiment
            
        except Exception as e:
            print(f"情感分析时出错: {str(e)}")
            return {"positive": 0.33, "negative": 0.33, "neutral": 0.34} 