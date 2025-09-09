# region

# import os
# import re
# from enum import Enum
# from dotenv import load_dotenv
# from pydantic import BaseModel, Field, validator
# from langchain_core.messages import HumanMessage, SystemMessage
# from utils.llm_services import llm
# import logging

# logger = logging.getLogger(__name__)

# # Define Pydantic Models as per the instructions
# class Product(str, Enum):
#     """Enumeration for the different products."""
#     TRAVEL = "TRAVEL"
#     MAID = "MAID"
#     POLICY_CLAIM_STATUS = "POLICY_CLAIM_STATUS"
#     UNKNOWN = "UNKNOWN"

# class Intent(BaseModel):
#     """Pydantic model that will be used for the function calling output."""
#     product: Product = Field(default=Product.UNKNOWN, description="The identified product the user is interested in.")
#     intent: str = Field(..., description="A string describing the user's goal (e.g., 'product_inquiry', 'greeting', 'informational', 'policy_claim_status', 'unwanted').")
#     confidence: float = Field(default=0.8, description="Confidence score for the classification (0.0 to 1.0).")
#     requires_clarification: bool = Field(default=False, description="Whether the user's intent requires clarification.")

# def validate_user_input(user_message: str) -> dict:
#     """
#     Validates user input for common issues before processing.
#     Returns validation result with flags for different types of invalid input.
#     """
#     if not user_message or not user_message.strip():
#         return {
#             "is_valid": False,
#             "issue_type": "empty_input",
#             "message": "Please type your message. I'm here to help with your insurance needs! 😊"
#         }
    
#     # Check for extremely short input, but allow numbers and basic responses
#     stripped_message = user_message.strip()
#     if len(stripped_message) < 2:
#         # Allow single digit numbers (party size) and single character responses
#         if not (stripped_message.isdigit() or stripped_message.lower() in ['y', 'n', '1', '2', '3', '4', '5']):
#             return {
#                 "is_valid": False,
#                 "issue_type": "too_short",
#                 "message": "Could you please provide a bit more detail? I'd love to help you with your insurance questions! 🤔"
#             }
    
#     # Check for gibberish or repeated characters
#     if re.match(r'^(.)\1{10,}$', user_message.strip()):
#         return {
#             "is_valid": False,
#             "issue_type": "repeated_characters",
#             "message": "I didn't quite understand that. Could you please rephrase your question about insurance? 😅"
#         }
    
#     # Check for only numbers or special characters, but allow reasonable single numbers
#     stripped_message = user_message.strip()
#     if re.match(r'^[0-9\s\-\+\(\)\.]+$', stripped_message):
#         # Allow single digit numbers (party size) and reasonable numbers
#         if not (len(stripped_message) <= 2 and stripped_message.isdigit()):
#             return {
#                 "is_valid": False,
#                 "issue_type": "only_numbers",
#                 "message": "I see you've shared some numbers. Could you please let me know what insurance information you're looking for? 📱"
#             }
    
#     # Check for only special characters
#     if re.match(r'^[^\w\s]+$', user_message.strip()):
#         return {
#             "is_valid": False,
#             "issue_type": "only_symbols",
#             "message": "I see some symbols there! Could you please type your insurance question in words? 💬"
#         }
    
#     # Check for extremely long input (potential spam)
#     if len(user_message) > 1000:
#         return {
#             "is_valid": False,
#             "issue_type": "too_long",
#             "message": "That's quite a long message! Could you please summarize your insurance question in a shorter message? 📝"
#         }
    
#     return {"is_valid": True, "message": "Input is valid"}

# # Create the Langchain Chain using the .with_structured_output() method
# # This creates a chain that automatically uses function calling to populate the Intent object.
# chain = llm.with_structured_output(Intent, method="function_calling")

# def get_primary_intent(user_message: str, chat_history: list) -> Intent:
#     """
#     Classifies the user's intent and identifies the product of interest using an LLM.
#     """
#     try:
#         # First validate the input
#         validation_result = validate_user_input(user_message)
#         if not validation_result["is_valid"]:
#             logger.warning(f"Invalid input detected: {validation_result['issue_type']} - {user_message[:50]}...")
#             return Intent(product=Product.UNKNOWN, intent="invalid_input", confidence=1.0, requires_clarification=False)

#         # Prepare the prompt for the LLM
#         prompt = [
#             SystemMessage(
#                 content="""You are an expert AI assistant for Hong Leong Assurance Singapore (HLAS). Your role is to classify user messages and determine the primary intent.

# CRITICAL: You MUST analyze the message for product keywords and classify accordingly, even in policy questions.

# You should classify the user's intent into one of the following categories:
# - 'greeting': For greetings like 'hello', 'hi', etc.
# - 'unwanted': For irrelevant or spam messages.
# - 'informational': For informational queries about insurance terms, coverage details, benefits, or general questions that can be answered from documentation (e.g., "what countries are covered?", "what does curtailment mean?", "what is covered under liability?", "explain deductible").
# - 'policy_claim_status': For checking actual policy or claim status (requires NRIC/policy number) - currently under implementation.
# - 'product_inquiry': For when the user wants to buy/purchase insurance or get a quote (e.g., "I need travel insurance", "I want to buy maid insurance").

# IMPORTANT: If the user asks for the definition/meaning/explanation of an insurance term or coverage details that can be found in documentation, treat this as 'informational', NOT 'unwanted'.

# For both 'product_inquiry' AND 'informational', you must also identify the product when possible. The available products are:
# - 'TRAVEL': For travel insurance, travel policies, Travel Protect360, trip insurance, travel coverage.
# - 'MAID': For maid insurance, domestic helper insurance, foreign worker insurance, maid policies.

# IMPORTANT: Even for policy questions, try to detect the product from context:
# - "Travel Protect360 policy" → TRAVEL
# - "travel insurance", "trip insurance", "travel coverage", "travel policy" → TRAVEL
# - "personal liability under travel", "travel" + any policy terms → TRAVEL  
# - "maid insurance", "domestic helper insurance", "foreign worker insurance" → MAID
# - "domestic helper policy", "maid policy", "maid coverage" → MAID

# Consider the entire conversation history to make an informed decision.

# REMEMBER: If you see words like "travel", "trip", "Travel Protect360" → set product to TRAVEL
# If you see words like "maid", "domestic helper", "foreign worker" → set product to MAID

# Edge cases and disambiguation:
# - If the message could plausibly be about insurance (e.g., insurance terms like curtailment, deductible, excess, pre-existing condition), classify as 'informational' even if the product is not mentioned. Prefer Product.UNKNOWN in that case unless the product is explicitly implied by context.
# - Only use 'unwanted' for clearly off-topic content (e.g., weather, jokes, unrelated spam).
# - Use 'policy_claim_status' only when user explicitly wants to check their policy status or claim status with NRIC/policy number.
# """
#             ),
#             HumanMessage(content=f"Chat History:\n{chat_history}\n\nUser Message: {user_message}"),
#         ]

#         # Invoke the LLM with the prepared prompt
#         result = chain.invoke(prompt)
#         logger.info(f"PRIMARY INTENT AGENT RESULT: {result}")
        
#         # Log the classification for monitoring
#         logger.info(f"Intent classification - Product: {result.product}, Intent: {result.intent}")
        
#         return result

#     except Exception as e:
#         logger.error(f"Error in intent classification: {str(e)}")
#         # Return a safe fallback response
#         return Intent(product=Product.UNKNOWN, intent="unwanted", confidence=0.0, requires_clarification=True)

# # Example usage block for testing the script directly

# endregion

# Version 2 Update (with all Product Flows)


import os
import re
from enum import Enum
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator
from langchain_core.messages import HumanMessage, SystemMessage
from utils.llm_services import llm
import logging

logger = logging.getLogger(__name__)

# ---- Enum extended to include new products ----
class Product(str, Enum):
    """Enumeration for the different products."""
    TRAVEL = "TRAVEL"
    MAID = "MAID"
    CAR = "CAR"
    FAMILY = "FAMILY"
    CHOICE = "CHOICE"
    EARLY = "EARLY"
    POLICY_CLAIM_STATUS = "POLICY_CLAIM_STATUS"
    UNKNOWN = "UNKNOWN"

class Intent(BaseModel):
    """Pydantic model that will be used for the function calling output."""
    product: Product = Field(default=Product.UNKNOWN, description="The identified product the user is interested in.")
    intent: str = Field(..., description="A string describing the user's goal (e.g., 'product_inquiry', 'greeting', 'informational', 'policy_claim_status', 'unwanted').")
    confidence: float = Field(default=0.8, description="Confidence score for the classification (0.0 to 1.0).")
    requires_clarification: bool = Field(default=False, description="Whether the user's intent requires clarification.")

def validate_user_input(user_message: str) -> dict:
    if not user_message or not user_message.strip():
        return {"is_valid": False, "issue_type": "empty_input",
                "message": "Please type your message. I'm here to help with your insurance needs! 😊"}
    stripped_message = user_message.strip()
    if len(stripped_message) < 2:
        if not (stripped_message.isdigit() or stripped_message.lower() in ['y','n','1','2','3','4','5']):
            return {"is_valid": False, "issue_type": "too_short",
                    "message": "Could you please provide a bit more detail? I'd love to help you with your insurance questions! 🤔"}
    if re.match(r'^(.)\1{10,}$', stripped_message):
        return {"is_valid": False, "issue_type": "repeated_characters",
                "message": "I didn't quite understand that. Could you please rephrase your question about insurance? 😅"}
    if re.match(r'^[0-9\s\-\+\(\)\.]+$', stripped_message):
        if not (len(stripped_message) <= 2 and stripped_message.isdigit()):
            return {"is_valid": False, "issue_type": "only_numbers",
                    "message": "I see you've shared some numbers. Could you please let me know what insurance information you're looking for? 📱"}
    if re.match(r'^[^\w\s]+$', stripped_message):
        return {"is_valid": False, "issue_type": "only_symbols",
                "message": "I see some symbols there! Could you please type your insurance question in words? 💬"}
    if len(user_message) > 1000:
        return {"is_valid": False, "issue_type": "too_long",
                "message": "That's quite a long message! Could you please summarize your insurance question in a shorter message? 📝"}
    return {"is_valid": True, "message": "Input is valid"}

# Create the Langchain Chain using structured output
chain = llm.with_structured_output(Intent, method="function_calling")

# ---- Keyword backstop if LLM returns UNKNOWN (keeps routing robust) ----
def _keyword_backstop_product(user_message: str, chat_history: list) -> Product:
    txt = f"{(user_message or '')} {' '.join(map(str, chat_history or []))}".lower()
    if any(k in txt for k in ["travel protect", "travel policy", "travel insurance", "trip", "vacation", "flight"]):
        return Product.TRAVEL
    if any(k in txt for k in ["maid insurance", "maid policy", "domestic helper", "fdw", "foreign worker"]):
        return Product.MAID
    if any(k in txt for k in ["car insurance", "motor", "auto", "vehicle", "car policy"]):
        return Product.CAR
    if any(k in txt for k in ["family protect", "family policy", "family insurance"]):
        return Product.FAMILY
    if any(k in txt for k in ["choice protect", "choice policy"]):
        return Product.CHOICE
    if any(k in txt for k in ["early protect", "critical illness", "ci policy", "ci cover"]):
        return Product.EARLY
    return Product.UNKNOWN

def get_primary_intent(user_message: str, chat_history: list) -> Intent:
    """
    Classifies the user's intent and identifies the product of interest using an LLM.
    """
    try:
        vr = validate_user_input(user_message)
        if not vr["is_valid"]:
            logger.warning(f"Invalid input detected: {vr['issue_type']} - {user_message[:50]}...")
            return Intent(product=Product.UNKNOWN, intent="invalid_input", confidence=1.0, requires_clarification=False)

        prompt = [
            SystemMessage(content="""You are an expert AI assistant for Hong Leong Assurance Singapore (HLAS).
Classify the message and determine the primary intent and product.

INTENTS:
- 'greeting'            : hello/hi/etc.
- 'unwanted'            : clearly off-topic or spam.
- 'informational'       : asks about terms/coverage/benefits from docs (e.g., "what is curtailment?", "what countries are covered?").
- 'policy_claim_status' : user wants to check real policy/claim status (NRIC/policy number context).
- 'product_inquiry'     : wants to buy/quote a policy (e.g., "I need travel insurance").

PRODUCTS (return EXACTLY one of these values):
- 'TRAVEL' : travel insurance, Travel Protect360, trip/vacation/flight coverage.
- 'MAID'   : maid/domestic helper/FDW insurance.
- 'CAR'    : car/motor/auto/vehicle insurance.
- 'FAMILY' : Family Protect.
- 'CHOICE' : Choice Protect.
- 'EARLY'  : Early Protect / Critical Illness.
- 'POLICY_CLAIM_STATUS' : when intent revolves around checking policy/claim status only.
- 'UNKNOWN': if not clear.

RULES:
- For 'product_inquiry' and 'informational', identify the PRODUCT if possible.
- Use the conversation history for context.
- Prefer 'informational' over 'unwanted' if the query is about insurance concepts.
- Return values MUST match the enums exactly.
"""),
            HumanMessage(content=f"Chat History:\n{chat_history}\n\nUser Message: {user_message}"),
        ]

        result = chain.invoke(prompt)
        logger.info(f"PRIMARY INTENT AGENT RESULT: {result}")
        logger.info(f"Intent classification - Product: {result.product}, Intent: {result.intent}")

        # Backstop: if LLM couldn't set a product but it's clearly an insurance/product message, infer it.
        if (result.product == Product.UNKNOWN) and (result.intent in {"product_inquiry", "informational"}):
            inferred = _keyword_backstop_product(user_message, chat_history)
            if inferred != Product.UNKNOWN:
                logger.info(f"Backstop product inference applied: {inferred}")
                result.product = inferred

        return result

    except Exception as e:
        logger.error(f"Error in intent classification: {str(e)}")
        return Intent(product=Product.UNKNOWN, intent="unwanted", confidence=0.0, requires_clarification=True)
