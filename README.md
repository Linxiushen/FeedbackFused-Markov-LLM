# 马尔可夫-LLM集成系统

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

结合马尔可夫模型与大语言模型的智能对话系统，具有自动化反馈学习能力。该系统能够根据用户反馈自动调整马尔可夫模型的状态转移概率，提高系统响应的质量和相关性。

## 主要特性

- 马尔可夫模型与LLM集成的混合对话生成
- 自动化反馈学习系统
  - 用户点赞/踩的应答自动标注权重
  - 每周用新数据微调马尔可夫转移概率
  - 重要变更通过Git Hook触发CI/CD
- 稀疏矩阵优化的马尔可夫状态机
- 规则引擎验证层确保响应质量
- 高性能并发处理

## 技术栈

- **后端**: FastAPI, Python 3.9+
- **存储**: PostgreSQL, Redis
- **前端**: React
- **部署**: Docker, CI/CD自动化

## 快速开始

### 环境准备

1. 克隆仓库:
```bash
git clone https://github.com/yourusername/markov-llm.git
cd markov-llm
```

2. 创建并激活虚拟环境:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

3. 安装依赖:
```bash
pip install -r requirements.txt
```

4. 配置环境变量:
```bash
cp .env.example .env
# 编辑.env文件，设置你的API密钥和数据库连接信息
```

### 运行服务

```bash
uvicorn api:app --reload
```

服务将在 http://localhost:8000 启动，API文档可在 http://localhost:8000/docs 查看。

## 自动化反馈学习系统

### 系统架构

自动化反馈学习系统是本项目的核心特性之一，主要分为三个部分：

1. **反馈收集**: 通过用户点赞/踩、评分等方式收集反馈，并自动分配权重
2. **模型微调**: 定期使用收集到的反馈数据更新马尔可夫模型的转移概率
3. **变更管理**: 监测模型变更程度，管理模型版本，重要变更触发CI/CD流程

### 反馈权重分配

系统对不同类型的反馈分配不同权重：

| 反馈类型 | 权重 | 说明 |
|---------|------|------|
| 5星评分 | 2.0 | 强烈喜欢 |
| 4星评分 | 1.5 | 喜欢 |
| 3星评分 | 1.0 | 中性 |
| 2星评分 | 0.5 | 不喜欢 |
| 1星评分 | 0.2 | 强烈不喜欢 |
| 点赞 | 1.8 | 明确正向 |
| 点踩 | 0.3 | 明确负向 |
| 保存/收藏 | 1.6 | 隐式正向 |
| 分享 | 1.7 | 隐式强正向 |
| 复制 | 1.4 | 隐式中正向 |
| 再次使用 | 1.5 | 隐式中强正向 |

### 模型微调流程

1. 系统每天凌晨1点自动收集未处理的反馈数据
2. 每周日凌晨2点执行模型微调：
   - 备份当前模型
   - 处理累积的反馈数据
   - 更新马尔可夫模型转移概率
   - 分析变更程度
   - 如果变更显著，触发Git提交和CI/CD流程

### CI/CD集成

系统通过Git钩子和webhook实现与CI/CD系统的集成：

1. 当模型发生显著变更时，自动提交到Git仓库
2. Git的post-commit钩子检测到显著变更提交时，触发CI/CD webhook
3. CI/CD系统收到通知后，执行自动测试和部署流程

## API接口

### 消息处理

```
POST /api/message
```

处理用户消息并返回响应。

### 反馈提交

```
POST /api/feedback
```

提交评分反馈。

### 反应处理

```
POST /api/reaction
```

处理用户反应（点赞、点踩等）。

### 管理接口

```
POST /api/admin/fine-tune
```

手动触发模型微调（需管理员权限）。

## 贡献

欢迎提交Issue和Pull Request。在提交PR前，请确保代码通过所有测试。

## 许可证

本项目采用MIT许可证。详情请参见LICENSE文件。 