import os
import re
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator
from typing import List, Type, Optional

from app.config import llm
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.tools import Tool
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.messages import HumanMessage, AIMessage

from app.session_manager import set_collected_info, get_collected_info

logger = logging.getLogger(__name__)

from app.session_manager import get_session, update_session
from utils.llm_services import llm
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
import json

class CarInfo(BaseModel):
    """Essential fields for Car Protect 360."""
    car_model: Optional[str] = Field(None, description="Vehicle make/model, e.g., 'Toyota Corolla'.")
    year_of_registration: Optional[int] = Field(None, description="First registration year, e.g., 2019.")
    usage_type: Optional[str] = Field(None, description="private or commercial")
    plan_type: Optional[str] = Field(None, description="e.g., Comprehensive")
    policy_start_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    response: str = Field(..., description="The assistant's conversational reply.")

def run_car_agent(user_message: str, chat_history: list, session_id: str):
    """
    Car Protect (Flow A): collect only essentials, step-by-step.
    """
    session = get_session(session_id)
    collected_info = session.get("collected_info", {}).get("car_info", {})

    required_info = ["car_model", "year_of_registration", "usage_type", "plan_type", "policy_start_date"]

    chain = llm.with_structured_output(CarInfo, method="function_calling")
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = [
        SystemMessage(content=f"""You are a helpful car insurance assistant. 
Collect ONLY these essentials:
- car_model
- year_of_registration
- usage_type (private/commercial)
- plan_type (e.g., Comprehensive)
- policy_start_date (YYYY-MM-DD)

Rules:
- Today is {today}. policy_start_date must be today or later. If past, ask again.
- If user gives "2018" after asking registration year, map to year_of_registration.
- Normalize usage_type to "private" or "commercial".
- Always acknowledge what they gave and ask the next missing item.
Current collected: {collected_info}
Conversation history: {chat_history}
"""),
        HumanMessage(content=user_message),
    ]

    result: CarInfo = chain.invoke(prompt)

    # persist
    for k, v in result.model_dump().items():
        if k != "response" and v not in (None, "", []):
            collected_info[k] = v

    set_collected_info(session_id, "car_info", collected_info)
    logger.info(f"[Car] {session_id} collected={collected_info}")

    # completeness
    if all(k in collected_info and collected_info[k] not in (None, "", []) for k in required_info):
        from app.session_manager import set_stage, update_conversation_context
        set_stage(session_id, "recommendation")
        try:
            from .recommendation_agent import get_recommendation
            from .rec_retriever_agent import get_recommendation_message

            rec = get_recommendation(session_id, "CAR")
            plan_tier = rec.get("plan", "Comprehensive")

            update_conversation_context(session_id, recommended_plan=plan_tier)
            msg = get_recommendation_message("CAR", plan_tier)
            msg += "\n\n**What’s Next?**\n" \
                   "🚗 Ask me to *compare plan options*\n" \
                   "💬 Ask any *coverage* questions\n" \
                   "💳 Say **“proceed with purchase”** when ready"
            return msg
        except Exception as e:
            logger.exception("Car recommendation error: %s", e)
            return ("I'm having trouble generating a car insurance recommendation right now.\n"
                    "Please try again shortly, or ask me specific questions about plans/coverage.")

    return result.response
