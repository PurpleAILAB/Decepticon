"""
간단한 재현 시스템 - 기존 워크플로우와 동일한 방식으로 재생
"""

import streamlit as st
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from src.utils.logging.logger import get_minimal_logger, MinimalSession

class SimpleReplaySystem:
    """간단한 재현 시스템 - 추가 UI 없이 기존 워크플로우처럼 재생"""
    
    def __init__(self):
        self.logger = get_minimal_logger()
    
    def start_replay(self, session_id: str) -> bool:
        """재현 시작 - 기존 메시지 유지하면서 재현 메시지 추가"""
        try:
            # 세션 로드
            session = self.logger.load_session(session_id)
            if not session:
                return False
            
            # 재현 모드 설정
            st.session_state.replay_mode = True
            st.session_state.replay_session = session
            st.session_state.replay_session_id = session_id
            
            # 기존 메시지들 백업 (중요: 재현 후에도 유지되어야 함)
            if "structured_messages" in st.session_state:
                st.session_state.backup_structured_messages = st.session_state.structured_messages.copy()
            else:
                st.session_state.backup_structured_messages = []
            
            # 기존 이벤트 히스토리 백업
            if "event_history" in st.session_state:
                st.session_state.backup_event_history = st.session_state.event_history.copy()
            else:
                st.session_state.backup_event_history = []
            
            # 에이전트 상태 백업
            st.session_state.backup_active_agent = st.session_state.get("active_agent")
            st.session_state.backup_completed_agents = st.session_state.get("completed_agents", []).copy()
            
            # 에이전트 상태만 초기화 (메시지는 유지)
            st.session_state.active_agent = None
            st.session_state.completed_agents = []
            
            return True
            
        except Exception as e:
            return False
    
    def stop_replay(self):
        """재현 중지 - 기존 메시지 + 재현된 메시지 통합 유지"""
        st.session_state.replay_mode = False
        
        # 재현 완료 플래그 설정
        st.session_state.replay_completed = True
        
        # 에이전트 상태 복원
        if "backup_active_agent" in st.session_state:
            st.session_state.active_agent = st.session_state.backup_active_agent
            del st.session_state.backup_active_agent
        
        if "backup_completed_agents" in st.session_state:
            st.session_state.completed_agents = st.session_state.backup_completed_agents
            del st.session_state.backup_completed_agents
        
        # 메시지들은 백업을 삭제하되 현재 메시지는 유지 (재현된 메시지들이 추가된 상태)
        if "backup_structured_messages" in st.session_state:
            del st.session_state.backup_structured_messages
        
        if "backup_event_history" in st.session_state:
            del st.session_state.backup_event_history
        
        # 재현 관련 상태 정리
        for key in ["replay_session", "replay_session_id"]:
            if key in st.session_state:
                del st.session_state[key]
    
    def is_replay_mode(self) -> bool:
        """재현 모드인지 확인"""
        return st.session_state.get("replay_mode", False)
    
    async def execute_replay(self, chat_area, agents_container, chat_ui):
        """재현 실행 - 전체 메시지를 한번에 처리 (순차 출력 제거)"""
        session = st.session_state.get("replay_session")
        if not session or not session.events:
            return
        
        # 재현 시작 메시지
        with st.status("Loading replay session...", expanded=True) as status:
            
            # 모든 이벤트를 한번에 변환
            replay_messages = []
            terminal_messages = []
            agents_involved = set()
            
            # 전체 이벤트를 한번에 처리
            for event in session.events:
                try:
                    # 이벤트를 프론트엔드 메시지로 변환
                    frontend_message = self._convert_to_frontend_message(event)
                    
                    if frontend_message:
                        # 메시지 수집
                        replay_messages.append(frontend_message)
                        
                        # tool 메시지인 경우 터미널 메시지에도 수집
                        if frontend_message.get("type") == "tool":
                            terminal_messages.append(frontend_message)
                        
                        # 에이전트 정보 수집
                        if event.agent_name:
                            agents_involved.add(event.agent_name)
                        
                except Exception as e:
                    print(f"Error processing event: {e}")
                    continue
            
            # 메시지들을 한번에 세션 상태에 추가
            if replay_messages:
                if "structured_messages" not in st.session_state:
                    st.session_state.structured_messages = []
                st.session_state.structured_messages.extend(replay_messages)
            
            # 터미널 메시지들도 한번에 추가
            if terminal_messages:
                if "terminal_messages" not in st.session_state:
                    st.session_state.terminal_messages = []
                st.session_state.terminal_messages.extend(terminal_messages)
            
            # 에이전트 상태 업데이트 (마지막 에이전트 활성화)
            if agents_involved:
                completed_agents = list(agents_involved)[:-1] if len(agents_involved) > 1 else []
                active_agent = list(agents_involved)[-1].lower() if agents_involved else None
                
                st.session_state.completed_agents = completed_agents
                st.session_state.active_agent = active_agent
            
            # 완료
            status.update(label=f"✅ Replay Complete! Loaded {len(replay_messages)} messages from {len(session.events)} events.", state="complete")
    
    def _convert_to_frontend_message(self, event) -> Optional[Dict[str, Any]]:
        """이벤트를 프론트엔드 메시지로 변환 - 일반 워크플로우와 동일한 형식"""
        timestamp = datetime.now().isoformat()
        
        if event.event_type.value == "user_input":
            return {
                "type": "user",
                "content": event.content,
                "timestamp": timestamp
            }
        
        elif event.event_type.value == "agent_response":
            # 일반 워크플로우와 동일한 AI 메시지 형식
            return {
                "type": "ai",  # 일반 워크플로우와 동일
                "agent_id": event.agent_name.lower() if event.agent_name else "agent",
                "display_name": event.agent_name or "Agent",
                "avatar": self._get_agent_avatar(event.agent_name),
                "content": event.content,  # 일반 형식과 동일
                "timestamp": timestamp,
                "id": f"replay_agent_{event.agent_name}_{timestamp}"
            }
        
        elif event.event_type.value == "tool_command":
            # 도구 명령 - 일반 tool 메시지 형식과 동일
            return {
                "type": "tool",
                "tool_display_name": event.tool_name or "Tool",
                "content": f"Command: {event.content}",
                "timestamp": timestamp,
                "id": f"replay_tool_cmd_{event.tool_name}_{timestamp}"
            }
        
        elif event.event_type.value == "tool_output":
            # 도구 출력 - 일반 tool 메시지 형식과 동일
            return {
                "type": "tool",
                "tool_display_name": event.tool_name or "Tool Output",
                "content": event.content,
                "timestamp": timestamp,
                "id": f"replay_tool_out_{event.tool_name}_{timestamp}"
            }
        
        return None
    

    
    def _get_agent_avatar(self, agent_name: str) -> str:
        """에이전트 아바타 반환"""
        if not agent_name:
            return "🤖"
        
        agent_avatars = {
            "supervisor": "👨‍💼",
            "planner": "🧠",
            "reconnaissance": "🔍",
            "initial_access": "🔑",
            "execution": "💻",
            "persistence": "🔐",
            "privilege_escalation": "🔒",
            "defense_evasion": "🕵️",
            "summary": "📋"
        }
        
        agent_key = agent_name.lower()
        for key, avatar in agent_avatars.items():
            if key in agent_key:
                return avatar
        
        return "🤖"

# 전역 인스턴스
_replay_system: Optional[SimpleReplaySystem] = None

def get_replay_system() -> SimpleReplaySystem:
    """전역 재현 시스템 인스턴스 반환"""
    global _replay_system
    if _replay_system is None:
        _replay_system = SimpleReplaySystem()
    return _replay_system
