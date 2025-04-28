import numpy as np
import json
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Set, Optional
import config


class MarkovModel:
    def __init__(self, alpha: float = config.DEFAULT_ALPHA):
        """
        初始化马尔可夫模型
        
        参数:
            alpha: 平滑参数，用于处理未见过的状态转移
        """
        self.states: Set[str] = set()  # 状态集合
        self.state_indices: Dict[str, int] = {}  # 状态到索引的映射
        self.transition_matrix = None  # 转移概率矩阵
        self.alpha = alpha  # 平滑参数
        self.state_count = 0  # 状态数量
    
    def add_states(self, states: List[str]) -> None:
        """添加新状态到模型"""
        new_states = [s for s in states if s not in self.states]
        for state in new_states:
            if len(self.states) < config.MAX_STATES:  # 限制状态数量
                self.states.add(state)
                self.state_indices[state] = len(self.state_indices)
        
        # 更新状态数量
        self.state_count = len(self.states)
        
        # 如果转移矩阵已存在，则调整其大小
        if self.transition_matrix is not None:
            old_size = self.transition_matrix.shape[0]
            if old_size < self.state_count:
                new_matrix = np.zeros((self.state_count, self.state_count))
                new_matrix[:old_size, :old_size] = self.transition_matrix
                self.transition_matrix = new_matrix
        else:
            # 初始化转移矩阵
            self.transition_matrix = np.zeros((self.state_count, self.state_count))
    
    def update_transition_probabilities(self, transitions: List[Tuple[str, str]], 
                                        weights: Optional[List[float]] = None) -> None:
        """
        更新转移概率
        
        参数:
            transitions: 状态转移列表，每个元素为(当前状态, 下一状态)
            weights: 每个转移的权重，默认为等权重
        """
        if not transitions:
            return
            
        # 确保所有状态都已添加
        all_states = set()
        for current, next_state in transitions:
            all_states.add(current)
            all_states.add(next_state)
        self.add_states(list(all_states))
        
        # 如果未提供权重，则使用等权重
        if weights is None:
            weights = [1.0] * len(transitions)
            
        # 更新转移计数
        for (current, next_state), weight in zip(transitions, weights):
            current_idx = self.state_indices[current]
            next_idx = self.state_indices[next_state]
            self.transition_matrix[current_idx, next_idx] += weight
            
        # 应用平滑并归一化
        self._normalize_matrix()
    
    def _normalize_matrix(self) -> None:
        """应用平滑并归一化转移矩阵"""
        # 添加平滑
        smoothed_matrix = self.transition_matrix + self.alpha
        
        # 按行归一化
        row_sums = smoothed_matrix.sum(axis=1, keepdims=True)
        self.transition_matrix = smoothed_matrix / row_sums
        
        # 处理全零行（未见过的状态）
        zero_rows = (row_sums == 0).flatten()
        if np.any(zero_rows):
            self.transition_matrix[zero_rows, :] = 1.0 / self.state_count
    
    def get_next_state_distribution(self, current_state: str) -> Dict[str, float]:
        """获取给定当前状态的下一状态概率分布"""
        if current_state not in self.state_indices:
            # 未见过的状态，返回均匀分布
            return {state: 1.0 / self.state_count for state in self.states}
            
        current_idx = self.state_indices[current_state]
        distribution = {}
        
        for state, idx in self.state_indices.items():
            prob = self.transition_matrix[current_idx, idx]
            if prob >= config.MIN_PROBABILITY:  # 仅保留高于阈值的概率
                distribution[state] = prob
                
        # 重新归一化
        total = sum(distribution.values())
        return {state: prob / total for state, prob in distribution.items()}
    
    def predict_next_state(self, current_state: str) -> str:
        """基于当前状态预测下一个状态"""
        distribution = self.get_next_state_distribution(current_state)
        states = list(distribution.keys())
        probabilities = list(distribution.values())
        
        return np.random.choice(states, p=probabilities)
    
    def predict_sequence(self, start_state: str, length: int) -> List[str]:
        """预测状态序列"""
        sequence = [start_state]
        current = start_state
        
        for _ in range(length - 1):
            current = self.predict_next_state(current)
            sequence.append(current)
            
        return sequence
    
    def visualize_transitions(self, top_n: int = 10) -> None:
        """可视化转移概率矩阵（显示前N个状态）"""
        n = min(top_n, self.state_count)
        if n <= 1:
            print("状态数量不足，无法可视化")
            return
            
        # 获取前N个状态
        states = list(self.states)[:n]
        indices = [self.state_indices[s] for s in states]
        
        # 提取子矩阵
        sub_matrix = self.transition_matrix[np.ix_(indices, indices)]
        
        # 可视化
        plt.figure(figsize=(10, 8))
        plt.imshow(sub_matrix, cmap='viridis', interpolation='nearest')
        plt.colorbar(label='转移概率')
        plt.xticks(range(n), states, rotation=45)
        plt.yticks(range(n), states)
        plt.xlabel('下一状态')
        plt.ylabel('当前状态')
        plt.title('状态转移概率矩阵')
        plt.tight_layout()
        plt.show()
    
    def save_model(self, filepath: str) -> None:
        """保存模型到文件"""
        model_data = {
            'states': list(self.states),
            'state_indices': self.state_indices,
            'transition_matrix': self.transition_matrix.tolist(),
            'alpha': self.alpha,
            'state_count': self.state_count
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(model_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load_model(cls, filepath: str) -> 'MarkovModel':
        """从文件加载模型"""
        with open(filepath, 'r', encoding='utf-8') as f:
            model_data = json.load(f)
            
        model = cls(alpha=model_data['alpha'])
        model.states = set(model_data['states'])
        model.state_indices = {k: int(v) for k, v in model_data['state_indices'].items()}
        model.transition_matrix = np.array(model_data['transition_matrix'])
        model.state_count = model_data['state_count']
        
        return model 