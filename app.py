import argparse
import os
import sys
from api import start_api
from markov_model import MarkovModel
from llm_integration import LLMIntegration
from feedback_system import FeedbackSystem
import config

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="马尔可夫-LLM集成系统")
    
    parser.add_argument("--api", action="store_true", help="启动API服务器")
    parser.add_argument("--interactive", action="store_true", help="启动交互式CLI")
    parser.add_argument("--model_path", default="model_data/markov_model.json", help="马尔可夫模型路径")
    parser.add_argument("--force_update", action="store_true", help="强制更新模型")
    
    return parser.parse_args()


def interactive_cli(model_path):
    """交互式命令行界面"""
    print("正在初始化系统...")
    
    # 初始化各组件
    llm = LLMIntegration()
    feedback_system = FeedbackSystem(model_path=model_path)
    
    print("\n欢迎使用马尔可夫-LLM集成系统")
    print("输入 'exit' 或 'quit' 退出")
    print("输入 'update' 更新模型")
    print("输入 'feedback' 启用反馈模式")
    print("输入 'stats' 显示模型统计信息")
    
    context = {}
    feedback_mode = False
    
    while True:
        try:
            # 获取用户输入
            user_input = input("\n> ")
            
            # 检查特殊命令
            if user_input.lower() in ["exit", "quit"]:
                break
                
            elif user_input.lower() == "update":
                print("正在更新模型...")
                success = feedback_system.update_model()
                print("模型更新成功" if success else "无足够数据更新或更新失败")
                continue
                
            elif user_input.lower() == "feedback":
                feedback_mode = not feedback_mode
                print(f"反馈模式已{'启用' if feedback_mode else '禁用'}")
                continue
                
            elif user_input.lower() == "stats":
                if feedback_system.model:
                    print(f"模型状态数: {len(feedback_system.model.states)}")
                print(f"反馈缓冲区大小: {len(feedback_system.feedback_buffer)}")
                continue
                
            # 获取马尔可夫模型建议
            suggestions = feedback_system.get_suggestions(user_input)
            if suggestions:
                print("\n可能的回复建议:")
                for i, suggestion in enumerate(suggestions, 1):
                    print(f"{i}. {suggestion}")
            
            # 获取LLM回复
            response = llm.generate_response(
                user_input=user_input,
                context=context,
                markov_suggestions=suggestions
            )
            
            print(f"\n系统: {response}")
            
            # 如果启用了反馈模式，收集反馈
            if feedback_mode:
                rating = input("\n请评分(1-5): ")
                try:
                    rating = int(rating)
                    if 1 <= rating <= 5:
                        feedback = {"rating": rating}
                        feedback_system.add_feedback(
                            user_input=user_input,
                            system_response=response,
                            user_feedback=feedback,
                            context=context
                        )
                        print("反馈已记录")
                    else:
                        print("无效评分，应为1-5")
                except ValueError:
                    print("无效评分，应为1-5")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"错误: {str(e)}")
    
    print("正在保存数据...")
    feedback_system.save_feedback_buffer()
    print("再见!")


def main():
    """主函数"""
    args = parse_args()
    
    # 确保模型目录存在
    os.makedirs(os.path.dirname(args.model_path), exist_ok=True)
    
    # 如果需要强制更新模型
    if args.force_update:
        feedback_system = FeedbackSystem(model_path=args.model_path)
        print("正在强制更新模型...")
        success = feedback_system.update_model()
        print("模型更新成功" if success else "无足够数据更新或更新失败")
    
    # 启动API服务器
    if args.api:
        print("正在启动API服务器...")
        start_api()
    
    # 启动交互式CLI
    elif args.interactive:
        interactive_cli(args.model_path)
    
    # 默认启动交互式CLI
    else:
        interactive_cli(args.model_path)


if __name__ == "__main__":
    main() 