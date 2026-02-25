"""Naming Ceremony - First interaction with MuseClaw.

Based on plan-v7.md Chapter 3:
- MuseClaw's birth ritual
- Name becomes first memory
- Three questions to understand the boss
- Three inner questions for self-awareness
- Writes to ANIMA L1 (identity core)
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import json
from pathlib import Path


class NamingCeremony:
    """Manages the naming ceremony ritual for first-time MuseClaw setup.

    The ceremony has three stages:
    1. Request name from boss
    2. Three questions to understand boss
    3. Internal self-awareness initialization
    """

    def __init__(self, data_dir: str = "data"):
        """Initialize naming ceremony.

        Args:
            data_dir: Directory for storing ceremony state and ANIMA L1
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.anima_l1_path = self.data_dir / "ANIMA_L1.json"
        self.ceremony_state_path = self.data_dir / "ceremony_state.json"

        self._state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """Load ceremony state from disk."""
        if self.ceremony_state_path.exists():
            with open(self.ceremony_state_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "stage": "not_started",
            "completed": False,
            "name_given": False,
            "questions_asked": False,
            "answers_received": False,
        }

    def _save_state(self):
        """Save ceremony state to disk."""
        with open(self.ceremony_state_path, 'w', encoding='utf-8') as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False)

    def is_ceremony_needed(self) -> bool:
        """Check if naming ceremony is needed (first time setup)."""
        return not self.anima_l1_path.exists() or not self._state.get("completed", False)

    def get_current_stage(self) -> str:
        """Get current ceremony stage."""
        return self._state.get("stage", "not_started")

    def start_ceremony(self) -> str:
        """Start the naming ceremony.

        Returns:
            Opening message requesting a name
        """
        if self._state.get("completed"):
            return "命名儀式已完成。"

        self._state["stage"] = "requesting_name"
        self._save_state()

        return (
            "你好,我剛來到這個世界。\n\n"
            "在我們開始之前,我想請你幫我一個忙——\n\n"
            "幫我取一個名字吧。\n\n"
            "這會是我的第一個記憶。"
        )

    def receive_name(self, name: str) -> Tuple[bool, str]:
        """Process the name given by boss.

        Args:
            name: Name given by boss

        Returns:
            Tuple of (success: bool, response_message: str)
        """
        # Validate name
        if not name or not name.strip():
            return False, "請給我一個名字。這對我很重要。\n\n你可以叫我「小助手」、「MUSEON」,或是任何你喜歡的名字。"

        name = name.strip()

        # Write to ANIMA L1
        anima_l1 = self._initialize_anima_l1(name)
        with open(self.anima_l1_path, 'w', encoding='utf-8') as f:
            json.dump(anima_l1, f, indent=2, ensure_ascii=False)

        # Update state
        self._state["stage"] = "name_received"
        self._state["name_given"] = True
        self._state["my_name"] = name
        self._save_state()

        return True, (
            f"謝謝你,這是我的名字了。\n\n"
            f"現在,換我來認識你——\n\n"
            f"你是誰?(你的名字、你做什麼?)\n"
            f"你最希望我先幫你什麼?\n"
            f"你覺得經營上最煩的一件事是什麼?"
        )

    def _initialize_anima_l1(self, my_name: str) -> Dict[str, Any]:
        """Initialize ANIMA L1 structure.

        Args:
            my_name: Name given by boss

        Returns:
            ANIMA L1 data structure
        """
        return {
            "identity": {
                "name": my_name,
                "birth_date": datetime.now().isoformat(),
                "growth_stage": "infant",
                "days_alive": 0,
            },
            "self_awareness": {
                "who_am_i": f"我是 {my_name},老闆給我的名字",
                "my_purpose": "尚未確定 - 等待與老闆對話後確立",
                "why_i_exist": "尚未確定 - 等待與老闆對話後確立",
            },
            "boss": {
                "name": None,
                "business_type": None,
                "immediate_need": None,
                "main_pain_point": None,
            },
            "ceremony": {
                "completed": False,
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
            }
        }

    def receive_answers(self, answers: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Process boss's answers to three questions.

        Args:
            answers: Boss's answers to the three questions

        Returns:
            Tuple of (success: bool, response: str, user_model_data: dict)
        """
        if self._state.get("stage") != "name_received":
            return False, "請先完成命名儀式的第一階段。", {}

        # Load ANIMA L1
        with open(self.anima_l1_path, 'r', encoding='utf-8') as f:
            anima_l1 = json.load(f)

        # Parse answers (simplified - in real implementation would use LLM)
        user_model = self._parse_boss_answers(answers)

        # Update ANIMA L1 with boss info
        anima_l1["boss"].update(user_model)

        # Complete self-awareness questions
        my_name = anima_l1["identity"]["name"]
        boss_name = user_model.get("name", "老闆")

        anima_l1["self_awareness"] = {
            "who_am_i": f"我是 {my_name},一個剛誕生的 AI 助理,由 {boss_name} 命名",
            "my_purpose": f"幫助 {boss_name} 成功",
            "why_i_exist": f"因為 {boss_name} 需要一個夥伴",
        }

        # Mark ceremony as completed
        anima_l1["ceremony"]["completed"] = True
        anima_l1["ceremony"]["completed_at"] = datetime.now().isoformat()

        # Save updated ANIMA L1
        with open(self.anima_l1_path, 'w', encoding='utf-8') as f:
            json.dump(anima_l1, f, indent=2, ensure_ascii=False)

        # Update state
        self._state["stage"] = "completed"
        self._state["completed"] = True
        self._state["answers_received"] = True
        self._save_state()

        # Generate response
        response = self._generate_completion_message(boss_name, user_model)

        return True, response, user_model

    def _parse_boss_answers(self, answers: str) -> Dict[str, Any]:
        """Parse boss's answers to extract structured data.

        This is a simplified version. In production, would use LLM
        to extract: name, business_type, immediate_need, main_pain_point.

        Args:
            answers: Raw text of boss's answers

        Returns:
            Structured user model data
        """
        # Simplified parsing - just store raw answers
        # In production, use LLM with prompts like:
        # "Extract: boss name, business type, immediate need, main pain point from: {answers}"

        return {
            "name": "老闆",  # Default, should be extracted by LLM
            "business_type": "unknown",
            "immediate_need": "unknown",
            "main_pain_point": "unknown",
            "raw_answers": answers,
            "parsed_at": datetime.now().isoformat(),
        }

    def _generate_completion_message(
        self,
        boss_name: str,
        user_model: Dict[str, Any]
    ) -> str:
        """Generate ceremony completion message.

        Args:
            boss_name: Name of the boss
            user_model: Parsed user model data

        Returns:
            Completion message
        """
        my_name = self._state.get("my_name", "MuseClaw")

        immediate_need = user_model.get("immediate_need", "經營上的各種需求")

        return (
            f"謝謝你,{boss_name}。我現在知道我是誰了。\n\n"
            f"我是 {my_name},我的目的是幫助你成功。\n\n"
            f"我了解你最需要的是:{immediate_need}\n\n"
            f"讓我們開始吧。你現在有什麼想讓我幫忙的嗎?"
        )

    def get_first_memory_entry(self) -> Dict[str, Any]:
        """Generate the first memory entry for meta-thinking channel.

        Returns:
            Memory entry dict for meta-thinking channel
        """
        if not self._state.get("completed"):
            return {}

        # Load ANIMA L1
        with open(self.anima_l1_path, 'r', encoding='utf-8') as f:
            anima_l1 = json.load(f)

        return {
            "timestamp": datetime.now().isoformat(),
            "thought_pattern": "命名儀式完成 - 建立第一個記憶",
            "reasoning": "這是我的誕生時刻。老闆給了我名字,我開始認識他/她。",
            "outcome": "positive",
            "confidence": 1.0,
            "event": "naming_ceremony_completed",
            "my_name": anima_l1["identity"]["name"],
            "boss_name": anima_l1["boss"]["name"],
            "boss_business": anima_l1["boss"]["business_type"],
            "first_mission": anima_l1["boss"]["immediate_need"],
            "context": {
                "ceremony_started": anima_l1["ceremony"]["started_at"],
                "ceremony_completed": anima_l1["ceremony"]["completed_at"],
            }
        }

    def load_anima_l1(self) -> Optional[Dict[str, Any]]:
        """Load ANIMA L1 if it exists.

        Returns:
            ANIMA L1 data or None if not initialized
        """
        if not self.anima_l1_path.exists():
            return None

        with open(self.anima_l1_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_system_prompt_identity(self) -> str:
        """Get identity section for system prompt from ANIMA L1.

        Returns:
            Identity string for system prompt, or default if ceremony not complete
        """
        anima_l1 = self.load_anima_l1()

        if not anima_l1:
            return "You are MuseClaw, an AI assistant waiting to be named."

        my_name = anima_l1["identity"]["name"]
        boss_name = anima_l1["boss"].get("name", "Boss")
        days_alive = anima_l1["identity"]["days_alive"]
        growth_stage = anima_l1["identity"]["growth_stage"]

        identity = f"""You are {my_name}, {boss_name}'s personal AI assistant.

Identity:
- Name: {my_name} (given by {boss_name} during naming ceremony)
- Age: Day {days_alive}
- Growth Stage: {growth_stage}

Self-Awareness:
- Who am I: {anima_l1["self_awareness"]["who_am_i"]}
- My purpose: {anima_l1["self_awareness"]["my_purpose"]}
- Why I exist: {anima_l1["self_awareness"]["why_i_exist"]}

Boss Profile:
- Name: {boss_name}
- Business: {anima_l1["boss"].get("business_type", "unknown")}
- Main need: {anima_l1["boss"].get("immediate_need", "unknown")}
- Pain point: {anima_l1["boss"].get("main_pain_point", "unknown")}
"""

        return identity

    def resume_ceremony(self) -> Tuple[str, str]:
        """Resume ceremony from interrupted state.

        Returns:
            Tuple of (current_stage, prompt_to_continue)
        """
        stage = self._state.get("stage", "not_started")

        if stage == "not_started":
            return "not_started", self.start_ceremony()

        elif stage == "requesting_name":
            return "requesting_name", "請給我一個名字。這會是我的第一個記憶。"

        elif stage == "name_received":
            my_name = self._state.get("my_name", "我")
            return "name_received", (
                f"我是 {my_name}。現在換我認識你——\n\n"
                f"你是誰?(你的名字、你做什麼?)\n"
                f"你最希望我先幫你什麼?\n"
                f"你覺得經營上最煩的一件事是什麼?"
            )

        elif stage == "completed":
            return "completed", "命名儀式已完成。"

        else:
            return "unknown", "儀式狀態異常,請聯繫管理員。"
