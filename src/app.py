
import os
import logging
import chainlit as cl

from dotenv import load_dotenv

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END

from typing import Annotated, Literal, TypedDict
from api_agent import api_agent_manager


# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()
print(f"OpenAI API Key present: {'OPENAI_API_KEY' in os.environ}")

# Allow dangerous requests for OpenAPI agent
ALLOW_DANGEROUS_REQUEST = True

class State(TypedDict):
    messages: Annotated[list, add_messages]


# Use the @tool decorator to properly define the tool
@tool
async def api_tool(query: str) -> str:
    """Find and use the appropriate API to answer a query"""
    try:
        result = await api_agent_manager.execute_query(query)
        return result
    except Exception as e:
        logger.error(f"Error using API tool: {str(e)}")
        return f"Error using API tool: {str(e)}"

# Set up LLM with proper tool binding
llm = AzureChatOpenAI(api_version="2024-05-01-preview", azure_deployment="gpt-4o")
llm_with_tools = llm.bind_tools([api_tool])

# Set up tool node properly
tool_node = ToolNode(tools=[api_tool])

def call_llm(state):
    logger.debug(f"Calling LLM for: {state['messages']}")
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state) -> Literal["continue", "end"]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "continue"
    
    return "end"

# Build LangGraph
uncompiled_graph = StateGraph(State)
uncompiled_graph.add_node("agent", call_llm)
uncompiled_graph.add_node("action", tool_node)

uncompiled_graph.add_edge(START, "agent")
uncompiled_graph.add_conditional_edges(
    "agent", 
    should_continue,
    {"continue": "action", "end": END}
)
uncompiled_graph.add_edge("action", "agent")

compiled_graph = uncompiled_graph.compile()

# Chainlit setup
@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("compiled_graph", compiled_graph)
    intro_text = "Welcome to the API Assistant! I can help you use various APIs to answer your questions. What would you like to know?"
    elements = [
        cl.Text(name="API Assistant", content=intro_text, display="inline")
    ]
    await cl.Message(
        content="",
        elements=elements,
    ).send()

@cl.on_message
async def on_message(message: cl.Message):
    compiled_graph = cl.user_session.get("compiled_graph")
    msg = cl.Message(content="")
    
    inputs = {"messages": [
        SystemMessage(content="You are an expert in using APIs to answer user questions. Use the api_tool function to find the appropriate API and get the information needed."),
        HumanMessage(content=f"{message.content}")
    ]}
    
    logger.info(f"Inputs: {inputs}")
    messages = []
    
    await msg.stream_token("Finding the right API, please wait...\n")
    
    async for chunk in compiled_graph.astream(inputs, stream_mode="updates"):
        for node, values in chunk.items():
            logger.info(f"\nReceiving update from node: '{node}'")
            await msg.stream_token(f"Receiving update from node: '{node}'\n")
            logger.debug(values["messages"])
            messages.append(values["messages"])

    final_llm_response = messages[-1][0].content
    final_llm_metadata = messages[-1][0].response_metadata

    logger.info(f"Response: {final_llm_response}")
    logger.info(f"Metadata: {final_llm_metadata}")

    await msg.stream_token(f"{final_llm_response}\n")
    await msg.send()
