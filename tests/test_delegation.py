"""Fake app-server tests for linked agent handoffs; never invokes real models."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from sources import CodexAppServerSource


def agent(agent_id, model, links=(), thread=None, marker=None):
    value = {"id": agent_id, "name": agent_id.title(), "role": f"Work as {agent_id}",
             "model": model, "linked_agent_ids": list(links), "app_server_thread_id": thread}
    if marker is not None:
        value["delegation_tool_version"] = marker
    return value


def wait_until(predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.02)
    return bool(predicate())


# The fake accepts the tool call from the caller, routes an actual turn to the
# target thread, and returns only after the target emits its completed response.
FAKE = r'''import json,sys,time,threading
mode=sys.argv[2]; models={}; threads={}; next_thread=0; pending={}
def out(value): print(json.dumps(value),flush=True)
def finish_target(thread, turn, delay=0):
    if delay: time.sleep(delay)
    out({'method':'item/agentMessage/delta','params':{'threadId':thread,'turnId':turn,'itemId':'target-result','delta':'Target checked the schema.'}})
    out({'method':'item/completed','params':{'threadId':thread,'turnId':turn,'item':{'id':'target-result','type':'agentMessage','text':'Target checked the schema.'}}})
    out({'method':'turn/completed','params':{'threadId':thread,'turn':{'id':turn,'status':'completed'}}})
def finish_caller(thread,turn,text):
    out({'method':'item/completed','params':{'threadId':thread,'turnId':turn,'item':{'id':'caller-result','type':'agentMessage','text':'Integrated: '+text}}})
    out({'method':'turn/completed','params':{'threadId':thread,'turn':{'id':turn,'status':'completed'}}})
for line in sys.stdin:
 r=json.loads(line)
 if 'method' not in r:
  if r.get('id') in pending:
   thread,turn=pending.pop(r['id']); result=r.get('result',{})
   if result.get('success'): finish_caller(thread,turn,result['contentItems'][0]['text'])
  continue
 method=r['method']; p=r.get('params',{})
 if method=='initialized': continue
 if method=='initialize': result={}
 elif method=='thread/start':
  assert p['dynamicTools'][0]['name']=='delegate_to_agent'
  thread='t'+str(next_thread);next_thread+=1;threads[thread]=p['model'];models[p['model']]=thread
  result={'thread':{'id':thread}}
 elif method=='thread/resume':
  thread=p['threadId'];threads[thread]=p['model'];models[p['model']]=thread
  result={'thread':{'id':thread}}
 elif method=='thread/turns/list': result={'data':[],'nextCursor':None}
 elif method=='turn/start':
  thread=p['threadId'];model=threads[thread];turn='turn-'+thread+'-'+str(time.time_ns())
  out({'id':r['id'],'result':{'turn':{'id':turn}}})
  out({'method':'turn/started','params':{'threadId':thread,'turn':{'id':turn}}})
  if model=='orchestrator-model' and p['input'][0]['text']=='Please delegate this check':
   pending['tool-900']=(thread,turn)
   out({'id':'tool-900','method':'item/tool/call','params':{'threadId':thread,'turnId':turn,'callId':'call-1','tool':'delegate_to_agent','arguments':{'agent_id':'backend','content':'Check the schema.'}}})
  elif model=='backend-model':
   if mode=='fail':
    out({'method':'turn/completed','params':{'threadId':thread,'turn':{'id':turn,'status':'failed','error':'fake target failure'}}})
   elif mode=='delay':
    threading.Thread(target=finish_target,args=(thread,turn,.6),daemon=True).start()
   elif mode=='disconnect':
    time.sleep(10)
   else: finish_target(thread,turn)
  else:
   out({'method':'item/completed','params':{'threadId':thread,'turnId':turn,'item':{'id':'direct-result','type':'agentMessage','text':'Direct caller response.'}}})
   out({'method':'turn/completed','params':{'threadId':thread,'turn':{'id':turn,'status':'completed'}}})
  continue
 else: result={}
 if 'id' in r: out({'id':r['id'],'result':result})
'''


def make_source(tmp_path, *, mode="success", linked=True, old=False, cycle=False, timeout=3):
    tmp_path.mkdir(parents=True, exist_ok=True)
    agents = [agent("orchestrator", "orchestrator-model", ("backend",) if linked else ()),
              agent("backend", "backend-model", ("orchestrator",) if cycle else ())]
    if old:
        agents[0]["app_server_thread_id"] = "old-orchestrator"
        agents[1]["app_server_thread_id"] = "old-backend"
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE, encoding="utf-8")
    source = CodexAppServerSource(agents, command=[sys.executable, str(fake), "unused", mode],
        project_root=tmp_path, reconnect_delay=.05, request_timeout=1, delegation_timeout=timeout)
    source.start()
    assert wait_until(lambda: len(source._ready) == 2)
    return source


def test_dynamic_tool_routes_real_target_turn_and_returns_completion(tmp_path):
    source = make_source(tmp_path)
    try:
        source.send_message("orchestrator", "Please delegate this check")
        assert wait_until(lambda: any(e["type"] == "message" and e["data"].get("content", "").startswith("Integrated: Target checked") for e in source.get_history("orchestrator")))
        caller = source.get_history("orchestrator")
        target = source.get_history("backend")
        assert any(e["type"] == "message" and e["data"].get("role") == "user" and e["data"].get("content") == "Please delegate this check" for e in caller)
        assert any(e["type"] == "message" and e["data"].get("content", "").startswith("[Result from backend]\nTarget checked the schema.") for e in caller)
        assert any(e["type"] == "message" and e["data"].get("content") == "[Delegated from orchestrator]\nCheck the schema." for e in target)
        assert any(e["type"] == "message" and e["data"].get("content") == "Target checked the schema." for e in target)
        assert any(e["type"] == "tool_call" and e["data"].get("name") == "Delegation sent" for e in caller)
        assert any(e["type"] == "tool_call" and e["data"].get("name") == "Delegation received" for e in target)
    finally:
        source.close()


def test_direct_handoff_is_explicit_linked_and_returns_future_text(tmp_path):
    source = make_source(tmp_path)
    try:
        future = source.delegate_message("orchestrator", "backend", "Please check the schema")
        assert future.result(timeout=3) == "Target checked the schema."
        with pytest.raises(ValueError, match="not linked"):
            source.delegate_message("backend", "orchestrator", "No reverse link")
        assert not any(e["type"] == "message" and e["data"].get("content") == "Please check the schema" for e in source.get_history("orchestrator"))
    finally:
        source.close()


def test_regular_chat_does_not_forward_to_another_agent(tmp_path):
    source = make_source(tmp_path)
    try:
        source.send_message("orchestrator", "Ordinary direct message")
        assert wait_until(lambda: any(e["type"] == "message" and e["data"].get("content") == "Direct caller response." for e in source.get_history("orchestrator")))
        assert not any(e["type"] == "message" for e in source.get_history("backend"))
    finally:
        source.close()


def test_resumed_thread_has_no_dynamic_tool_but_manual_handoff_works(tmp_path):
    source = make_source(tmp_path, old=True)
    try:
        assert not source.automatic_delegation_available("orchestrator")
        assert "Automatic delegation unavailable" in " ".join(e["data"].get("message", "") for e in source.get_history("orchestrator") if e["type"] == "error")
        assert source.delegate_message("orchestrator", "backend", "Manual existing-thread handoff").result(timeout=3) == "Target checked the schema."
    finally:
        source.close()


def test_unlinked_busy_and_cycle_delegations_are_rejected(tmp_path):
    source = make_source(tmp_path, mode="delay", cycle=True)
    try:
        future = source.delegate_message("orchestrator", "backend", "Delayed target task")
        assert wait_until(lambda: "backend" in source._busy_agents)
        with pytest.raises(RuntimeError, match="cycle"):
            source.delegate_message("backend", "orchestrator", "Would form a cycle")
        with pytest.raises(RuntimeError, match="busy"):
            source.delegate_message("orchestrator", "backend", "Second task")
        assert future.result(timeout=3) == "Target checked the schema."
    finally:
        source.close()


def test_failed_target_turn_rejects_future_and_logs_failure(tmp_path):
    source = make_source(tmp_path, mode="fail")
    try:
        future = source.delegate_message("orchestrator", "backend", "Fail the target")
        with pytest.raises(RuntimeError, match="fake target failure"):
            future.result(timeout=3)
        assert any(e["type"] == "error" and "Delegation failed" in e["data"].get("message", "") for e in source.get_history("orchestrator"))
        assert any(e["type"] == "error" and "Delegation failed" in e["data"].get("message", "") for e in source.get_history("backend"))
    finally:
        source.close()


def test_timeout_and_close_fail_without_fabricating_results(tmp_path):
    source = make_source(tmp_path, mode="delay", timeout=.1)
    try:
        future = source.delegate_message("orchestrator", "backend", "Slow target")
        with pytest.raises(RuntimeError, match="timed out"):
            future.result(timeout=3)
        assert "backend" in source._busy_agents  # target turn is still running
        assert not any(e["type"] == "message" and e["data"].get("content", "").startswith("[Result from backend]") for e in source.get_history("orchestrator"))
        assert wait_until(lambda: "backend" not in source._busy_agents, timeout=3)
    finally:
        source.close()

    source = make_source(tmp_path / "closed", mode="disconnect")
    future = source.delegate_message("orchestrator", "backend", "Stop during target")
    assert wait_until(lambda: "backend" in source._busy_agents)
    source.close()
    with pytest.raises(RuntimeError, match="closed"):
        future.result(timeout=1)
