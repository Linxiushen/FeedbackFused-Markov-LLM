from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uvicorn
import json
import time
import os
from datetime import datetime

from markov_model import MarkovModel
from llm_integration import LLMIntegration
from feedback_system import FeedbackSystem
from redis_client import redis_client
from scheduler import scheduler
from models import User, Conversation, Message, Feedback, get_db
from sqlalchemy.orm import Session
import config

# 初始化组件
llm = LLMIntegration()
feedback_system = FeedbackSystem()

# 导入反馈学习系统
from feedback_learning import init_feedback_learning

# 初始化反馈学习系统
feedback_learning_system = init_feedback_learning()

# 创建FastAPI应用
app = FastAPI(
    title="马尔可夫-LLM集成系统",
    description="结合马尔可夫模型与大语言模型的智能对话系统API",
    version="1.0.0"
)

# 允许CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件目录，用于React前端
if os.path.exists("frontend/build"):
    app.mount("/", StaticFiles(directory="frontend/build", html=True), name="static")


# 模型定义
class MessageRequest(BaseModel):
    user_input: str
    conversation_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None
    use_markov_suggestions: bool = True


class FeedbackRequest(BaseModel):
    message_id: int
    rating: int = Field(..., ge=1, le=5, description="评分（1-5分）")
    comment: Optional[str] = None


class ReactionRequest(BaseModel):
    message_id: int
    reaction_type: str = Field(..., description="反应类型: like, dislike, save, share, copy, reuse")


class MessageResponse(BaseModel):
    id: Optional[int] = None
    response: str
    suggestions: List[str] = []
    processing_time: float
    conversation_id: Optional[int] = None


class StatusResponse(BaseModel):
    status: str
    message: str


class ConversationResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class StatsResponse(BaseModel):
    states_count: int
    feedback_count: int
    last_update: Optional[float] = None
    active_users: int
    total_conversations: int
    total_messages: int


# API路由
@app.post("/api/message", response_model=MessageResponse)
async def process_message(request: MessageRequest, db: Session = Depends(get_db)):
    """处理用户消息并返回响应"""
    start_time = time.time()
    message_id = None
    conversation_id = request.conversation_id
    
    try:
        # 检查Redis缓存是否有之前的回复
        cache_key = f"response:{request.user_input}"
        cached_response = redis_client.get(cache_key)
        
        # 如果有缓存且不需要上下文，直接返回
        if cached_response and not request.context:
            processing_time = time.time() - start_time
            return MessageResponse(
                response=cached_response.get("response", ""),
                suggestions=cached_response.get("suggestions", []),
                processing_time=processing_time,
                conversation_id=conversation_id
            )
        
        # 获取马尔可夫模型建议（如果需要）
        suggestions = []
        if request.use_markov_suggestions:
            suggestions = feedback_system.get_suggestions(request.user_input)
        
        # 获取LLM回复
        response = llm.generate_response(
            user_input=request.user_input,
            context=request.context,
            markov_suggestions=suggestions
        )
        
        # 保存到数据库
        try:
            # 如果没有会话ID，创建新会话
            if not conversation_id:
                conversation = Conversation(
                    title=request.user_input[:50] + ("..." if len(request.user_input) > 50 else "")
                )
                db.add(conversation)
                db.flush()
                conversation_id = conversation.id
            
            # 添加用户消息
            user_message = Message(
                conversation_id=conversation_id,
                role="user",
                content=request.user_input
            )
            db.add(user_message)
            
            # 添加系统回复
            system_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=response
            )
            db.add(system_message)
            db.commit()
            
            message_id = system_message.id
            
        except Exception as e:
            db.rollback()
            print(f"保存消息到数据库时出错: {str(e)}")
        
        # 缓存响应到Redis
        if response:
            redis_client.set(
                cache_key, 
                {"response": response, "suggestions": suggestions},
                ex=3600  # 缓存1小时
            )
        
        processing_time = time.time() - start_time
        
        return MessageResponse(
            id=message_id,
            response=response,
            suggestions=suggestions,
            processing_time=processing_time,
            conversation_id=conversation_id
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/feedback", response_model=StatusResponse)
async def submit_feedback(request: FeedbackRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """提交用户反馈"""
    try:
        # 查找消息
        message = db.query(Message).filter(Message.id == request.message_id).first()
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 查找相关用户输入
        user_message = db.query(Message).filter(
            Message.conversation_id == message.conversation_id,
            Message.role == "user"
        ).order_by(Message.created_at.desc()).first()
        
        if not user_message:
            raise HTTPException(status_code=404, detail="找不到相关的用户输入")
        
        # 创建或更新反馈
        feedback = db.query(Feedback).filter(Feedback.message_id == message.id).first()
        if feedback:
            feedback.rating = request.rating
            feedback.comment = request.comment
        else:
            feedback = Feedback(
                message_id=message.id,
                rating=request.rating,
                comment=request.comment
            )
            db.add(feedback)
        
        db.commit()
        
        # 在后台处理反馈数据
        background_tasks.add_task(
            feedback_system.add_feedback,
            user_message.content,
            message.content,
            {"rating": request.rating, "comment": request.comment},
            db=db
        )
        
        return StatusResponse(
            status="success",
            message="反馈已接收"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/update_model", response_model=StatusResponse)
async def update_model():
    """手动触发模型更新"""
    try:
        success = feedback_system.update_model()
        
        if success:
            return StatusResponse(
                status="success",
                message="模型已更新"
            )
        else:
            return StatusResponse(
                status="warning",
                message="无需更新或无足够的反馈数据"
            )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats(db: Session = Depends(get_db)):
    """获取系统统计信息"""
    try:
        # 获取模型统计信息
        model_stats = feedback_system.get_model_statistics()
        
        # 获取数据库统计信息
        active_users = db.query(User).filter(User.is_active == True).count()
        total_conversations = db.query(Conversation).count()
        total_messages = db.query(Message).count()
        
        return StatsResponse(
            states_count=model_stats["states_count"],
            feedback_count=model_stats["feedback_count"],
            last_update=model_stats["last_update"],
            active_users=active_users,
            total_conversations=total_conversations,
            total_messages=total_messages
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversations", response_model=List[ConversationResponse])
async def get_conversations(limit: int = 10, offset: int = 0, db: Session = Depends(get_db)):
    """获取最近的会话列表"""
    try:
        conversations = db.query(Conversation).order_by(
            Conversation.updated_at.desc()
        ).offset(offset).limit(limit).all()
        
        result = []
        for conv in conversations:
            # 计算消息数量
            message_count = db.query(Message).filter(
                Message.conversation_id == conv.id
            ).count()
            
            result.append(ConversationResponse(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=message_count
            ))
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversation/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: int, db: Session = Depends(get_db)):
    """获取会话中的消息"""
    try:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.asc()).all()
        
        result = []
        for msg in messages:
            # 获取反馈信息
            feedback = db.query(Feedback).filter(
                Feedback.message_id == msg.id
            ).first()
            
            msg_data = {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
                "feedback": None
            }
            
            if feedback:
                msg_data["feedback"] = {
                    "rating": feedback.rating,
                    "comment": feedback.comment
                }
            
            result.append(msg_data)
        
        return {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
            "messages": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/conversation/{conversation_id}")
async def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    """删除会话"""
    try:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 删除相关消息和反馈
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).all()
        
        for msg in messages:
            db.query(Feedback).filter(Feedback.message_id == msg.id).delete()
        
        db.query(Message).filter(Message.conversation_id == conversation_id).delete()
        db.query(Conversation).filter(Conversation.id == conversation_id).delete()
        
        db.commit()
        
        return {"status": "success", "message": "会话已删除"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": time.time()}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "path": str(request.url.path)}
    )


# 启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    # 启动调度器
    if config.ENABLE_AUTO_UPDATE:
        scheduler.start()


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    # 停止调度器
    scheduler.stop()


# 辅助函数
def start_api():
    """启动API服务器"""
    uvicorn.run(
        "api:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=True
    )


# 用户反应端点
@app.post("/api/reaction", response_model=StatusResponse)
async def process_reaction(
    request: ReactionRequest,
    db: Session = Depends(get_db)
):
    """处理用户反应（点赞、点踩等）"""
    try:
        success = feedback_learning_system.process_reaction(request.message_id, request.reaction_type, db)
        
        if success:
            return StatusResponse(
                status="success",
                message=f"已记录反应: {request.reaction_type}"
            )
        else:
            raise HTTPException(status_code=400, detail=f"处理反应失败")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 触发手动微调端点（仅限管理员）
@app.post("/api/admin/fine-tune", response_model=Dict[str, Any])
async def trigger_fine_tuning(db: Session = Depends(get_db)):
    """触发模型手动微调（管理员权限）"""
    try:
        success, result = feedback_learning_system.perform_weekly_update(db)
        
        return {
            "success": success,
            "result": result
        }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 