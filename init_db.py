import os
import sys
import argparse
from sqlalchemy import create_engine
from models import Base, User, Conversation, Message, Feedback, MarkovState, MarkovTransition
import config


def create_tables(drop_existing=False):
    """创建数据库表"""
    engine = create_engine(config.POSTGRES_URI)
    
    # 如果需要，先删除所有表
    if drop_existing:
        print("删除现有表...")
        Base.metadata.drop_all(engine)
    
    print("创建数据库表...")
    Base.metadata.create_all(engine)
    print("数据库表创建完成！")


def create_admin_user(username="admin", email="admin@example.com", password="adminpassword"):
    """创建管理员用户"""
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(config.POSTGRES_URI)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # 简单的密码哈希（在实际应用中应使用更安全的方法）
    import hashlib
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    try:
        # 检查用户是否已存在
        existing_user = session.query(User).filter(User.username == username).first()
        
        if existing_user:
            print(f"用户 '{username}' 已存在，跳过创建")
            return
        
        # 创建新用户
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_active=True
        )
        
        session.add(user)
        session.commit()
        print(f"管理员用户 '{username}' 创建成功")
        
    except Exception as e:
        session.rollback()
        print(f"创建管理员用户失败: {str(e)}")
    finally:
        session.close()


def verify_connection():
    """验证数据库连接"""
    engine = create_engine(config.POSTGRES_URI)
    try:
        connection = engine.connect()
        connection.close()
        print("数据库连接成功！")
        return True
    except Exception as e:
        print(f"数据库连接失败: {str(e)}")
        return False


def verify_redis_connection():
    """验证Redis连接"""
    from redis_client import redis_client
    try:
        redis_client.client.ping()
        print("Redis连接成功！")
        return True
    except Exception as e:
        print(f"Redis连接失败: {str(e)}")
        return False


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="数据库初始化工具")
    
    parser.add_argument("--drop", action="store_true", help="删除并重新创建所有表")
    parser.add_argument("--admin", action="store_true", help="创建管理员用户")
    parser.add_argument("--verify", action="store_true", help="验证数据库连接")
    parser.add_argument("--username", default="admin", help="管理员用户名")
    parser.add_argument("--email", default="admin@example.com", help="管理员邮箱")
    parser.add_argument("--password", default="adminpassword", help="管理员密码")
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    # 验证数据库连接
    if args.verify or not args.drop and not args.admin:
        db_ok = verify_connection()
        redis_ok = verify_redis_connection()
        
        if not db_ok or not redis_ok:
            print("数据库或Redis连接失败，退出")
            sys.exit(1)
            
        if not args.drop and not args.admin:
            sys.exit(0)
    
    # 创建表
    if args.drop:
        create_tables(drop_existing=True)
    else:
        create_tables()
    
    # 创建管理员用户
    if args.admin:
        create_admin_user(args.username, args.email, args.password)


if __name__ == "__main__":
    main() 