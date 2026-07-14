from typing import TypedDict
from langgraph import StateGraph, START, END

class State(TypedDict):
    name: str
    values: list[int]
    operation: str
    result: str

def calculate_and_format(state: State) -> State:
    if state["operation"] == "sum":
        result = sum(state["values"])
    elif state["operation"] == "product":
        result = 1
        for value in state["values"]:
            result *= value
    else:
        raise ValueError(f"Unsupported operation: {state['operation']}")
    # 更新状态中的 result 字段
    state["result"] = str(result)
    return state

# 创建状态图
graph_builder = StateGraph(State)

# 添加节点
graph_builder.add_node("calculate_and_format", calculate_and_format)

# 添加边
graph_builder.add_edge(START, "calculate_and_format")
graph_builder.add_edge("calculate_and_format", END)

# 编译图
graph = graph_builder.compile()

# 测试运行
if __name__ == "__main__":
    input_state = {
        "name": "test",
        "values": [1, 2, 3, 4],
        "operation": "sum",
        "result": ""
    }
    output = graph.invoke(input_state)
    print(f"计算结果: {output['result']}")