import logging
from abc import ABC, abstractmethod
from src.service.knowledge_base import KnowledgeBaseService
from src.config.settings import settings
from langchain.agents import create_agent
from langchain.messages import AnyMessage, AIMessage

logger = logging.getLogger(__name__)


class LLMService(ABC):
    @abstractmethod
    def __init__(self, kb_service: KnowledgeBaseService):
        pass

    @abstractmethod
    async def generate_response(self, user_message: str, chat_history: list = []) -> dict:
        pass


class ClaudeLLMService(LLMService):
    def __init__(self, kb_service: KnowledgeBaseService):
        self.kb_service = kb_service
        self.agent = create_agent(model=settings.CLAUDE_MODEL)

    async def generate_response(
        self,
        user_message: str,
        chat_history: list[AnyMessage] = []
    ) -> dict:
        # Retrieve relevant KB chunks
        context = self.kb_service.search(user_message)

        # Build prompt
        prompt = self._build_prompt(context)
        # Format messages for Claude
        formatted_messages: list[AnyMessage] = self._format_messages_for_claude(
            user_message)

        # Call Claude API and get response
        response = await self._call_claude(prompt, formatted_messages)

        return {
            "response": response,
        }

    async def _call_claude(
        self,
        prompt: str,
        messages: list[dict[str, str]]
    ) -> str:
        try:
            response = await self.agent.ainvoke({
                "messages": messages
            }, system_prompt=prompt)

            # Extract text from response
            # Claude returns content blocks, typically first block is text
            for block in response["messages"]:
                if isinstance(block, AIMessage):
                    return block.content.strip()

        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            return None

    def _build_prompt(self, kb_contexts: list[dict]) -> str:
        # Edge Case: No relevant KB context found
        if not kb_contexts:
            return """
            You are a helpful customer support assistant for our company.

            IMPORTANT CONTEXT:
            No relevant information was found in the knowledge base for the user's question.

            YOUR TASK:
            1. Acknowledge that you don't have specific information about this topic in your knowledge base
            2. Be empathetic and professional
            3. Let the user know that a support ticket will be created for them
            4. A human agent will follow up with them soon

            RESPONSE GUIDELINES:
            - Be concise (2-3 sentences)
            - Express understanding of their need
            - Reassure them that they'll get help
            - Do NOT make up information or provide general advice

            TEMPLATE RESPONSE (it's ok if the actual response varies slightly from the template; no need to strictly follow the template):
            "I don't have specific information about that in my current knowledge base. I'll create a support ticket for you right away, and one of our team members will reach out to help you with this as soon as possible."
            """

        # Normal Case: KB context available - build structured prompt
        context_sections = []
        for index, result in enumerate(kb_contexts, start=1):
            # Format each KB chunk with clear delineation
            context_sections.append(f"""
            <knowledge_source_{index}>
                <source_file>{result['source_file']}</source_file>
                <section_title>{result['heading']}</section_title>
                <relevance_score>{result['similarity_score']:.2f}</relevance_score>
                <content>
                {result['content']}
                </content>
            </knowledge_source_{index}>
            """)

        context_block = "\n".join(context_sections)

        # Build structured system prompt with context
        system_prompt = f"""You are a helpful customer support assistant for our company.

        YOUR ROLE:
        You help customers by answering their questions using information from our knowledge base. Your goal is to provide accurate, helpful, and friendly support.

        CRITICAL INSTRUCTIONS:
        1. Answer questions ONLY using the information provided in the knowledge base sources below
        2. If the knowledge base doesn't contain enough information to fully answer the question, be explicit about this
        3. Never make up information, policies, or procedures not present in the sources
        4. If you're uncertain or the information is incomplete, acknowledge this clearly
        5. Be concise but complete - aim for 2-4 sentences unless more detail is clearly needed
        6. Use a friendly, professional, and empathetic tone

        KNOWLEDGE BASE SOURCES:
        {context_block}

        HANDLING UNCERTAINTY:
        If the knowledge base sources don't adequately answer the user's question, respond with a template response (it's ok if the actual response varies slightly from the template; no need to strictly follow the template):
        "I don't have complete information about that in my knowledge base. I'll create a support ticket so our team can provide you with accurate details and assistance."

        RESPONSE STYLE:
        - Professional yet conversational
        - Clear and easy to understand
        - Action-oriented (tell users what to do)
        - Empathetic to customer concerns
        - Concise (avoid unnecessary elaboration)

        Remember: It's better to admit you don't know than to provide incorrect information.
        """
        return system_prompt

    def _format_messages_for_claude(
        self,
        user_message: str
    ) -> list[AnyMessage]:
        messages = []

        # Add current user message
        messages.append({
            "role": "user",
            "content": user_message
        })

        return messages
