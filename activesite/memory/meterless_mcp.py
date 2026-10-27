"""ActiveSite — Meterless H-MEM Model Context Protocol (MCP) server.

Exposes memory recall, episodic resolution recording, and trust ledger verification
via JSON-RPC for agent frameworks and IDE integrations.
"""
from __future__ import annotations

import json
import sys
import uuid
from typing import Any, Dict
from activesite.memory.meterless import EpisodicMemoryRecord, MeterlessHMEM


def handle_request(hmem: MeterlessHMEM, req: Dict[str, Any]) -> Dict[str, Any]:
    method = req.get("method", "")
    params = req.get("params", {})
    req_id = req.get("id")

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "query_memory",
                        "description": "Query Meterless H-MEM episodic memory for past simulation lessons",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "system_id": {"type": "string"},
                                "error_type": {"type": "string"},
                                "keywords": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                    {
                        "name": "record_lesson",
                        "description": "Store a newly discovered resolution or heuristic into episodic memory",
                        "inputSchema": {
                            "type": "object",
                            "required": ["system_id", "stage", "learned_rule"],
                            "properties": {
                                "system_id": {"type": "string"},
                                "stage": {"type": "string"},
                                "learned_rule": {"type": "string"},
                                "error_type": {"type": "string"},
                                "corrective_action": {"type": "string"},
                            },
                        },
                    },
                    {
                        "name": "get_trust_ledger",
                        "description": "Retrieve the verifiable trust ledger of agent decisions",
                        "inputSchema": {"type": "object"},
                    },
                ]
            },
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "query_memory":
            records = hmem.query_memories(
                system_id=args.get("system_id"),
                error_type=args.get("error_type"),
                keywords=args.get("keywords"),
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps([r.model_dump() for r in records])}]},
            }

        elif tool_name == "record_lesson":
            record = EpisodicMemoryRecord(
                record_id=f"MEM_USER_{uuid.uuid4().hex[:10]}",
                system_id=args.get("system_id", "generic"),
                stage=args.get("stage", "general"),
                state_signature="user_recorded_lesson",
                action_taken="Agent self-correction or user feedback",
                outcome="SELF_CORRECTED",
                error_type=args.get("error_type"),
                corrective_action=args.get("corrective_action"),
                learned_rule=args.get("learned_rule"),
                trust_score=0.90,
            )
            hmem.record_episode(record)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Lesson recorded with ID: {record.record_id}"}]},
            }

        elif tool_name == "get_trust_ledger":
            ledger = hmem.get_ledger()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps([e.model_dump() for e in ledger])}]},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method {method} not found"},
    }


def run_mcp_server() -> None:
    hmem = MeterlessHMEM()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(hmem, req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            err_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_mcp_server()
