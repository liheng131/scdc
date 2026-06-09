import asyncio
from app.agents.master_agent import MasterAgent, MasterDecision
from app.services.workflow import workflow_service

print("MasterAgent imported OK")
print(f"WorkflowService.master_agent      = {type(workflow_service.master_agent).__name__}")
print(f"WorkflowService._intent_classifier= {type(workflow_service._intent_classifier).__name__}")
print(f"WorkflowService._direct_response  = {type(workflow_service._direct_response).__name__}")


async def test():
    # 1) 简单闲聊 -> direct
    decision = await workflow_service.master_agent.process_message(
        message="你好",
        conversation_history=[],
        use_rag=False,
    )
    print("\n[test 1] 闲聊 - 期望 action=direct")
    print(f"  action={decision.action}  intent={decision.intent_type}  conf={decision.confidence:.2f}  use_rag={decision.extra.get('use_rag')}")

    # 2) 复杂问题 -> orchestrate
    decision = await workflow_service.master_agent.process_message(
        message="2025年AI芯片市场趋势",
        conversation_history=[],
        use_rag=True,
    )
    print("\n[test 2] 复杂问题 - 期望 action=orchestrate")
    print(f"  action={decision.action}  intent={decision.intent_type}  conf={decision.confidence:.2f}  use_rag={decision.extra.get('use_rag')}")

    # 3) 复杂历史后问简单问题 -> direct (Task 2 修复验证)
    history = [
        {"role": "user", "content": "帮我分析2025年AI芯片市场趋势"},
        {"role": "assistant", "content": "已生成完整的AI芯片市场分析报告..."},
    ]
    decision = await workflow_service.master_agent.process_message(
        message="你会做什么",
        conversation_history=history,
        use_rag=False,
        has_existing_report=True,
    )
    print("\n[test 3] 复杂历史后问简单问题 - 期望 action=direct (Task 2 修复)")
    print(f"  action={decision.action}  intent={decision.intent_type}  conf={decision.confidence:.2f}  use_rag={decision.extra.get('use_rag')}")

    # 4) 回退 (workflow_reentry)
    decision = await workflow_service.master_agent.process_message(
        message="分析不够详细，重新分析",
        conversation_history=history,
        use_rag=False,
        has_existing_report=True,
    )
    print("\n[test 4] 回退请求 - 期望 action=reentry")
    print(f"  action={decision.action}  intent={decision.intent_type}  conf={decision.confidence:.2f}  target_stage={decision.target_stage}")


asyncio.run(test())
