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

class ChoiceInfo(BaseModel):
    """Essential fields for Choice Protect."""
    policy_start_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    cep_customer: Optional[bool] = Field(None, description="CEP customer?")
    first_time_cep: Optional[bool] = Field(None, description="First CEP purchase?")
    riders: Optional[bool] = Field(None, description="Include riders?")
    spouse_coverage: Optional[bool] = Field(None, description="Include spouse?")
    children_coverage: Optional[bool] = Field(None, description="Include children?")
    premium_payment_frequency: Optional[str] = Field(None, description="monthly or yearly")
    response: str = Field(..., description="Assistant's reply.")

def run_choice_agent(user_message: str, chat_history: list, session_id: str):
    """
    Choice Protect (Flow A): essentials only, step-by-step.
    """
    session = get_session(session_id)
    collected_info = session.get("collected_info", {}).get("choice_info", {})

    required_info = [
        "policy_start_date",
        "cep_customer",
        "first_time_cep",
        "riders",
        "spouse_coverage",
        "children_coverage",
        "premium_payment_frequency",
    ]

    chain = llm.with_structured_output(ChoiceInfo, method="function_calling")
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = [
        SystemMessage(content=f"""You are a Choice Protect assistant. Collect ONLY these essentials:
- policy_start_date (YYYY-MM-DD; today or later)
- cep_customer (true/false)
- first_time_cep (true/false)
- riders (true/false)
- spouse_coverage (true/false)
- children_coverage (true/false)
- premium_payment_frequency (monthly/yearly)

Rules:
- Today is {today}. Validate date.
- Normalize yes/no to booleans.
- Short confirmations; then ask next missing item.
Current collected: {collected_info}
Conversation: {chat_history}
"""),
        HumanMessage(content=user_message),
    ]

    result: ChoiceInfo = chain.invoke(prompt)

    for k, v in result.model_dump().items():
        if k != "response" and v not in (None, "", []):
            collected_info[k] = v

    set_collected_info(session_id, "choice_info", collected_info)
    logger.info(f"[Choice] {session_id} collected={collected_info}")

    if all(k in collected_info and collected_info[k] not in (None, "", []) for k in required_info):
        from app.session_manager import set_stage, update_conversation_context
        set_stage(session_id, "recommendation")
        try:
            from .recommendation_agent import get_recommendation
            from .rec_retriever_agent import get_recommendation_message

            rec = get_recommendation(session_id, "CHOICE")
            plan_tier = rec.get("plan", "Standard")

            update_conversation_context(session_id, recommended_plan=plan_tier)
            msg = get_recommendation_message("CHOICE", plan_tier)
            msg += "\n\n**What’s Next?**\n" \
                   "🧩 Ask to *compare riders/options*\n" \
                   "💬 Ask *coverage* questions*\n" \
                   "💳 Say **“proceed with purchase”** when ready"
            return msg
        except Exception as e:
            logger.exception("Choice recommendation error: %s", e)
            return ("I'm having trouble generating a Choice Protect recommendation right now.\n"
                    "Please try again shortly, or ask plan/coverage questions.")

    return result.response
