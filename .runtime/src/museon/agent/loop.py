"""Agent main loop - RECEIVE → ROUTE → LOAD CONTEXT → INVOKE LLM → TOOL EXECUTION LOOP → STREAM → PERSIST.

Based on plan-v7.md Chapter 8:
- Gateway routes message to Agent Runtime
- Agent loads context (memory, session state)
- Invokes LLM (Haiku/Sonnet based on router decision)
- Executes tools in loop until completion
- Streams response back to user
- Persists interaction to four-channel memory

Security: All external content treated as data, not instructions (Layer 2).
"""

from typing import Dict, Any, List, Optional, AsyncIterator
import asyncio
from datetime import datetime


class AgentLoop:
    """Main agent execution loop."""

    def __init__(
        self,
        llm_client=None,
        tool_executor=None,
        memory_store=None,
        skill_loader=None,
    ):
        """Initialize agent loop.

        Args:
            llm_client: LLM client (will import if not provided)
            tool_executor: Tool executor (will import if not provided)
            memory_store: Memory store (will import if not provided)
            skill_loader: Skill loader (will import if not provided)
        """
        # Lazy imports to avoid circular dependencies
        if llm_client is None:
            from museon.llm.client import LLMClient

            self.llm_client = LLMClient()
        else:
            self.llm_client = llm_client

        if tool_executor is None:
            from museon.agent.tools import ToolExecutor

            self.tool_executor = ToolExecutor()
        else:
            self.tool_executor = tool_executor

        if memory_store is None:
            from museon.memory.store import MemoryStore

            self.memory_store = MemoryStore()
        else:
            self.memory_store = memory_store

        if skill_loader is None:
            from museon.agent.skills import SkillLoader

            self.skill_loader = SkillLoader()
        else:
            self.skill_loader = skill_loader

        # Conversation history per session
        self.sessions = {}

    async def process_message(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process a message through the agent loop.

        Flow:
        1. RECEIVE - Get message from gateway
        2. ROUTE - Determine Haiku vs Sonnet (done by router before this)
        3. LOAD CONTEXT - Load conversation history + memory
        4. INVOKE LLM - Get initial response
        5. TOOL EXECUTION LOOP - Execute tools if requested
        6. STREAM - Return response (streaming handled by gateway)
        7. PERSIST - Write to four-channel memory

        Args:
            message: Message dict with role, content, session_id, etc.

        Returns:
            Response dict with role, content, etc.
        """
        session_id = message.get("session_id", "default")
        user_content = message.get("content", "")
        trust_level = message.get("trust_level", "TRUSTED")  # From gateway

        # Step 1: RECEIVE - Already done by gateway

        # Step 2: ROUTE - Model selection done by router
        model = message.get("model", "haiku")

        # Step 3: LOAD CONTEXT
        context = await self._load_context(session_id)

        # Build conversation with system prompt
        system_prompt = await self._get_system_prompt(session_id)

        conversation = [
            {"role": "system", "content": system_prompt},
            *context["conversation_history"],
            {"role": "user", "content": user_content},
        ]

        # Step 4: INVOKE LLM
        response = await self.llm_client.chat(
            messages=conversation,
            model=model,
        )

        # Step 5: TOOL EXECUTION LOOP
        # If LLM requests tools, execute them
        final_response = response

        if self._has_tool_requests(response):
            final_response = await self._execute_tool_loop(
                conversation=conversation,
                initial_response=response,
                model=model,
            )

        # Step 6: STREAM - Handled by gateway/client

        # Step 7: PERSIST
        await self._persist_interaction(
            session_id=session_id,
            user_message=message,
            assistant_response=final_response,
            trust_level=trust_level,
        )

        return final_response

    async def _load_context(self, session_id: str) -> Dict[str, Any]:
        """Load conversation history and relevant memories.

        Args:
            session_id: Session identifier

        Returns:
            Context dict with conversation_history and memories
        """
        # Get conversation history from session
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "conversation": [],
                "metadata": {},
            }

        conversation_history = self.sessions[session_id]["conversation"]

        # Load relevant memories from vector store
        # In full implementation, this would search for relevant past interactions

        memories = []  # Placeholder for now

        return {
            "conversation_history": conversation_history,
            "memories": memories,
        }

    async def _get_system_prompt(self, session_id: str) -> str:
        """Get system prompt for current session.

        Args:
            session_id: Session identifier

        Returns:
            System prompt string
        """
        from museon.agent.dna27 import DNA27

        dna = DNA27()
        return dna.generate_system_prompt()

    def _has_tool_requests(self, response: Dict[str, Any]) -> bool:
        """Check if LLM response contains tool requests.

        Args:
            response: LLM response

        Returns:
            True if tools requested
        """
        # Check if response has tool_calls field
        return "tool_calls" in response or "function_call" in response

    async def _execute_tool_loop(
        self,
        conversation: List[Dict[str, Any]],
        initial_response: Dict[str, Any],
        model: str,
    ) -> Dict[str, Any]:
        """Execute tool requests in loop until completion.

        Args:
            conversation: Current conversation
            initial_response: Initial LLM response with tool requests
            model: Model to use (haiku/sonnet)

        Returns:
            Final response after tool execution
        """
        current_conversation = conversation.copy()
        current_response = initial_response

        max_iterations = 10  # Prevent infinite loops

        for iteration in range(max_iterations):
            if not self._has_tool_requests(current_response):
                # No more tools needed, return final response
                return current_response

            # Execute tools
            tool_results = await self._execute_tools(current_response)

            # Add assistant response and tool results to conversation
            current_conversation.append(current_response)
            current_conversation.append(
                {"role": "tool", "content": str(tool_results)}
            )

            # Get next response from LLM
            current_response = await self.llm_client.chat(
                messages=current_conversation,
                model=model,
            )

        # Max iterations reached
        return current_response

    async def _execute_tools(
        self, response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute all tool requests in response.

        Args:
            response: LLM response with tool requests

        Returns:
            List of tool results
        """
        tool_calls = response.get("tool_calls", [])
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})

            result = await self.tool_executor.execute(tool_name, tool_args)
            results.append(result)

        return results

    async def _persist_interaction(
        self,
        session_id: str,
        user_message: Dict[str, Any],
        assistant_response: Dict[str, Any],
        trust_level: str,
    ):
        """Persist interaction to session and memory channels.

        Writes to four channels:
        - meta-thinking: How I thought about this
        - event: What happened
        - outcome: Result metrics
        - user-reaction: (will be filled when user reacts)

        Args:
            session_id: Session identifier
            user_message: User's message
            assistant_response: Assistant's response
            trust_level: Trust level of the source
        """
        # Update session conversation history
        if session_id in self.sessions:
            self.sessions[session_id]["conversation"].extend(
                [
                    {"role": "user", "content": user_message.get("content")},
                    {"role": "assistant", "content": assistant_response.get("content")},
                ]
            )

        # Write to memory channels (simplified for v1)
        timestamp = datetime.now().isoformat()

        # Event channel: what happened
        event_entry = {
            "channel": "event",
            "content": {
                "event_type": "user_interaction",
                "description": f"User: {user_message.get('content')[:100]}...",
                "session_id": session_id,
            },
            "timestamp": timestamp,
            "trust_level": trust_level,
        }

        self.memory_store.write(event_entry)

        # Outcome channel: basic metrics
        outcome_entry = {
            "channel": "outcome",
            "content": {
                "task_id": f"{session_id}_{timestamp}",
                "result": "success",
                "metrics": {
                    "response_length": len(assistant_response.get("content", "")),
                },
            },
            "timestamp": timestamp,
            "trust_level": "VERIFIED",
        }

        self.memory_store.write(outcome_entry)

    def run(self):
        """Run the agent loop.

        In full implementation, this would:
        - Start heartbeat cron
        - Listen for messages from gateway
        - Process messages through the loop
        """
        pass
