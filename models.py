from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime
import config

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # 关系
    conversations = relationship("Conversation", back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(255))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # 关系
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    role = Column(String(20))  # "user" 或 "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # 关系
    conversation = relationship("Conversation", back_populates="messages")
    feedback = relationship("Feedback", back_populates="message", uselist=False)


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"))
    rating = Column(Integer)  # 1-5分
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # 关系
    message = relationship("Message", back_populates="feedback")


class MarkovState(Base):
    __tablename__ = "markov_states"

    id = Column(Integer, primary_key=True, index=True)
    state_key = Column(String(255), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # 关系
    transitions = relationship("MarkovTransition", foreign_keys="MarkovTransition.from_state_id", back_populates="from_state")
    incoming_transitions = relationship("MarkovTransition", foreign_keys="MarkovTransition.to_state_id", back_populates="to_state")


class MarkovTransition(Base):
    __tablename__ = "markov_transitions"

    id = Column(Integer, primary_key=True, index=True)
    from_state_id = Column(Integer, ForeignKey("markov_states.id"))
    to_state_id = Column(Integer, ForeignKey("markov_states.id"))
    probability = Column(Float, default=0.0)
    count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # 关系
    from_state = relationship("MarkovState", foreign_keys=[from_state_id], back_populates="transitions")
    to_state = relationship("MarkovState", foreign_keys=[to_state_id], back_populates="incoming_transitions")


# 创建数据库引擎和会话
engine = create_engine(config.POSTGRES_URI)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 创建数据库表
def create_tables():
    Base.metadata.create_all(bind=engine)


# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 