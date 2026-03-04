#!/usr/bin/env python3
"""
MUSEON 承諾追蹤系統
智能監控承諾狀態，自動生成提醒和道歉
"""

import json
import datetime
import requests
from pathlib import Path
from typing import List, Dict, Optional
import pytz

class CommitmentTracker:
    def __init__(self, data_file="commitment_schema.json"):
        self.data_file = Path(__file__).parent / data_file
        self.data = self.load_data()
        self.tz = pytz.timezone('Asia/Taipei')
        
    def load_data(self) -> Dict:
        """載入承諾數據"""
        if self.data_file.exists():
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"commitments": [], "settings": {}}
    
    def save_data(self):
        """儲存承諾數據"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def get_current_time(self) -> datetime.datetime:
        """取得當前台灣時間"""
        return datetime.datetime.now(self.tz)
    
    def parse_datetime(self, dt_string: str) -> datetime.datetime:
        """解析時間字串"""
        dt = datetime.datetime.fromisoformat(dt_string.replace('+08:00', ''))
        return self.tz.localize(dt)
    
    def check_overdue_commitments(self) -> List[Dict]:
        """檢查逾期承諾"""
        current_time = self.get_current_time()
        overdue = []
        
        for commit in self.data.get('commitments', []):
            if commit['status'] in ['pending', 'reminded']:
                due_date = self.parse_datetime(commit['due_date'])
                if current_time > due_date:
                    commit['status'] = 'overdue'
                    hours_overdue = (current_time - due_date).total_seconds() / 3600
                    commit['hours_overdue'] = round(hours_overdue, 1)
                    overdue.append(commit)
        
        self.save_data()
        return overdue
    
    def generate_reminder_message(self, commitments: List[Dict]) -> str:
        """生成提醒訊息"""
        if not commitments:
            return ""
        
        message_parts = ["🚨 MUSEON 承諾追蹤提醒"]
        message_parts.append("")
        message_parts.append("逾期未完成的承諾：")
        
        for i, commit in enumerate(commitments, 1):
            hours_over = commit.get('hours_overdue', 0)
            message_parts.append(f"{i}. {commit['description']}")
            message_parts.append(f"   ⏰ 逾期 {hours_over} 小時")
            message_parts.append("")
        
        message_parts.append("我知道你很忙，但這些承諾對你的進展很重要。")
        message_parts.append("需要重新排程嗎？還是有什麼阻礙需要解決？")
        
        return "\n".join(message_parts)
    
    def send_openclaw_notification(self, message: str) -> bool:
        """通過 OpenClaw API 發送通知"""
        try:
            api_url = "http://localhost:18789/api/agents/main/sessions/isolated/messages"
            headers = {
                "Authorization": "Bearer a4dc4a2c5acfc5f5d4d37f740fe2032a85ff53cbd15c97b8",
                "Content-Type": "application/json"
            }
            payload = {
                "message": message,
                "announce": True
            }
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"發送通知失敗: {e}")
            return False
    
    def add_commitment(self, description: str, due_date: str, priority: str = "medium") -> str:
        """新增承諾"""
        commit_id = f"commit_{len(self.data['commitments']) + 1:03d}"
        commitment = {
            "id": commit_id,
            "created_at": self.get_current_time().isoformat(),
            "promised_to": "達達大師",
            "description": description,
            "due_date": due_date,
            "priority": priority,
            "status": "pending",
            "reminders_sent": 0,
            "completion_evidence": None
        }
        
        self.data.setdefault('commitments', []).append(commitment)
        self.save_data()
        return commit_id
    
    def complete_commitment(self, commit_id: str, evidence: str = None):
        """標記承諾為完成"""
        for commit in self.data.get('commitments', []):
            if commit['id'] == commit_id:
                commit['status'] = 'completed'
                commit['completed_at'] = self.get_current_time().isoformat()
                if evidence:
                    commit['completion_evidence'] = evidence
                break
        self.save_data()
    
    def run_check(self) -> Dict:
        """執行完整檢查"""
        overdue = self.check_overdue_commitments()
        result = {
            "check_time": self.get_current_time().isoformat(),
            "overdue_count": len(overdue),
            "overdue_commitments": overdue,
            "notification_sent": False
        }
        
        if overdue:
            message = self.generate_reminder_message(overdue)
            result["message"] = message
            result["notification_sent"] = self.send_openclaw_notification(message)
        
        return result

def main():
    tracker = CommitmentTracker()
    result = tracker.run_check()
    
    print(f"檢查時間: {result['check_time']}")
    print(f"逾期承諾數量: {result['overdue_count']}")
    
    if result['overdue_count'] > 0:
        print(f"通知發送: {'成功' if result['notification_sent'] else '失敗'}")
        print("\n生成的提醒訊息:")
        print(result.get('message', ''))
    else:
        print("✅ 所有承諾都在時程內")

if __name__ == "__main__":
    main()
