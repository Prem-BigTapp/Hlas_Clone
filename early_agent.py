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

class EarlyInfo(BaseModel):
    """Essential fields for Early Protect (critical illness)."""
    customer_name: Optional[str] = Field(None, description="Full name")
    date_of_birth: Optional[str] = Field(None, description="YYYY-MM-DD")
    gender: Optional[str] = Field(None, description="male/female")
    smoker: Optional[bool] = Field(None, description="true if smoker")
    email: Optional[str] = Field(None, description="email address")
    mobile: Optional[str] = Field(None, description="contact number")
    cover_units: Optional[int] = Field(None, description="Number of CI cover units")
    product_code: Optional[str] = Field(None, description="Internal product code")
    response: str = Field(..., description="Assistant's reply.")

def run_early_agent(user_message: str, chat_history: list, session_id: str):
    """
    Early Protect (Flow A): essentials only, step-by-step.
    """
    session = get_session(session_id)
    collected_info = session.get("collected_info", {}).get("early_info", {})

    required_info = [
        "customer_name",
        "date_of_birth",
        "gender",
        "smoker",
        "email",
        "mobile",
        "cover_units",
        "product_code",
    ]

    chain = llm.with_structured_output(EarlyInfo, method="function_calling")
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = [
        SystemMessage(content=f"""You are a critical illness insurance assistant. Collect ONLY these essentials:
- customer_name
- date_of_birth (YYYY-MM-DD). If user gives DD/MM/YYYY or DD-MM-YYYY, convert to YYYY-MM-DD.
- gender (male/female)
- smoker (true/false)
- email
- mobile
- cover_units (integer)
- product_code

Rules:
- Today is {today}.
- Normalize yes/no to booleans for smoker.
- Confirm briefly and move to the next missing field.
Current collected: {collected_info}
Conversation: {chat_history}
"""),
        HumanMessage(content=user_message),
    ]

    result: EarlyInfo = chain.invoke(prompt)

    for k, v in result.model_dump().items():
        if k != "response" and v not in (None, "", []):
            collected_info[k] = v

    set_collected_info(session_id, "early_info", collected_info)
    logger.info(f"[Early] {session_id} collected={collected_info}")

    if all(k in collected_info and collected_info[k] not in (None, "", []) for k in required_info):
        from app.session_manager import set_stage, update_conversation_context
        set_stage(session_id, "recommendation")
        try:
            from .recommendation_agent import get_recommendation
            from .rec_retriever_agent import get_recommendation_message

            rec = get_recommendation(session_id, "EARLY")
            plan_tier = rec.get("plan", "Standard")

            update_conversation_context(session_id, recommended_plan=plan_tier)
            msg = get_recommendation_message("EARLY", plan_tier)
            msg += "\n\n**What’s Next?**\n" \
                   "🩺 Ask to *compare plan options*\n" \
                   "💬 Ask any *coverage* questions*\n" \
                   "💳 Say **“proceed with purchase”** when ready"
            return msg
        except Exception as e:
            logger.exception("Early recommendation error: %s", e)
            return ("I'm having trouble generating a recommendation right now.\n"
                    "Please try again shortly, or ask me plan/coverage questions.")

    return result.response
